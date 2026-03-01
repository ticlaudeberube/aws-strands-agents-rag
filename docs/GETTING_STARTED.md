# Getting Started with AWS Strands Agents RAG

This guide will walk you through setting up and running the StrandsRAGAgent RAG system step-by-step.

**Note**: This system uses **qwen2.5:0.5b** (500M parameters) as the optimal model, providing 85% faster inference compared to larger models while maintaining high-quality answers. See [Model Performance Comparison](MODEL_PERFORMANCE_COMPARISON.md) for detailed benchmarks.

## Features

- **Smart Caching**: Response cache with semantic similarity and entity validation
- **Cache Warmup**: 16 Q&A pairs pre-loaded on startup (ENABLE_CACHE_WARMUP=true)
- **Knowledge Base**: Milvus vector database for document retrieval
- **Opt-In Web Search**: Explicit globe icon (🌐) trigger, no automatic web search
- **Entity Validation**: Prevents cached cross-product responses

## Prerequisites Checklist

- [ ] Python 3.10 or higher installed
- [ ] Docker and Docker Compose installed
- [ ] Git (for cloning or version control)
- [ ] Internet connection (for downloading Docker images and Ollama models)
- [ ] At least 4GB of available RAM
- [ ] At least 5GB of disk space

## Step 1: Prepare Your Environment

### macOS/Linux

```bash
# Navigate to project directory
cd /path/to/aws-stands-agents-rag

# Make setup script executable
chmod +x setup.sh

# Run setup
./scripts/setup.sh 
```

### Windows

```bash
# Navigate to project directory
cd C:\path\to\aws-stands-agents-rag

# Run setup (requires PowerShell or CMD)
setup.bat
```

### Manual Setup

If you prefer to set up manually:

```bash
# Create Python environment
python3 -m venv venv

# Activate environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -e .
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
```

## Step 2: Start Milvus Docker Services (Optimized Setup)

This project includes an optimized Docker setup in the `./docker/` directory with automatic performance tuning. This is the recommended approach.

Open a terminal and run:

```bash
# Navigate to docker directory
cd docker

# Run optimization and start services (recommended for first time)
chmod +x optimize.sh
./optimize.sh --all

# This will:
# - Configure Docker daemon settings
# - Optimize system parameters (Linux)
# - Provide macOS setup recommendations
# - Start all services with proper resource allocation
# - Display service information
```

**Check status:**

```bash
# Verify services are running
docker-compose ps

# Expected output:
# NAME            COMMAND                  SERVICE   STATUS
# rag-etcd        "etcd -advertise-cli…"   etcd      Up (healthy)
# rag-minio       "minio server /minio…"   minio     Up (healthy)
# rag-milvus      "milvus run standalo…"   milvus    Up (healthy)
# rag-api         "python api_server.py"   rag-api   Up (healthy)
```

**Access services:**

```bash
# Milvus gRPC: localhost:19530
# Milvus WebUI: http://localhost:9091/webui
# MinIO Console: http://localhost:9001
# RAG API: http://localhost:8000

# Test connections
curl http://localhost:8000/health           # RAG API
curl http://localhost:9091/healthz          # Milvus
```

**Return to project root** for next steps:

```bash
cd ..
```

### Alternative: Quick Start (without optimizations)

If you just want to start services without optimization:

```bash
cd docker
docker-compose up -d
cd ..
```

### Alternative: Docker Compose Only

If you prefer not to use the optimization script:

```bash
# Direct docker-compose
cd docker
docker-compose up -d
docker-compose ps
curl http://localhost:19530
cd ..
```

## Step 3: Install and Start Ollama

### Download and Install

