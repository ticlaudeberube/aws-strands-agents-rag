# Running Serverless Mode locally

This guide runs the **serverless** deployment mode (the Lambda code path:
Bedrock + OpenSearch + Redis) on a developer machine, **without deploying
anything to AWS**. It is the closest you can get to the cloud instance locally.

What runs where:

| Component | Serverless (cloud) | This local setup |
|-----------|--------------------|------------------|
| LLM + embeddings | Amazon Bedrock | **Real Bedrock** (there is no local Bedrock) |
| Vector store + L4 cache | OpenSearch Serverless (`rag-kb` / `rag-cache`) | Local **OpenSearch** container |
| L2/L3 cache | ElastiCache Redis | Local **Redis** container |
| Session store | DynamoDB | Local **DynamoDB Local** container |
| Compute | Lambda + API Gateway | Local FastAPI (`scripts/serverless_api_server.py`) or the real handler via `scripts/run_lambda_handler_local.py` |

> Bedrock is the one piece that is always real. Every chat message makes live
> Bedrock calls (cents per message). The OpenSearch/Redis containers are local
> and free.

---

## Why a wrapper instead of `api_server.py` / `sam local`

- **`sam local invoke --hook-name terraform`** can't run this stack: the SAM
  Terraform hook needs a clean `terraform plan`, but the compute module has a
  `count` that depends on an apply-time output, so planning fails. SAM's own
  workaround is "run `terraform apply` first" — i.e. deploy real infra. Not local.
- **`api_server.py` directly** is hardwired for Local Mode: its agent class
  (`StrandsGraphRAGAgent`) always builds Ollama + Milvus and only injects the
  Milvus backend into `create_rag_graph`. It has no path to inject the
  serverless Bedrock/OpenSearch/Redis clients.
- The production serverless clients also assume the cloud: `OpenSearchClient`
  hardcodes TLS + SigV4 (`aoss`) on port 443, and `RedisCache` hardcodes
  `ssl=True`. Neither can point at a plain local container through settings.

So the local serverless path is driven by two **wrapper scripts** that inject
local-pointed clients into the real `create_rag_graph` / `shared_route`. They do
**not** modify `api_server.py` or anything in `src/`.

The one production change that *was* made (approved separately) is migrating
`src/tools/bedrock_client.py` to the Bedrock **Converse** API, so generation
works across Claude, Nova, and Llama with no per-provider body code.

---

## Prerequisites

1. **Docker** running (`docker ps`).
2. **AWS credentials** for the account with Bedrock access, in the project
   Region. This guide uses account `996428372683` in `us-east-1`.
3. **Bedrock model access**. The project's historical default
   `anthropic.claude-3-haiku-20240307-v1:0` is **end-of-life** and no longer
   invokable. Two options:
   - **Amazon Nova** (default here): `amazon.nova-lite-v1:0`. No extra access
     form; works immediately via Converse.
   - **Anthropic Claude**: requires a one-time **Anthropic use-case (First Time
     Use) form** per account, submitted from the redesigned Bedrock console
     model catalog (the old "Model access" page is retired). Once cleared, set
     `BEDROCK_MODEL_OVERRIDE=us.anthropic.claude-haiku-4-5-20251001-v1:0` and
     restart — no code change needed.
   The embedding model `amazon.titan-embed-text-v1` is used in both cases.
4. **Python serverless deps** in the venv: `redis` and `msgpack`
   (`opensearch-py` is already present). Install with:
   ```bash
   .venv/bin/pip install 'redis>=5.0.0' 'msgpack>=1.0.0'
   ```

---

## Step 1 — Start the local backing services

```bash
docker compose -f docker/serverless-local/docker-compose.yml up -d
```

This starts:
- `rag-serverless-opensearch` on `localhost:9200` (security plugin disabled, so
  the wrapper connects over plain HTTP, no SigV4/TLS).
- `rag-serverless-redis` on `localhost:6379` (plain TCP, no TLS).
- `rag-serverless-dynamodb` on `localhost:8001` (DynamoDB Local, in-memory;
  stand-in for the serverless session + analytics tables).

Ports are chosen to avoid colliding with the Local-Mode Milvus stack
(19530/9091/9000/9001), so both can run at once. Verify:

```bash
curl -s http://localhost:9200/_cluster/health
docker exec rag-serverless-redis redis-cli ping   # -> PONG
curl -s http://localhost:8001/ -o /dev/null -w "dynamodb: %{http_code}\n"
```

---

## Step 2 — Configuration

The wrapper scripts auto-load [`.env.serverless-local`](../.env.serverless-local)
from the repo root. Key values:

```env
DEPLOYMENT_MODE=serverless
AWS_REGION=us-east-1
BEDROCK_MODEL_OVERRIDE=amazon.nova-lite-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v1
OPENSEARCH_LOCAL_HOST=localhost
OPENSEARCH_LOCAL_PORT=9200
REDIS_ENDPOINT=localhost:6379
```

---

## Step 3 — Option A: CLI (one-shot question)

Fastest way to confirm the pipeline end-to-end:

