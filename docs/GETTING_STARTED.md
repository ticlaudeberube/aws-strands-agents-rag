# Getting Started with AWS Strands Agents RAG

This guide will walk you through setting up and running the RAG system step-by-step.

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

## Step 2: Start Milvus Docker Services (Using Milvus-Standalone - Recommended)

The `milvus-standalone` folder contains an optimized Docker setup for local development.

Open a terminal and run:

```bash
# Navigate to milvus-standalone folder
cd ../milvus-standalone

# Start all services
docker-compose up -d

# Check status (should see services running)
docker-compose ps

# View logs (Ctrl+C to exit)
docker-compose logs -f
```

Expected output should include:
```
etcd              Up
minio             Up
milvus            Up
```

**Verify Milvus is running:**

```bash
# Check Milvus direct connection
curl http://localhost:19530

# Should respond (connection successful)
```

**Return to project root** for next steps:
```bash
cd ../aws-stands-agents-rag
```

**Alternative: Using Generic Docker Compose** (if milvus-standalone is not available)
```bash
# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Check status
docker-compose -f docker/docker-compose.yml ps

# View logs
docker-compose -f docker/docker-compose.yml logs -f milvus

# Verify health
curl http://localhost:9091/healthz

# Access UI: http://localhost:9091/webui/
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

In another terminal, pull the models:

```bash
# For LLM (text generation)
ollama pull mistral

# For embeddings
ollama pull all-minilm

# Optional: pull more models
ollama pull llama2
ollama pull nomic-embed-text
```

**Verify Ollama:**

```bash
# Check available models
ollama list

# Test a model
ollama run mistral "What is Python?"

# Check embedding model
ollama run all-minilm "test"
```

## Step 4: Configure Application

Edit `.env` file with your settings:

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

## Step 5: Start API Server

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

### Example 3: Load Your Own Documents

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
2. Use smaller models: Switch to `all-minilm` for embeddings
3. Reduce chunk size: In loaders, use `chunk_size=200`
4. Reduce top_k: Use `top_k=3` in queries

### Issue: "Model not found"

**Solution:**
```bash
# List available models
ollama list

# Pull missing model
ollama pull all-minilm

# Verify installation
ollama run all-minilm "test"
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

## Performance Tips

1. **Faster Embeddings**: Use `all-minilm` (fast but smaller dimension)
2. **Better Quality**: Use `nomic-embed-text` (slower but higher quality)
3. **Batch Processing**: Embed multiple documents at once
4. **Limit Search**: Use `top_k=3` for faster but less comprehensive results
5. **Chunk Size**: Smaller chunks = more search results, larger = fewer but longer

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
