# Chatbot Examples

This directory contains chatbot examples for the AWS Strands Agents RAG system.

## Overview

Choose your preferred interface:

| Option | Type | Technology | Best For |
|--------|------|-----------|----------|
| **React Chatbot** | Web UI | React + Streaming | Modern web interfaces, Deployments |
| **Interactive Chat** | CLI | Python CLI | Testing, Quick setup |

## React Web Chatbot

A modern, streaming-enabled React chatbot with beautiful UI.

### Quick Start

```bash
# Development
npm start  # or: ./build.sh dev

# Production build
./build.sh build

# Docker deployment
./build.sh compose
```

**Features**
- 🚀 Real-time streaming responses
- 💬 Beautiful message UI
- 📱 Responsive design
- 🔌 Automatic API health checks

**Documentation**: See [react-chatbot/README.md](react-chatbot/README.md) and [docs/REACT_DEPLOYMENT.md](../docs/REACT_DEPLOYMENT.md)

### Deployment Options
- **Local**: `npm start`
- **Docker**: Multi-stage build with Nginx
- **Serverless**: AWS Lambda + CloudFront with AgentCore

## Interactive Python CLI Chatbot

```bash
python chatbot/interactive_chat.py
```

### Requirements

Before running the chatbot, ensure:
1. **The vector DB is running** - The local provider is OpenSearch; start it with `docker compose up -d opensearch` in the docker directory
2. **Ollama is installed and running** - Make sure Ollama is available at the configured host (default: http://localhost:11434)
3. **Documents are loaded** - Follow the [GETTING_STARTED.md](../docs/GETTING_STARTED.md) guide to:
   - Seed the knowledge-base corpus with `python document_loaders/load_docs_opensearch.py`, OR
   - Ingest an arbitrary directory with `python scripts/ingest_local_opensearch.py --docs ./data/docs`

### Features

- **Interactive Q&A** - Ask questions about vector databases and RAG using the configured knowledge base
- **RAG-based answers** - Answers are grounded in the loaded documentation
- **Real-time responses** - Get immediate answers using Ollama

### Commands

While chatting, you can use these special commands:

- `/quit` or `/exit` - Exit the chatbot
- `/help` - Show help message
- `/collections` - List available collections

### Example Interaction

```
You: What is Milvus?
Assistant: Milvus is an open-source vector database built to power similarity search and AI applications. It stores and searches high-dimensional vector data...

You: How do I create a collection?
Assistant: To create a collection in Milvus, you can use the create_collection() method. Here's an example...

You: /quit
Goodbye! 👋
```

### Configuration

The chatbot uses settings from your `.env` file:

- `OLLAMA_HOST` - Ollama server host
- `OLLAMA_MODEL` - LLM model to use for generating answers
- `OLLAMA_EMBED_MODEL` - Embedding model for vector search
- `OLLAMA_COLLECTION_NAME` - Legacy KB collection label (metadata only)
- `OPENSEARCH_LOCAL_HOST` / `OPENSEARCH_LOCAL_PORT` - Local OpenSearch connection
- `OPENSEARCH_KB_INDEX` - Knowledge-base index name (default `rag-kb`)

### Troubleshooting

**"Ollama is not available"**
- Ensure Ollama is running: `ollama serve`
- Check `OLLAMA_HOST` in `.env` matches your setup

**"Vector database unavailable"** (OpenSearch connection error)
- Start the local OpenSearch container: `cd docker && docker compose up -d opensearch`
- Wait for services to initialize (30-60 seconds)

**"No results found"**
- Ensure documents are loaded: `python document_loaders/load_docs_opensearch.py`
- Check that `OPENSEARCH_KB_INDEX` matches the loaded index