```bash
.venv/bin/python scripts/run_serverless_local.py "What is a vector database and how does HNSW indexing help RAG?"
```

The runner builds the injected backends, ensures the `rag-kb` / `rag-cache`
indexes exist, seeds a couple of KB documents, then runs the question through
`shared_route` (the exact Lambda path) and prints the answer, tier, and sources.

---

## Step 3 — Option B: the GUI (FastAPI + React)

### 3.1 Start the serverless API server

```bash
.venv/bin/python scripts/serverless_api_server.py
```

This reuses the existing OpenAI-compatible FastAPI `app` and swaps in a
serverless-backed agent shim. It listens on `http://localhost:8000`.

> If startup fails with `address already in use`, a stale Local-Mode
> `api_server.py` is holding port 8000. Find and stop it:
> `lsof -nP -iTCP:8000 -sTCP:LISTEN` then `kill <pid>`.

Verify it reports the serverless backends:

```bash
curl -s http://localhost:8000/health
# -> {"status":"ok","deployment_mode":"serverless","vector_db":"http://localhost:9200",
#     "vector_db_available":true,"redis_available":true,"bedrock_model":"amazon.nova-lite-v1:0",...}
```

### 3.2 Start the React chatbot

```bash
cd chatbots/react-chatbot
npm install        # first time only
BROWSER=none npm start
```

