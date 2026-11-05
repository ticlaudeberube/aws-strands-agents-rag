# Implementation Plan: Milvus → OpenSearch Migration (Local Mode)

## Overview

This plan converts the design into incremental coding steps, in two phases that
match the requirements. **Phase 1 is additive and reversible** — it adds a
`LOCAL_VECTOR_BACKEND` selector (default `milvus`), the OpenSearch Local-Mode
path routed through the existing `shared_route`, an Ollama→OpenSearch ingestion
script, the local container, the vendor-neutral `vectordb_*` settings rename
(with `MILVUS_*` aliases), and docs. Nothing is removed and the default is
unchanged, so each step can land independently with the Milvus path intact.
**Phase 2 removes Milvus** once Phase 1 is validated in day-to-day use: flip the
default, delete the Milvus client/cache/loaders/settings/Docker, converge the
local path on `shared_route`, and scrub docs/tests.

Guardrail throughout: **Serverless Mode and the existing Milvus Local path must
not regress.** Phase-1 tasks preserve current behavior under the default
selector; the full unit/serverless suites must stay green after every task.
Tests tagged `[ ]*` are optional-but-recommended and use injected fakes (no live
Ollama/OpenSearch/Redis), following `tests/unit/test_tools/test_opensearch_knn_search.py`.

Application code is Python (`uv run` tooling: ruff, mypy, pytest).

---

## Phase 1 — Additive OpenSearch Local Mode

- [ ] 1. Vendor-neutral settings rename (`milvus_*` → `vectordb_*`)
  - [ ] 1.1 Rename the engine-agnostic tuning settings in `src/config/settings.py`
    - Rename fields: `milvus_index_type`→`vectordb_index_type`,
      `milvus_metric_type`→`vectordb_metric_type`, `milvus_hnsw_m`→`vectordb_hnsw_m`,
      `milvus_hnsw_ef_construction`→`vectordb_hnsw_ef_construction`,
      `milvus_ivf_nlist`→`vectordb_ivf_nlist`, `milvus_search_ef`→`vectordb_search_ef`
    - Use `AliasChoices("VECTORDB_*", "MILVUS_*")` so the old env vars still work
      (deprecated), with a one-time deprecation log when an old alias is used
    - Leave the Milvus *connection* settings unchanged (deleted in Phase 2)
    - _Requirements: 1.6, 1.7, 1.8_
  - [ ] 1.2 Update all readers of the renamed settings
    - `src/tools/milvus_client.py` `create_collection` (M/efConstruction/nlist/index/metric)
    - `src/tools/opensearch_client.py` `__init__` getattr lookups (`vectordb_hnsw_m`,
      `vectordb_hnsw_ef_construction`, `vectordb_search_ef`)
    - `.env.example` (`MILVUS_*` → `VECTORDB_*`, keep a note that MILVUS_* still
      read as deprecated aliases in Phase 1)
    - `tests/unit/test_config/test_config_validation.py` (the `milvus_search_ef`
      references → `vectordb_search_ef`)
    - _Requirements: 1.6_
  - [ ]* 1.3 Test: old `MILVUS_*` env still resolves the renamed field; new
    `VECTORDB_*` wins; invalid values behave as before
    - File: `tests/unit/test_config/test_vectordb_settings_rename.py`
    - _Requirements: 1.6, 1.7_

- [ ] 2. `LOCAL_VECTOR_BACKEND` selector
  - [ ] 2.1 Add `local_vector_backend: Literal["milvus","opensearch"]`
    (default `milvus`, alias `LOCAL_VECTOR_BACKEND`) plus `opensearch_local_host`
    (`localhost`) / `opensearch_local_port` (`9200`) to `src/config/settings.py`
    - _Requirements: 1.1, 1.5_
  - [ ]* 2.2 Test: default is `milvus`; invalid value raises at load; serverless
    ignores the selector
    - File: `tests/unit/test_config/test_local_vector_backend.py`
    - _Requirements: 1.1, 1.2, 1.5_

