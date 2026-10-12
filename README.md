# AWS Strands Agents RAG

A dual-mode RAG system that currently supports both local development and AWS serverless deployment.

- Local: FastAPI + Ollama + Milvus
- Serverless AWS: Lambda + AgentCore + Bedrock + OpenSearch Serverless

## Start here

- [docs/HOW_TO.md](docs/HOW_TO.md) — practical setup and usage guide
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) — setup steps for both modes
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — runtime architecture and routing
- [docs/API_SERVER.md](docs/API_SERVER.md) — API contract and endpoints
- [docs/CHATBOT_GUI_FEATURES.md](docs/CHATBOT_GUI_FEATURES.md) — frontend feature reference
- [docs/INDEX.md](docs/INDEX.md) — active doc index

## Quick start

### Local mode

```bash
cd docker
docker-compose up -d
cd ..
python api_server.py
```

### Serverless mode

```bash
export DEPLOYMENT_MODE=serverless
# fill in AWS / Bedrock / OpenSearch values in .env
```

## Core runtime flow

```text
User query
  -> TopicChecker
  -> SecurityChecker
  -> RAGWorker
     -> retrieval backend
     -> answer + sources
```

## Supported modes

| Mode | Use case | Active stack |
|------|----------|--------------|
| Local | development and debugging | FastAPI, Ollama, Milvus |
| Serverless AWS | production deployment | Lambda, AgentCore, Bedrock, OpenSearch |

The source of truth for mode selection is `DEPLOYMENT_MODE` in `.env` and `src/config/settings.py`.

See [docs/HOW_TO.md](docs/HOW_TO.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the verified setup and architecture.
