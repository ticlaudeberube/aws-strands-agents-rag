# Getting Started

This project supports two active deployment modes, selected by `DEPLOYMENT_MODE` in `.env` and `src/config/settings.py`.

## Deployment modes

- `DEPLOYMENT_MODE=local` — FastAPI + Ollama + Milvus
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
python api_server.py
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
python api_server.py

# local chat
python chatbots/interactive_chat.py

# health check
curl http://localhost:8000/health
```

## Configuration notes

The settings file is the live source of truth for runtime selection:

- `src/config/settings.py`
- `.env.example`

The app does not rely on a legacy `use_agentcore` flag. The supported switch is `DEPLOYMENT_MODE`.

## What is actually supported

- Local mode uses Ollama and Milvus.
- Serverless mode uses Bedrock, OpenSearch, Redis/DynamoDB, and AWS Lambda/AgentCore patterns.
- Web search is optional and controlled by the current Tavily configuration.
- The Strands graph remains the shared business flow: TopicChecker → SecurityChecker → RAGWorker.

See [docs/ARCHITECTURE.md](ARCHITECTURE.md), [docs/API_SERVER.md](API_SERVER.md), and [docs/HOW_TO.md](HOW_TO.md).
