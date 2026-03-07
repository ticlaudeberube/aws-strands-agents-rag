# API Server Guide

The RAG Agent is exposed as an OpenAI-compatible REST API server. This allows you to use it with any client that supports OpenAI's API format, including Ollama GUI and other compatible tools.

**📚 Related Documentation:**
- [Cache and LLM Response Flow](CACHE_AND_LLM_RESPONSE_FLOW.md) - Understand what to expect from queries (with/without cache)
- [Caching Strategy](CACHING_STRATEGY.md) - Semantic response cache implementation

## 🚀 Performance Highlights

The API server now includes an advanced caching system that provides **1200x+ speedup** for repeated or semantically similar queries:

- **First query**: ~400ms (full RAG pipeline with LLM generation)
- **Second identical query**: <1ms (returned from semantic response cache)
- **Similar query**: <1ms (semantic matching finds similar cached answer)

This means the second time you ask "What is Milvus?" or similar questions, you get instant responses from the cache!

See [CACHING_STRATEGY.md](CACHING_STRATEGY.md) for detailed caching architecture.

## Starting the Server

### Option 1: Using Docker (Recommended)

The API server runs automatically as part of the Docker setup:

```bash
cd docker
./optimize.sh --all              # Starts all services including rag-api
```

The server will start on `http://localhost:8000` inside the container (exposed to localhost:8000)

### Option 2: Manual Start

For development, run directly:

```bash
python api_server.py
```

The server will start on `http://localhost:8000`

**Prerequisites:**
- Milvus running at `localhost:19530`
- Ollama running at configured `OLLAMA_HOST`
- Documents loaded in configured collection

## Endpoints

### Health Check

```bash
GET http://localhost:8000/health
```

Returns server status:
```json
{
  "status": "ok",
  "model": "rag-agent",
  "ollama": "http://localhost:11434",
  "milvus": "localhost:19530"
}
```

### List Models

```bash
GET http://localhost:8000/v1/models
```

OpenAI-compatible endpoint returning available models.

### Chat Completions

```bash
POST http://localhost:8000/v1/chat/completions
```

OpenAI-compatible chat completions endpoint.

**Request:**
```json
{
  "model": "rag-agent",
  "messages": [
    {
      "role": "user",
      "content": "What is Milvus?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 2000
}
```

**Response:**
```json
{
  "id": "chatcmpl-123456789",
  "object": "chat.completion",
  "created": 1708800000,
  "model": "rag-agent",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Milvus is an open-source vector database..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 3,
    "completion_tokens": 150,
    "total_tokens": 153
  }
}
```

## Usage Examples

### cURL

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-agent",
    "messages": [
      {"role": "user", "content": "How do I create a collection in Milvus?"}
    ]
  }'
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "rag-agent",
        "messages": [
            {"role": "user", "content": "What are the benefits of Milvus?"}
        ],
        "temperature": 0.7,
    },
)

answer = response.json()["choices"][0]["message"]["content"]
print(answer)
```

### JavaScript/Node.js

```javascript
const response = await fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    model: 'rag-agent',
    messages: [
      { role: 'user', content: 'Explain vector databases' }
    ],
    temperature: 0.7,
  }),
});

const data = await response.json();
const answer = data.choices[0].message.content;
console.log(answer);
```

## Request Parameters (Advanced Control)

The `/v1/chat/completions` endpoint supports additional parameters beyond OpenAI compatibility to control caching and search behavior:

### force_web_search (Boolean, Optional)
**Forces web-only search, bypassing the knowledge base.**

- `false` (default): Normal mode - checks cache first, then searches both docs + web
- `true`: Force fresh web search only, ignores knowledge base and cache

**Use when:** You need the latest web information and don't want knowledge base results.

**Example:**
```json
{
  "model": "rag-agent",
  "messages": [{"role": "user", "content": "Latest AI developments"}],
  "force_web_search": true
}
```

**Performance Impact:** 5-15 seconds (web search timeout and processing)

### bypass_cache (Query Parameter, Optional)
**Bypasses the response cache, forcing fresh KB search.**

- `false` (default): Uses response cache if available (<50ms for cached answers)
- `true`: Skips response cache, performs fresh KB retrieval (1-2s)

**Use when:** You need the freshest answer from the knowledge base.

**Example:**
```bash
curl -X POST "http://localhost:8000/v1/chat/completions?bypass_cache=true" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-agent",
    "messages": [{"role": "user", "content": "What is Milvus?"}]
  }'
