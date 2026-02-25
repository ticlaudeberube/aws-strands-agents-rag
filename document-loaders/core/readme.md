# Core Package

The core package provides a modular interface for Milvus database operations with backward compatibility.

## Architecture

```
core/
├── __init__.py          # Package exports and MilvusUtils compatibility class
├── client.py            # Milvus client connection management
├── config.py            # Configuration management
├── databases.py         # Database operations (create, drop, list)
├── collections.py       # Collection operations (create, drop, insert, search)
├── embeddings.py        # Text embedding providers (HuggingFace, Ollama)
├── exceptions.py        # Custom exception classes
├── utils/               # Command-line utility scripts
└── mcp/                 # Model Context Protocol server
```

## Quick Start

```python
from core import MilvusUtils, get_client

# Legacy interface (recommended for existing code)
client = MilvusUtils.get_client()
MilvusUtils.create_collection("my_collection")
embeddings = MilvusUtils.embed_text("Hello world", provider="ollama")

# New modular interface
from core import get_client, create_collection, EmbeddingProvider
client = get_client()
create_collection("my_collection")
embeddings = EmbeddingProvider.embed_text("Hello world", provider="ollama")
```

## Modules

### client.py
Manages Milvus client connections with lazy initialization.

```python
from core import get_client, reset_client

client = get_client()  # Lazy initialization
reset_client()         # Reset for testing
```

### databases.py
Database lifecycle management.

```python
from core import create_database, drop_database, list_databases

create_database("my_db")
databases = list_databases()
drop_database("my_db")
```

### collections.py
Collection operations with flexible creation options.

```python
from core import create_collection, drop_collection, has_collection

# Auto-index collection (default)
create_collection("my_collection", dimension=1536)

# Schema-based collection (no auto-index)
create_collection("my_collection", dimension=1536, auto_index=False)

exists = has_collection("my_collection")
drop_collection("my_collection")
```

### embeddings.py
Unified embedding interface supporting multiple providers.

```python
from core import EmbeddingProvider

# HuggingFace embeddings
embeddings = EmbeddingProvider.embed_text("Hello", provider="huggingface")

# Ollama embeddings
embeddings = EmbeddingProvider.embed_text("Hello", provider="ollama")

# Batch processing
texts = ["Hello", "World"]
embeddings = EmbeddingProvider.embed_text(texts, provider="ollama")
```

### config.py
Configuration management with environment variable support.

```python
from core import get_milvus_config, get_embedding_config

milvus_config = get_milvus_config()  # URI, token
embedding_config = get_embedding_config()  # Provider, models
```

### exceptions.py
Custom exception hierarchy for better error handling.

```python
from core import MilvusConnectionError, DatabaseError, CollectionError, EmbeddingError

try:
    create_collection("test")
except CollectionError as e:
    print(f"Collection error: {e}")
```

## Utility Scripts

Located in `core/utils/` for command-line operations:

```bash
# Database operations
python core/utils/create_db.py my_database
python core/utils/drop_db.py my_database

# Collection operations
python core/utils/create_collection.py my_collection
python core/utils/drop_collection.py my_collection

# Index management
python core/utils/create_index.py my_collection
```

## MCP Server

Model Context Protocol server for external tool integration:

```bash
# Start MCP server
python core/mcp/milvus_server.py

# HTTP server for Docker
python core/mcp/http_server.py
```

See [MCP README](mcp/README.md) for detailed integration guide.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MILVUS_URI` | Milvus server URI | `http://localhost:19530` |
| `MILVUS_TOKEN` | Authentication token | `root:Milvus` |
| `EMBEDDING_PROVIDER` | Default provider | `huggingface` |
| `HF_EMBEDDING_MODEL` | HuggingFace model | - |
| `OLLAMA_EMBEDDING_MODEL` | Ollama model | - |

## Backward Compatibility

The `MilvusUtils` class provides full backward compatibility:

```python
from core import MilvusUtils

# All legacy methods work unchanged
client = MilvusUtils.get_client()
MilvusUtils.create_database("test")
MilvusUtils.create_collection("test_collection")
embeddings = MilvusUtils.embed_text("Hello", provider="ollama")

# Deprecated methods still supported
embeddings = MilvusUtils.embed_text_hf("Hello")  # Use embed_text instead
embeddings = MilvusUtils.embed_text_ollama("Hello")  # Use embed_text instead
```

## Error Handling

All operations use specific exception types:

```python
from core import MilvusConnectionError, DatabaseError, CollectionError

try:
    from core import get_client
    client = get_client()
except MilvusConnectionError:
    print("Failed to connect to Milvus")

try:
    from core import create_collection
    create_collection("test")
except CollectionError as e:
    print(f"Collection operation failed: {e}")
```

## Testing

The core package is fully tested with 17+ comprehensive tests:

```bash
# Run core tests
pytest Tests/test_milvus_utils.py -v

# Test with coverage
pytest Tests/test_milvus_utils.py --cov=core --cov-report=term-missing
```

## Migration Guide

### From Legacy MilvusUtils
No changes needed - backward compatibility maintained.

### To New Modular Interface
```python
# Old
from core import MilvusUtils
client = MilvusUtils.get_client()

# New
from core import get_client
client = get_client()
```

## Best Practices

1. **Use specific imports**: Import only what you need
2. **Handle exceptions**: Use specific exception types
3. **Environment config**: Use `.env` files for configuration
4. **Connection reuse**: Client connections are cached automatically
5. **Batch operations**: Use list inputs for multiple embeddings

## Dependencies

- `pymilvus`: Milvus Python SDK
- `sentence-transformers`: HuggingFace embeddings
- `ollama`: Ollama embeddings
- `torch`: Device detection
- `python-dotenv`: Environment management