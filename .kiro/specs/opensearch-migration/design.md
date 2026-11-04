# Design Document

## Overview

This design migrates Local Mode's vector store from Milvus to OpenSearch in two
phases. Phase 1 adds an OpenSearch option behind a `LOCAL_VECTOR_BACKEND`
selector (default `milvus`) and routes it through the existing backend-agnostic
`shared_route` pipeline — reusing tested code instead of writing new retrieval
logic. Phase 2 flips the default and removes Milvus entirely.

The guiding principle: **the `VectorStore` / `SemanticCache` protocols and
`shared_route` already make the pipeline backend-agnostic; Serverless Mode
proves it.** The Milvus coupling is isolated to the Local-Mode `answer_question`
runtime path (`create_milvus_retrieval_tool` → `MilvusVectorDB.search`, and the
`MilvusResponseCache` L4 lookup). We therefore make OpenSearch Local Mode take
the *protocol* path (`shared_route` → `knn_search`), not the Milvus-native one.

### Why route through `shared_route` (Path A)

| Consideration | Path A: `shared_route` | Path B: make `answer_question` backend-agnostic |
|---|---|---|
| New retrieval code | ~none (reuses `route_rag_query`) | substantial (rewrite the protected path) |
| Risk to current Milvus local path | none (untouched) | high (edits the stable path) |
| Prod parity | higher (same path as Lambda) | same engine, different path |
| Within-local-mode parity | Milvus uses `answer_question`, OpenSearch uses `shared_route` | identical path |

Path A accepts one tradeoff: during Phase 1 the two local backends run through
different code paths. That is acceptable because (a) it is temporary — Phase 2
removes the Milvus path entirely, converging everything on `shared_route`, and
(b) it avoids risky surgery on `answer_question` while Milvus is still the
default. Phase 2 is where `answer_question` either moves onto `shared_route` or
is refactored to the protocol, so the end state has a single local path.

---

## Architecture

### Phase 1 — additive

```text
DEPLOYMENT_MODE=local
  ├─ LOCAL_VECTOR_BACKEND=milvus (default)
  │     api_server.py → StrandsGraphRAGAgent.answer_question
  │       → create_milvus_retrieval_tool → MilvusVectorDB.search   (UNCHANGED)
  │       → MilvusResponseCache (L4)                               (UNCHANGED)
  │
  └─ LOCAL_VECTOR_BACKEND=opensearch (new)
        api_server.py → serverless-style agent shim → shared_route
          → route_rag_query → OpenSearchClient.knn_search (KB)
          → OpenSearchClient semantic cache (L4)
          → OllamaClient (embeddings + generation)       [NOT Bedrock]
          → L2/L3 cache:                                  [NOT ElastiCache]
              REDIS_CACHE_ENABLED=false (default) → InMemoryCache
              REDIS_CACHE_ENABLED=true            → local RedisCache (plain TCP)

DEPLOYMENT_MODE=serverless  (UNCHANGED)
  Lambda → shared_route → OpenSearchClient.knn_search + BedrockClient + Redis
```

The new local-OpenSearch path is the serverless `shared_route` wiring with
**local substitutions**: Ollama instead of Bedrock, local plain-HTTP OpenSearch
instead of OpenSearch Serverless, and a configurable L2/L3 cache — `InMemoryCache`
by default (zero-setup quick start) or a plain-TCP local `RedisCache` when
`REDIS_CACHE_ENABLED=true` (full prod-parity backend set: OpenSearch + Redis).
This is a new backend combination the existing `create_rag_graph` does not
produce today (it only builds Bedrock+OpenSearch+Redis for serverless, or
Ollama+Milvus+InMemory for local).

### Phase 2 — end state

```text
DEPLOYMENT_MODE=local → Ollama + OpenSearch (local container) + InMemoryCache
DEPLOYMENT_MODE=serverless → Bedrock + OpenSearch Serverless + Redis
(single vector-store engine: OpenSearch; Milvus code deleted)
```

---

## Components and Interfaces

### 1. Settings (`src/config/settings.py`)

Add, mirroring the `deployment_mode` field style:

```python
local_vector_backend: Literal["milvus", "opensearch"] = Field(
    default="milvus",
    validation_alias="LOCAL_VECTOR_BACKEND",
    description="Local Mode vector store: 'milvus' (default) or 'opensearch'.",
)
# Local OpenSearch connection (plain HTTP, security disabled).
opensearch_local_host: str = Field(default="localhost", validation_alias="OPENSEARCH_LOCAL_HOST")
opensearch_local_port: int = Field(default=9200, validation_alias="OPENSEARCH_LOCAL_PORT")
```

