# API Server

The app exposes an OpenAI-compatible REST API from `api_server.py`.

## Health check

```bash
curl http://localhost:8000/health
```

Expected response includes server status and backend availability metadata.
In local mode, `status` is `"warning"` and `vector_db_available` is `false` if
the configured vector DB cannot be reached. The API remains available for health checks, but
knowledge-base search and persistent cached questions are unavailable. The
React client displays this warning without treating the API as offline.

The health response's `vector_db` and `vector_db_available` fields are provider-neutral.
The current local adapter uses Milvus. `/health/vector-db` provides detailed
vector DB health; `/health/milvus` remains as a deprecated compatibility route.

## Chat completions

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "rag-agent",
    "messages": [{
      "role": "user",
      "content": "What is Milvus?"
    }],
    "temperature": 0.1,
    "max_tokens": 2000
  }'
```

The request accepts standard OpenAI-style chat fields plus project-specific options such as `force_web_search`.

## Request fields

The live request model in `api_server.py` includes:

- `messages`
- `model`
- `temperature`
- `top_p`
- `max_tokens`
- `top_k`
- `stream`
- `force_web_search`

## Response shape

The API returns the standard OpenAI-compatible completion payload with `choices`, `usage`, `sources`, and `timing` metadata.

## Local vs serverless behavior

The chat request and streaming response format are shared, but the available
cache APIs differ by mode. In local mode, the React client fetches the answered
question list from `/v1/cache/questions` and refreshes it after a response when
caching is enabled. The list is hidden while empty.

Serverless mode does not expose that local question-list endpoint. Its semantic
response cache and session persistence are backend features, not a browsable
answered-question history in the client. The client therefore does not request
the local list endpoint in serverless mode. Providing a cloud history would
require a separately designed, authenticated API rather than assuming the local
cache-list contract exists there.

See [docs/HOW_TO.md](HOW_TO.md) and [docs/ARCHITECTURE.md](ARCHITECTURE.md) for setup context.