- [ ] 3. Local client builders (injected plain-HTTP / plain-TCP)
  - [ ] 3.1 Add `OpenSearchClient.for_local(settings)` classmethod building a
    plain-HTTP `opensearchpy.OpenSearch` (no TLS/SigV4) and injecting it, reusing
    the `scripts/run_serverless_local.py:build_local_opensearch_client` pattern.
    Preserve the cloud `_build_client` path when no client is injected.
    - _Requirements: 2.1, 8.3_
  - [ ] 3.2 Add `RedisCache.for_local(settings)` classmethod building a plain-TCP
    `redis.Redis(ssl=False)` and injecting it (reuse `build_local_redis_cache`
    pattern). Preserve the TLS default when no client is injected.
    - _Requirements: 2.7, 8.3_
  - [ ]* 3.3 Test: `for_local` constructors inject a non-TLS client and leave the
    cloud path intact when `client` is omitted (fake transport)
    - File: `tests/unit/test_tools/test_local_client_builders.py`
    - _Requirements: 2.1, 2.7, 8.3_

- [ ] 4. `create_rag_graph` — local OpenSearch sub-branch
  - [ ] 4.1 In the local branch, branch on `settings.local_vector_backend`:
    - `opensearch`: `vector_db = semantic_cache = OpenSearchClient.for_local(...)`
      (or injected `opensearch_client`); `kb_index = settings.opensearch_kb_index`;
      `cache = RedisCache.for_local(...)` if `redis_cache_enabled` else
      `InMemoryCache(...)`; `llm = Ollama`
    - `milvus` (default): unchanged (Milvus + MilvusResponseCache + `milvus_docs`
      + InMemoryCache)
    - _Requirements: 1.3, 1.4, 2.2, 2.7_
  - [ ] 4.2 Generalize the `kb_index` selection so OpenSearch local uses the
    OpenSearch index (not the hardcoded `"milvus_docs"`)
    - _Requirements: 2.3_
  - [ ]* 4.3 Test: local+opensearch wires OpenSearchClient as vector_store AND
    semantic_cache, Ollama llm, cache per `redis_cache_enabled`, `kb_index=rag-kb`
    - _Requirements: 1.4, 2.2, 2.3, 2.7_
  - [ ]* 4.4 Regression test: local+milvus (default) branch is byte-for-byte
    unchanged (Milvus client + MilvusResponseCache + `milvus_docs` + InMemory)
    - _Requirements: 1.3, 8.2_

- [ ] 5. Local-OpenSearch agent facade (route through `shared_route`)
  - [ ] 5.1 Add a thin local agent facade (modeled on `ServerlessAgentShim`) whose
    `answer_question` / `stream_answer` delegate to the graph's `shared_route`
    with the Ollama + (InMemory|Redis) locals. New module under `src/agents/`
    (e.g. `local_opensearch_agent.py`) — does NOT modify `StrandsGraphRAGAgent`.
    - _Requirements: 2.2, 2.3_
  - [ ] 5.2 Select the agent in `api_server.py` by `local_vector_backend`:
    `opensearch` → facade; `milvus` → existing `StrandsGraphRAGAgent` (unchanged)
    - _Requirements: 1.3, 1.4_
  - [ ] 5.3 `/health`: when `local_vector_backend=opensearch`, probe OpenSearch
    (`_cluster/health`/`indices.exists`) instead of Milvus `list_collections`;
    report unavailable cleanly on failure
    - _Requirements: 2.5_
  - [ ]* 5.4 Test: facade delegates to `shared_route` with injected locals; health
    uses the OpenSearch probe for the opensearch backend, the Milvus probe for milvus
    - _Requirements: 2.2, 2.5_