The `Literal` type gives Requirement 1.5's fail-fast validation for free
(pydantic rejects other values at load). `opensearch_kb_index` /
`opensearch_cache_index` (already present, default `rag-kb`/`rag-cache`) are
reused for the local index names.

Also in this phase, rename the engine-agnostic tuning settings off the
`milvus_` prefix to `vectordb_` (with `MILVUS_*` env aliases retained for Phase
1) — see "Settings naming" under Data Model for the full table and rationale.

### 2. Local OpenSearch client builder

A small factory that returns an `OpenSearchClient` wrapping a plain-HTTP
transport — the exact pattern already in `scripts/run_serverless_local.py`:

```python
def build_local_opensearch_client(settings) -> OpenSearchClient:
    from opensearchpy import OpenSearch
    raw = OpenSearch(
        hosts=[{"host": settings.opensearch_local_host,
                "port": settings.opensearch_local_port}],
        http_auth=None, use_ssl=False, verify_certs=False, ssl_show_warn=False,
    )
    return OpenSearchClient(settings=settings, client=raw)
```

Placement: this is `src/` runtime wiring (not loader code), so it lives in
`src/` — likely a helper in `src/tools/opensearch_client.py` (e.g.
`OpenSearchClient.for_local(settings)` classmethod) so the injected-client
knowledge stays with the client. `OpenSearchClient.__init__` already accepts
`client=` and uses it verbatim (Req 8.3 preserved — cloud path untouched when no
client is injected). `vector_dim` resolves to 768 via `bedrock_pca_target_dim`,
which already matches Ollama; no PCA is involved because Ollama returns 768-dim
directly.

### 2b. Local Redis cache builder (optional L2/L3)

When `REDIS_CACHE_ENABLED=true`, the local-OpenSearch path uses a plain-TCP
local `RedisCache` instead of `InMemoryCache`, so the cache tier matches prod
(ElastiCache) and exercises the real `RedisCache` code (circuit breaker,
msgpack serialization). This reuses the proven pattern in
`scripts/run_serverless_local.py:build_local_redis_cache` — a non-TLS
`redis.Redis(host, port, ssl=False, ...)` injected into `RedisCache(settings,
client=raw)`. Mirroring 2's placement, this is exposed as
`RedisCache.for_local(settings)` so the injected-client knowledge lives with the
client. `RedisCache.__init__` already accepts `client=` and uses it verbatim, so
its cloud (TLS) default is preserved when no client is injected (Req 8.3). The
endpoint comes from the existing `REDIS_ENDPOINT` (default `localhost:6379`); if
Redis is unreachable, `RedisCache`'s existing soft circuit-breaker degrades to
cache-miss behavior (the `cache/redis_unavailable` signal) rather than failing
the query.

### 3. `create_rag_graph` — local-OpenSearch branch

Today the local branch builds Ollama+Milvus+InMemory+MilvusResponseCache. Add a
sub-branch on `local_vector_backend`:

```python
else:  # local
    ollama_runtime = ollama_client or OllamaClient(...)

    if settings.local_vector_backend == "opensearch":
        os_client = opensearch_client or OpenSearchClient.for_local(settings)
        vector_db = os_client
        semantic_cache = os_client          # L4 = rag-cache index, same client
        kb_index = settings.opensearch_kb_index
        # L2/L3: configurable — InMemory (default) or local Redis for parity.
        if settings.redis_cache_enabled:
            cache = redis_cache or RedisCache.for_local(settings)
        else:
            cache = InMemoryCache(ttl=settings.embedding_cache_ttl)
    else:  # milvus (unchanged)
        vector_db = milvus_client or MilvusVectorDB(...)
        semantic_cache = MilvusResponseCache(vector_db=vector_db, ...)
        kb_index = "milvus_docs"
        cache = InMemoryCache(ttl=settings.embedding_cache_ttl)  # unchanged
```

Then `kb_index` is already consumed by `shared_route`. The current line
`kb_index = ... if serverless else "milvus_docs"` is generalized to pick the
OpenSearch index for the OpenSearch-local case.

**Retrieval-path routing.** The Milvus local path runs through
`answer_question`; the OpenSearch local path must run through `shared_route`
(which calls `knn_search`). Two sub-options for how `api_server.py` reaches
`shared_route` in local-OpenSearch mode:

