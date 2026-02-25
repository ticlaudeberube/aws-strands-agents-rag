# API Server Guide

The RAG Agent is exposed as an OpenAI-compatible REST API server. This allows you to use it with any client that supports OpenAI's API format, including Ollama GUI and other compatible tools.

## Starting the Server

```bash
python api_server.py
```

The server will start on `http://localhost:8000`

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

```bash
# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=mistral
OLLAMA_EMBED_MODEL=nomic-embed-text:v1.5

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DB_NAME=knowledge_base
LOADER_MILVUS_DB_NAME=knowledge_base

# Collection
OLLAMA_COLLECTION_NAME=milvus_rag_collection
```

## Requirements

Before starting the server:

1. **Milvus is running** - Start with `cd ../milvus-standalone && docker-compose up -d` (or use `cd docker && docker-compose up -d` as alternative)
2. **Ollama is running** - Ensure Ollama is available at `http://localhost:11434`
3. **Documents are loaded** - Run `python document-loaders/load_milvus_docs_ollama.py`
4. **Dependencies are installed** - FastAPI and uvicorn are included in pyproject.toml

> **Note**: The `milvus-standalone` folder provides an optimized Docker setup for local development and is recommended over the generic docker-compose approach.

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
