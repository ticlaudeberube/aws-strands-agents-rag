# AgentCore RAG — Docker Configuration

Consolidated local stack for the AWS Strands Agents RAG system. One Compose file
(`docker-compose.yml`, project name `agentcore-rag`) brings up the whole local
app on the **OpenSearch** vector engine. Milvus has been removed — OpenSearch is
the sole vector store in both local and serverless modes.

## Services

| Service | Container | Image | Port(s) | Purpose |
|---|---|---|---|---|
| opensearch | `agentcore-rag-opensearch` | `opensearchproject/opensearch:2.17.1` | 9200 | Vector store (`rag-kb`) + Layer 4 semantic cache (`rag-cache`). Security plugin disabled — local-only, plain HTTP, no TLS/auth. |
| redis | `agentcore-rag-redis` | `redis:7.4-alpine` | 6379 | Layer 2/3 cache (plain TCP, no TLS). |
| dynamodb | `agentcore-rag-dynamodb` | `amazon/dynamodb-local:2.5.2` | 8001 | Session/analytics store (DynamoDB Local, in-memory). |
| rag-api | `agentcore-rag-api` | built from `docker/Dockerfile` | 8000 | FastAPI app, Local Mode on OpenSearch. |
| react-chatbot | `agentcore-rag-react` | built from `docker/Dockerfile.react` | 3000 | React chatbot UI. |

> **Ollama runs on the host**, not in Docker — the app reaches it at
> `http://host.docker.internal:11434`. Make sure `ollama serve` is running and
> the embedding model is pulled: `ollama pull nomic-embed-text:v1.5`.

## Quick start

```bash
cd docker
docker compose up -d          # starts all 5 services
docker compose ps             # wait for opensearch + rag-api to be healthy
```

Then ingest documents into OpenSearch (Ollama embeddings) and query:

```bash
# from the repo root, with the stack up:
uv run python document_loaders/load_docs_opensearch.py    # index the KB corpus
# or an arbitrary directory:
uv run python scripts/ingest_local_opensearch.py --docs ./data/docs

curl http://localhost:8000/health        # vector_db: "opensearch (local ...)"
open http://localhost:3000               # chat UI
```

## Common commands

```bash
docker compose up -d                 # start
docker compose down                  # stop (add -v to drop the opensearch volume)
docker compose logs -f rag-api       # tail a service
docker compose logs -f opensearch
docker compose ps                    # health
docker stats                         # resource usage
```

## rag-api configuration

The `rag-api` service runs Local Mode against OpenSearch via these env vars
(set in `docker-compose.yml`):

- `DEPLOYMENT_MODE=local`
- `LOCAL_VECTOR_BACKEND=opensearch`
- `OPENSEARCH_LOCAL_HOST=opensearch` / `OPENSEARCH_LOCAL_PORT=9200`
- `OLLAMA_HOST=http://host.docker.internal:11434`
- `API_PORT=8000`

`api_server.py`, `src/`, `chatbots/`, and `document_loaders/` are bind-mounted,
so source edits take effect without rebuilding the image. Rebuild only when
`Dockerfile` or dependencies change: `docker compose build rag-api`.

## Health checks

```bash
curl http://localhost:8000/health                 # RAG API (reports OpenSearch)
curl http://localhost:9200/_cluster/health        # OpenSearch
docker exec agentcore-rag-redis redis-cli ping     # Redis -> PONG
curl http://localhost:8000/health/vector-db        # detailed vector-store health
```

## Access

| Service | URL |
|---|---|
| RAG API | http://localhost:8000 |
| React UI | http://localhost:3000 |
| OpenSearch | http://localhost:9200 |

## Serverless-local (optional)

To exercise the **serverless** code path locally (real Bedrock + these same
local OpenSearch/Redis/DynamoDB containers), bring this stack up and run the
wrapper scripts — see [docs/SERVERLESS_LOCAL.md](../docs/SERVERLESS_LOCAL.md).
Those scripts reuse the `agentcore-rag` OpenSearch/Redis/DynamoDB services on
ports 9200/6379/8001.

## Troubleshooting

- **Port already in use (8000/9200/6379/3000):** find and stop the holder
  (`lsof -nP -iTCP:8000 -sTCP:LISTEN`), or stop a stale container
  (`docker compose stop rag-api`).
- **`vector database is unavailable` in the UI:** OpenSearch isn't up or the KB
  index is empty. Check `docker compose ps` and run the ingest step above.
- **Out of memory / container killed (exit 137):** raise Docker Desktop memory
  (Preferences → Resources). OpenSearch wants ~2GB.
- **React restart loop:** rebuild after editing `nginx.conf`
  (`docker compose build react-chatbot`), since it's baked into the image.

## References

- [OpenSearch Documentation](https://opensearch.org/docs/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
