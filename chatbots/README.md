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
python examples/interactive_chat.py
```

### Requirements

Before running the chatbot, ensure:
1. **Milvus is running** - Start with `docker-compose up -d` in the docker directory
2. **Ollama is installed and running** - Make sure Ollama is available at the configured host (default: http://localhost:11434)
3. **Sync or load Documents embeddings** 
- Run `python document-loaders/load_milvus_docs_ollama.py` first to populate the vector database and json cache
- Run `python document-loaders/sync_from_json.py` to load the cached embeddings without reprocessing the whole documents

### Features

- **Interactive Q&A** - Ask questions about the Milvus documentation
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
- `OLLAMA_COLLECTION_NAME` - Collection to search for documents
- `MILVUS_HOST` / `MILVUS_PORT` - Milvus server connection
- `MILVUS_DB_NAME` - Database name

### Troubleshooting

**"Ollama is not available"**
- Ensure Ollama is running: `ollama serve`
- Check `OLLAMA_HOST` in `.env` matches your setup

**"Failed to connect to Milvus"**
- Start Milvus: `cd docker && docker-compose up -d`
- Wait for services to initialize (30-60 seconds)

**"No results found"**
- Ensure documents are loaded: `python document-loaders/load_milvus_docs_ollama.py`
- Check that `OLLAMA_COLLECTION_NAME` matches the loaded collection

