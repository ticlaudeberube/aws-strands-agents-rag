# Implementation Plan: Dual-Mode Deployment (Local Strands + Serverless AWS)

## Overview

This plan converts the dual-mode deployment design into incremental coding steps. The guiding
principle is that **Local Mode must never regress**: the first tasks introduce shared backend
interfaces and the `create_rag_graph` dual-mode factory while keeping the existing Ollama +
Milvus + FastAPI path behaving exactly as before. Only after the shared abstractions and the
factory are in place do we build the serverless backend clients (Bedrock, OpenSearch, Redis),
each fully unit/property-tested in isolation before being wired into the Lambda handler.

Infrastructure (Terraform) is built module-by-module (networking → data → compute → api →
frontend → observability) with `terraform fmt`/`validate`/`plan` checks at each step. Property
tests reference the design's property→test-file mapping table and are tagged
`# Feature: serverless-deployment, Property {N}: ...` using Hypothesis (`max_examples=100`).

Application code is **Python** (per the design: `boto3`, `opensearch-py`, `redis-py`,
`hypothesis`). Infrastructure code is **Terraform HCL**. The Terraform MCP power is available
for provider/module registry lookups while authoring the HCL.

Both modes are validated by a final integration/smoke task.

## Tasks

- [x] 1. Settings and shared backend interfaces (local-preserving foundation)
  - [x] 1.1 Add `deployment_mode` to settings with backward-compatible `use_agentcore` derivation
    - Add `deployment_mode: Literal["local", "serverless"]` (default `"local"`, alias `DEPLOYMENT_MODE`) to `src/config/settings.py`
    - Derive `use_agentcore` from `deployment_mode` (`use_agentcore == (deployment_mode == "serverless")`) so existing config keeps working
    - Add serverless-only settings fields (Bedrock model IDs + `bedrock_model_override`, OpenSearch endpoint/index names, Redis endpoint/TTLs, DynamoDB table names, Secrets Manager keys) with safe defaults
    - Update `.env.example` with the new `DEPLOYMENT_MODE` and serverless variables (keep all local variables intact)
    - _Requirements: 1.2, 5.1, 5.4, 11.2_

  - [ ]* 1.2 Write property test for dual-mode backend selection determinism
    - **Property 33: Deployment mode selects backends deterministically**
    - **Validates: Requirements 1.2, 5.1**
    - File: `tests/test_graph_factory.py` (generate random `Settings` with each `deployment_mode`)

  - [x] 1.3 Define shared backend interfaces/protocols for LLM, vector store, and cache
    - Create `src/tools/interfaces.py` with `Protocol`s: `LLMClient` (`generate`, `embed_text`), `VectorStore` (`knn_search`, `index_document`), `CacheBackend` (`get/set_embedding`, `get/set_search_results`), `SemanticCache` (`search_semantic_cache`, `store_semantic_cache`)
    - Implement `InMemoryCache` (L1/L2/L3 dicts, L2 TTL from `EMBEDDING_CACHE_TTL`) in `src/tools/in_memory_cache.py`, extracting the existing in-process dict behavior from `strands_graph_agent.py`
    - Confirm existing `OllamaClient`, `MilvusVectorDB`, and `MilvusResponseCache` conform to these protocols (adapter shims only if needed; do not change their behavior)
    - _Requirements: 1.2, 3.4_

