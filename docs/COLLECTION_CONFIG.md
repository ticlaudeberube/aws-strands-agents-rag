# Collection Configuration Guide

## Overview

The collection name used by the RAG system is configured via the `.env` file and is read consistently across all loaders and services.

## Configuration

### Setting Collection Name

Edit your `.env` file:

```env
# Collection Names
OLLAMA_COLLECTION_NAME=milvus_rag_collection
```

This collection name is used by:
- **Data Loader**: `document-loaders/load_milvus_docs_ollama.py` - creates the collection and loads documents
- **Sync Tool**: `document-loaders/sync_from_json.py` - syncs embeddings from JSON
- **Interactive Chat**: `chatbots/interactive_chat.py` - queries the collection
- **API Server**: `api_server.py` - queries the collection via REST API
- **RAG Agent**: `src/agents/rag_agent.py` - main retrieval logic

## How It Works

### Configuration Loading

The `Settings` class in `src/config/settings.py` loads environment variables from `.env`:

```python
class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Environment variables are case-insensitive
        extra='ignore'
    )
    # ... field definitions
    ollama_collection_name: str = "milvus_rag_collection"  # Default if not in .env
```

### Using in Loaders

```python
from src.config.settings import Settings

settings = Settings()
collection_name = settings.ollama_collection_name  # Reads from .env or uses default
```

## Workflow

### 1. Load Documents into Collection

```bash
# Make sure Milvus is running
cd ../milvus-standalone
docker-compose up -d

# Navigate back and run loader
cd ../aws-strands-agents-rag
python document-loaders/load_milvus_docs_ollama.py
```

**Output:**
```
📋 Configuration loaded:
   Collection name: milvus_rag_collection
   Database name: knowledge_base
   Milvus: localhost:19530
   Ollama: http://localhost:11434
   Embedding model: nomic-embed-text:v1.5

============================================================
RAG Data Loader - Milvus Documentation
============================================================

🗄️  Using Milvus database: 'knowledge_base'
📦 Target collection: 'milvus_rag_collection'
   (from env variable: OLLAMA_COLLECTION_NAME in .env)
```

The loader will:
- Create the collection if it doesn't exist
- Drop and recreate if it does exist (user prompted)
- Load documents and generate embeddings using Ollama
- Insert embeddings into Milvus

### 2. Query the Collection

```bash
# Interactive chat
python chatbots/interactive_chat.py

# Or start API server
python api_server.py
```

Both will use the collection name from `.env`:
- Read from `OLLAMA_COLLECTION_NAME`
- Default fallback: `milvus_rag_collection`

## Multiple Collections

To use multiple collections, you have options:

### Option 1: Use Different .env Files

```bash
# Create separate .env files
.env                    # Production config
.env.local             # Local testing
.env.staging           # Staging config

# Run with specific config
PYTHONENV=.env.staging python chatbots/interactive_chat.py
```

> Note: Pydantic Settings loads from `.env` by default. To use a different file, you need to modify the Settings class.

### Option 2: Different Databases

Instead of different collections, use different databases:

```env
# .env
LOADER_MILVUS_DB_NAME=knowledge_base_prod
OLLAMA_COLLECTION_NAME=documents

# .env.test
LOADER_MILVUS_DB_NAME=knowledge_base_test
OLLAMA_COLLECTION_NAME=documents
```

### Option 3: Dynamic Collection Selection

Modify `src/config/settings.py` to accept command-line arguments:

```python
import os
from typing import Optional

class Settings(BaseSettings):
    # ... existing config ...
    
    @classmethod
    def settings_customise_sources(
        cls,
        init_settings,
        env_settings,
        file_settings,
        user_settings,
        env_file,
        env_file_encoding,
    ):
        # Check for CLI override
        cli_collection = os.environ.get("CLI_COLLECTION_NAME")
        if cli_collection:
            return (
                init_settings,
                user_settings,
                env_settings,
                cli_collection,
                file_settings,
            )
        return (
            init_settings,
            user_settings,
            env_settings,
            file_settings,
        )
```

Then use:
```bash
CLI_COLLECTION_NAME=my_custom_collection python chatbots/interactive_chat.py
```

## Troubleshooting

### Collection Not Found

```bash
# Check what collections exist
python -c "
from src.tools import MilvusVectorDB
from src.config.settings import Settings

settings = Settings()
db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=settings.milvus_db_name
)
print('Collections:', db.list_collections())
"
```

### Collection Name Mismatch

Verify the collection name in your `.env`:
```bash
grep OLLAMA_COLLECTION_NAME .env
```

Ensure loader, API, and chat scripts read the same collection:
```bash
# Check what's actually being used
python -c "from src.config.settings import Settings; print(Settings().ollama_collection_name)"
```

### .env File Not Loaded

Ensure:
1. `.env` file exists in the project root
2. File is readable by your Python process
3. Variables are formatted correctly (no spaces around `=`)
4. Run from the project root directory

```bash
# Verify .env is present
ls -la .env

# Verify format
cat .env | grep OLLAMA_COLLECTION_NAME

# Verify from correct directory
pwd  # Should output project root
python document-loaders/load_milvus_docs_ollama.py
```

## Best Practices

1. **Always use `.env`** - Don't hardcode collection names in code
2. **Version control** - Add `.env` to `.gitignore`, commit `.env.example` instead
3. **Clear naming** - Use descriptive collection names (e.g., `milvus_docs`, `user_documents`, `product_catalog`)
4. **Document changes** - Update `.env.example` when adding new configuration options
5. **Verify before loading** - Always check collection name before running the loader

```bash
# Good practice workflow
cat .env | grep OLLAMA_COLLECTION_NAME  # Verify settings
python document-loaders/load_milvus_docs_ollama.py  # Load with verified config
```

## References

- [Settings Configuration](../src/config/settings.py)
- [Environment Variables](../.env.example)
- [Data Loaders](../document-loaders/)
- [Milvus Collections Guide](https://milvus.io/docs/manage_collections.md)