Visit [https://ollama.ai](https://ollama.ai) and download the installer for your OS.

### Pull Required Models

In a new terminal, ensure Ollama is running:

```bash
# Start Ollama server
ollama serve
```

In another terminal, pull the required models:

```bash
# For LLM - RECOMMENDED: qwen2.5:0.5b (optimized model)
ollama pull qwen2.5:0.5b

# For embeddings (REQUIRED)
ollama pull nomic-embed-text:v1.5
```

**Why qwen2.5:0.5b?**
- ✅ **85% faster** than larger models (8-15s vs 40-54s)
- ✅ **High quality answers** - generates comprehensive, accurate responses
- ✅ **Small footprint** - 500M parameters (14x smaller than 7B models)
- ✅ **Local inference** - runs efficiently on consumer hardware
- See [MODEL_PERFORMANCE_COMPARISON.md](MODEL_PERFORMANCE_COMPARISON.md) for full benchmarks

**Verify Ollama:**

```bash
# Check available models
ollama list

# Test the language model
ollama run qwen2.5:0.5b "What is Python?"

# Test the embedding model  
ollama run nomic-embed-text:v1.5 "test"
```

## Step 4: Configure Application

Edit `.env` file with your settings:

```env
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:0.5b              # ✅ Recommended: 85% faster, high quality
OLLAMA_EMBED_MODEL=nomic-embed-text:v1.5

# Milvus Configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DB_NAME=knowledge_base

# Collection Configuration
OLLAMA_COLLECTION_NAME=milvus_rag_collection

# Performance Settings
OLLAMA_NUM_THREADS=6              # Adjust based on your CPU
TOKENIZERS_PARALLELISM=false
MAX_CHUNK_LENGTH=400              # Optimal chunk size for retrieval
EMBEDDING_DIM=768
AGENT_CACHE_SIZE=500              # LRU cache size

# Application Configuration
LOG_LEVEL=INFO
API_PORT=8000

# Cache Configuration
# Enable/disable response cache warmup on startup (pre-loads Q&A pairs from data/responses.json)
# Set to false to skip cache warmup in development/testing environments
ENABLE_CACHE_WARMUP=true
```

**Key Configuration Notes:**
- **OLLAMA_MODEL**: Using `qwen2.5:0.5b` (500M parameters)
  - See [MODEL_PERFORMANCE_COMPARISON.md](MODEL_PERFORMANCE_COMPARISON.md) for benchmarks
  - Provides 85% faster inference than larger models
- **MILVUS_HOST**: Use "milvus" for Docker, "localhost" for local installation

## Step 5: Load Sample Documents

```bash
# Load sample Milvus documentation
python document-loaders/add_sample_docs.py

# Expected output:
# Initializing RAG Agent...
# ✓ Created collection 'milvus_rag_collection'
# ✓ Documents added successfully!
# ✓ Collection 'milvus_rag_collection' now has 6 documents
```

## Step 5a: Load Embeddings (Optional - For Faster Reloads)

If you've already processed documents and want to reload embeddings without reprocessing:

**Option 1: Load from Full Milvus Documentation**

Populate vector database with complete Milvus documentation:

```bash
python document-loaders/load_milvus_docs_ollama.py

# This will:
# - Download Milvus documentation
# - Generate embeddings for all documents
# - Store embeddings in Milvus
# - Cache embeddings to data/embeddings.json
# - Takes 5-15 minutes depending on hardware
```

**Option 2: Load Cached Embeddings (Fast Path)**

If embeddings have already been generated load them directly:

```bash
python document-loaders/load_embeddings_from_json.py

# This will:
# - Load pre-cached embeddings from data/embeddings.json
# - Import them into Milvus without reprocessing
# - Takes <1 minute (no embedding computation needed)
```

**When to use each option:**
- Use **Option 1** first time or when you have new documentation
- Use **Option 2** for faster reloads on subsequent runs
- Skip this step if you only want to use sample documents (Step 5)

## Step 6: Start API Server

```bash
# Start the OpenAI-compatible API server
python api_server.py

# Expected output:
# INFO:     Uvicorn running on http://127.0.0.1:8000
# INFO:     Application startup complete
```

## Step 6: Run Examples

### Example 1: Basic RAG

```bash
python examples/basic_rag.py
```

This example:
- Creates sample documents about Python
- Chunks them into smaller pieces
- Adds them to Milvus
- Asks 3 questions and shows answers

### Example 2: Interactive Chat

```bash
python examples/interactive_chat.py
```

Features:
- Interactive Q&A interface
- Type questions and get instant answers
- Type "exit" to quit
- Uses RAG to provide context-aware answers

### Example 3: React Web Chatbot

**Modern streaming-enabled web interface with globe icon for forced web search:**

```bash
# Navigate to React chatbot directory
cd chatbots/react-chatbot

# Install dependencies
npm install

# Start the development server
npm start

# Open http://localhost:3000 in your browser
```

**Features:**
- Beautiful modern web UI
- Real-time streaming responses
- 🌐 **Globe icon** - Click to force web-only search
- Source attribution (documents + web search results)
- Clean, intuitive interface

**Using the Globe Icon:**
1. Click the **🌐 globe icon** in the chat input area (toggles ON/OFF)
2. Icon changes color when active
3. Type your question
4. Press Send
5. System searches ONLY the web, ignores documentation

For detailed React chatbot documentation, see:
- [`chatbots/react-chatbot/README.md`](../chatbots/react-chatbot/README.md)
- [`docs/REACT_DEPLOYMENT.md`](./REACT_DEPLOYMENT.md) - Deployment options

### Example 4: Load Your Own Documents

Edit `examples/file_based_rag.py`:

```python
file_paths = [
    "/path/to/document1.txt",
    "/path/to/document2.md",
    # Add your paths here
]
```

Then run:

```bash
python examples/file_based_rag.py
```

## Troubleshooting

### Issue: "Ollama is not available"

**Solution:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not available:
# 1. Start Ollama: ollama serve
# 2. Check firewall settings
# 3. Verify OLLAMA_HOST in .env matches

# Common fix:
export OLLAMA_HOST=http://127.0.0.1:11434
ollama serve
```

### Issue: "Failed to connect to Milvus"

**Solution:**
```bash
# Check Docker services
docker-compose -f docker/docker-compose.yml ps

# Restart services
docker-compose -f docker/docker-compose.yml restart

# View detailed logs
docker-compose -f docker/docker-compose.yml logs --tail=100

# Clean restart (careful - removes data)
docker-compose -f docker/docker-compose.yml down -v
docker-compose -f docker/docker-compose.yml up -d
```

### Issue: "Memory error" or "Out of memory"

**Solutions:**
1. Reduce batch size: Change `BATCH_SIZE=5` in .env
2. Use smaller models: Switch to `nomic-embed-text:v1.5` for embeddings
3. Reduce chunk size: In loaders, use `chunk_size=200`
4. Reduce top_k: Use `top_k=3` in queries

### Issue: "Model not found"

**Solution:**
```bash
# List available models
ollama list

# Pull missing model
ollama pull nomic-embed-text:v1.5

# Verify installation
ollama run nomic-embed-text:v1.5 "test"
```

### Issue: Port already in use

**Solutions:**
```bash
# Find what's using the port (macOS/Linux)
lsof -i :11434  # Ollama
lsof -i :19530  # Milvus

# Kill the process
kill -9 <PID>

# Or use different port in .env and update docker-compose.yml
```

## Next Steps

1. **Add Your Documents**: Use `FileDocumentLoader` to load your own documents
2. **Customize Agent**: Modify `RAGAgent` to add custom tools and logic
3. **Deploy**: See Strands Agents documentation for deployment options
4. **Integrate with AWS**: Use AWS Bedrock for Claude models instead of Ollama
5. **Add Monitoring**: Implement logging and monitoring for production use

## Common Commands Reference

```bash
# View Milvus logs
docker-compose -f docker/docker-compose.yml logs -f milvus

# Stop all services
docker-compose -f docker/docker-compose.yml stop

# Restart services
docker-compose -f docker/docker-compose.yml restart

# Remove everything
docker-compose -f docker/docker-compose.yml down -v

# Test Python setup
python -c "import src; print('Setup OK')"

# Run with debug logging
LOG_LEVEL=DEBUG python examples/basic_rag.py

# Pull different model
ollama pull <model-name>

# Check Python version
python --version

# Update packages
pip install --upgrade -e .
```

## Performance Optimization

For detailed performance tuning guide, see [LATENCY_OPTIMIZATION.md](LATENCY_OPTIMIZATION.md).

**Quick Performance Tips:**

1. **Current Setup is Optimized**: Default Qwen + top_k=3 achieves 3-5s / <100ms cached
2. **For Even Faster**: Try `orca-mini` model (1-2s, lower quality)
3. **For Better Quality**: Use more context (`top_k=5`) and longer responses (`max_tokens=512`)
4. **Cache Warm-up**: Run `python document-loaders/sync_responses_cache.py` for <100ms responses
5. **Streaming**: Use `/v1/chat/completions/stream` endpoint for progressive results
6. **Disable Logging**: Set `LOG_LEVEL=WARNING` in .env for production

**Performance Metrics:**
- First Query: 3-5 seconds (5.6-9.3x faster than baseline)
- Cached Query: <100ms (instant)
- Model: neural-chat (2-3s generation)
- Context: top_k=3 (3 chunks per query)

## Architecture Diagrams

```
┌─────────────────────────────────────────────────────┐
│         AWS Strands Agents RAG System               │
└─────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
    ┌───▼────┐         ┌──▼──────┐      ┌───▼──────┐
    │ Ollama │         │ Milvus  │      │ Documents│
    │ (LLM & │         │ (Vector │      │ (Files/  │
    │ Embed) │         │  DB)    │      │  URLs)   │
    └───┬────┘         └──┬──────┘      └───┬──────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                   ┌───────▼────────┐
                   │   RAG Agent    │
                   │ (Strands Agent)│
                   └────────────────┘
                           │
                   ┌───────▼────────┐
                   │  User Query    │
                   └────────────────┘
```

## Success Checklist

After completing setup:

- [ ] Python environment is activated
- [ ] `.env` file is configured
- [ ] Milvus containers are running (`docker-compose ps`)
- [ ] Ollama is running and models are pulled (`ollama list`)
- [ ] `python api_server.py` starts successfully on http://localhost:8000
- [ ] `python examples/basic_rag.py` completes successfully
- [ ] `python examples/interactive_chat.py` responds to questions

If all items are checked, your RAG system is ready to use! 🎉

## Getting Help

- Check [README.md](README.md) for more detailed documentation
- Review example scripts in `examples/` folder
- Check [Strands Agents Docs](https://strandsagents.com/latest/documentation/)
- Review logs with increased `LOG_LEVEL=DEBUG`
- Check Docker logs: `docker-compose logs -f`

---

**Happy Building! 🚀**
