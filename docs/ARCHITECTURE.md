# Architecture

The current codebase supports two deployment modes with the same core Strands workflow:

- Local mode: FastAPI + Ollama + vector DB
- Serverless AWS mode: Lambda + AgentCore + Bedrock + OpenSearch Serverless

## Shared workflow

```text
User query
  -> TopicChecker
  -> SecurityChecker
  -> RAGWorker
     -> retrieval backend
     -> answer generation
     -> source output
```

The Strands graph is the shared application flow. The difference between modes is the backend wiring, not the agent logic itself.
The graph uses a vector-store role rather than requiring one vendor's product.
The current adapters are Milvus for local mode and OpenSearch Serverless for
AWS mode; another provider needs a compatible adapter and configuration.

## Local mode

Local mode is the default path for development and debugging.

- FastAPI app in `api_server.py`
- Ollama for LLM and embeddings
- A vector DB for retrieval; the current local adapter uses Milvus
- Docker Compose for the current Milvus-backed local stack

## Serverless AWS mode

Serverless mode is the cloud deployment path.

- Lambda/AgentCore execution path
- Bedrock for inference and embeddings
- OpenSearch Serverless for vector search
- Redis/DynamoDB for cache/session support

## Mode selection

The switch is controlled by `DEPLOYMENT_MODE` in `.env` and `src/config/settings.py`:

```env
DEPLOYMENT_MODE=local
# or
DEPLOYMENT_MODE=serverless
```

This is the actual source of truth in the current project. There is no supported legacy `use_agentcore` toggle in the live configuration.

## Runtime responsibilities

- `api_server.py` exposes the OpenAI-compatible REST API
- `src/config/settings.py` selects the active backend stack
- `src/agents/strands_graph_agent.py` handles the topic/security/RAG flow
- `src/tools/` contains the retrieval, embedding, cache, and web-search clients
- The app captures sources and response metadata for the frontend and API callers

## Practical guidance

Use local mode when:
- you are developing locally
- you want Ollama with the currently configured Milvus vector DB
- you need offline or quick demos

Use serverless mode when:
- you are deploying to AWS
- you want Bedrock/OpenSearch managed infrastructure
- you need the production cloud stack

See [docs/GETTING_STARTED.md](GETTING_STARTED.md) and [docs/API_SERVER.md](API_SERVER.md) for concrete setup instructions.