- [x] 2. Dual-mode factory (`create_rag_graph`) preserving local behavior
  - [x] 2.1 Implement the `create_rag_graph` dual-mode factory
    - Add `create_rag_graph(settings, ollama_client=None, milvus_client=None, bedrock_client=None, opensearch_client=None, redis_cache=None)` to `src/agents/strands_graph_agent.py`
    - Read `settings.deployment_mode` once at construction; for `"local"` wire `OllamaClient` + `MilvusVectorDB` + `InMemoryCache` + `MilvusResponseCache`; for `"serverless"` leave injection points for `BedrockClient` + `OpenSearchClient` + `RedisCache` (constructed in later tasks)
    - Refactor `StrandsGraphRAGAgent` so `TopicChecker`/`SecurityChecker` remain pure/backend-agnostic and `RAGWorker` consumes injected backends through the shared interfaces
    - Keep the default (`deployment_mode="local"`) path byte-for-byte equivalent to current behavior; `api_server.py` continues to construct the local graph
    - _Requirements: 1.2, 2.7, 2.8, 5.1_

  - [ ]* 2.2 Write property tests for the shared graph nodes (early-exit guarantees)
    - **Property 8: TopicChecker always prevents RAGWorker execution for out-of-scope queries**
    - **Property 9: SecurityChecker always prevents RAGWorker execution for injection queries**
    - **Validates: Requirements 2.7, 2.8**
    - File: `tests/test_graph_nodes.py`

  - [ ]* 2.3 Write unit tests for local-mode factory default path
    - `create_rag_graph` with default settings produces an Ollama + Milvus-backed graph; mode read once and stable
    - Local `OllamaClient` uses `qwen2.5:0.5b` (generation) and `nomic-embed-text:v1.5` (embeddings)
    - _Requirements: 1.2, 5.1_

- [ ] 3. Checkpoint - local mode intact
  - Ensure all tests pass and local-mode factory/graph behavior is unchanged, ask the user if questions arise.

- [x] 4. Bedrock LLM/embedding client (serverless)
  - [x] 4.1 Implement `BedrockClient` with generation, embeddings, PCA reduction, and retry
    - Create `src/tools/bedrock_client.py` wrapping `boto3.client("bedrock-runtime")`
    - `generate(prompt, model_id=None, ...)` defaults to `anthropic.claude-3-haiku-20240307-v1:0`, honors `bedrock_model_override`
    - `embed_text` calls `amazon.titan-embed-text-v1` (1536-dim) then applies the deterministic 1536→768 PCA projection (matrix loaded from S3/local artifact)
    - Retry on HTTP 429 up to 3× with exponential backoff starting at 500ms (500/1000/2000ms)
    - Ensure retrieved-context prompt formatting matches the shared prompt template in `src/agents/prompts.py`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 4.2 Write property test for dimensionality reduction
    - **Property 16: Dimensionality reduction always produces 768-dimensional output**
    - **Validates: Requirements 5.3**
    - File: `tests/test_bedrock_client.py` (random 1536-dim float vectors)

  - [ ]* 4.3 Write property test for model ID override
    - **Property 17: Bedrock model ID override is always respected**
    - **Validates: Requirements 5.4**
    - File: `tests/test_bedrock_client.py` (random model ID strings)

  - [ ]* 4.4 Write property test for retry/backoff behavior
    - **Property 18: Bedrock retry on throttling obeys exponential backoff up to 3 attempts**
    - **Validates: Requirements 5.5**
    - File: `tests/test_bedrock_client.py` (429 response sequences N=0..4)

  - [ ]* 4.5 Write property test for prompt context inclusion
    - **Property 19: LLM prompts always include all retrieved document context**
    - **Validates: Requirements 5.6**
    - File: `tests/test_bedrock_client.py` (random document sets)

  - [ ]* 4.6 Write unit tests for Bedrock default models
    - Default inference model is `anthropic.claude-3-haiku-20240307-v1:0`; embedding model is `amazon.titan-embed-text-v1`
    - _Requirements: 5.1, 5.2_

- [x] 5. OpenSearch vector store (serverless)
  - [x] 5.1 Implement `OpenSearchClient` for KB search and semantic cache
    - Create `src/tools/opensearch_client.py` wrapping `opensearch-py` against the OpenSearch Serverless endpoint
    - Implement `knn_search(index, query_vector, k=10)` (HNSW m=30, ef_construction=200, cosine; results sorted non-increasing by score)
    - Implement `index_document`, `search_semantic_cache(threshold=0.92)`, `store_semantic_cache` for the two indexes `rag-kb` and `rag-cache`
    - _Requirements: 4.1, 4.2, 4.3, 4.6, 3.3_

  - [ ]* 5.2 Write property test for KB result ordering
    - **Property 14: Vector search results are always ranked by cosine similarity (descending)**
    - **Validates: Requirements 4.2**
    - File: `tests/test_opensearch_client.py` (random document/query vector collections)

