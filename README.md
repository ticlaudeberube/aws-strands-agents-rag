# AWS Strands Agents RAG

A Retrieval-Augmented Generation (RAG) system using AWS Strands Agents, Ollama for local LLM/embeddings, and Milvus as a vector database.

## Features

- **Local LLM & Embeddings**: Uses Ollama for running language models and generating embeddings locally
- **Vector Database**: Milvus for efficient similarity search on large datasets
- **Strands Agents Integration**: AWS Strands Agents SDK for intelligent agent capabilities
- **Multiple Document Loaders**: Support for files, URLs, and text documents
- **Easy Deployment**: Docker Compose setup for Milvus and dependencies

## Architecture

```
┌──────────────────┐
│  Strands Agents  │
│   (RAG Agent)    │
└────────┬─────────┘
         │
    ┌────┴──────┬──────────┐
    │            │        │
┌───▼────┐  ┌───▼──────┐  ┌▼────────┐
│ Ollama │  │ Milvus   │  │Document │
│  LLM   │  │ Vector   │  │Loaders  │
│ & Emb  │  │   DB     │  │         │
└────────┘  └──────────┘  └─────────┘
```

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (or use Milvus-standalone for optimized local setup)
- Ollama (running locally)
- 4GB+ RAM recommended

> **Note**: This project includes a `milvus-standalone` folder with an optimized Docker setup specifically for local development. It's recommended to use this over the generic docker-compose approach.

## Quick Start

### 1. Setup Environment

```bash
# Clone the repository
cd /path/to/aws-stands-agents-rag

# Create .env file
cp .env.example .env

# Edit .env with your configuration (optional, defaults provided)
```

### 2. Start Milvus (Using Milvus-Standalone - Recommended)

The `milvus-standalone` folder contains an optimized Docker Compose setup for local development:

```bash
# Navigate to milvus-standalone folder
cd ../milvus-standalone

# Start Milvus services
docker-compose up -d

# Wait for services to start (check logs)
docker-compose logs -f

# Verify Milvus is running
curl http://localhost:19530

# Return to project root for next steps
cd ../aws-stands-agents-rag
```

**Milvus Standalone Features:**
- Pre-configured for local development
- Optimized resource usage
- Includes etcd, MinIO, and Milvus services
- Persistent volumes in `volumes/` directory
- Configuration in `milvus.yaml`

**Alternative: Using Docker Compose** (if not using milvus-standalone)
```bash
# Only use this if milvus-standalone is not available
docker-compose -f docker/docker-compose.yml up -d
docker-compose -f docker/docker-compose.yml logs -f milvus
curl http://localhost:9091/healthz
```

### 3. Install Ollama

```bash
# Download and install from https://ollama.ai

# Pull required models
ollama pull mistral      # For text generation
ollama pull all-minilm   # For embeddings (or nomic-embed-text)

# Start Ollama server (usually runs on http://localhost:11434)
ollama serve
```

### 4. Install Dependencies

```bash
# Using pip
pip install -e .

# Or using UV (faster)
uv sync
```

### 5. Start the API Server

```bash
# In a new terminal, from the project root:
uv run python api_server.py

# Server will start on http://localhost:8000
# Health check: curl http://localhost:8000/health
```

### 6. Run Examples

#### Option A: REST API (Ollama GUI compatible)

```bash
# Test with curl
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is Milvus?"}],
    "model": "rag-agent"
  }'
```

#### Option B: Interactive Chatbot

```bash
# In a new terminal:
uv run python examples/interactive_chat.py

# Then type questions and press Enter
# Type /quit to exit
# Type /help for more commands
```

## Configuration

### Environment Variables (.env)

```env
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=mistral
OLLAMA_EMBED_MODEL=all-minilm

# Milvus Configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DB_NAME=knowledge_base

# Application Configuration
LOG_LEVEL=INFO
BATCH_SIZE=10
EMBEDDING_DIM=384
```

## Project Structure

```
aws-stands-agents-rag/
├── src/
│   ├── agents/              # Agent implementations
│   │   ├── rag_agent.py    # Main RAG agent
│   │   └── __init__.py
│   ├── tools/               # Tools and utilities
│   │   ├── milvus_client.py # Milvus wrapper
│   │   ├── ollama_client.py # Ollama wrapper
│   │   └── __init__.py
│   ├── loaders/             # Document loaders
│   │   ├── document_loader.py
│   │   └── __init__.py
│   └── config/              # Configuration
│       ├── settings.py
│       └── __init__.py
├── examples/                # Example scripts
│   ├── basic_rag.py
│   ├── file_based_rag.py
│   └── interactive_chat.py
├── docker/                  # Docker setup
│   └── docker-compose.yml
├── .env.example            # Environment template
├── pyproject.toml          # Project configuration
└── README.md               # This file
```

## Usage

### Basic RAG Pattern