- [ ] 6. Offline Ollama → OpenSearch ingestion
  - [ ] 6.1 Add `scripts/ingest_local_opensearch.py` (in `scripts/`, not
    `document_loaders/`, per isolation rule): ensure indexes → read/chunk docs
    (bound by `settings.max_chunk_length`) → Ollama embed (768-dim) →
    `OpenSearchClient.index_document(...)`. No AWS/Bedrock dependency.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - [ ]* 6.2 Test: ingestion chunks → faked Ollama embed → `index_document` called
    with 768-dim vectors and the `{id,text,metadata}` shape `knn_search` returns
    - File: `tests/unit/test_ingest_local_opensearch.py`
    - _Requirements: 3.1, 3.5_

- [ ] 7. Local OpenSearch container
  - [ ] 7.1 Add an OpenSearch service to `docker/docker-compose.yml` on `9200`
    (security disabled, plain HTTP), guarded to not collide with Milvus ports.
    (Phase 1 may alternatively document reuse of
    `docker/serverless-local/docker-compose.yml`'s OpenSearch service.)
    - _Requirements: 4.1, 4.2_

- [ ] 8. Phase 1 documentation
  - [ ] 8.1 `.env.example` + `docs/GETTING_STARTED.md`: document
    `LOCAL_VECTOR_BACKEND`, `OPENSEARCH_LOCAL_HOST/PORT`, the `REDIS_CACHE_ENABLED`
    cache choice, and the `VECTORDB_*` rename (with the `MILVUS_*` deprecation note)
    - _Requirements: 5.1_
  - [ ] 8.2 `docs/ARCHITECTURE.md`: describe the Local-Mode vector-backend choice
    and OpenSearch as the parity option
    - _Requirements: 5.2_
  - [ ] 8.3 `docs/HOW_TO.md` (or GETTING_STARTED): end-to-end steps (start
    container → ingest → run on OpenSearch); update `docs/INDEX.md` if a doc is added
    - _Requirements: 5.3, 5.4_

- [ ] 9. Phase 1 verification
  - [ ] 9.1 Run ruff + mypy + full unit suite; confirm Milvus default path and
    serverless suites are unchanged (Req 8.2). Manually smoke the OpenSearch path
    (container up → ingest → ask a question) and record the result.
    - _Requirements: 8.1, 8.2_

> **Gate:** Phase 2 does not start until Phase 1 is merged and validated in
> day-to-day use. Phase 2 is a separate change set (so its deletion is revertible
> as one commit).

---

## Phase 2 — Make OpenSearch default and remove Milvus

> **Scope reminder (Req 7.7):** remove Milvus **the vector-store engine** — the
> database client, cache, settings, Docker stack, loader coupling. KEEP
> `document_loaders/milvus_docs/` — that is the knowledge-base *content*
> (documentation about Milvus), re-indexed into OpenSearch. The `grep` gate
> excludes that corpus, `.kiro/specs/`, and incidental KB-topic mentions.

- [ ] 10. Flip the default
  - [ ] 10.1 Change `local_vector_backend` default to `opensearch`; docs
    migration note (re-index content; `milvus` selectable until task 12 removes it)
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 11. Converge the local path on `shared_route`
  - [ ] 11.1 Make the single Local-Mode path the `shared_route`/protocol path;
    retire the Milvus-native `answer_question`/`create_milvus_retrieval_tool`/
    `retrieve_context` coupling (or refactor backend-agnostic). The
    `StrandsGraphRAGAgent` Milvus path is removed; `LocalOpenSearchAgent`
    becomes the sole local agent.
    - _Requirements: 7.2_
  - [ ] 11.2 Make the MCP server (`RAGAgentMCPServer`) use the selected backend
    instead of always constructing a Milvus `StrandsGraphRAGAgent` (the
    degraded-mode noise seen in the Phase 1 smoke test).
    - _Requirements: 7.2_

- [ ] 12. Remove Milvus engine code
  - [ ] 12.1 Delete `src/tools/milvus_client.py` (`MilvusVectorDB`),
    `src/tools/providers/milvus.py`, and the Milvus-backed `MilvusResponseCache`;
    Local Mode L4 = OpenSearch semantic cache.
    - _Requirements: 7.1_
  - [ ] 12.2 Remove Milvus connection settings from `src/config/settings.py` and
    all `MILVUS_*` entries (including the deprecated `vectordb_*` aliases) from
    `.env.example`; keep the `vectordb_*` settings.
    - _Requirements: 7.3_
  - [ ] 12.3 Remove `pymilvus` from project dependencies (`pyproject.toml`,
    `requirements*`), and the `start-milvus.sh/.bat` scripts.
    - _Requirements: 7.1_

- [ ] 13. Document ingestion: OpenSearch + full vectorization parity
  - [ ] 13.1 Rework `document_loaders/` to target OpenSearch via a package-local
    OpenSearch client (source-isolation: no `src/` import); remove the Milvus
    loader client. Preserve capabilities: recursive dir read, `max_chunk_length`
    chunking, batch/parallel Ollama embedding, per-chunk metadata.
    - _Requirements: 7.5, 10.2, 10.4_
  - [ ] 13.2 Index the retained `document_loaders/milvus_docs/` corpus into
    OpenSearch `rag-kb` (KB content kept; engine swapped).
    - _Requirements: 7.5, 10.1_
  - [ ] 13.3 Retain the `data/embeddings.json` snapshot behavior (or a documented
    equivalent).
    - _Requirements: 10.3_
  - [ ] 13.4 Ensure `scripts/ingest_local_opensearch.py` either absorbs or
    delegates to the reworked loader so there is ONE documented ingestion path
    that does both demo-seed and arbitrary-directory vectorization.
    - _Requirements: 10.2_
  - [ ]* 13.5 Test: loader indexes a temp doc dir into a fake OpenSearch with the
    expected chunk/metadata shape; embeddings.json written.
    - _Requirements: 10.2, 10.3_

- [ ] 14. Consolidated Docker stack (`agentcore-rag`)
  - [ ] 14.1 Rewrite `docker/docker-compose.yml` as the single stack: services
    `opensearch`, `redis`, `dynamodb`, `rag-api`, `rag-react`; compose
    `name: agentcore-rag`; container names `agentcore-rag-*`. Remove the Milvus
    services (Milvus/etcd/MinIO) and delete
    `docker/serverless-local/docker-compose.yml` (folded in).
    - _Requirements: 9.1, 9.2_
  - [ ] 14.2 Wire `rag-api`: `DEPLOYMENT_MODE=local` +
    `LOCAL_VECTOR_BACKEND=opensearch` + `OPENSEARCH_LOCAL_HOST/PORT`,
    `depends_on: opensearch`; mount `../api_server.py` to avoid rebuild-on-edit.
    - _Requirements: 9.3, 9.4_
  - [ ] 14.3 Update scripts referencing `docker/serverless-local/...`
    (`run_serverless_local.py`, `serverless_api_server.py`) and `docker/README.md`
    for the consolidated stack.
    - _Requirements: 9.5_
  - [ ] 14.4 `api_server.py` `/health`: OpenSearch probe only; remove the Milvus
    `list_collections` probe.
    - _Requirements: 7.8_

- [ ] 15. Docs + tests scrub
  - [ ] 15.1 Remove/rewrite Milvus-as-engine references in `ARCHITECTURE`,
    `GETTING_STARTED`, `HOW_TO`, `API_SERVER`, README, `docker/README`, and
    tests. Keep references where Milvus is the KB subject matter.
    - _Requirements: 7.6_
  - [ ] 15.2 Repo gate: `grep -ri milvus` excluding `document_loaders/milvus_docs/`,
    `.kiro/specs/`, and historical docs returns no engine references.
    - _Requirements: 7.7_

- [ ] 16. Phase 2 verification
  - [ ] 16.1 ruff + mypy + full unit + serverless suites green; the scoped grep
    gate passes; consolidated `docker compose up -d` healthy; smoke ingest →
    query → answer end-to-end.
    - _Requirements: 7.7, 8.2, 9.6, 10.5_
