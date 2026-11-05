# Requirements Document

## Introduction

This feature replaces Milvus with OpenSearch as the vector store for **Local
Mode**, so the project standardizes on a single vector-store engine
(OpenSearch) across both deployment modes. Today Local Mode is hardwired to
Milvus (Ollama + Milvus + FastAPI) while Serverless Mode uses OpenSearch
Serverless (Bedrock + OpenSearch + Lambda). The two already sit behind the
shared `VectorStore` / `SemanticCache` protocols, but the Local-Mode runtime
path (`StrandsGraphRAGAgent.answer_question` → `create_milvus_retrieval_tool` →
`MilvusVectorDB.search`, plus `MilvusResponseCache` for Layer 4) calls
Milvus-native methods and never uses the protocol path the serverless side
uses.

The migration is deliberately **phased** to keep each step reversible:

- **Phase 1 (additive):** introduce a `LOCAL_VECTOR_BACKEND = milvus | opensearch`
  selector (default `milvus`), add an offline Ollama + OpenSearch Local-Mode
  path, and an Ollama-embedded ingestion path into OpenSearch. Nothing is
  removed; existing Milvus behavior is unchanged unless the selector is flipped.
- **Phase 2 (removal):** once Phase 1 is validated in day-to-day use, make
  `opensearch` the default, remove the Milvus client, Milvus-backed cache, the
  Milvus loader path, Milvus settings, and the Milvus Docker stack, and update
  all documentation and tests.

Embeddings remain **Ollama `nomic-embed-text:v1.5` (768-dim)** in Local Mode;
only the vector store changes. The local OpenSearch runs as a plain-HTTP
container (security plugin disabled), reusing the proven injected-client pattern
from `scripts/run_serverless_local.py` so no TLS/SigV4 is required locally.

---

## Glossary

- **Local_Mode**: `DEPLOYMENT_MODE=local` — Ollama for embeddings + generation,
  FastAPI (`api_server.py`), a local vector store. The developer/offline path.
- **Serverless_Mode**: `DEPLOYMENT_MODE=serverless` — Bedrock + OpenSearch
  Serverless + Lambda. Unchanged by this feature.
- **Local_Vector_Backend**: new setting `LOCAL_VECTOR_BACKEND` selecting the
  Local-Mode vector store: `milvus` (current) or `opensearch` (new).
- **Local_OpenSearch**: an OpenSearch container on `localhost:9200`, security
  plugin disabled (plain HTTP, no SigV4/TLS), used by Local Mode when
  `LOCAL_VECTOR_BACKEND=opensearch`.
- **OpenSearchClient**: `src/tools/opensearch_client.py` — implements the
  `VectorStore` and `SemanticCache` protocols; accepts an injected
  `opensearchpy.OpenSearch` transport, bypassing its cloud (443/TLS/SigV4)
  defaults.
- **MilvusVectorDB**: `src/tools/milvus_client.py` — the current Local-Mode
  vector store (native `search(collection_name, query_embedding, limit)`).
- **MilvusResponseCache**: `src/tools/response_cache.py` — the current
  Milvus-backed Layer 4 semantic response cache.
- **VectorStore_Protocol**: `src/tools/interfaces.py` `VectorStore` —
  `knn_search(index, query_vector, k)` + `index_document(...)`. The
  backend-agnostic retrieval contract the serverless path uses.
- **Shared_Route**: `rag_routing.route_rag_query` (bound as `shared_route` in
  `create_rag_graph`) — the backend-agnostic Cache→KB→Web pipeline that calls
  `VectorStore.knn_search`. The serverless runtime path.
- **Local_Ingestion**: an offline path that chunks documents, embeds chunks with
  Ollama, and indexes them into Local_OpenSearch (the Ollama analog of the
  serverless Bedrock `IndexingHandler`).
- **KB_Index**: the OpenSearch knowledge-base index (`settings.opensearch_kb_index`,
  default `rag-kb`).
- **Cache_Index**: the OpenSearch Layer 4 semantic cache index
  (`settings.opensearch_cache_index`, default `rag-cache`).

---

## Requirements

### Requirement 1: Local Vector Backend Selector (Phase 1)

**User Story:** As a developer, I want to choose the Local-Mode vector store
without changing deployment mode, so I can run Local Mode on OpenSearch for
prod parity while keeping Milvus available as a fallback.

#### Acceptance Criteria

1. THE system SHALL provide a setting `local_vector_backend` (env
   `LOCAL_VECTOR_BACKEND`) accepting `milvus` or `opensearch`, defaulting to
   `milvus`.
2. WHEN `DEPLOYMENT_MODE=serverless`, THE system SHALL ignore
   `LOCAL_VECTOR_BACKEND` (serverless always uses OpenSearch Serverless).