Its `.env` already defaults to `localhost:8000` with no auth, so it talks to the
local serverless API. Open **http://localhost:3000** and chat. Ask
vector-DB/RAG questions (that's what the KB is seeded with).

Request flow per message:

```
React UI (:3000)
  -> POST /v1/chat/completions  (serverless API :8000)
     -> shared_route            (real Lambda code path)
        -> Bedrock Titan embeddings + Nova generation   (real AWS)
        -> OpenSearch k-NN retrieval                    (local :9200)
        -> Redis L2/L3 cache                            (local :6379)
```

---

## Step 3 — Option C: the REAL Lambda handler (end-to-end validation)

To validate the actual production entry point — `agentcore_handler.lambda_handler`
— rather than the GUI shim, run:

```bash
.venv/bin/python scripts/run_lambda_handler_local.py "What is a vector database?"
```

This pre-seeds the handler's warm caches with the injected local backends
(OpenSearch/Redis/DynamoDB + real Bedrock) and invokes `lambda_handler` with an
API Gateway v2 proxy event. It exercises full handler behavior the shim does
not: request validation, **DynamoDB session history load + persist across two
turns**, the serverless response envelope, and the HTTP 400 validation path. It
prints a `✅ PASS` / `❌ FAIL` result.

This is the authoritative check that the production handler (including DynamoDB
session persistence) works end-to-end, backed only by local containers + real
Bedrock.

## The "vector database unavailable" warning (fixed)

**Symptom:** the GUI showed *"The vector database is unavailable. Knowledge-base
search and persistent cached questions are unavailable."* even though chat
answers returned real sources.

**Cause:** the stock `/health` endpoint in `api_server.py` is Local-Mode only.
It probes `agent.vector_db.client.list_collections(db_name=milvus_db_name, ...)`
— a **Milvus-specific** call. The serverless shim has no `vector_db` attribute
(it uses OpenSearch), so the probe was skipped and health always reported
`vector_db_available: false` against the Milvus endpoint. Retrieval was never
actually broken; only the health check was wrong.

**Fix (local-only):** `scripts/serverless_api_server.py` overrides the `/health`
route with a serverless-aware version that pings the local **OpenSearch** and
**Redis** backends and reports `deployment_mode: serverless`,
`vector_db: http://localhost:9200`, and `vector_db_available: true` when
OpenSearch responds. This lives entirely in the wrapper — `api_server.py` and
`src/` are untouched, so Local Mode behaviour is unchanged.

---

## Switching to Claude later

Once the Anthropic FTU form is approved for the account, edit
`.env.serverless-local`:

```env
BEDROCK_MODEL_OVERRIDE=us.anthropic.claude-haiku-4-5-20251001-v1:0
```

and restart the API server. No code change — the Converse migration already
makes the client model-agnostic.

---

## Known limitations (local only)

- **Streaming is single-chunk, not token-by-token.** The GUI sends
  `stream: true`, but `BedrockClient.generate()` uses the synchronous Bedrock
  `converse` API, so the serverless shim runs `shared_route` once and yields the
  full answer as a single SSE chunk (followed by the sources trailer). The
  answer and sources render correctly; you just won't see the incremental
  typewriter effect. See TODO below for true streaming.
- **Web search is enabled** via `ENABLE_WEB_SEARCH_SUPPLEMENT=true` +
  `TAVILY_API_KEY` in `.env.serverless-local`. In serverless mode the key would
  normally come from Secrets Manager (`SECRETS_TAVILY_API_KEY`); we leave that
  unset so the resolver falls back to the env-var key — no Secrets Manager
  needed locally. Both the normal path (web supplementation for time-sensitive /
  low-confidence queries) and the GUI's force-web-search toggle work.
- **Seeded KB is tiny** (2 docs, created by the wrapper for demonstration). Ask
  RAG/vector-DB questions, or extend `_SEED_DOCS` in
  `scripts/run_serverless_local.py` to index your own content.
- **No Cognito/JWT auth** locally — the cloud API Gateway enforces it; the local
  FastAPI does not.

---

## Teardown

```bash
# stop the servers (Ctrl+C in their terminals), then the containers:
docker compose -f docker/serverless-local/docker-compose.yml down
```

To also drop the local index data, add `-v` to remove volumes (there are none
persisted by default in this compose file).

---

## What the serverless shim does — and does not — implement

`scripts/serverless_api_server.py` defines `ServerlessAgentShim`, a **local-only
GUI test harness** (not production code). The real serverless entry point is the
Lambda handler `agentcore_handler.lambda_handler`, which is separate and more
complete.

**Implemented** (routes answering through the real serverless `shared_route`):

| GUI feature | Shim member | Backing |
|---|---|---|
| Non-stream chat | `answer_question` | `shared_route` |
| Non-stream, bypass cache | `answer_question_no_cache` | `shared_route` |
| Streaming chat (default) | `stream_answer` | `shared_route` (single chunk) |
| Streaming, bypass cache | `stream_answer_no_cache` | `shared_route` |
| Force web search | `stream_answer_web_search_only` | Tavily + Bedrock |
| Health status | `opensearch_healthy` / `redis_healthy` + `/health` override | local containers |
| Questions sidebar | `response_cache.vector_db.list_all_cached_questions` | OpenSearch `rag-cache` |
| Click a question | `response_cache.vector_db.client.query` | OpenSearch `rag-cache` |
| Common questions | `api_server.common_questions` loaded in `main()` | static JSON |

**Not implemented / approximated:**

- **No token-by-token streaming** — the full answer is yielded as one chunk
  (Bedrock `converse`, not `converse_stream`).
- **`answer_question_no_cache` doesn't truly bypass the cache** — it reuses
  `shared_route`, which still consults the semantic cache.
- **Non-stream force-web / bypass-cache chat paths** aren't backed (the GUI uses
  streaming, so these aren't exercised).
- **No multi-turn context fed to the model** — session history is loaded and
  persisted to DynamoDB (see below), but the loaded history is not yet injected
  into the prompt; each `shared_route` call answers from the current question +
  KB only. (The real Lambda has the same characteristic — it loads history for
  persistence/observability but the shared route is single-turn.)
- **DynamoDB session persistence IS wired** — the shim builds a local
  `DynamoDBClient` and, when a `session_id` is supplied, loads history before
  and persists the Q/A turn after answering, matching the Lambda. Note the GUI's
  chat handler does not pass a `session_id`, so persistence is exercised by the
  Lambda-handler harness (below) rather than the browser.
- **MCP endpoints, `/health/detailed`, cache stats, competitor-query handling**
  — not implemented; those endpoints return empty or error if called.

For the full list of what separates this local setup from a real AWS deploy, see
[AWS_DEPLOYMENT_GAPS.md](./AWS_DEPLOYMENT_GAPS.md).

## TODO / future enhancements

- **True token streaming.** Replace the single-chunk SSE behavior with real
  token-by-token streaming by having `BedrockClient` use the Bedrock
  `converse_stream` API and having the serverless shim's `stream_answer` /
  `stream_answer_no_cache` yield those deltas as they arrive. This is a larger
  change to `src/tools/bedrock_client.py` (and the shared routing, which
  currently returns a finished `RoutingResult`), so it is deferred.
- **Richer seed KB** or a loader so retrieval reflects real content instead of
  the two demonstration documents.

## Cached questions list (GUI sidebar)

The GUI's "answered questions" sidebar works in serverless-local. Questions and
their stored answers come from the OpenSearch `rag-cache` index (the serverless
L4 semantic cache), surfaced through two endpoints:

- `GET /v1/cache/questions` — lists cached questions.
- `GET /v1/cache/responses/{id}` — returns a specific cached answer + sources.

Both are Milvus-oriented in `api_server.py`; the serverless shim adapts them to
OpenSearch via a small `response_cache` adapter (no `api_server.py` / `src/`
changes). Entries only appear **after** a question has been asked (each answer
is written to `rag-cache`).

## Files involved

| Path | Purpose |
|------|---------|
| `docker/serverless-local/docker-compose.yml` | Local OpenSearch + Redis |
| `.env.serverless-local` | Serverless-local configuration |
| `scripts/run_serverless_local.py` | CLI runner (injects local backends into `shared_route`); also holds the shared local-backend builders (OpenSearch/Redis/DynamoDB) |
| `scripts/serverless_api_server.py` | GUI server (serverless agent shim + serverless `/health`) |
| `scripts/run_lambda_handler_local.py` | Invokes the REAL `agentcore_handler.lambda_handler` end-to-end with local backends (validates DynamoDB session persistence) |
| `src/tools/bedrock_client.py` | Converse-API client (model-agnostic; the one production change) |
