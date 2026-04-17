# AWS Strands Agents RAG

A high-performance Retrieval-Augmented Generation (RAG) system using AWS Strands Agents, Ollama for local LLM/embeddings, and Milvus as a vector database.

**Key Features**: Strands framework integration • Local LLM (qwen2.5:0.5b) • Milvus vector DB • Semantic response caching • Web search integration • React UI • Docker deployment

## 📚 Documentation

| Category | Documents |
|----------|-----------|
| **🚀 Quick Start** | [Implementation Status](IMPLEMENTATION_STATUS.md) • [Setup Guide](docs/GETTING_STARTED.md#dual-mode-deployment-strands-local-and-agentcore-cloud) • [Developer Guide](docs/DEVELOPER_GUIDE.md) • [Infrastructure Status](docs/INFRASTRUCTURE_IMPLEMENTATION_STATUS.md) |
| **🏗️ Architecture** | [Complete Implementation](docs/IMPLEMENTATION_ARCHITECTURE.md) • [System Design](docs/ARCHITECTURE.md#dual-mode-architecture-strands-local-and-agentcore-cloud) • [Query Routing](docs/QUERY_ROUTING.md) |
| **👩‍💻 Development** | [API Reference](docs/DEVELOPER_GUIDE.md) • [Code Examples](docs/DEVELOPMENT.md) • [Strands Reference](docs/STRANDS_QUICK_REFERENCE.md) |
| **🛠️ Dev Tools** | [StrandsCoreAgent Overview](dev_tools/AGENT_OVERVIEW.md) • [Architecture & Integration](dev_tools/README.md) • [Technical Reference](dev_tools/DOCUMENTATION.md) |
| **⚡ Performance** | [Optimization Guide](docs/LATENCY_OPTIMIZATION.md) • [Model Comparison](docs/MODEL_PERFORMANCE_COMPARISON.md) • [Caching Strategy](docs/CACHING_STRATEGY.md) |
| **🚀 Deployment** | [Production Readiness](docs/PRODUCTION_READINESS.md) • [React UI](docs/REACT_DEPLOYMENT.md) • [AWS Architecture](docs/AWS_ARCHITECTURE.md) |
| **📋 Complete Index** | [All Documentation](docs/INDEX.md) |


> **Supports Dual-Mode Deployment:**
> - Strands (local/container) and AgentCore (cloud/serverless)
> - See [Getting Started: Dual-Mode](docs/GETTING_STARTED.md#dual-mode-deployment-strands-local-and-agentcore-cloud) and [Architecture: Dual-Mode](docs/ARCHITECTURE.md#dual-mode-architecture-strands-local-and-agentcore-cloud)

## Architecture Overview

```
┌──────────────────────┐
│  StrandsRAGAgent     │ ✅ Strands Agents Framework
│  (Strands-based)     │
└────────┬─────────────┘
         │
    ┌────┴──────┬──────────────┐
    │            │              │
┌───▼────┐  ┌───▼──────┐  ┌────▼────────┐
│ Ollama │  │ Milvus   │  │ Document    │
│(qwen   │  │ Vector   │  │ Loaders     │
│ 2.5)   │  │   DB     │  │             │
└────────┘  └──────────┘  └─────────────┘
```

**Components**:
- **StrandsGraphRAGAgent**: Graph-based 3-node RAG agent (Topic Check → Security Check → RAG Worker) with semantic response cache
- **Ollama** (qwen2.5:0.5b): Local LLM for generation and embeddings
- **Milvus**: Vector database for semantic search
- **MCP Server**: Model Context Protocol server for tool management

## How It Works

**Pipeline**: Documents → Embeddings → Milvus Vector Search → LLM Answer Generation

Semantic response caching provides <50ms cache hits for frequently asked questions.

### Data Flow Diagram

```mermaid
graph TD
    subgraph Index["🔧 INDEXING PIPELINE"]
        A["📄 Documents"] --> B["📥 Document Loaders"]
        B --> C["✂️ Split into Chunks"]
        C --> D["🧮 Generate Embeddings<br/>Ollama LLM"]
        D --> E["💾 Store in Milvus<br/>with metadata"]
    end

    subgraph Query["❓ QUERY PIPELINE - 3-Tier Architecture"]
        F["👤 User Question"]

        subgraph Tier1["Tier 1: Response Cache"]
            F --> G{"Semantic<br/>Match<br/>in Cache?"}
            G -->|YES<br/>99%+ similar| M1["✅ Return Cached<br/>Answer + Sources<br/>&lt;50ms"]
        end

        G -->|NO| H["🧮 Generate Embedding<br/>Ollama LLM"]
        H --> I["🔍 Vector Search<br/>Milvus HNSW"]

        subgraph Tier2["Tier 2: Knowledge Base"]
            I --> K["📋 Retrieve Top-K<br/>Chunks + Sources"]
            K --> L["💬 LLM Prompt<br/>Question + Context"]
            L --> N["✍️ Generate Answer<br/>with Sources"]
            N --> O["💾 Store in Cache"]
            O --> P["📤 Return Response<br/>1-2s"]
        end

        subgraph Tier3["Tier 3: Web Search (Opt-in)"]
            F2["👤 User Clicks 🌐"] --> W1["🌐 Tavily API<br/>Web Search"]
            W1 --> W2["✍️ Generate from<br/>Web Results"]
            W2 --> W3["📤 Return Response<br/>5-15s"]
        end

        M1 -.->|Short-circuit| P
    end

    E -.->|Stored vectors| I
    P --> Q["Done"]
    W3 --> Q

    style Tier1 fill:#c8e6c9
    style Tier2 fill:#bbdefb
    style Tier3 fill:#ffe0b2
    style Index fill:#e1f5ff
    style M1 fill:#4caf50,color:#fff
```

**3-Tier Performance:**
- **Tier 1 - Cache Hit**: <50ms (25-300x faster)
- **Tier 2 - Knowledge Base**: 1-2s (baseline)
- **Tier 3 - Web Search**: 5-15s (explicit user request)

## Advanced Features

### Connection Pooling & Timeouts
- **HTTP Connection Pooling**: Reuses connections to Ollama and Milvus for better performance
- **Configurable Timeouts**: Set request timeouts to prevent hanging on slow/down services
  - `OLLAMA_TIMEOUT`: Default 30 seconds
  - `MILVUS_TIMEOUT`: Default 30 seconds
- **Connection Pool Sizes**: Configure pool sizes via environment variables
  - `OLLAMA_POOL_SIZE`: Default 5 connections
  - `MILVUS_POOL_SIZE`: Default 10 connections

### Authentication
- **Milvus Authentication**: Configurable username and password via environment variables
  - `MILVUS_USER`: Default `root`
  - `MILVUS_PASSWORD`: Default `Milvus`

### Health Checks & Monitoring
Three health check endpoints for service monitoring:

```bash
# Basic health check
curl http://localhost:8000/health

# Detailed health check with service status
curl http://localhost:8000/health/detailed

# Service-specific health checks
curl http://localhost:8000/health/ollama
curl http://localhost:8000/health/milvus
```

### Asynchronous Operations
Non-blocking async methods for long-running operations:

```python
# Async answer generation
answer, sources = await agent.answer_question_async(
    collection_name="my_collection",
    question="What is Milvus?"
)

# Async context retrieval
context, sources = await agent.retrieve_context_async(
    collection_name="my_collection",
    query="Milvus features"
)

# Streaming responses for large answers
async for chunk in agent.stream_answer(
    collection_name="my_collection",
    question="Explain Milvus architecture"
):
    print(chunk, end="", flush=True)
```

Streaming support also available via API endpoint:
```bash
curl http://localhost:8000/v1/chat/completions/stream \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is Milvus?"}],
    "stream": true
  }'
```

## Quick Start

```bash
# 1. Start services
cd docker && ./optimize.sh --all && cd ..

# 2. Pull models
ollama pull qwen2.5:0.5b nomic-embed-text:v1.5

# 3. Install & run
pip install -e .
python api_server.py

# 4. Test
curl http://localhost:8000/health
```

👉 **[Full setup guide →](docs/GETTING_STARTED.md)**

## Project Structure

```
aws-strands-agents-rag/
├── src/agents/              # StrandsRAGAgent implementation
├── src/tools/               # Ollama & Milvus clients
├── src/config/              # Configuration management
├── dev_tools/               # StrandsCoreAgent for code/docs analysis
├── document-loaders/        # Document loading utilities
├── docker/                  # Docker Compose setup
├── tests/                   # Test suite
├── docs/                    # Detailed documentation
└── README.md                # This file
```

## Usage

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for:
- Basic RAG pattern and examples
- Custom tools and agents
- Advanced features (filtering, batch processing, async, metadata, etc.)
- Web search integration
- Entity validation and caching strategies

## Roadmap

**Todos:**
- [ ] Open Telemetry with SideSeat
- [ ] Grade agents with Strands Evals SDK or Langfuse
- [ ] Evaluate and Improve with Ragas
- [ ] Strands Agents AG-UI GUI integration
- [ ] Provide rich, interactive "mini-apps" or widgets with MCP-UI
- [ ] Red Teaming (Giskard / PromptFoo)
- [ ] Integrate pre-commit into GitHub pipeline
- [ ] Serverless deployment with AgentCore (Lambda, SAM, CloudFront)
- [ ] AgentCore SessionManager for conversation history caching
- [ ] Add new searches in the client cache list
- [X] Show a responses cache list to the web app users

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Resources

- [Strands Agents Documentation](https://strandsagents.com/latest/documentation/)
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