3. WHEN `DEPLOYMENT_MODE=local` AND `LOCAL_VECTOR_BACKEND=milvus` (default),
   THE system SHALL behave exactly as today (Ollama + Milvus), with no change
   to the existing retrieval, cache, or answer paths.
4. WHEN `DEPLOYMENT_MODE=local` AND `LOCAL_VECTOR_BACKEND=opensearch`, THE
   system SHALL use Ollama for embeddings/generation and Local_OpenSearch for
   KB retrieval and the Layer 4 semantic cache.
5. IF `LOCAL_VECTOR_BACKEND` is set to any value other than `milvus` or
   `opensearch`, THEN THE system SHALL fail fast at settings load with a clear
   validation error naming the allowed values.
6. THE engine-agnostic vector tuning settings SHALL be renamed off the
   vendor-specific `milvus_` prefix to a neutral `vectordb_` prefix
   (`index_type`, `metric_type`, `hnsw_m`, `hnsw_ef_construction`, `ivf_nlist`,
   `search_ef`), with the corresponding env vars renamed `MILVUS_*` →
   `VECTORDB_*`.
7. WHILE Phase 1 is in effect, THE renamed settings SHALL still accept the old
   `MILVUS_*` env vars as deprecated aliases so existing `.env` files keep
   working; the aliases are removed in Phase 2.
8. THE Milvus *connection* settings (`milvus_host`, `milvus_port`,
   `milvus_db_name`, `milvus_user`, `milvus_password`, `milvus_timeout`,
   `milvus_pool_size`, `loader_milvus_db_name`) are vendor-specific and SHALL
   NOT be renamed to `vectordb_`; they are removed with Milvus in Phase 2
   (Requirement 7).

---

### Requirement 2: Offline Ollama + OpenSearch Retrieval Path (Phase 1)

**User Story:** As a developer, I want Local Mode on OpenSearch to retrieve and
answer using the same backend-agnostic pipeline the serverless path uses, so
behavior is consistent and I reuse tested code rather than new retrieval logic.

#### Acceptance Criteria

1. WHEN Local_Mode runs with `LOCAL_VECTOR_BACKEND=opensearch`, THE system SHALL
   construct an `OpenSearchClient` backed by a plain-HTTP `opensearchpy.OpenSearch`
   transport pointed at Local_OpenSearch (no TLS, no SigV4), using the injected-
   client pattern already proven in `scripts/run_serverless_local.py`.
2. WHEN Local_Mode runs with `LOCAL_VECTOR_BACKEND=opensearch`, THE system SHALL
   use that `OpenSearchClient` as BOTH the `VectorStore` (KB retrieval) and the
   `SemanticCache` (Layer 4), matching the serverless wiring.
3. WHEN a query is answered in this mode, retrieval SHALL go through the
   `VectorStore_Protocol` (`knn_search`) — not `MilvusVectorDB.search` — so the
   Ollama embedding (768-dim) is queried against KB_Index.
