# Development Guide

This guide provides information for developers working on this project.

## 🔧 Recent Improvements (Feb 28, 2026)

**Critical Caching System Fixes**: The response caching system was debugged and completely fixed:
- Fixed COSINE distance threshold calculation (was using wrong metric interpretation)
- Corrected similarity score calculation for Milvus embeddings (distance IS similarity in COSINE metric)
- Added collection flushing after data insertion to ensure persistence
- Added collection loading before vector searches
- Fixed ID generation to use safe 31-bit unsigned integers

**Performance Impact**: Semantic response caching now works perfectly, providing **1200x+ speedup** for identical or semantically similar queries (first query ~400ms, second query <1ms).

For details, see [CACHING_STRATEGY.md](CACHING_STRATEGY.md) and [RESPONSE_CACHE.md](RESPONSE_CACHE.md).

## Project Structure

```
aws-stands-agents-rag/
├── src/                              # Main source code
│   ├── __init__.py                  # Package initialization
│   ├── agents/                      # Agent implementations
│   │   ├── __init__.py
│   │   ├── strands_rag_agent.py    # Strands-compliant RAG agent
│   │   └── skills/                 # Tool skills (organized by category)
│   │       ├── __init__.py
│   │       ├── retrieval_skill.py      # Retrieval tools
│   │       ├── answer_generation_skill.py  # Generation tools
│   │       └── knowledge_base_skill.py     # Knowledge base tools
│   ├── tools/                       # Tools and utilities
│   │   ├── __init__.py
│   │   ├── milvus_client.py       # Milvus vector DB wrapper
│   │   ├── ollama_client.py        # Ollama LLM client
│   │   ├── web_search.py           # Web search client (Tavily)
│   │   ├── tool_registry.py        # Tool management & discovery
│   │   └── response_cache.py       # Response caching system
│   ├── mcp/                         # Model Context Protocol
│   │   ├── __init__.py
│   │   └── mcp_server.py           # MCP protocol server for tools
│   └── config/                      # Configuration
│       ├── __init__.py
│       └── settings.py              # Settings with pydantic
├── document-loaders/                # Document loading scripts
│   ├── load_milvus_docs_ollama.py  # Load Milvus docs with embedding
│   ├── add_sample_docs.py          # Add sample documents
│   ├── core/                        # Core loader utilities
│   └── milvus_docs/                # Downloaded Milvus documentation
├── chatbots/                        # Chat interfaces
│   ├── interactive_chat.py          # Terminal RAG chat
│   └── react-chatbot/              # React web UI chatbot
├── docker/                          # Docker configuration
│   ├── docker-compose.yml          # Services: Milvus, MinIO, etcd, API
│   ├── Dockerfile                  # RAG API container
│   ├── optimize.sh                 # Performance optimization script
│   ├── daemon.json                 # Docker daemon config
│   └── README.md                   # Docker documentation
├── scripts/                         # Utility scripts
│   ├── check_setup.py              # System diagnostics
│   ├── verify_collection.py        # Collection verification
│   ├── DOCKER_MIGRATION.md         # Migration from milvus-standalone
│   └── setup.sh / setup.bat        # Project setup
├── examples/                        # Example scripts
│   └── phase_1_2_examples.py       # Strands agent architecture examples
├── tests/                           # Unit tests
├── api_server.py                   # FastAPI server - REST API endpoint
├── pyproject.toml                  # Project configuration
└── README.md                        # Main documentation
```

## Key Components

### Milvus
**Milvus** is an open-source vector database designed for similarity search and AI applications. It efficiently stores and retrieves high-dimensional vector embeddings, making it ideal for RAG (Retrieval-Augmented Generation) systems. In this project, Milvus:
- Stores document embeddings from Ollama
- Performs semantic similarity search to retrieve relevant documents
- Runs in a Docker container via the `docker` folder for local development

### Ollama
**Ollama** is a local LLM (Large Language Model) platform that allows you to run models locally without cloud dependencies. This project uses:
- **qwen2.5:0.5b** (500M parameters) for fast text generation - 85% faster than larger models
- **nomic-embed-text:v1.5** for semantic embeddings

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
# In one terminal - Start Milvus with optimized Docker setup (recommended)
cd docker
chmod +x optimize.sh
./optimize.sh --all              # Optimizes system and starts all services