- [x] 6. Redis distributed cache (serverless)
  - [x] 6.1 Implement `RedisCache` for Layer 2/3 with TTLs and health check
    - Create `src/tools/redis_cache.py` wrapping `redis-py` over TLS to the ElastiCache endpoint
    - `set_embedding` TTL 3600s, `set_search_results` TTL 86400s; keys use SHA-256 of normalized question (`emb:{hash}`, `srch:{hash}:{top_k}`); payloads msgpack-serialized
    - Implement `ping()` and the soft circuit-breaker flag (`redis_available=False` for the warm context on ping failure)
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6_

  - [ ]* 6.2 Write property test for cache TTLs
    - **Property 10: Cache write operations always set correct TTLs**
    - **Validates: Requirements 3.1, 3.2**
    - File: `tests/test_redis_cache.py` (random vectors and result payloads)

  - [ ]* 6.3 Write property test for embedding round-trip
    - **Property 11: Embedding cache round-trip preserves the vector**
    - **Validates: Requirements 3.4**
    - File: `tests/test_redis_cache.py` (random float vectors, msgpack round-trip)

  - [ ]* 6.4 Write property test for search-result cache threshold
    - **Property 12: Search result cache threshold is enforced** (L2 distance ≤ 0.05)
    - **Validates: Requirements 3.5**
    - File: `tests/test_redis_cache.py` (embedding pairs at varying L2 distances)

- [x] 7. Checkpoint - serverless backend clients
  - Ensure all backend-client tests pass, ask the user if questions arise.

- [x] 8. Wire serverless backends into the factory and routing
  - [x] 8.1 Complete serverless branch of `create_rag_graph` and shared routing
    - In `create_rag_graph`, construct/inject `BedrockClient` + `OpenSearchClient` + `RedisCache` (OpenSearch `rag-cache` as L4 semantic cache) for `deployment_mode == "serverless"`
    - Ensure the shared RAGWorker routing (Cache → KB → Web Search) honors the 0.92 semantic threshold, temporal-keyword bypass, 0.15 web-search fallback, `force_web_search`, empty-answer fallback, and graceful degradation on Redis/OpenSearch unavailability (emitting `cache/redis_unavailable` / `cache/opensearch_unavailable`)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.6, 3.7_

  - [ ]* 8.2 Write property test for cache-hit short-circuit
    - **Property 4: Cache hit at similarity ≥ 0.92 never calls the LLM backend**
    - **Validates: Requirements 2.2**
    - File: `tests/test_routing.py` (cosine similarities around 0.92)

  - [ ]* 8.3 Write property test for temporal keyword bypass
    - **Property 5: Temporal keyword queries always bypass cache**
    - **Validates: Requirements 2.3**
    - File: `tests/test_routing.py`

  - [ ]* 8.4 Write property test for low-relevance web-search fallback
    - **Property 6: Low-relevance KB results trigger web search fallback**
    - **Validates: Requirements 2.4**
    - File: `tests/test_routing.py` (random relevance score sets)

  - [ ]* 8.5 Write property test for force_web_search bypass
    - **Property 7: force_web_search always bypasses cache and KB**
    - **Validates: Requirements 2.6**
    - File: `tests/test_routing.py`

  - [ ]* 8.6 Write property test for graceful degradation
    - **Property 13: Cache layer unavailability causes graceful degradation**
    - **Validates: Requirements 3.6, 3.7**
    - File: `tests/test_routing.py` (mocked unavailable services)

