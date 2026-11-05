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
The client also rechecks API health every 10 seconds so it can recover from
an API server that was unavailable when the page loaded. The API limits its
vector DB health probe to two seconds, so an unresponsive database is reported
as a warning rather than leaving the GUI on a stale connected status.

The health response's `vector_db` and `vector_db_available` fields are provider-neutral.
`web_search_enabled` is true only when web search is enabled in settings and a
Tavily API key is configured.
The local adapter uses OpenSearch. `/health/vector-db` provides detailed
vector DB health.

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
When forced web search is requested while web search is disabled in settings,
the API reports that it is disabled rather than presenting the condition as a
Tavily quota or authentication failure.

The `POST /v1/chat/completions` endpoint also accepts a `bypass_cache` query
parameter (default `false`); set it to `true` to skip all caches and query the
LLM directly, e.g. `POST /v1/chat/completions?bypass_cache=true`.

## Request fields

The live request model in `api_server.py` includes:

- `messages`
- `model`
- `temperature`
- `top_p`
- `max_tokens`
- `top_k` (when unset, retrieval defaults to 5)
- `stream`
- `force_web_search`

## Response shape

The API returns the standard OpenAI-compatible completion payload with `choices`, `usage`, `sources`, and `timing` metadata.

## Endpoint reference

The live routes in `api_server.py` (local mode):

| Method & path | Purpose |
|---|---|
| `GET /` | Service/info descriptor: name, version, endpoint map, feature flags. |
| `GET /health` | Health check with local vector-DB availability (used by the GUI). |
| `GET /health/detailed` | Per-service status (Ollama, vector DB) plus cache sizes. |
| `GET /health/ollama` | Ollama service health. |
| `GET /health/vector-db` | Detailed OpenSearch vector-DB health. |
| `GET /metrics` | RAG graph node metrics (counts, durations, early-exit rates, uptime). |
| `GET /metrics/reset` | Clears accumulated metrics (testing/benchmarking — destructive). |
| `GET /v1/models` | OpenAI-compatible model list. |
| `POST /v1/chat/completions` | Chat completions (JSON or SSE when `stream: true`); `bypass_cache` query param. |
| `POST /v1/chat/completions/stream` | Dedicated SSE streaming endpoint. |
| `GET /api/cache/questions` | Pre-warmed common questions for GUI suggestions. |
| `GET /api/cache/stats` | Cache statistics and performance metrics. |
| `POST /v1/cache/clear` | Clear all RAG agent caches. |
| `GET /v1/cache/responses` | Retrieve cached Q&A pairs (`limit` query param). |
| `GET /v1/cache/responses/{cache_id}` | Fetch a specific cached response by ID. |
| `GET /v1/cache/questions` | Deduplicated lightweight cached-question list. |
| `GET /api/mcp/server/info` | MCP server metadata, tool count, skills. |
| `GET /api/mcp/tools` | List all tools in MCP format. |
| `GET /api/mcp/skills` | List skill categories (progressive tool disclosure). |
| `GET /api/mcp/skills/{skill_name}` | Documentation for one skill. |
| `POST /api/mcp/tools/call` | Invoke a tool via the MCP interface. |

The `/api/mcp/*` suite exposes the project's MCP server
(`src/mcp/mcp_server.py`) over REST — the same tools the agent uses, for
inspection and direct invocation.

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

The serverless handler (`agentcore_handler.py`) returns a different envelope
from the local OpenAI-compatible payload above. Alongside the answer and
`sources`, each response includes anti-hallucination quality fields —
`confidence_score`, `grounding_score`, and `web_search_unavailable` — plus
`tier_used` (`cache` / `kb` / `websearch`), `session_id`, and `latency_ms`. See
[docs/ANTI_HALLUCINATION.md](ANTI_HALLUCINATION.md) for how `grounding_score`
and `confidence_score` are computed and surfaced.

See [docs/HOW_TO.md](HOW_TO.md) and [docs/ARCHITECTURE.md](ARCHITECTURE.md) for setup context.
