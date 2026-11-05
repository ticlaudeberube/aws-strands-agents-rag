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