4. THE embedding dimension used to create KB_Index and Cache_Index in this mode
   SHALL be 768 (matching Ollama `nomic-embed-text:v1.5`), and querying SHALL
   succeed without PCA (PCA applies only to Bedrock's 1536→768 path).
5. WHEN Local_OpenSearch is unreachable, THE system SHALL degrade clearly
   (health reports the vector store unavailable; answering does not crash with
   an opaque error), mirroring today's Milvus degraded-mode behavior.
6. THE `TopicChecker` and `SecurityChecker` behavior SHALL be identical
   regardless of `LOCAL_VECTOR_BACKEND` (they are backend-agnostic).
7. THE Layer 2/3 cache in OpenSearch Local Mode SHALL be configurable via the
   existing `REDIS_CACHE_ENABLED` setting: WHEN `false` (default) THE system
   SHALL use `InMemoryCache` (zero-setup quick start); WHEN `true` THE system
   SHALL use a plain-TCP local `RedisCache` (full prod-parity backend set:
   OpenSearch + Redis), reusing the injected-client pattern.
8. WHEN local Redis is enabled but unreachable, THE system SHALL degrade to
   cache-miss behavior via the existing `RedisCache` circuit breaker (emitting
   `cache/redis_unavailable`) rather than failing the query.

---

### Requirement 3: Offline Ollama → OpenSearch Ingestion (Phase 1)

**User Story:** As a developer, I want to load my documents into Local_OpenSearch
with Ollama embeddings offline, so the OpenSearch Local Mode has a populated
knowledge base without using AWS/Bedrock.

#### Acceptance Criteria

1. THE system SHALL provide an offline ingestion path that chunks documents,
   embeds each chunk with Ollama (`nomic-embed-text:v1.5`, 768-dim), and indexes
   them into KB_Index via the `VectorStore` `index_document` contract.
2. THE ingestion path SHALL ensure KB_Index and Cache_Index exist (creating them
   as 768-dim HNSW cosine indexes) before indexing.
3. THE ingestion path SHALL NOT require AWS credentials, Bedrock, or any cloud
   dependency.
4. WHERE the project's source-isolation rule forbids `document_loaders/` from
   importing `src/`, THE ingestion path SHALL either live outside
   `document_loaders/` or use a package-local OpenSearch client, consistent with
   that rule.
5. THE ingestion path SHALL produce an index whose chunk/metadata shape is
   compatible with what `OpenSearchClient.knn_search` returns
   (`{id, text, metadata, distance}`).

> Note: Phase 1 ships a minimal ingest script. Requirement 10 (Phase 2) expands
> it to full "vectorize documents as before" parity.

---

### Requirement 4: Local OpenSearch Container (Phase 1)

**User Story:** As a developer, I want a one-command local OpenSearch so I can
run OpenSearch Local Mode without AWS.

#### Acceptance Criteria

1. THE project SHALL provide a Docker service that runs OpenSearch on
   `localhost:9200` with the security plugin disabled (plain HTTP).
2. THE local OpenSearch service SHALL be runnable alongside, or independently
   of, the existing Milvus stack during Phase 1 (no port collision).
3. THE configuration SHALL be documented so a developer can start the container,
   ingest documents, and run Local Mode on OpenSearch end-to-end.

---

### Requirement 5: Documentation and Configuration (Phase 1)

**User Story:** As a developer, I want the OpenSearch Local Mode documented and
every new setting captured, so the option is discoverable and configurable.

#### Acceptance Criteria

1. THE new setting(s) (`LOCAL_VECTOR_BACKEND`, any local OpenSearch host/port/
   ssl settings) SHALL be documented in `.env.example` and
   `docs/GETTING_STARTED.md`, per the project documentation rules.
2. `docs/ARCHITECTURE.md` SHALL describe the Local-Mode vector-backend choice
   and that OpenSearch is the parity option.
3. `docs/HOW_TO.md` (or `docs/GETTING_STARTED.md`) SHALL include the end-to-end
   steps: start container → ingest → run.
4. `docs/INDEX.md` SHALL reference any new doc added.

---

### Requirement 6: Make OpenSearch the Local Default (Phase 2)

**User Story:** As a maintainer, once OpenSearch Local Mode is proven, I want it
to be the default so the project standardizes on OpenSearch.

#### Acceptance Criteria

1. WHEN Phase 2 begins, THE default of `local_vector_backend` SHALL change to
   `opensearch`.
2. THE change SHALL be announced in the docs with a migration note (how to
   re-index existing content, how to keep Milvus temporarily via the selector).
3. UNTIL Milvus is removed (Requirement 7), setting
   `LOCAL_VECTOR_BACKEND=milvus` SHALL still work.

---

### Requirement 7: Remove Milvus (Phase 2)

**User Story:** As a maintainer, I want all Milvus code, config, infrastructure,
and documentation removed so there is a single vector-store engine to maintain.

#### Acceptance Criteria

1. THE system SHALL remove `src/tools/milvus_client.py`
   (`MilvusVectorDB`) and the Milvus-backed `MilvusResponseCache`, replacing the
   Layer 4 cache with the OpenSearch semantic cache in Local Mode.
2. THE system SHALL remove the Milvus-specific Local-Mode code paths
   (`create_milvus_retrieval_tool` Milvus coupling, `retrieve_context`,
   `answer_question`'s Milvus cache lookup) OR refactor them to be backend-
   agnostic against the `VectorStore`/`SemanticCache` protocols.
3. THE system SHALL remove the Milvus *connection* settings from
   `src/config/settings.py` (`milvus_host`, `milvus_port`, `milvus_db_name`,
   `milvus_user`, `milvus_password`, `milvus_timeout`, `milvus_pool_size`,
   `loader_milvus_db_name`) and all `MILVUS_*` entries (including the deprecated
   `MILVUS_*` aliases on the renamed `vectordb_*` settings) from `.env.example`.
   The engine-agnostic `vectordb_*` settings (renamed in Phase 1, Requirement
   1.6) are retained.
4. THE system SHALL replace the Milvus Docker stack (Milvus + etcd + MinIO) with
   the OpenSearch service in `docker/docker-compose.yml`.
5. THE system SHALL migrate the `document_loaders/` ingestion to OpenSearch and
   remove Milvus loader code.
6. THE system SHALL remove or rewrite every Milvus reference in docs
   (`ARCHITECTURE`, `GETTING_STARTED`, `HOW_TO`, `API_SERVER`, README,
   `docker/README`) and in tests, so no stale Milvus guidance remains.
7. WHEN Phase 2 is complete, a repository-wide search for `milvus` (case-
   insensitive) SHALL return no references to Milvus **as a vector-store engine**
   in runtime code, configuration, or active docs, EXCLUDING:
   - the knowledge-base corpus `document_loaders/milvus_docs/` — this is the
     demo's subject-matter content (documentation *about* Milvus), not engine
     code, and is retained as the KB (re-indexed into OpenSearch);
   - `.kiro/specs/` and historical/archive documents;
   - unavoidable incidental mentions where "milvus" is the KB topic being
     described.
   That is: remove Milvus-the-database-client, not Milvus-the-subject.
8. THE `api_server.py` health check SHALL report OpenSearch availability in
   Local Mode (no Milvus-specific `list_collections` probe).

---

### Requirement 8: No Serverless Regression (both phases)

**User Story:** As a maintainer, I want the serverless path untouched by this
migration, so production behavior does not change.

#### Acceptance Criteria

1. THE Serverless_Mode wiring (`_build_serverless_backends`, the Lambda handler,
   `shared_route`, Terraform) SHALL be unchanged by Phase 1.
2. THE existing serverless and unit test suites SHALL continue to pass after
   each phase.
3. Changes to `OpenSearchClient` to support an injected local transport (if any)
   SHALL preserve its existing cloud (443/TLS/SigV4) behavior when no client is
   injected.

---

### Requirement 9: Consolidated Docker Stack (Phase 2)

**User Story:** As a developer, I want a single Docker Compose stack for the
whole local app (OpenSearch + Redis + DynamoDB + API + React), named
consistently, so I run one command and there is no leftover Milvus or separate
serverless-local compose to juggle.

#### Acceptance Criteria

1. THE project SHALL have ONE primary compose file (`docker/docker-compose.yml`)
   defining: `opensearch`, `redis`, `dynamodb`, `rag-api`, `rag-react`. The
   separate `docker/serverless-local/docker-compose.yml` and the Milvus services
   (Milvus/etcd/MinIO) SHALL be removed/folded in.
2. THE compose project and container names SHALL use the `agentcore-rag` prefix:
   compose `name: agentcore-rag`; containers `agentcore-rag-opensearch`,
   `agentcore-rag-redis`, `agentcore-rag-dynamodb`, `agentcore-rag-api`,
   `agentcore-rag-react`.
3. THE `rag-api` service SHALL run against OpenSearch: env
   `DEPLOYMENT_MODE=local` + `LOCAL_VECTOR_BACKEND=opensearch` +
   `OPENSEARCH_LOCAL_HOST`/`PORT`, `depends_on: opensearch` (no `MILVUS_*`, no
   `depends_on: milvus`).
4. THE `rag-api` service SHALL mount the top-level entrypoint (`api_server.py`)
   so edits do not require an image rebuild (the Phase 1 stale-image quirk).
5. THE scripts that referenced `docker/serverless-local/...`
   (`run_serverless_local.py`, `serverless_api_server.py`) SHALL be updated or
   retired consistently with the consolidated compose.
6. THE consolidated stack SHALL start cleanly (`docker compose up -d`) with all
   services healthy, validated by a smoke test (ingest → query → answer).

---

### Requirement 10: Full Document Vectorization Parity (Phase 2)

**User Story:** As a developer, I want to vectorize my own documents into the
knowledge base exactly as the old Milvus loader allowed — not just a demo seed —
but targeting OpenSearch.

#### Acceptance Criteria

1. THE ingestion path SHALL index the existing `document_loaders/milvus_docs/`
   corpus into OpenSearch KB_Index (the KB content is retained; only the engine
   changes).
2. THE ingestion path SHALL support vectorizing an arbitrary directory of
   documents (not only the built-in demo set), preserving the old loader's
   capabilities: recursive read, chunking by `max_chunk_length`, batch/parallel
   Ollama embedding, and per-chunk metadata (filename/source).
3. THE ingestion path SHALL retain the `data/embeddings.json` snapshot behavior
   the old loader produced (or an explicitly documented equivalent), so an
   embeddings export remains available.
4. THE migrated `document_loaders/` package SHALL target OpenSearch via a
   package-local OpenSearch client (source-isolation: no `src/` import) and
   SHALL NOT retain Milvus client code.
5. WHEN ingestion completes against a running OpenSearch, a query through the
   app SHALL retrieve from the ingested content (validated by the smoke test).

---

## Out of Scope

- Changing the embedding model or dimension (stays Ollama 768-dim locally,
  Bedrock→768 PCA in serverless).
- Any change to Serverless_Mode infrastructure or the Lambda path.
- Metadata filtering/boosting beyond the optional passthrough already added.
- A managed/cloud OpenSearch for local development (the local container is
  plain-HTTP, security disabled, dev-only).
