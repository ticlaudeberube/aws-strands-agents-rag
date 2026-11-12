# Getting Started

This project supports two active deployment modes, selected by `DEPLOYMENT_MODE` in `.env` and `src/config/settings.py`.

## Deployment modes

- `DEPLOYMENT_MODE=local` — FastAPI + Ollama + vector DB
- `DEPLOYMENT_MODE=serverless` — Lambda + AgentCore + Bedrock + OpenSearch Serverless

## Local quick start

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Set local mode:

```env
DEPLOYMENT_MODE=local
```

3. Start required services:

```bash
cd docker
docker-compose up -d
cd ..
```

4. Start the API:

```bash
uv run python api_server.py
```

5. Verify the app:

```bash
curl http://localhost:8000/health
```

## Serverless quick start

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Set serverless mode:

```env
DEPLOYMENT_MODE=serverless
```

3. Fill in the AWS values required by the current implementation, including:

```env
AWS_REGION=us-west-1
BEDROCK_INFERENCE_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v1
OPENSEARCH_ENDPOINT=https://...
REDIS_ENDPOINT=...
TAVILY_API_KEY=...
```

4. Use the productized serverless entrypoint for your AWS deployment flow.

## Common commands

```bash
# local API
uv run python api_server.py

# local chat
uv run python chatbots/interactive_chat.py

# health check
curl http://localhost:8000/health
```

## Configuration notes

The settings file is the live source of truth for runtime selection:

- `src/config/settings.py`
- `.env.example`

The app does not rely on a legacy `use_agentcore` flag. The supported switch is `DEPLOYMENT_MODE`.

### Local vector backend (OpenSearch)

In local mode the vector store is a local OpenSearch container, matching the
serverless engine for dev/prod parity. Embeddings stay Ollama
(`nomic-embed-text:v1.5`, 768-dim). `LOCAL_VECTOR_BACKEND` selects the local
engine and currently accepts only `opensearch` (the default).

To run Local Mode end-to-end:

```bash
# 1. Start the consolidated local stack (OpenSearch + Redis + DynamoDB):
docker compose -f docker/docker-compose.yml up -d opensearch

# 2. Point the app at it and ingest documents (Ollama embeddings, no AWS):
export DEPLOYMENT_MODE=local
export LOCAL_VECTOR_BACKEND=opensearch
uv run python scripts/ingest_local_opensearch.py --docs ./data/docs

# 3. Run the API server as usual:
uv run python api_server.py
```

The Layer 2/3 cache defaults to in-process (`InMemoryCache`); set
`REDIS_CACHE_ENABLED=true` (with a local Redis on `REDIS_ENDPOINT`, default
`localhost:6379`) to use Redis instead for a fuller prod-parity backend set.

### Hybrid search (BM25 + vector)

Knowledge-base retrieval uses hybrid search by default in both local and
serverless modes. It runs a vector k-NN search and a BM25 lexical search over
chunk text separately, then combines their rankings with weighted Reciprocal
Rank Fusion (RRF). This can improve retrieval for exact terms and rare tokens
such as API names, acronyms, and version numbers. The semantic response-cache
index remains vector-only.

The positive `HYBRID_SEARCH_BM25_WEIGHT` and `HYBRID_SEARCH_VECTOR_WEIGHT`
settings control the relative contribution of each result ranking during RRF;
they are not boosts on OpenSearch scores. Metadata filters, when supplied by a
caller, constrain both searches. The `distance` field remains the raw vector
score for documents returned by k-NN; lexical-only matches have no vector score
and are excluded from the average vector-relevance calculation used for web
fallback. RRF determines result order, not the relevance threshold.

No index migration is needed for existing indexes that already map chunk
`text` as a searchable text field. Configure these values in `.env` (see
`.env.example`), or set `HYBRID_SEARCH_ENABLED=false` to use vector-only
knowledge-base retrieval.

### Bedrock Guardrails (serverless)

The Terraform serverless stack provisions a Bedrock Guardrail, creates an
immutable numbered version, and passes its ID and version to the chat Lambda.
The Lambda execution role receives `bedrock:ApplyGuardrail` scoped to that
Guardrail. Guardrails are active only when `DEPLOYMENT_MODE=serverless` and
both `BEDROCK_GUARDRAIL_ID` and `BEDROCK_GUARDRAIL_VERSION` are configured;
these two settings must be provided together.

The provisioned policy currently:

- Checks prompt attacks on input (`HIGH`) and hate/misconduct on input and
  output (`MEDIUM`).
- Denies the configured `OffTopicGeneralChatter` topic.
- Anonymizes email addresses; blocks US Social Security Numbers, Canadian
  Social Insurance Numbers, and Canadian health numbers.
- Uses contextual grounding and query relevance thresholds of `0.7`.

At entry to the shared RAG router (after the topic and security checks), a
serverless query is screened with `ApplyGuardrail` using source `INPUT` before
semantic-cache lookup. A blocked query returns a refusal without proceeding;
if the Guardrail anonymizes PII, the sanitized query is used for embedding,
cache lookup, and generation. Bedrock Converse also applies the configured
guardrail to model calls.

After RAG generation, the application calls `ApplyGuardrail` with the question
marked as `query`, the answer marked as `guard_content`, and retrieved text
marked as `grounding_source`. The shared router refuses to generate when its
selected sources contain no usable text. If the output check intervenes, the
response is replaced by the Guardrail's output (or a generic refusal). If an
`ApplyGuardrail` call fails or returns an unexpected action, the error is
surfaced rather than silently returning unchecked content. Semantic-cache hits
are input-screened but do not make a Converse call or re-run output/contextual
grounding against their cached answer. Local mode does not invoke Bedrock
Guardrails.

`BEDROCK_GUARDRAIL_TRACE` defaults to `false`. Enable it only for controlled
debugging: Converse trace details can contain sensitive matched text. The
Terraform Lambda environment does not enable trace, so setting this value in
your local `.env` does not change an already-deployed Lambda; configure the
Lambda environment explicitly only if debugging requires it.

PII anonymization affects the response, not the original content sent to
Bedrock. If Bedrock model invocation logging is enabled, review CloudWatch log
encryption, access controls, and retention before processing sensitive or
regulated data.

## What is actually supported

- Local mode uses Ollama and a local OpenSearch container.
- Serverless mode uses Bedrock, OpenSearch, Redis/DynamoDB, and AWS Lambda/AgentCore patterns.
- Web search is optional and controlled by the current Tavily configuration.
- The Strands graph remains the shared business flow: TopicChecker → SecurityChecker → RAGWorker.

### Anti-hallucination tuning

The Layer-3 thresholds (grounding, confidence, web-search fallback, semantic
cache) and the grounding-retry controls are env-overridable — see
`.env.example` and the full table in
[docs/ANTI_HALLUCINATION.md](ANTI_HALLUCINATION.md#configuration).

In **serverless mode** these same thresholds can also be changed at runtime
without a redeploy: set `DYNAMODB_THRESHOLDS_TABLE` and add one row per knob.
The values are read once at Lambda cold start and override the `settings.py`
defaults; any failure (or local mode) falls back to `settings.py`. See
[Runtime tuning without a redeploy](ANTI_HALLUCINATION.md#runtime-tuning-without-a-redeploy-serverless).

See [docs/ARCHITECTURE.md](ARCHITECTURE.md), [docs/API_SERVER.md](API_SERVER.md), and [docs/HOW_TO.md](HOW_TO.md).