- **A1 (preferred, lowest risk):** reuse the existing serverless API shim
  approach. `api_server.py`'s agent is selected based on
  `local_vector_backend`: for `opensearch`, build an agent facade whose
  `answer_question`/`stream_answer` delegate to `shared_route` (exactly what
  `scripts/serverless_api_server.py`'s `ServerlessAgentShim` does, but with
  Ollama+InMemory locals). This keeps `StrandsGraphRAGAgent` (Milvus) untouched.
- **A2:** teach `StrandsGraphRAGAgent.answer_question` to call `shared_route`
  when `local_vector_backend == "opensearch"`. More invasive to the protected
  class.

Design chooses **A1**: a thin local-OpenSearch agent facade, so the Milvus
`StrandsGraphRAGAgent` is not modified in Phase 1. The facade and the serverless
shim share the same underlying `shared_route`, differing only in injected
backends (Ollama/InMemory vs Bedrock/Redis).

### 4. Offline Ollama → OpenSearch ingestion

A script (e.g. `scripts/ingest_local_opensearch.py`, in `scripts/` to stay clear
of the `document_loaders/` isolation rule) that:

1. builds the local OpenSearch client and calls `ensure_indexes()` (creates
   768-dim HNSW cosine `rag-kb`/`rag-cache`);
2. reads source documents (reusing the existing chunking bound
   `settings.max_chunk_length`);
3. embeds each chunk with `OllamaClient.embed_text(..., model=nomic-embed-text)`;
4. indexes via `OpenSearchClient.index_document(index=kb_index, doc_id, vector,
   text, metadata)`.

This is the Ollama analog of `scripts/run_serverless_local.py:seed_knowledge_base`
(which uses Bedrock). It requires no AWS. Chunk/metadata shape matches what
`knn_search` returns (`{id, text, metadata, distance}`), satisfying Req 3.5.

> Note: `OpenSearchClient.index_document` uses `refresh=True`, fine for a local
> one-shot ingest. For large corpora a bulk path could be added later; out of
> scope for Phase 1.

### 5. Local OpenSearch container (`docker/`)

Phase 1 reuses the existing `docker/serverless-local/docker-compose.yml`
OpenSearch service (already on `9200`, security disabled) — no new container is
strictly required; the Local-Mode-on-OpenSearch path can point at it. For a
cleaner local-only experience we add an OpenSearch service to the main
`docker/docker-compose.yml` guarded so it does not collide with Milvus ports
(Milvus 19530/9091, MinIO 9000/9001; OpenSearch 9200). Developers can run either
stack. Phase 2 replaces the Milvus services here with OpenSearch outright.

### 6. Health check (`api_server.py`)

Phase 1: when `local_vector_backend == "opensearch"`, the `/health` probe pings
OpenSearch (`GET /_cluster/health` or `indices.exists`) instead of the
Milvus-specific `list_collections`. Mirrors the serverless-shim health override
already documented in `SERVERLESS_LOCAL.md`. Phase 2: the Milvus probe is
removed entirely.

---

## Data Model

Local OpenSearch indexes are created by the **existing**
`OpenSearchClient.ensure_indexes()` / `_knn_index_body()` — no new schema:

- `rag-kb`: `{ vector: knn_vector(768, hnsw, cosinesimil, nmslib, m, ef_construction),
  text: text, metadata: object }`.
- `rag-cache`: the above plus `{ question, answer, sources, created_at }`.

768 dim is correct for Ollama `nomic-embed-text:v1.5`. HNSW `m` /
`ef_construction` / search `ef` come from shared, **vendor-neutral** settings
(see "Settings naming" below) that both backends read.

### Settings naming — `milvus_*` → `vectordb_*`

The engine-agnostic tuning knobs are renamed off the `milvus_` prefix to
`vectordb_` in **Phase 1**, since they already drive both backends (the
OpenSearch client reads them today). Renamed:

| Old | New | Env var old → new |
|---|---|---|
| `milvus_index_type` | `vectordb_index_type` | `MILVUS_INDEX_TYPE` → `VECTORDB_INDEX_TYPE` |
| `milvus_metric_type` | `vectordb_metric_type` | `MILVUS_METRIC_TYPE` → `VECTORDB_METRIC_TYPE` |
| `milvus_hnsw_m` | `vectordb_hnsw_m` | `MILVUS_HNSW_M` → `VECTORDB_HNSW_M` |
| `milvus_hnsw_ef_construction` | `vectordb_hnsw_ef_construction` | `MILVUS_HNSW_EF_CONSTRUCTION` → `VECTORDB_HNSW_EF_CONSTRUCTION` |
| `milvus_ivf_nlist` | `vectordb_ivf_nlist` | `MILVUS_IVF_NLIST` → `VECTORDB_IVF_NLIST` |
| `milvus_search_ef` | `vectordb_search_ef` | `MILVUS_SEARCH_EF` → `VECTORDB_SEARCH_EF` |

Backward compatibility during Phase 1: each renamed pydantic field uses
`AliasChoices(new_env, old_env)` so a `MILVUS_*` value in an existing `.env`
still works (with a one-time deprecation log). The old names are dropped in
Phase 2.

**Not renamed — deleted in Phase 2.** The Milvus *connection* settings are
vendor-specific, not engine-agnostic, so they are not renamed to `vectordb_`;
they are removed with Milvus in Phase 2: `milvus_host`, `milvus_port`,
`milvus_db_name`, `loader_milvus_db_name`, `milvus_user`, `milvus_password`,
`milvus_timeout`, `milvus_pool_size`. (Renaming a Milvus URI/credential to
`vectordb_` would be misleading, since OpenSearch uses endpoint/host+port and no
such credentials locally.)

Code that reads the renamed settings is updated in the same change:
`src/tools/milvus_client.py` (`create_collection`), `src/tools/opensearch_client.py`
(the `getattr(settings, "milvus_hnsw_m", …)` lookups → `vectordb_hnsw_m`), and
the `MILVUS_SEARCH_EF` references in `.env.example` / the config-validation test.

---

## Error Handling

- **OpenSearch unreachable (local):** the local-OpenSearch agent facade and
  `/health` report unavailable (Req 2.5), matching Milvus degraded mode. A query
  returns the honest "no grounding" refusal rather than a stack trace, because
  `route_rag_query` already treats an empty/failed KB search as low relevance →
  web-fallback → honest refusal when nothing grounds.
- **Invalid `LOCAL_VECTOR_BACKEND`:** pydantic `Literal` rejects at settings
  load (Req 1.5).
- **`opensearch-py` missing:** `OpenSearchClient.for_local` surfaces the same
  clear ImportError guidance the serverless constructor uses.
- **Serverless untouched:** no change to `_build_serverless_backends`; injecting
  a local client never runs for serverless (Req 8.1).

---

## Testing Strategy

Phase 1 (unit, no live services — inject a fake OpenSearch transport like
`tests/unit/test_tools/test_opensearch_knn_search.py` already does):

1. `local_vector_backend` selector: default `milvus`; invalid value raises;
   serverless ignores it.
2. `create_rag_graph` local+opensearch branch wires `OpenSearchClient` as both
   `vector_store` and `semantic_cache`, Ollama as `llm`, `InMemoryCache` as
   cache, and `kb_index = rag-kb`.
3. `create_rag_graph` local+milvus branch is byte-for-byte unchanged (regression
   guard — assert Milvus client + MilvusResponseCache + `milvus_docs`).
4. Local-OpenSearch agent facade delegates `answer_question` to `shared_route`
   with the injected locals.
5. Ingestion: chunks → Ollama embed (faked) → `index_document` called with
   768-dim vectors and the expected metadata shape.
6. Health: opensearch backend → OpenSearch probe path; milvus backend → existing
   probe (regression guard).

Serverless regression: existing `tests/` suites must still pass unchanged
(Req 8.2).

Phase 2 (added when Phase 2 tasks run): a repo-wide `grep -ri milvus` gate
(excluding `.kiro/specs/` and historical docs) returns nothing (Req 7.7);
removed-module imports fail; `/health` has no Milvus probe.

---

## Migration / Rollout

1. Ship Phase 1 (default `milvus`) — zero behavior change until opt-in.
2. Developers run `LOCAL_VECTOR_BACKEND=opensearch` + the ingest script; validate
   parity in daily use.
3. Phase 2: flip default to `opensearch`, announce in docs with a re-index note,
   then delete Milvus (client, cache, loaders, settings, Docker, docs, tests)
   and converge the local path onto `shared_route`.

Rollback: Phase 1 is fully reversible (flip the selector back). After Phase 2's
deletion, rollback means reverting the removal commit — hence Phase 2 is a
separate, clearly-scoped change set, not mixed with Phase 1.