```python
from src.config.settings import get_settings
from src.agents.rag_agent import RAGAgent

# Initialize
settings = get_settings()
agent = RAGAgent(settings=settings)

# Add documents
documents = ["Document 1 text...", "Document 2 text..."]
agent.add_documents(
    collection_name="my_docs",
    documents=documents
)

# Query
answer = agent.answer_question(
    collection_name="my_docs",
    question="What is the main topic?",
    top_k=3
)
print(answer)
```

### Custom Tools and Agents

The framework supports adding custom tools using Strands Agents SDK:

```python
from strands_agents import tool

@tool
def custom_tool(input: str) -> str:
    """Custom tool description."""
    return f"Result: {input}"

# Add to agent
agent.agent.add_tool(custom_tool)
```

## Available Ollama Models

### For Text Generation
- `mistral` - Fast, high-quality reasoning
- `llama2` - Meta's LLama 2 model
- `neural-chat` - Intel's Neural Chat
- `dolphin-mixtral` - Enhanced Mixtral variant

### For Embeddings
- `all-minilm` - Fast embedding model (384-dim)
- `nomic-embed-text` - High-quality embeddings (768-dim)
- `all-mpnet-base-v2` - MiniLM variant

Pull more models: `ollama pull <model-name>`

## Docker Management

### Using Milvus-Standalone (Recommended)

```bash
cd ../milvus-standalone

# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Clean up everything
docker-compose down -v

# Access Milvus directly
# Milvus runs on http://localhost:19530
cd ../aws-stands-agents-rag
```

### Using Alternative Docker Setup

```bash
# Start services
docker-compose -f docker/docker-compose.yml up -d

# Stop services
docker-compose -f docker/docker-compose.yml down

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Clean up everything
docker-compose -f docker/docker-compose.yml down -v

# Access Milvus UI
# Navigate to http://localhost:9091/webui/
```

## Milvus Operations

### Using Python

```python
from src.tools import MilvusVectorDB

db = MilvusVectorDB(
    host="localhost",
    port=19530,
    db_name="knowledge_base"
)

# List collections
collections = db.list_collections()

# Search
results = db.search(
    collection_name="my_docs",
    query_embedding=[...],
    limit=5
)
```

### Using Milvus CLI

```bash
# Install
pip install pymilvus

# Connect
milvus_cli

# In CLI:
# connect -uri http://localhost:19530
# list databases
# use database knowledge_base
# list collections
# show collection_name
```

## Troubleshooting

### Ollama Not Available
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Check model
ollama list
```

### Milvus Connection Issues
```bash
# Check container status
docker-compose -f docker/docker-compose.yml ps

# View logs
docker-compose -f docker/docker-compose.yml logs milvus

# Restart services
docker-compose -f docker/docker-compose.yml restart
```

### Memory Issues
- Reduce `BATCH_SIZE` in .env
- Use smaller embedding models
- Reduce `chunk_size` in document loading
- Check available system memory

## Advanced Features

### Custom Embedding Models
```python
agent = RAGAgent(settings=settings)
embeddings = agent.ollama_client.embed_texts(
    texts=["text1", "text2"],
    model="nomic-embed-text"  # Different model
)
```

### Batch Processing
```python
from src.loaders import FileDocumentLoader, chunk_documents

loader = FileDocumentLoader(paths)
docs = loader.load()
chunks = chunk_documents(docs, chunk_size=1000)
agent.add_documents("collection", chunks)
```

### Metadata Support
```python
agent.vector_db.insert_embeddings(
    collection_name="docs",
    embeddings=embeddings,
    texts=texts,
    metadata=[
        {"source": "file1.txt", "page": 1},
        {"source": "file2.txt", "page": 2},
    ]
)
```

## Integration with AWS Services

For production deployment with AWS:

- **AWS Lambda**: Deploy agent as serverless function
- **Amazon Bedrock**: Use Claude/Nova models instead of Ollama
- **Amazon S3**: Store documents and model weights
- **Amazon ECS**: Containerized agent deployment
- **Amazon RDS**: Persistent session storage

See [Strands Agents Deployment Guide](https://strandsagents.com/latest/documentation/docs/user-guide/deploy/) for details.

## Performance Tips

1. **Batch Embeddings**: Process documents in batches
2. **Index Optimization**: Use AUTOINDEX for Milvus
3. **Query Limits**: Start with `top_k=3-5` for fastest results
4. **Model Selection**: Use smaller models for faster inference
5. **Caching**: Cache embeddings for repeated queries

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Resources

- [Strands Agents Documentation](https://strandsagents.com/latest/documentation/)
- [Strands Agents Examples](https://strandsagents.com/latest/documentation/docs/examples/)
- [Ollama Documentation](https://github.com/ollama/ollama)
- [Milvus Documentation](https://milvus.io/docs)
- [Milvus Python SDK](https://milvus.io/docs/pymilvus-ref/)

## License

MIT License - See LICENSE file for details

## Support

For issues and questions:
- Check existing documentation
- Review example scripts
- Check Strands Agents community resources
- Open an issue in the repository

---

**Happy Building! 🚀**
