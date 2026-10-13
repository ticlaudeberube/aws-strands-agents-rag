# How to use this project

This project is a dual-mode RAG application. The codebase supports both a local developer workflow and an AWS serverless deployment workflow.

## 1. Choose your mode

The mode is selected by `DEPLOYMENT_MODE` in `.env` and enforced by `src/config/settings.py`.

```env
DEPLOYMENT_MODE=local
# or
DEPLOYMENT_MODE=serverless
```

### Local mode

Use this when you want to run the app on a laptop or dev machine.

- `FastAPI` app via `api_server.py`
- `Ollama` for LLM and embeddings
- A vector DB for document search (the current local provider is Milvus)
- Docker Compose for the current local vector DB service

### Serverless mode

Use this when you want the AWS production path.

- `Lambda` / `AgentCore` execution pattern
- `Bedrock` for inference and embeddings
- `OpenSearch Serverless` for vector search
- `Redis` / `DynamoDB` for cache and session support

## 2. Local setup

1. Create your local config:

```bash
cp .env.example .env
```

2. Set local mode:

```env
DEPLOYMENT_MODE=local
```

3. Start the local vector DB stack:

```bash
cd docker
docker-compose up -d
cd ..
```

4. Start the API:

```bash
python api_server.py
```

5. Check the app health endpoint:

```bash
curl http://localhost:8000/health
```

## 3. Serverless setup

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Set serverless mode:

```env
DEPLOYMENT_MODE=serverless
```

3. Add the required AWS values in `.env`, including at minimum:

```env
AWS_REGION=us-west-1
BEDROCK_INFERENCE_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v1
OPENSEARCH_ENDPOINT=https://...
REDIS_ENDPOINT=...
TAVILY_API_KEY=...
```

4. Use the serverless deployment flow already implemented in the repo for Lambda/AgentCore operation.

## 4. Common commands

```bash
# local API
python api_server.py

# local chat UI
python chatbots/interactive_chat.py

# local health check
curl http://localhost:8000/health
```

## 5. Actual runtime flow

The app uses the same core Strands pattern in both modes:

```text
User query
  -> TopicChecker
  -> SecurityChecker
  -> RAGWorker
     -> retrieval backend
     -> answer generation
     -> source output
```

This is the live architecture implemented in the current codebase.

## 6. What to trust

The verified source of truth is:

- `.env.example`
- `src/config/settings.py`
- `api_server.py`
- `src/agents/strands_graph_agent.py`

Use these files as the authoritative reference. Do not rely on older historical docs that describe a previous single-mode or deprecated implementation.

## 7. Useful validation checks

- Confirm `DEPLOYMENT_MODE` matches your intended environment.
- Confirm the app boots with `python api_server.py`.
- Confirm `curl http://localhost:8000/health` returns the server status.
- Confirm local mode has Ollama and its configured vector DB available.
- Confirm serverless mode has AWS and OpenSearch settings configured.

This keeps the documentation grounded in real runtime behavior instead of legacy design notes.
