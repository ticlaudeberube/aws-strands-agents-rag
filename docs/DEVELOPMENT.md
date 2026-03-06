# Development Guide

This guide provides information for developers working on this project.

## 🔧 Recent Improvements (Mar 5, 2026)

**Graph-Based Agent Architecture**: Migrated from monolithic `StrandsRAGAgent` to new `StrandsGraphRAGAgent`:
- 3-node graph: Topic Check → Security Check → RAG Worker
- Pattern-matching security detection (28+ jailbreak, 9 command, 8 injection patterns)
- Real Ollama streaming with 5-byte buffer (not simulated)
- Web search optimization with relevance scoring
- Multi-layer caching: embedding, search, answer, response (1200x+ speedup)

**Test Suite Migration**: Updated all tests to work with new graph agent:
- 77 tests passing (100% pass rate)
- Test coverage: 48% overall (619/1303 statements)
- Removed obsolete test files for old monolithic agent

For details, see [ARCHITECTURE.md](ARCHITECTURE.md) and [CACHING_STRATEGY.md](CACHING_STRATEGY.md).

## Project Structure

```
aws-stands-agents-rag/
├── src/                              # Main source code
│   ├── __init__.py                  # Package initialization
│   ├── agents/                      # Agent implementations
│   │   ├── __init__.py
│   │   ├── strands_graph_agent.py   # Graph-based RAG agent (3-node)
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
black src/ document_loaders/

# Lint code
ruff check src/ document_loaders/

# Type checking
mypy src/
```

### 4. Pre-commit Setup & Troubleshooting

#### Installation

```bash
# Install pre-commit
pip install pre-commit

# Install git hooks (runs checks before each commit)
pre-commit install
```

Once installed, pre-commit runs automatically on `git commit`. To run manually:

```bash
# Run all checks on all files
pre-commit run --all-files

# Run only before committing
pre-commit run
```

#### Fixing Pre-commit Issues

When pre-commit checks fail, use these commands and strategies to fix common issues.

### Override pre-commit
git commit --no-verify -m "Your commit message"

##### Ruff Linting Errors

**Auto-fix most violations:**
```bash
ruff check --fix
```

**Common issues and fixes:**

- **Unused imports** (F401): `from x import y  # unused`
  - Fix: `ruff check --fix` auto-removes unused imports
  
- **Unused variables** (F841): `x = value  # assigned but never used`
  - Fix: Remove the assignment or use `_ = value` for intentional discards
  ```python
  # Before
  unused_var = some_function()
  
  # After
  _ = some_function()  # Intentionally discarding return value
  ```

- **Line too long** (E501): Lines > 88 characters
  - Fix: Break long lines using backslash or implicit continuation
  ```python
  # Before
  result = some_function(arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg9)
  
  # After
  result = some_function(
      arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg9
  )
  ```

- **Undefined name** (F405): `x is not defined`
  - Fix: Import the missing module or define the variable
  ```python
  # Before
  print(datetime.now())
  
  # After
  from datetime import datetime
  print(datetime.now())
  ```

- **Bare except** (E722): `except:`
  - Fix: Specify exception type
  ```python
  # Before
  try:
      something()
  except:
      pass
  
  # After
  try:
      something()
  except Exception as e:
      logger.error("Error", exc_info=e)
  ```

**View violations without fixing:**
```bash
ruff check  # Show all violations
ruff check --select=F401  # Show specific error code (F401 = unused imports)
```

##### Code Formatting (ruff-format / Black)

**Auto-format all files:**
```bash
ruff format
```

**Common issues:**
- **Inconsistent line length**: Automatically reformatted
- **Inconsistent quotes**: Converted to double quotes (Black style)
- **Indentation**: Auto-corrected to 4 spaces

**View formatting changes without applying:**
```bash
ruff format --diff  # Show what would change
```

**Examples of what ruff-format fixes:**
```python
# Before
x=1+2
y={  'a':1,'b':2  }
z="single quoted string"

# After
x = 1 + 2
y = {"a": 1, "b": 2}
z = "double quoted string"
```

