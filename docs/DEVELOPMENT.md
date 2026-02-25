# Development Guide

This guide provides information for developers working on this project.

## Project Structure

```
aws-stands-agents-rag/
├── src/                          # Main source code
│   ├── __init__.py              # Package initialization
│   ├── agents/                  # Agent implementations
│   │   ├── __init__.py
│   │   └── rag_agent.py        # Main RAG agent class
│   ├── tools/                   # Tools and utilities
│   │   ├── __init__.py
│   │   ├── milvus_client.py    # Milvus vector DB wrapper
│   │   └── ollama_client.py    # Ollama LLM wrapper
│   ├── loaders/                 # Document loaders
│   │   ├── __init__.py
│   │   └── document_loader.py  # Document loading utilities
│   └── config/                  # Configuration
│       ├── __init__.py
│       └── settings.py          # Settings with pydantic
├── examples/                    # Example scripts
├── docker/                      # Docker configuration
├── tests/                       # Unit tests (to be created)
├── api_server.py               # FastAPI server - REST API entry point
├── pyproject.toml              # Project configuration
├── setup.sh / setup.bat        # Setup scripts
└── README.md                   # Documentation
```

## Development Setup

### 1. Clone and Setup

```bash
# Clone repository
git clone <repository-url>
cd aws-stands-agents-rag

# Create virtual environment
python3 -m venv venv
source .venv/bin/activate  # or venv\Scripts\activate on Windows

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### 2. Start Services

```bash
# In one terminal - Start Milvus (using milvus-standalone - recommended)
cd ../milvus-standalone
docker-compose up -d

# Alternative: Use generic docker-compose
# cd docker && docker-compose up -d

# In another terminal - Start Ollama
ollama serve
```

> **Milvus-Standalone Features**:
> - Pre-configured for local development
> - Optimized resource usage
> - Includes etcd, MinIO, and Milvus services
> - Persistent volumes in `volumes/` directory

### 3. Code Style

We use:
- **Black** for code formatting
- **Ruff** for linting
- **MyPy** for type checking

```bash
# Format code
black src/ examples/

# Lint code
ruff check src/ examples/

# Type checking
mypy src/
```

### 4. Testing

Tests are located in `tests/` directory:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test
pytest tests/test_*.py -k test_name -v
```

## Adding New Features

### 1. Adding a New Agent Tool

```python
# In src/tools/my_tool.py
from strands_agents import tool

@tool
def my_custom_tool(input: str) -> str:
    """Description of what the tool does."""
    # Implementation
    return result

# Update src/tools/__init__.py to export
```

### 2. Adding a New Document Loader

```python
# In src/loaders/document_loader.py
class MyDocumentLoader(DocumentLoader):
    def __init__(self, config):
        self.config = config
    
    def load(self) -> List[str]:
        """Load and return documents."""
        documents = []
        # Implementation
        return documents

# Update src/loaders/__init__.py to export
```

### 3. Adding New Agent Functionality

```python
# In src/agents/rag_agent.py
class RAGAgent:
    def new_method(self, param: str) -> str:
        """New method description."""
        # Implementation
        return result
```

## Code Examples

### Example 1: Using the RAG Agent

```python
from src.config.settings import get_settings
from src.agents import RAGAgent

settings = get_settings()
agent = RAGAgent(settings=settings)

# Add documents
agent.add_documents(
    collection_name="docs",
    documents=["Document 1", "Document 2"]
)

# Query
answer = agent.answer_question(
    collection_name="docs",
    question="What is the topic?",
    top_k=3
)
print(answer)
```

### Example 2: Using Milvus Directly

```python
from src.tools import MilvusVectorDB

db = MilvusVectorDB(host="localhost", port=19530)

# Create collection
db.create_collection("my_collection", embedding_dim=384)

# Insert data
db.insert_embeddings(
    collection_name="my_collection",
    embeddings=[[0.1, 0.2, ...], ...],
    texts=["text1", "text2", ...]
)

# Search
results = db.search(
    collection_name="my_collection",
    query_embedding=[0.1, 0.2, ...],
    limit=5
)
```

