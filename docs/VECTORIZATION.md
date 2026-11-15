# Vectorization: how documents become searchable vectors

This is the canonical description of the embedding pipeline in both modes: how
documents are chunked, embedded, stored, and searched, and which embedding
spaces must match. Other docs link here instead of repeating it.

## 1. Two embedding spaces

Vectors from different embedding models are not comparable. Documents and
queries must use the same space, or cosine similarity returns noise.

| Aspect | Local mode (`DEPLOYMENT_MODE=local`) | Serverless mode (`DEPLOYMENT_MODE=serverless`) |
|---|---|---|
| Embedding model | Ollama `nomic-embed-text:v1.5` (`OLLAMA_EMBED_MODEL`) | Bedrock `amazon.titan-embed-text-v1` (`BEDROCK_EMBEDDING_MODEL_ID`) |
| Raw dimension | 768 | 1536 |
| Dimension in index | 768 (native) | 768 (1536 reduced by a fixed projection) |
| Vector store | Local OpenSearch container (`localhost:9200`, no auth) | OpenSearch Serverless collection (SigV4) |
| Document trigger | Manual script run | S3 `ObjectCreated` under `documents/` |
| Scope-gate threshold | 0.50 | 0.35 |

The index name and layout are the same in both modes: `rag-kb` for documents and
`rag-cache` for the semantic response cache. Both use `knn_vector` fields, HNSW
(`m=30`, `ef_construction=200`, `nmslib`), and `cosinesimil`. Those values are
set in `src/tools/opensearch_client.py`.

## 2. Pipeline stages

Every ingestion path runs the same four stages. Only the source of the bytes
and the embedder differ.

1. **Load.** Read UTF-8 text. Local scripts read `.md`/`.txt` files from a
   directory. Serverless reads the S3 object (`indexing_handler._download`).
2. **Chunk.** `src/indexing/chunking.py::chunk_text` splits text into windows of
   at most `MAX_CHUNK_LENGTH` (default 400) tokens. A *token* here is a
   whitespace-delimited word, not a model subword token. Oversized words are
   hard-split at 2000 characters. This function is shared by all paths.
3. **Embed.** One vector per chunk. The embedder depends on the mode (section 1).
4. **Index.** Write `{vector, text, metadata}` under a document ID. The ID is
   `<name>-<chunk index>` locally and `<s3 key>_chunk_<index>` in serverless.
   Writes are upserts, so re-indexing the same ID overwrites the chunk.

### 2.1 Serverless (`src/indexing/indexing_handler.py`)

```
S3 PutObject (documents/)
  -> S3 ObjectCreated event -> indexing Lambda
  -> DynamoDB analytics: already indexed for (doc_key, etag)? -> skip
  -> S3 GetObject -> decode UTF-8
  -> chunk_text(max 400 words)
  -> for each chunk: BedrockClient.embed_text
       -> Titan InvokeModel (1536-dim, one inputText per call)
       -> _reduce_dimensions: x @ P, P is 1536x768
  -> OpenSearch index_document (retry once, then skip the chunk)
  -> DynamoDB analytics put: {doc_key, etag, s3_uri, chunk_count, indexed_at}
```

Failure policy: an embedding error skips that chunk. An OpenSearch write error
is retried once. An analytics write error is logged and ignored, so indexing
still counts as complete.

### 2.1a Serverless, direct script (`scripts/ingest_serverless_opensearch.py`)
Runs the same embedding path as the Lambda from a workstation, with no S3 and no
Lambda. It chunks each file, calls `BedrockClient.embed_text` (Titan plus the
projection), and writes each chunk to `settings.opensearch_kb_index` through the
SigV4-signed `OpenSearchClient`. Each chunk's metadata carries
`embedding_pipeline: titan-1536-projected-768`.

The script refuses to run unless `OPENSEARCH_ENDPOINT` is an `https://` host
ending in `.aoss.amazonaws.com`. It has no path to the local container. An
embedding or write error stops the run and names the chunk. It does not skip, so
the knowledge base has no silent gaps. The caller needs `bedrock:InvokeModel` and
an OpenSearch Serverless data access policy for its IAM principal.

### 2.2 Local, Ollama path (`scripts/ingest_local_opensearch.py`)

Reads files, chunks them, embeds each chunk with Ollama, and writes each chunk
straight to the local OpenSearch index. No S3, no AWS credentials. An embedding
failure logs a warning and skips that chunk.

### 2.3 Local, bulk JSON path (`document_loaders/`)

`load_docs_opensearch.py` embeds a markdown corpus with Ollama in batches and
writes `data/embeddings.json` (6,878 records of `{id, vector, text, metadata}`,
768-dim, about 144 MB). `load_embeddings_from_json.py` then bulk-loads that file
into the local index with `opensearchpy.helpers.bulk`. The `document_loaders/`
package must not import from `src/`, so it has its own `OpenSearchVectorDB`
client (`document_loaders/core/tools.py`). That client talks plain HTTP with no
auth and cannot reach OpenSearch Serverless. The loader connects only to
`opensearch_local_host`, so it cannot write to the serverless collection.

### 2.4 Query path

1. The question passes the security screen and the scope gate. The scope gate
   embeds the question and compares it to eight anchor descriptions. A cosine
   score below the threshold is out of scope.
2. The question is embedded with the same embedder used for documents.
3. `OpenSearchClient.knn_search` returns the top-k chunks. `ef_search` is at
   least `k`.
4. The chunks become the LLM context. Answers cite the returned sources.
5. Answers are cached in `rag-cache`. Cache keys use the raw question.