- [x] 9. Tavily web search adaptation (serverless)
  - [x] 9.1 Adapt Tavily client for Lambda (Secrets Manager key, timeout, unavailable flag)
    - Update `src/tools/web_search.py` to load the Tavily API key from Secrets Manager at cold start and cache it for the warm invocation
    - Enforce a 10s call budget; on no results/timeout return best KB answer with `web_search_unavailable=true`; pass `WEB_SEARCH_FALLBACK_THRESHOLD=0.15`
    - Ensure returned `sources` include non-empty `url` and `timestamp` matching the shared response schema
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 9.2 Write property tests for Tavily failure flag and source fields
    - **Property 29: Tavily failure always sets web_search_unavailable flag**
    - **Property 30: Web search results always include sources with URL and timestamp**
    - **Validates: Requirements 10.3, 10.5**
    - File: `tests/test_routing.py` (random queries + Tavily mocked, random result sets)

- [x] 10. Lambda chat handler (`agentcore_handler.py`)
  - [x] 10.1 Implement request parsing, validation, and `top_k` guard
    - Replace the stub in `src/agents/agentcore_handler.py`: parse body extracting `question`, `session_id`, optional `force_web_search`, optional `top_k`
    - Return HTTP 400 for malformed JSON (`BAD_REQUEST`), missing `question` (`MISSING_FIELD`), and `top_k` outside [1,50] (`INVALID_TOP_K`) before invoking any agent node
    - _Requirements: 1.1, 4.4_

  - [ ]* 10.2 Write property tests for parsing and top_k validation
    - **Property 1: Request body parsing is total and correct**
    - **Property 15: top_k validation is exhaustive over the integer domain**
    - **Validates: Requirements 1.1, 4.4**
    - File: `tests/test_handler_parsing.py`

  - [x] 10.3 Implement DynamoDB session load/persist and graph invocation
    - Add a `DynamoDBClient` helper (session + analytics tables); load history via `query(session_id, ScanIndexForward=True, Limit=20)`; invoke the serverless graph via `create_rag_graph`
    - Persist Q/A to the session table with `ttl = floor(now) + 86400`; degrade gracefully on read/write failures per the error table
    - _Requirements: 1.3, 1.4_

  - [ ]* 10.4 Write property test for session persistence TTL
    - **Property 2: Session persistence always writes with correct TTL**
    - **Validates: Requirements 1.4**
    - File: `tests/test_handler_session.py` (random Q/A strings, timestamps)

  - [x] 10.5 Implement structured error handling and HTTP 500 envelope
    - Catch unhandled exceptions, log full stack trace, emit `errors/total`, return HTTP 500 with `{error_code, message}`
    - Map documented conditions (`LLM_ERROR`, `INTERNAL_ERROR`, etc.) per the error-handling table
    - _Requirements: 1.5, 6.6_

  - [ ]* 10.6 Write property test for error response format
    - **Property 3: Unhandled exceptions always produce structured HTTP 500**
    - **Validates: Requirements 1.5**
    - File: `tests/test_handler_errors.py` (random exception types/messages)

  - [x] 10.7 Implement structured JSON logging and custom CloudWatch metrics
    - Emit log fields `request_id`, `session_id`, `tier_used`, `latency_ms`, `cache_hit`, `error_code`, and `cold_start=true` on cold start
    - Emit metrics `cache/hit_rate`, `cache/miss_rate`, `rag/latency_p50`, `rag/latency_p99`, `websearch/invocation_count`, `errors/total`; enable X-Ray tracing hooks
    - _Requirements: 12.1, 12.2, 12.5_

  - [ ]* 10.8 Write property test for log field completeness
    - **Property 32: Structured log entries always contain all required fields**
    - **Validates: Requirements 12.1, 12.5**
    - File: `tests/test_handler_logging.py` (random cold/warm, success/error invocations)

- [x] 11. Checkpoint - serverless handler end-to-end (mocked backends)
  - Ensure all handler and routing tests pass, ask the user if questions arise.

