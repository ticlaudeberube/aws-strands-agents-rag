# Core Package

The core package provides the loader-facing clients for the standalone
`document_loaders/` ingestion utility. It vectorizes documents into a local
OpenSearch container and is intentionally isolated from the runtime application
in `src/` (no imports in either direction).

## Architecture

```
core/
├── __init__.py   # Re-exports OpenSearchVectorDB and OllamaClient from tools.py
└── tools.py      # OpenSearchVectorDB (vector store) + OllamaClient (embeddings)
```

## Standalone Loader Usage

```python
from document_loaders.core.tools import OpenSearchVectorDB, OllamaClient

vector_db = OpenSearchVectorDB(host="localhost", port=9200)
vector_db.ensure_index("rag-kb", embedding_dim=768)

ollama_client = OllamaClient(host="http://localhost:11434")
embedding = ollama_client.embed_text("What is a vector database?")

vector_db.index_documents(
    index_name="rag-kb",
    embeddings=[embedding],
    texts=["What is a vector database?"],
    metadata=[{"source": "example"}],
)
```

`document_loaders.core.tools` is the canonical standalone path used by:

- `document_loaders/load_docs_opensearch.py`
- `document_loaders/sync_responses_cache.py`
- `document_loaders/load_embeddings_from_json.py`
- `document_loaders/add_sample_docs.py`

These scripts read configuration from `.env` through
`document_loaders/local_settings.py`.

## `OpenSearchVectorDB`

Connects to a local, plain-HTTP OpenSearch container (no TLS, no auth, security
plugin disabled). The index body mirrors `src/tools/opensearch_client.py` so the
runtime `OpenSearchClient.knn_search` reads indexed documents correctly
(fields: `vector` / `text` / `metadata`; 768-dim HNSW cosine, `m=30`,
`ef_construction=200`).

| Method | Description |
|--------|-------------|
| `ensure_index(index_name, embedding_dim=768)` | Create the k-NN index if absent. |
| `index_documents(index_name, embeddings, texts, metadata)` | Bulk-index `{vector, text, metadata}`; returns the count indexed. |
| `delete_index(index_name)` | Delete an index if it exists. |
| `list_indexes()` | List non-system index names. |
| `count(index_name)` | Document count for an index. |

## `OllamaClient`

Unchanged. Embeds text via the Ollama HTTP API (`embed_text` / `embed_texts`
with parallel workers) and checks model availability (`is_available`,
`get_available_models`).

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENSEARCH_LOCAL_HOST` | Local OpenSearch host | `localhost` |
| `OPENSEARCH_LOCAL_PORT` | Local OpenSearch port | `9200` |
| `OPENSEARCH_KB_INDEX` | Knowledge base index | `rag-kb` |
| `OPENSEARCH_CACHE_INDEX` | Response cache index | `rag-cache` |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_EMBED_MODEL` | Ollama embedding model | `nomic-embed-text:v1.5` |

## Dependencies

- `opensearch-py`: OpenSearch Python client
- `ollama` / `requests`: embeddings
- `python-dotenv`: environment management
