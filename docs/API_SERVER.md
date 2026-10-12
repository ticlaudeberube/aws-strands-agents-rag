# API Server

The app exposes an OpenAI-compatible REST API from `api_server.py`.

## Health check

```bash
curl http://localhost:8000/health
```

Expected response includes server status and backend availability metadata.

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

The API contract stays the same across modes. The selected backend changes based on `DEPLOYMENT_MODE`, while the request and response format remain consistent.

See [docs/HOW_TO.md](HOW_TO.md) and [docs/ARCHITECTURE.md](ARCHITECTURE.md) for setup context.