- [x] 12. Document indexing pipeline Lambda
  - [x] 12.1 Implement shared chunking and the indexing handler
    - Ensure the shared chunking function enforces ≤ 400-token chunks (used by local loaders and the pipeline)
    - Create `src/indexing/indexing_handler.py`: S3 `ObjectCreated` handler that downloads, chunks, embeds via `BedrockClient`, indexes into `rag-kb`, and records `{doc_key, s3_uri, chunk_count, indexed_at}` in the analytics table
    - Implement idempotent skip on matching `(key, etag)` with `indexing/document_skipped` log and `indexing/skip_enforcement_failure` defect metric
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 12.2 Write property test for chunk size bound
    - **Property 26: Document chunking never produces chunks exceeding 400 tokens**
    - **Validates: Requirements 9.2**
    - File: `tests/test_indexing.py` (random text documents)

  - [ ]* 12.3 Write property test for indexing idempotency
    - **Property 27: Indexing pipeline is idempotent on (key, ETag) pairs**
    - **Validates: Requirements 9.4**
    - File: `tests/test_indexing.py` (random documents, run twice)

  - [ ]* 12.4 Write property test for analytics record completeness
    - **Property 28: Indexing pipeline always records all required DynamoDB fields**
    - **Validates: Requirements 9.5**
    - File: `tests/test_indexing.py` (random document metadata)