##### Type Checking (mypy)

**Check types without fixing:**
```bash
mypy src  # Type check the src folder
```

**Common issues and fixes:**

- **Missing type annotation** (error: Function is missing a type annotation):
  ```python
  # Before
  def get_value(key):
      return config[key]
  
  # After
  def get_value(key: str) -> Any:
      return config[key]
  ```

- **Type mismatch** (error: Incompatible types):
  ```python
  # Before
  x: int = "hello"  # error: str incompatible with int
  
  # After
  x: str = "hello"
  ```

- **None type expected**:
  ```python
  # Before
  value: str = None  # error: Optional expected
  
  # After
  value: Optional[str] = None
  # or with Python 3.10+
  value: str | None = None
  ```

- **Undefined attribute**:
  ```python
  # Before
  obj.nonexistent_attr  # error: has no attribute
  
  # After: Check if attribute exists or add type hints
  if hasattr(obj, 'attr'):
      obj.attr
  ```

**Ignore specific errors (last resort):**
```python
# For single line
x = None  # type: ignore

# For entire function
@typing.no_type_check
def untyped_function():
    pass
```

**Check specific file:**
```bash
mypy src/agents/strands_graph_agent.py
```

##### Run All Checks

**Run pre-commit on all files locally:**
```bash
pre-commit run --all-files
```

**Output will show:**
- ✓ Passed hooks (green)
- ✗ Failed hooks (red) with error details
- Auto-fixed issues

**After fixes, re-run:**
```bash
pre-commit run --all-files  # Run again to verify all fixed
pre-commit run --all-files --show-diff  # Show what changed
```

##### Quick Reference

**All three commands are needed to fully fix pre-commit issues:**

| Task | Command | What It Fixes |
|------|---------|---------------|
| Fix linting errors | `ruff check --fix` | Unused imports, undefined names, bare excepts, etc. |
| Fix formatting issues | `ruff format` | Spacing, indentation, line length, quotes |
| Check type errors | `mypy src` | Type mismatches, missing annotations (manual fix required) |
| Run all checks | `pre-commit run --all-files` | Runs ruff, format, mypy, pytest together |
| View linting issues | `ruff check` | Show violations without fixing |
| Preview formatting changes | `ruff format --diff` | Show what would be changed |
| Ignore single type error | `x = y  # type: ignore` | Last resort for specific lines |
| Clear caches | `pre-commit clean` | Remove cached hook files |

##### Prevention Tips

**Best practice workflow:**
```bash
# 1. Make code changes
git add .

# 2. Run pre-commit checks
pre-commit run --all-files

# 3. Fix any issues (repeat until all pass)
# Auto-fixes happen automatically, fix type errors manually

# 4. Commit when clean
git commit -m "Add feature"

# 5. Push to branch
git push origin your-branch
```

### 5. Testing

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

Document loaders are standalone scripts in the `document-loaders/` directory. They load documents from various sources, embed them, and insert them into Milvus.

```python
# In document-loaders/load_my_source.py
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import Settings
from src.tools import MilvusVectorDB, OllamaClient
from document_loaders.core.embeddings import embed_documents

settings = Settings()
vector_db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port
)
ollama_client = OllamaClient(host=settings.ollama_host)

def load_my_documents():
    """Load documents from your source."""
    documents = []
    
    # Load from your source (files, APIs, databases, etc.)
    documents = [
        {"content": "Document text", "source": "my_source", "metadata": {...}}
    ]
    
    # Embed documents
    embeddings = embed_documents(documents, ollama_client)
    
    # Insert into Milvus
    vector_db.insert_embeddings(
        collection_name="my_collection",
        embeddings=embeddings,
        text_field=[d["content"] for d in documents],
        metadata_field=[d.get("metadata", {}) for d in documents]
    )

if __name__ == "__main__":
    load_my_documents()
```

See [load_milvus_docs_ollama.py](../document-loaders/load_milvus_docs_ollama.py) and [add_sample_docs.py](../document-loaders/add_sample_docs.py) for complete examples.

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