```

**Note**: Passed as **query parameter**, not in request body.

**Performance Impact:** 1-2s (fresh vector search + LLM generation)

### Parameter Combinations

| force_web_search | bypass_cache | Behavior |
|---|---|---|
| false | false | ✅ **Default** - Uses cache if available, otherwise fresh KB search |
| false | true | Fresh KB search (bypasses cache) |
| true | false | Web-only search (cache not used) |
| true | true | Web-only search (cache not used) |

**Notes**:
- `force_web_search` completely bypasses the knowledge base
- `bypass_cache` only bypasses the response cache layer
- Both can improve answer freshness at the cost of latency

### Complete Example with Parameters

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "rag-agent",
        "messages": [
            {"role": "user", "content": "Latest Milvus updates"}
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
        "force_web_search": False,     # Include web results
        "bypass_cache": False          # Use cache if available
    },
)

answer = response.json()["choices"][0]["message"]["content"]
print(answer)
```

## MCP Server Endpoints (Tool Management)

The API server includes Model Context Protocol (MCP) endpoints for managing tools and skills. These are documented in [ARCHITECTURE.md](ARCHITECTURE.md#mcp-server).

### Get Server Info

```bash
GET http://localhost:8000/api/mcp/server/info
```

Returns server metadata and available endpoints:
```json
{
  "name": "RAG Agent MCP Server",
  "version": "1.0.0",
  "capabilities": ["tools", "resources"],
  "tools": 5,
  "skills": 3
}
```

### List All Tools

```bash
GET http://localhost:8000/api/mcp/tools
```

Returns all available tools with schemas:
```json
{
  "tools": [
    {
      "name": "retrieve_documents",
      "description": "Retrieve documents using semantic search",
      "skill": "retrieval",
      "parameters": {"type": "object", ...}
    },
    ...
  ]
}
```

### List Skills

```bash
GET http://localhost:8000/api/mcp/skills
```

Returns organized skills with tool counts:
```json
{
  "skills": {
    "retrieval": {"tools": 3, "description": "Document search"},
    "answer_generation": {"tools": 1, "description": "Answer synthesis"},
    "knowledge_base": {"tools": 1, "description": "Document management"}
  }
}
```

### Get Skill Documentation

```bash
GET http://localhost:8000/api/mcp/skills/{skill_name}
```

Returns markdown documentation for a skill:
```bash
curl http://localhost:8000/api/mcp/skills/retrieval
```

### Call Tool

```bash
POST http://localhost:8000/api/mcp/tools/call
```

Execute a tool with arguments:
```bash
curl -X POST http://localhost:8000/api/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "retrieve_documents",
    "arguments": {
      "collection": "milvus_docs",
      "query": "What is Milvus?",
      "top_k": 5
    }
  }'
```

Response:
```json
{
  "status": "success",
  "tool": "retrieve_documents",
  "result": [
    {
      "text": "Milvus is an open-source vector database...",
      "source": "milvus_docs",
      "score": 0.95
    },
    ...
  ]
}
```

## Using with Ollama GUI

Most Ollama web UI tools support OpenAI-compatible APIs.

### Configuration

In your Ollama GUI settings, configure:

```
API Base URL: http://localhost:8000/v1
Model: rag-agent
```

Or directly use the endpoint: `http://localhost:8000/v1/chat/completions`

### Popular GUI Options

1. **Open WebUI** (formerly Ollama Web UI)
   - Add custom API endpoint
   - URL: `http://localhost:8000/v1`
   - Model: `rag-agent`

2. **Ollama WebUI**
   - Settings → API Base
   - Set to: `http://localhost:8000/v1`

3. **ChatBox**
   - Model settings
   - Custom OpenAI endpoint: `http://localhost:8000`

## Configuration

The API server uses settings from your `.env` file:

```env
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434         # Local development
# OR for Docker:
OLLAMA_HOST=http://host.docker.internal:11434  # Docker Desktop

OLLAMA_MODEL=qwen2.5:0.5b                # LLM model
OLLAMA_EMBED_MODEL=nomic-embed-text:v1.5  # Embedding model

# Milvus Configuration
MILVUS_HOST=localhost                      # Local development
# OR for Docker:
MILVUS_HOST=milvus                         # Docker service name
MILVUS_PORT=19530
MILVUS_DB_NAME=knowledge_base

# Collection Configuration
OLLAMA_COLLECTION_NAME=milvus_rag_collection  # Must match loaded data

# Performance Settings
AGENT_CACHE_SIZE=500                       # LRU cache for embeddings/queries
EMBEDDING_BATCH_SIZE=32                    # Batch size for embedding
MAX_CHUNK_LENGTH=400                       # Text chunk size
EMBEDDING_DIM=768                          # Embedding vector dimension

# Application
LOG_LEVEL=INFO
BATCH_SIZE=10
```

### Docker-Specific Configuration

When running the API server in Docker:

```env
# Use service names instead of localhost
MILVUS_HOST=milvus
MILVUS_PORT=19530

# Connect to host Ollama (for Docker Desktop on macOS/Windows)
OLLAMA_HOST=http://host.docker.internal:11434

# For Linux or if Ollama is in another container
# OLLAMA_HOST=http://ollama:11434  # if using separate Ollama container
```

## Requirements

### For Docker Deployment (Recommended)

1. **Docker Compose Services** - Start with optimization script:
   ```bash
   cd docker
   ./optimize.sh --all
   ```
   This starts Milvus, MinIO, etcd, and RAG API automatically

2. **Ollama** - Ensure Ollama is running on your host:
   ```bash
   ollama serve
   ```

3. **Documents Loaded** - Load documentation:
   ```bash
   python document-loaders/load_milvus_docs_ollama.py
   ```

### For Manual Deployment

1. **Milvus** - Running at configured host/port
2. **Ollama** - Running at configured `OLLAMA_HOST`
3. **Documents** - Loaded in configured collection
4. **Dependencies** - FastAPI and uvicorn installed

### Environment Configuration

The server reads from `.env` file:

```bash
# Connection Settings
MILVUS_HOST=milvus                         # Use "milvus" for Docker, "localhost" for local
MILVUS_PORT=19530
OLLAMA_HOST=http://host.docker.internal:11434  # Docker desktop connects to host via this

# Collection
OLLAMA_COLLECTION_NAME=milvus_rag_collection

# Cache Configuration
ENABLE_CACHE_WARMUP=true                   # Pre-load Q&A pairs from data/responses.json on startup

# Performance
AGENT_CACHE_SIZE=500
EMBEDDING_BATCH_SIZE=32
LOG_LEVEL=INFO
```

**Cache Warmup Details:**
- `ENABLE_CACHE_WARMUP=true` (default): Pre-loads 17 pre-generated Q&A pairs on startup, enabling instant responses for common questions
- `ENABLE_CACHE_WARMUP=false`: Skips cache warmup - useful for development/testing or when you want to test the full RAG pipeline on every query

> **Docker Note**: When running in Docker container, use `MILVUS_HOST=milvus` (service name) and `OLLAMA_HOST=http://host.docker.internal:11434` (to connect back to host Ollama)

## Environment Variables

```bash
# Optional: Custom port and host
# export RAG_API_PORT=8000
# export RAG_API_HOST=0.0.0.0
```

## Troubleshooting

### "Ollama is not available"
- Ensure Ollama is running: `ollama serve`
- Check `OLLAMA_HOST` in `.env`

### "Agent not initialized" (503)
- Server is still starting, wait a moment
- Check logs for initialization errors

### "No messages provided" (400)
- Ensure your request includes `messages` array
- At least one message with `role: "user"` is required

### Empty responses
- Verify documents are loaded in Milvus
- Check `OLLAMA_COLLECTION_NAME` is correct
- Ensure Ollama model is available

## Performance Tips

1. **Batch requests** - The API handles one request at a time
2. **Connection pooling** - Reuse connections for multiple requests
3. **Increase Ollama threads** - Set `OLLAMA_NUM_THREADS` in `.env`
4. **Load documents efficiently** - Use `load_milvus_docs_ollama.py`

## Production Deployment

For production, consider:

1. **Use a production ASGI server** instead of uvicorn
   ```bash
   pip install gunicorn
   gunicorn -w 4 -k uvicorn.workers.UvicornWorker api_server:app
   ```

2. **Add authentication** - Implement API key authentication

3. **Add logging** - Configure proper log handlers

4. **Set up monitoring** - Monitor API performance and errors

5. **Use a reverse proxy** - Nginx/Apache for load balancing

## API Limitations

- **No streaming** - Responses are returned as complete messages
- **Single conversation** - No conversation history maintained
- **Token limits** - Responses are limited by Ollama model context window
- **RAG only** - Answers are grounded in loaded documents