- [ ] 13. Terraform networking module (base infrastructure)
  - [ ] 13.1 Scaffold root module and networking child module
    - Create `infrastructure/terraform/` root (`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `backend.tf`) with `required_version >= 1.6.0`, aws provider pinned `~> 5.60`, and S3+DynamoDB remote state/lock in `backend.tf`
    - Add `environments/{dev,staging,prod}.tfvars` with stage/model/node-type/capacity variables
    - Create `modules/networking/`: VPC, private subnets, VPC endpoints (OpenSearch Serverless, Bedrock, S3, DynamoDB, Secrets Manager), security groups (use the registry VPC module, pinned; use the Terraform MCP power for provider/module lookups)
    - Verify with `terraform fmt -check`, `terraform validate`, and `terraform plan -var-file=environments/dev.tfvars`
    - _Requirements: 11.1, 11.2, 11.7, 11.8_

- [ ] 14. Terraform data module (DynamoDB, OpenSearch, Redis)
  - [ ] 14.1 Implement the data child module
    - Create `modules/data/`: two `aws_dynamodb_table` (PAY_PER_REQUEST, TTL on `ttl`), `aws_opensearchserverless_collection` (`rag-vectors`, VECTORSEARCH) with encryption/network/data-access policies and separate `rag-kb`/`rag-cache` indexes (768-dim, cosine, HNSW m=30/ef_construction=200, no public access), and `aws_elasticache_replication_group` (Redis, TLS) in private subnets
    - Verify with `terraform fmt -check`, `terraform validate`, `terraform plan -var-file=environments/dev.tfvars`
    - _Requirements: 4.1, 4.3, 4.5, 4.6, 3.3, 11.1, 11.6_

- [ ] 15. Terraform compute module (Lambda + IAM)
  - [ ] 15.1 Implement the compute child module
    - Create `modules/compute/`: `aws_lambda_function` for the chat handler (`agentcore_handler.lambda_handler`) and indexing handler (`indexing_handler.lambda_handler`) with VPC config attached to networking private subnets; least-privilege `aws_iam_role`/`aws_iam_policy`
    - Restrict IAM actions to the permitted set only (no `*`): Bedrock InvokeModel, DynamoDB CRUD+Query, ElastiCache Connect, `aoss:APIAccessAll`, S3 GetObject/ListBucket, Secrets Manager GetSecretValue; add Secrets Manager secrets referenced by the role; wire S3 `ObjectCreated` trigger for the indexing Lambda
    - Verify with `terraform fmt -check`, `terraform validate`, `terraform plan -var-file=environments/dev.tfvars`
    - _Requirements: 11.1, 11.4, 11.5, 9.1_

  - [ ]* 15.2 Write property test for IAM policy scope
    - **Property 31: Lambda IAM role contains only permitted actions**
    - **Validates: Requirements 11.5**
    - File: `tests/test_iam_policy.py` (parse Terraform IAM HCL / `terraform plan` JSON, enumerate actions)

- [ ] 16. Terraform api module (API Gateway + Cognito + WAF)
  - [ ] 16.1 Implement the api child module
    - Create `modules/api/`: `POST /chat` (Lambda proxy) and `GET /health` (static 200 `{"status":"healthy"}`), Cognito user pool + client with JWT authorizer on `/chat`, password policy (≥12, upper, digit, special), 1-hour token expiry, CORS for the CloudFront origin (`Content-Type`, `Authorization`), and `aws_wafv2_web_acl` rate limit 100 rps → 429
    - Verify with `terraform fmt -check`, `terraform validate`, `terraform plan -var-file=environments/dev.tfvars`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3_

  - [ ]* 16.2 Write property tests for auth (JWT rejection + password policy)
    - **Property 20: Unauthenticated /chat requests are always rejected with HTTP 401**
    - **Property 22: Password policy validation is correct for all password strings**
    - **Validates: Requirements 6.3, 7.1**
    - File: `tests/test_auth.py` (random token strings; random password strings)

  - [ ]* 16.3 Write property test for API Gateway error passthrough
    - **Property 21: API Gateway always propagates Lambda error responses unchanged**
    - **Validates: Requirements 6.6**
    - File: `tests/test_auth.py` (or `tests/test_api_gateway.py`) — random error bodies and 4xx/5xx codes

- [ ] 17. Terraform frontend module and React serverless build
  - [ ] 17.1 Implement the frontend child module
    - Create `modules/frontend/`: versioned/SSE `aws_s3_bucket` (documents + `/frontend/`) and `aws_cloudfront_distribution` (HTTPS-only redirect, default TTL 86400s, `no-store` for `index.html`, SPA fallback to `index.html` for non-asset paths)
    - Verify with `terraform fmt -check`, `terraform validate`, `terraform plan -var-file=environments/dev.tfvars`
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [ ] 17.2 Add Cognito auth and API URL injection to the React frontend
    - In `chatbots/react-chatbot/`: add Amplify Auth / Cognito Hosted UI sign-in, hold JWT in memory (not localStorage), auto-refresh via refresh token and redirect to sign-in when invalid
    - Read API base URL from build-time `REACT_APP_API_URL`; remove hardcoded localhost from serverless builds; keep local-mode `REACT_APP_API_HOST`/`REACT_APP_API_PORT` behavior for dev
    - _Requirements: 7.4, 7.5, 8.4_

  - [ ]* 17.3 Write property tests for CloudFront headers, SPA routing, and build cleanliness
    - **Property 23: CloudFront cache headers are correct for every asset type** → `tests/test_cloudfront.py`
    - **Property 25: SPA routing always returns index.html for non-asset paths** → `tests/test_cloudfront.py`
    - **Property 24: React build artifacts never contain localhost references** → `tests/test_frontend_build.py`
    - **Validates: Requirements 8.3, 8.4, 8.5**

- [ ] 18. Terraform observability module
  - [ ] 18.1 Implement the observability child module
    - Create `modules/observability/`: `aws_cloudwatch_log_group` per Lambda, `aws_cloudwatch_metric_alarm` for `errors/total > 10` in 5 minutes, and X-Ray active tracing enabled on both Lambda functions
    - Compose all child modules in root `main.tf`; verify full-stack `terraform fmt -check`, `terraform validate`, `terraform plan -var-file=environments/dev.tfvars`
    - _Requirements: 12.3, 12.4, 11.1_

- [ ] 19. Final integration and dual-mode smoke validation
  - [ ] 19.1 Wire everything together and add dual-mode integration/smoke tests
    - Confirm `api_server.py` (local) and `agentcore_handler.lambda_handler` (serverless) both construct the graph via `create_rag_graph` with no orphaned code
    - Serverless smoke (against `terraform plan` JSON / mocks or LocalStack): required resource types present, remote state backend configured, provider versions pinned, Lambda VPC config present, DynamoDB PAY_PER_REQUEST+TTL, OpenSearch cosine/768-dim/HNSW m=30+ef_construction=200 with separate rag-kb/rag-cache and no public endpoint, CloudFront HTTPS, `/frontend/` assets, CloudWatch alarm, X-Ray enabled, CORS on `/chat`, default models correct
    - Local integration (Docker Compose + Ollama): `POST /v1/chat/completions` returns an answer with sources; `response_cache` warm-up loads when `ENABLE_CACHE_WARMUP=true`; React dev server reaches FastAPI
    - _Requirements: 1.2, 6.2, 11.1, 11.3, 11.4, 11.6, 11.7, 11.8, 4.1, 4.3, 4.5, 4.6, 8.1, 8.2, 12.3, 12.4_

  - [ ]* 19.2 Write/execute integration smoke tests for both modes
    - Serverless integration: S3 upload → indexing Lambda triggered; Cognito sign-in → 1h JWT; Tavily within 10s; Secrets Manager once per cold start; metrics appear; rate limit → 429
    - Local integration: full Docker Compose + Ollama end-to-end chat
    - _Requirements: 9.1, 7.2, 10.1, 10.2, 12.2, 6.4_

- [ ] 20. Final checkpoint - both modes validated
  - Ensure all tests pass and both local and serverless modes are validated, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Local Mode is preserved first (tasks 1–3) before any cloud backend is introduced; the default `deployment_mode="local"` path must not regress.
- Each serverless backend client (Bedrock, OpenSearch, Redis) is built and tested in isolation (tasks 4–7) before being wired into the handler (tasks 8–11).
- Terraform modules are built incrementally with `fmt`/`validate`/`plan` checks: networking (13) → data (14) → compute (15) → api (16) → frontend (17) → observability (18). Use the Terraform MCP power for registry provider/module lookups while authoring HCL.
- Property-based tests use Hypothesis (`max_examples=100`) and are tagged `# Feature: serverless-deployment, Property {N}: ...`; each test sub-task references the design's property→test-file mapping table.
- All 33 design properties are covered: P1,P15 (10.2); P2 (10.4); P3 (10.6); P4–P7,P13 (8.2–8.6); P8,P9 (2.2); P10–P12 (6.2–6.4); P14 (5.2); P16–P19 (4.2–4.5); P20,P22 (16.2); P21 (16.3); P23–P25 (17.3); P26–P28 (12.2–12.4); P29,P30 (9.2); P31 (15.2); P32 (10.8); P33 (1.2).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "2.1", "4.1", "5.1", "6.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.2", "4.3", "4.4", "4.5", "4.6", "5.2", "6.2", "6.3", "6.4"] },
    { "id": 3, "tasks": ["8.1", "9.1"] },
    { "id": 4, "tasks": ["8.2", "8.3", "8.4", "8.5", "8.6", "9.2", "10.1"] },
    { "id": 5, "tasks": ["10.2", "10.3", "10.5", "10.7", "12.1"] },
    { "id": 6, "tasks": ["10.4", "10.6", "10.8", "12.2", "12.3", "12.4", "13.1"] },
    { "id": 7, "tasks": ["14.1"] },
    { "id": 8, "tasks": ["15.1", "16.1", "17.1", "17.2"] },
    { "id": 9, "tasks": ["15.2", "16.2", "16.3", "17.3", "18.1"] },
    { "id": 10, "tasks": ["19.1"] },
    { "id": 11, "tasks": ["19.2"] }
  ]
}
```