# In another terminal - Start Ollama
ollama serve
```

**What the optimization script does:**
- Configures Docker daemon for optimal performance
- Tunes system parameters (Linux users)
- Sets up resource limits and health checks
- Starts all services (Milvus, MinIO, etcd, RAG API)
- Displays service information and monitoring commands

**Services started:**
- Milvus vector database: localhost:19530
- Milvus WebUI: http://localhost:9091/webui
- MinIO object storage: http://localhost:9001
- RAG API server: http://localhost:8000

**Alternative: Quick start without optimization**
```bash
cd docker
docker-compose up -d
```

**For macOS users:**
The optimization script provides recommendations for Docker Desktop settings. Open Docker Desktop Preferences and adjust:
- CPU: 8 cores (or more)
- Memory: 16GB (or more)
- Enable VirtioFS for better performance
- Enable Rosetta 2 (Apple Silicon)

**For Linux users:**
The optimization script automatically configures:
- File descriptor limits
- Memory swappiness
- Virtual memory parameters
- Network optimizations

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
# In src/agents/strands_rag_agent.py
class StrandsRAGAgent:
    def new_method(self, param: str) -> str:
        """New method description."""
        # Implementation
        return result
```

## Code Examples

### Example 1: Using the StrandsRAGAgent with RAG Pipeline

```python
from src.config.settings import Settings
from src.agents.strands_rag_agent import StrandsRAGAgent

settings = Settings()
agent = StrandsRAGAgent(settings=settings)

# Add documents to knowledge base
agent.add_documents(
    collection_name="docs",
    documents=["Document 1", "Document 2", "Document 3"]
)

# Ask a question with RAG pipeline
answer, sources = agent.answer_question(
    question="What is the topic?",
    collection_name="docs",
    top_k=3
)
print(f"Answer: {answer}")
print(f"Sources: {len(sources)} documents retrieved")

# Direct retrieval
context, sources = agent.retrieve_context(
    collection_name="docs",
    query="What is the topic?",
    top_k=5
)

# Clear caches to free memory
agent.clear_caches()
```

### Example 2: Using Milvus with Advanced Features

```python
from src.tools import MilvusVectorDB

db = MilvusVectorDB(host="localhost", port=19530)

# Create optimized collection
db.create_collection(
    "my_collection",
    embedding_dim=768,
    index_type="HNSW",      # Optimized for speed
    metric_type="COSINE"    # Similarity metric
)

# Insert data with metadata
db.insert_embeddings(
    collection_name="my_collection",
    embeddings=[[0.1, 0.2, ...], ...],
    texts=["text1", "text2", ...],
    metadata=[
        {"source": "file1.txt", "page": 1},
        {"source": "file2.txt", "page": 2},
    ]
)

# Search with offset support
results = db.search(
    collection_name="my_collection",
    query_embedding=[0.1, 0.2, ...],
    limit=5,
    offset=0          # Skip first N results
)

# Search with filtering
results = db.search(
    collection_name="my_collection",
    query_embedding=[0.1, 0.2, ...],
    limit=5,
    filter_expr="source == 'file1.txt'"  # Filter by metadata
)

# Search by source
results = db.search_by_source(
    collection_name="my_collection",
    query_embedding=[0.1, 0.2, ...],
    source="file1.txt",
    limit=5
)

# Async search
import asyncio
results = asyncio.run(db.search_async(
    collection_name="my_collection",
    query_embedding=[0.1, 0.2, ...],
    limit=5
))
```

### Example 3: Batch Embedding with Parallel Processing