## 3. Why the production S3 path exists

S3 is the trigger and the durable record of each source document. The indexing
Lambda is the only component that reads S3 for documents. The `ObjectCreated`
notification (`infrastructure/terraform/modules/compute/main.tf`) starts it, and
the `(doc_key, etag)` analytics record makes re-delivery idempotent. Bulk loads
bypass S3 and the Lambda, but they lose this trigger and audit trail.

## 4. Import local embeddings into production

Importing vectors computed on a laptop into the serverless collection works only
if the laptop computes them in the same space the production query uses. Local
nomic vectors (768-dim) do not match serverless Titan-plus-projection vectors
(768-dim), even though both are 768 wide. Loading nomic vectors into the
serverless index would make retrieval return unrelated chunks, and scope-gate
scores would not be comparable to the calibrated 0.35 threshold.

Options:

| Option | How | Trade-offs |
|---|---|---|
| **A. Precompute with Titan locally, bulk-load over SigV4** (recommended; implemented as `scripts/ingest_serverless_opensearch.py`) | Run `BedrockClient.embed_text` on the laptop, then bulk-index into the serverless collection with signed requests. The projection is deterministic and derived from the dimensions alone, so local and Lambda output match. | No S3 or Lambda in the write path. Still calls Bedrock (same token cost as the Lambda). Needs a data access policy in OpenSearch Serverless for the loader's IAM principal. Both sides use the built-in projection, so no matrix file is shared. |
| B. Serve nomic in production | Host Ollama in AWS (ECS or EC2), point serverless embeddings at it, and re-embed all documents. | Keeps one local/prod embedding space. Adds a hosted model to operate, changes the query path, and needs new scope-gate calibration. Large change. |
| C. Use native Titan 1536-dim everywhere | Remove the projection, set the index dimension to 1536, rebuild `rag-kb` and `rag-cache`. | Removes the lossy projection. Index memory and cost roughly double. Local mode then needs Bedrock calls. Requires a retrieval-quality comparison first. |

Option A is the smallest change that meets the goal of importing locally computed
vectors without S3. It does not remove the Bedrock dependency. Only B removes
that, and B is a much larger change.

Option A is implemented as `scripts/ingest_serverless_opensearch.py` (section 2.1a).
It embeds with Titan on the workstation and writes only to the serverless
collection. It does not accept local vectors.

### 4.1 Projection status
Local and serverless both use the built-in random projection, which the code
regenerates from the dimensions. No matrix file is committed, and
`BEDROCK_PCA_MATRIX_URI` is unset in every environment file. A data-fitted PCA
projection was evaluated and is not in use. It is tracked as a candidate in
[ROADMAP.md](ROADMAP.md) (item 21), with its measurements and the conditions for
adopting it.

## 5. Optimization opportunities

Each item is a hypothesis unless noted. Validate it with the local eval harness
(`docs/EVAL_LOCAL.md`) before changing production.

- **Batch local embedding.** `scripts/ingest_local_opensearch.py` embeds one
  chunk per request and writes one document per `index` call. Using
  `OllamaClient.embed_texts` (already used by `load_docs_opensearch.py`) and the
  OpenSearch `_bulk` API would cut request overhead. The `OpenSearchClient` has
  no bulk method yet.
- **Parallel Titan calls in the Lambda.** Titan `InvokeModel` takes one text per
  call, and the handler embeds chunks sequentially. Bounded concurrency reduces
  wall-clock time per document. It does not change Bedrock cost.
- **Skip unchanged chunks.** Re-indexing a changed file rewrites every chunk.
  Hashing chunk text and skipping unchanged chunk IDs would avoid re-embedding.
  Today only whole-document `(doc_key, etag)` skips exist.
- **Task prefixes for nomic.** The nomic-embed-text v1.5 model card recommends
  `search_document:` before documents and `search_query:` before queries. The
  code uses neither. Adding them may improve recall. The scope gate and cache
  keys must change with it. Measure before adopting.
- **Store precomputed vectors in a binary format.** `data/embeddings.json` is
  about 144 MB of JSON floats. A `.npy` or Parquet file would be smaller and
  faster to load.
- **Lower dimension, carefully.** The 768-dim index is already smaller than the
  1536-dim native Titan output. Going lower (for example 512) would save memory
  but needs a retrieval-quality test.

## 6. Known gaps

- **"PCA" is a misnomer.** `BedrockClient._build_deterministic_matrix` builds a
  random Gaussian matrix and orthonormalizes it with QR. It is a random
  orthogonal projection, not PCA. It preserves distances roughly, as a random
  projection does, but it does not keep the directions of highest variance.
  The `.env` files do not set `BEDROCK_PCA_MATRIX_URI`, so serverless uses the
  random projection. Docstrings and `docs/DEPLOYMENT.md` still say PCA.
- **Projection is implicit.** Local and serverless both regenerate the random
  matrix from the dimensions. Rebuilding it on Linux x86_64 (numpy 1.26.4) and
  comparing it to a macOS build gave a maximum absolute difference of 2.2e-16.
  No column changed sign, so the two are functionally identical. They are not
  bit-identical, so a stored vector can differ from a fresh one only in the
  last float64 digits.
- **Token unit.** `MAX_CHUNK_LENGTH` counts whitespace words. The model context
  limits are in model tokens, so a 400-word chunk can be well above 400 tokens.
  This is safe for both models today, but it is not what the name implies.
- **Local demo docs.** `scripts/ingest_local_opensearch.py` without `--docs` loads
  two built-in demo documents only.