### Example 3: Using Ollama Client

```python
from src.tools import OllamaClient

client = OllamaClient(host="http://localhost:11434")

# Generate embeddings
embedding = client.embed_text("Hello world")

# Batch embeddings
embeddings = client.embed_texts(["text1", "text2"])

# Generate text
response = client.generate(
    prompt="What is AI?",
    model="mistral"
)
```

### Example 4: Document Loading and Chunking

```python
from src.loaders import FileDocumentLoader, chunk_documents

# Load documents
loader = FileDocumentLoader([
    "path/to/file1.txt",
    "path/to/file2.md"
])
docs = loader.load()

# Chunk documents
chunks = chunk_documents(
    documents=docs,
    chunk_size=500,
    overlap=50
)
```

## Common Development Tasks

### Running the Example Scripts

```bash
# Basic RAG example
python examples/basic_rag.py

# Interactive chat
python examples/interactive_chat.py

# File-based RAG
python examples/file_based_rag.py
```

### Debugging

```bash
# Run with debug logging
LOG_LEVEL=DEBUG python examples/basic_rag.py

# Debug specific module
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from src.agents import RAGAgent
# Your debug code here
"
```

### Performance Testing

```bash
# Time execution
time python examples/basic_rag.py

# Profile code
python -m cProfile -s cumulative examples/basic_rag.py | head -30
```

## API Reference

### RAGAgent

```python
class RAGAgent:
    def __init__(self, settings: Settings)
    def retrieve_context(collection_name: str, query: str, top_k: int) -> List[str]
    def answer_question(collection_name: str, question: str, top_k: int) -> str
    def add_documents(collection_name: str, documents: List[str]) -> bool
```

### MilvusVectorDB

```python
class MilvusVectorDB:
    def __init__(host: str, port: int, db_name: str)
    def create_collection(collection_name: str, embedding_dim: int) -> bool
    def insert_embeddings(collection_name: str, embeddings, texts, metadata) -> List[int]
    def search(collection_name: str, query_embedding, limit: int) -> List[Dict]
    def delete_collection(collection_name: str) -> bool
    def list_collections() -> List[str]
```

### OllamaClient

```python
class OllamaClient:
    def __init__(host: str)
    def embed_text(text: str, model: str) -> List[float]
    def embed_texts(texts: List[str], model: str) -> List[List[float]]
    def generate(prompt: str, model: str, stream: bool) -> str
    def is_available() -> bool
```

## Deployment Considerations

### Local Development
- Use small models for faster iteration
- Set `LOG_LEVEL=DEBUG` for troubleshooting
- Keep `BATCH_SIZE` small for testing

### Testing Environment
- Use realistic model sizes
- Set `LOG_LEVEL=INFO`
- Test with actual document volumes

### Production
- Use optimized models
- Set up monitoring and logging
- Consider AWS Bedrock for better models
- Use managed services where possible
- Implement caching and optimization

## Related Documentation

- [README.md](README.md) - User documentation
- [GETTING_STARTED.md](GETTING_STARTED.md) - Setup guide
- [Strands Agents Docs](https://strandsagents.com/latest/documentation/)
- [Milvus Docs](https://milvus.io/docs)
- [Ollama Docs](https://github.com/ollama/ollama)

## Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes and test: `pytest tests/`
3. Format code: `black src/ examples/`
4. Lint: `ruff check src/`
5. Type check: `mypy src/`
6. Commit: `git commit -am 'Add my feature'`
7. Push: `git push origin feature/my-feature`
8. Create Pull Request

## Support

For questions or issues:
1. Check existing documentation
2. Review example scripts
3. Check logs with `LOG_LEVEL=DEBUG`
4. Review Strands Agents documentation
5. Open an issue with detailed description

---

Happy developing! 🚀