```python
from src.tools import OllamaClient

client = OllamaClient(host="http://localhost:11434")

# Batch embedding with parallel workers
texts = ["text1", "text2", "text3", ...]
embeddings = client.embed_texts(
    texts=texts,
    model="nomic-embed-text",
    batch_size=32,      # Process in batches
    max_workers=4       # Use 4 parallel workers
)

# This is much faster than embedding texts sequentially!
print(f"Embedded {len(embeddings)} texts")
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
    model="qwen2.5:0.5b"
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
LOG_LEVEL=DEBUG python examples/phase_1_2_examples.py

# Debug specific module
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from src.agents import StrandsRAGAgent
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

### StrandsRAGAgent

```python
class StrandsRAGAgent:
    # Initialization
    def __init__(self, settings: Settings, cache_size: int = None)
    
    # Answer Question (Full RAG Pipeline)
    def answer_question(
        question: str,
        collection_name: str = "default",
        top_k: int = 5,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Tuple[str, List[Dict]]  # (answer, sources)
    
    # Retrieve Context
    def retrieve_context(
        collection_name: str,
        query: str,
        top_k: int = 5,
        offset: int = 0,
        filter_source: Optional[str] = None
    ) -> Tuple[List[str], List[Dict]]  # (chunks, sources)
    
    # Document Management
    def add_documents(
        collection_name: str,
        documents: List[Union[str, Dict]]
    ) -> str  # status message
    
    # Cache Management
    def clear_caches() -> None
```
        collection_name: str,
        question: str,
        page: int = 0,
        page_size: int = 5
    ) -> Tuple[List[str], List[Dict], int]
    
    # Document Management
    def add_documents(
        collection_name: str,
        documents: List[str]
    ) -> bool
    
    # Cache Management
    def clear_caches() -> None
```

### MilvusVectorDB

```python
class MilvusVectorDB:
    # Initialization and Management
    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        db_name: str = "default"
    )
    
    # Collection Management
    def create_collection(
        collection_name: str,
        embedding_dim: int = 384,
        index_type: str = "HNSW",
        metric_type: str = "COSINE"
    ) -> bool
    
    def delete_collection(collection_name: str) -> bool
    def list_collections() -> List[str]
    
    # Data Management
    def insert_embeddings(
        collection_name: str,
        embeddings: List[List[float]],
        texts: List[str],
        metadata: List[Dict] = None
    ) -> List[int]
    
    # Search Methods
    def search(
        collection_name: str,
        query_embedding: List[float],
        limit: int = 5,
        offset: int = 0,
        search_params: Dict = None,
        filter_expr: Optional[str] = None
    ) -> List[Dict]
    
    async def search_async(
        collection_name: str,
        query_embedding: List[float],
        limit: int = 5,
        offset: int = 0,
        search_params: Dict = None,
        filter_expr: Optional[str] = None
    ) -> List[Dict]
    
    def search_by_source(
        collection_name: str,
        query_embedding: List[float],
        source: str,
        limit: int = 5
    ) -> List[Dict]
```

### OllamaClient

```python
class OllamaClient:
    def __init__(self, host: str = "http://localhost:11434")
    
    def is_available(timeout: int = 5) -> bool
    def get_available_models() -> List[str]
    
    def embed_text(
        text: str,
        model: str = "nomic-embed-text:v1.5"
    ) -> List[float]
    
    def embed_texts(
        texts: List[str],
        model: str = "nomic-embed-text:v1.5",
        batch_size: int = 32,
        max_workers: Optional[int] = None
    ) -> List[List[float]]
    
    def generate(
        prompt: str,
        model: str = "qwen2.5:0.5b",
        stream: bool = False,
        temperature: float = 0.1
    ) -> str
```

### Settings Configuration

```python
class Settings:
    # Ollama Configuration
    ollama_host: str
    ollama_model: str
    ollama_embed_model: str
    
    # Milvus Configuration
    milvus_host: str
    milvus_port: int
    milvus_db_name: str
    
    # Collection Configuration
    ollama_collection_name: str
    
    # Performance Settings
    agent_cache_size: int          # LRU cache size
    embedding_batch_size: int      # Batch size for bulk operations
    max_chunk_length: int
    embedding_dim: int
    
    # Application Configuration
    log_level: str
    batch_size: int
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

### WebSearchClient

```python
class WebSearchClient:
    def __init__(timeout: int = 10)
    
    # Basic web search
    def search(
        query: str,
        max_results: int = 5,
        safe_search: bool = True
    ) -> List[Dict[str, str]]  # [{"title", "snippet", "url", "source"}]
    
    # Comparative product search with feature-focused queries
    def search_comparison(
        product1: str,
        product2: str,
        max_results: int = 5
    ) -> Dict[str, Any]  # {"comparison": [...], "product1": {...}, "product2": {...}}
    
    # Format search results as readable text
    def extract_text_summary(
        results: List[Dict[str, str]]
    ) -> str
```

**Usage Example:**
```python
from src.tools.web_search import WebSearchClient

web_search = WebSearchClient(timeout=10)

# Basic search
results = web_search.search("Milvus vector database features", max_results=3)

# Comparative search (used by StrandsRAGAgent for comparative questions)
comparison = web_search.search_comparison("Milvus", "Pinecone", max_results=5)

# Extract formatted summary
summary = web_search.extract_text_summary(results)
print(summary)
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
