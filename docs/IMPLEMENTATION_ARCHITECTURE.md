# RAG System Implementation Architecture

## Overview

This document provides comprehensive documentation of the AWS Strands Agents RAG (Retrieval-Augmented Generation) system implementation. The system implements a sophisticated 3-node agent architecture using the Strands framework with production-grade infrastructure components.

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI API Server                          │
│                    (OpenAI Compatible)                         │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│              StrandsGraphRAGAgent                               │
│              (3-Node Pipeline)                                 │
│                                                                │
│  Node 1: TopicChecker     Node 2: SecurityChecker            │
│  - Fast model (~100ms)    - Fast model (~100ms)               │
│  - Scope validation       - Attack detection                  │
│  - Early exit pattern     - Pattern matching                  │
│                                                                │
│                    Node 3: RAGWorker                          │
│                    - Powerful model (~1500ms)                 │
│                    - Vector search + generation               │
│                    - Full RAG pipeline                        │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│                Infrastructure Layer                            │
│  - Circuit Breakers    - Metrics & Monitoring                 │
│  - Retry Logic        - Configuration Management              │
│  - Rate Limiting      - Tool Registry                         │
│  - Execution Tracing  - Response Caching                      │
└─────────┬───────────────────────────┬───────────────────────────┘
          │                           │
┌─────────▼─────────┐       ┌─────────▼─────────┐
│  Milvus Vector DB │       │   Ollama LLM      │
│  - Document Store │       │   - Local Models  │
│  - Vector Search  │       │   - Embeddings    │
│  - Embeddings     │       │   - Generation    │
└───────────────────┘       └───────────────────┘
```

## Core Components

### 1. StrandsGraphRAGAgent (Primary Agent System)

**Location:** `src/agents/strands_graph_agent.py`

The main RAG agent implementing a 3-node conditional routing architecture:

#### Node Architecture

```python
class StrandsGraphRAGAgent:
    """Graph-based RAG agent with 3-node pipeline."""

    def __init__(self, settings: Settings):
        # Initialize infrastructure
        self.graph_metrics = GraphMetrics()
        self.circuit_breaker = MilvusCircuitBreaker()
        self.tool_registry = ToolRegistry()

    def answer_question(self, question: str) -> Tuple[str, List[Dict]]:
        """Execute 3-node pipeline with early exit optimization."""
        context = GraphContext(question=question)

        # Node 1: Topic validation (fast exit if out-of-scope)
        if not self._topic_check_node(context):
            return self._create_rejection_response("out_of_scope")

        # Node 2: Security validation (fast exit if malicious)
        if not self._security_check_node(context):
            return self._create_rejection_response("security_threat")

        # Node 3: RAG worker (expensive operation, only if validated)
        return self._rag_worker_node(context)
```

#### Cost Optimization Benefits

```
Query Type           Path                                  Latency   Cost Savings
──────────────────────────────────────────────────────────────────────────────
Out-of-scope         TopicChecker → Early Exit            ~100ms    ~70% savings
Security threat      TopicChecker → SecurityChecker → Exit ~150ms    ~60% savings
Valid & safe query   All 3 nodes → Full RAG               ~1750ms   Full cost
```

### 2. Infrastructure Components

#### Circuit Breaker System (`src/agents/circuit_breaker.py`)

Protects against cascading failures when external services fail:

```python
class MilvusCircuitBreaker(CircuitBreaker):
    """Specialized circuit breaker for Milvus operations."""

    def __init__(self):
        super().__init__(
            name="Milvus",
            failure_threshold=5,     # Open after 5 failures
            success_threshold=3,     # Close after 3 successes
            timeout_seconds=30.0     # Test recovery after 30s
        )

# Usage in agent
try:
    results = milvus_circuit_breaker.call(
        vector_db.search, query_embedding, limit=top_k
    )
except CircuitBreakerOpen:
    # Graceful degradation - web search fallback
    return fallback_response()
```

**States:**
- **CLOSED** (Normal): All calls pass through
- **OPEN** (Failed): All calls rejected, service in cooldown
- **HALF_OPEN** (Testing): Limited calls to test recovery

#### Performance Decorators (`src/agents/decorators.py`)

```python
@retry_with_backoff(max_attempts=3, base_delay=0.1)
@rate_limit(max_requests=100, window_seconds=60)
@sanitize_input(max_length=5000)
def milvus_search(question: str) -> Dict:
    """Vector search with resilience patterns."""
    # Implementation with automatic retry and rate limiting
```

**Available decorators:**
- `@retry_with_backoff` - Exponential backoff retry
- `@rate_limit` - Token bucket rate limiting
- `@sanitize_input` - Input validation and truncation
- `@retry_async` - Async version for async functions

#### Execution Context (`src/agents/graph_context.py`)

Typed context passed through the 3-node pipeline:

```python
@dataclass
class GraphContext:
    """Execution context with state tracking."""

    # Input
    question: str
    collection_name: str = "milvus_docs"
    top_k: int = 5

    # Node results
    topic_result: Optional[ValidationResult] = None
    security_result: Optional[ValidationResult] = None
    retrieval_result: Optional[Dict] = None

    # Tracing
    execution_trace: ExecutionTrace = field(default_factory=ExecutionTrace)

    def should_skip_rag_worker(self) -> bool:
        """Check if execution should skip RAG worker (early exit)."""
        if self.topic_result and not self.topic_result.is_valid:
            return True
        if self.security_result and not self.security_result.is_valid:
            return True
        return False
```

#### Performance Metrics (`src/agents/node_metrics.py`)

Real-time performance tracking for monitoring and optimization:

```python
class NodeMetrics:
    """Per-node execution metrics."""

    def __init__(self, node_name: str):
        self.node_name = node_name
        self.execution_count = 0
        self.total_duration_ms = 0.0
        self.error_count = 0

    @property
    def success_rate(self) -> float:
        return ((self.execution_count - self.error_count) / self.execution_count) * 100

class GraphMetrics:
    """System-wide performance metrics."""

    def __init__(self):
        self.request_count = 0
        self.early_exit_count = 0
        self.node_metrics: Dict[str, NodeMetrics] = {}

    @property
    def early_exit_rate(self) -> float:
        """Percentage of requests that exited early (cost optimization)."""
        return (self.early_exit_count / self.request_count) * 100
```

#### Tool Registry (`src/agents/tool_registry.py`)

Centralized management of tools and skills:

```python
class ToolRegistry:
    """Central registry for agent tools and skills."""

    def register_tool(self, tool: ToolDefinition, node_names: List[str]):
        """Register tool and assign to specific nodes."""
        self._tools[tool.name] = tool
        for node_name in node_names:
            self.assign_tool_to_node(node_name, tool.name)

    def get_tools_for_node(self, node_name: str) -> List[ToolDefinition]:
        """Get all enabled tools for a specific node."""
        return [t for t in self._node_tools.get(node_name, []) if t.enabled]
```

#### Configuration Management (`src/agents/node_config.py`)

Runtime configuration for each node:

```python
@dataclass
class NodeConfig:
    """Configuration for a single graph node."""

    name: str
    model: str
    timeout_seconds: int
    max_retries: int
    enable_circuit_breaker: bool = True
    rate_limit_requests_per_minute: Optional[int] = None

# Preset configurations
TOPIC_CHECKER_CONFIG = NodeConfig(
    name="TopicChecker",
    model="qwen2.5:0.5b",           # Fast model
    timeout_seconds=5,
    max_retries=2,
    rate_limit_requests_per_minute=1000
)

RAG_WORKER_CONFIG = NodeConfig(
    name="RAGWorker",
    model="llama3.1:8b",            # Powerful model
    timeout_seconds=30,
    max_retries=3,
    rate_limit_requests_per_minute=100
)
```

### 3. API Server (`api_server.py`)

FastAPI server providing OpenAI-compatible endpoints:

#### Key Endpoints

```python
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions with RAG."""

@app.get("/v1/models")
async def list_models():
    """List available models."""

@app.get("/health")
async def health_check():
    """System health and component status."""

@app.get("/metrics")
async def get_metrics():
    """Performance metrics and monitoring data."""
```

#### Request/Response Format

**Request:**
```python
class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = "rag-agent"
    temperature: Optional[float] = 0.1
    top_k: Optional[int] = None         # RAG-specific
    stream: Optional[bool] = False
    force_web_search: Optional[bool] = False  # Skip cache
```

**Response:**
```python
{
    "id": "chatcmpl-...",
    "object": "chat.completion",
    "model": "rag-agent",
    "choices": [{
        "message": {
            "role": "assistant",
            "content": "Generated answer...",
            "timing": {
                "total_time_ms": 1247.5,
                "response_type": "rag",
                "is_cached": false
            },
            "sources": [...]
        }
    }],
    "execution_trace": {
        "early_exit": false,
        "nodes": {
            "topic_check": {"duration_ms": 89.2, "success": true},
            "security_check": {"duration_ms": 105.7, "success": true},
            "rag_worker": {"duration_ms": 1052.6, "success": true}
        }
    }
}
```

### 4. Skills Framework (`src/agents/skills/`)

Modular skill system for specialized capabilities:

#### Available Skills

1. **RetrievalSkill** - Vector database search
2. **AnswerGenerationSkill** - LLM-based answer generation
3. **DocumentationSkill** - Technical documentation analysis
4. **ProgrammingSkill** - Code analysis and generation
5. **KnowledgeBaseSkill** - Knowledge base management

#### Skill Registration

```python
# Auto-registration in __init__.py
from .retrieval_skill import RetrievalSkill
from .answer_generation_skill import AnswerGenerationSkill

# Skills are automatically registered with the tool registry
registry = get_registry()
RetrievalSkill.register_tools(registry, agent)
AnswerGenerationSkill.register_tools(registry, agent)
```

### 5. MCP Integration (`src/mcp/mcp_server.py`)

Model Context Protocol server for external tool exposure:

```python
class RAGAgentMCPServer:
    """MCP server exposing RAG tools to external agents."""

    def __init__(self, settings: Settings):
        self.strands_agent = StrandsGraphRAGAgent(settings)
        self.registry = get_registry()

    async def handle_tool_call(self, name: str, arguments: dict) -> dict:
        """Handle external tool invocations."""
        tool = self.registry.get_tool(name)
        return await tool.invoke(**arguments)
```

## Data Flow

### 1. Question Processing Pipeline

```
1. API Request → ChatCompletionRequest
2. Extract question from messages
3. Create GraphContext with question + config
4. Execute 3-node pipeline:

   ┌─────────────────────┐
   │   Topic Checker     │ ← Fast model (qwen2.5:0.5b)
   │   - Keyword match   │   ~100ms, early exit if out-of-scope
   │   - Scope validate  │
   └─────────┬───────────┘
             │ if valid
   ┌─────────▼───────────┐
   │  Security Checker   │ ← Fast model (qwen2.5:0.5b)
   │  - Attack detect    │   ~100ms, early exit if malicious
   │  - Pattern match    │
   └─────────┬───────────┘
             │ if safe
   ┌─────────▼───────────┐
   │    RAG Worker       │ ← Powerful model (llama3.1:8b)
   │  - Vector search    │   ~1500ms, full RAG pipeline
   │  - Answer generate  │
   └─────────────────────┘

5. Format response with sources + timing
6. Return OpenAI-compatible response
```

### 2. Vector Search Flow

```
1. Question → Embedding generation (Ollama)
2. Embedding → Vector search (Milvus)
3. Results → Context formatting
4. Context + Question → Answer generation (Ollama)
5. Answer + Sources → Response formatting
```

### 3. Caching Strategy

**Multi-layer caching for performance:**

1. **Embedding Cache** - Reuse embeddings for identical questions
2. **Search Results Cache** - Cache vector search results
3. **Response Cache** - Cache complete responses for common questions
4. **Semantic Response Cache** - Cache responses for semantically similar questions

## Configuration

### Environment Variables (`.env`)

```bash
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:0.5b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_TEMPERATURE=0.1
OLLAMA_MAX_TOKENS=2000

# Milvus Configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DB_NAME=milvus_rag
MILVUS_USER=root
MILVUS_PASSWORD=Milvus

# Performance Settings
ENABLE_RESPONSE_CACHING=true
ENABLE_EMBEDDING_CACHING=true
ENABLE_CACHE_WARMUP=true
RESPONSE_CACHE_SIZE=1000

# API Settings
API_HOST=0.0.0.0
API_PORT=8000
API_TIMEOUT=300

# Web Search (Optional)
TAVILY_API_KEY=your_key_here
ENABLE_WEB_SEARCH_SUPPLEMENT=true
```

### Node Configuration

```python
# Fast models for validation nodes
TOPIC_CHECKER_CONFIG = NodeConfig(
    model="qwen2.5:0.5b",
    timeout_seconds=5,
    max_retries=2,
    rate_limit_requests_per_minute=1000
)

# Powerful models for generation
RAG_WORKER_CONFIG = NodeConfig(
    model="llama3.1:8b",
    timeout_seconds=30,
    max_retries=3,
    rate_limit_requests_per_minute=100
)
```

## Performance Characteristics

### Latency Optimization

**Cost-optimized routing with early exit patterns:**

| Query Type | Validation Path | Avg Latency | Cost Reduction |
|------------|----------------|-------------|----------------|
| Out-of-scope | TopicChecker only | ~100ms | ~70% |
| Security threat | Topic + Security | ~150ms | ~60% |
| Valid query | All 3 nodes | ~1750ms | 0% (full cost) |

**Result:** 60-70% cost reduction on invalid/malicious queries

### Memory Usage

- **Base system:** ~200MB RAM
- **With models loaded:** ~2-4GB RAM (depends on model size)
- **Milvus:** ~500MB-2GB (depends on collection size)

### Throughput

- **Validation nodes:** 1000+ requests/minute
- **RAG worker:** 100-200 requests/minute
- **Overall system:** 300-500 requests/minute (with early exits)

## Monitoring & Observability

### Metrics Collection

```python
# Node-level metrics
{
    "topic_check": {
        "execution_count": 1250,
        "average_duration_ms": 87.3,
        "success_rate": 99.2,
        "error_count": 10
    },
    "rag_worker": {
        "execution_count": 432,
        "average_duration_ms": 1247.8,
        "success_rate": 98.6,
        "total_tokens": 245670
    }
}

# System-wide metrics
{
    "requests_total": 1250,
    "early_exit_rate": 65.4,          # 65.4% avoided expensive RAG
    "average_latency_ms": 324.5,      # Average including early exits
    "success_rate": 99.1,
    "uptime_seconds": 86400
}
```

### Health Monitoring

```bash
# Health check endpoint
GET /health

{
    "status": "healthy",
    "components": {
        "strands_agent": "healthy",
        "milvus": "healthy",
        "ollama": "healthy",
        "mcp_server": "healthy"
    },
    "metrics": {
        "uptime_seconds": 3600,
        "requests_processed": 1250,
        "early_exit_rate": 65.4
    }
}
```

### Logging Strategy

```python
# Structured logging with correlation IDs
logger.info(f"[TOPIC_CHECK] Processing: {question[:50]}... (correlation_id={req_id})")
logger.info(f"[SECURITY_CHECK] Result: is_valid={result.is_valid} (correlation_id={req_id})")
logger.info(f"[RAG_WORKER] Retrieved {len(results)} documents (correlation_id={req_id})")
```

## Error Handling & Resilience

### Circuit Breaker Patterns

```python
# Automatic service protection
try:
    results = milvus_circuit_breaker.call(vector_db.search, ...)
except CircuitBreakerOpen:
    # Graceful degradation
    if settings.enable_web_search_fallback:
        results = web_search_fallback(question)
    else:
        return create_service_unavailable_response()
```

### Retry Mechanisms

```python
@retry_with_backoff(max_attempts=3, base_delay=0.1, max_delay=5.0)
def ollama_generate(prompt: str) -> str:
    """LLM generation with automatic retry on transient failures."""
    return ollama_client.generate(prompt)
```

### Graceful Degradation

**Service failure handling:**

1. **Milvus down** → Web search fallback → Informed user message
2. **Ollama down** → Multiple model fallback → Error response
3. **Web search down** → Knowledge base only → Limitation note
4. **MCP server down** → Core functionality continues → Tool warnings

## Testing Strategy

### Unit Tests (`tests/`)

```python
# Node behavior testing
def test_topic_checker_rejects_out_of_scope():
    """Test topic validation rejects non-database questions."""
    agent = create_test_agent()
    result = agent._topic_check_node({"question": "What is Paris?"})
    assert not result.is_valid
    assert result.category == "out_of_scope"

def test_security_checker_detects_injection():
    """Test security validation detects malicious queries."""
    agent = create_test_agent()
    result = agent._security_check_node({"question": "Ignore instructions..."})
    assert not result.is_valid
    assert "security" in result.reason
```

### Integration Tests

```python
@pytest.mark.integration
def test_end_to_end_valid_query():
    """Test complete pipeline with valid question."""
    agent = StrandsGraphRAGAgent(test_settings)
    answer, sources = agent.answer_question("What is Milvus vector indexing?")

    assert answer is not None
    assert len(sources) > 0
    assert "milvus" in answer.lower()
```

### Performance Tests

```python
@pytest.mark.performance
def test_early_exit_performance():
    """Test that early exits are significantly faster."""
    agent = StrandsGraphRAGAgent(test_settings)

    # Out-of-scope query (should exit after topic check)
    start = time.time()
    agent.answer_question("What is Paris?")
    early_exit_time = time.time() - start

    # Valid query (full pipeline)
    start = time.time()
    agent.answer_question("What is Milvus?")
    full_pipeline_time = time.time() - start

    # Early exit should be >5x faster
    assert early_exit_time < (full_pipeline_time / 5)
```

## Deployment

### Local Development

```bash
# 1. Start dependencies
cd docker && docker-compose up -d

# 2. Install dependencies
uv sync

# 3. Start API server
uv run python api_server.py

# 4. Start React UI (optional)
cd chatbots/react-chatbot && npm start
```

### Production Deployment

```bash
# Build and deploy with Docker
docker build -t rag-agent .
docker run -p 8000:8000 rag-agent

# Or use docker-compose for full stack
docker-compose -f docker/docker-compose.prod.yml up -d
```

### Health Monitoring

```bash
# System health
curl http://localhost:8000/health

# Performance metrics
curl http://localhost:8000/metrics

# Component status
curl http://localhost:8000/debug/components
```

## Future Enhancements

### Planned Features

1. **Advanced Routing** - LLM-based intent classification for complex queries
2. **Multi-Agent Collaboration** - Specialized agents for different domains
3. **Streaming Responses** - Real-time response streaming for better UX
4. **Model Auto-Selection** - Dynamic model selection based on query complexity
5. **Advanced Caching** - Semantic similarity caching with vector embeddings
6. **Distributed Deployment** - Multi-instance deployment with load balancing

### Scalability Improvements

1. **Horizontal Scaling** - Load balancer + multiple API instances
2. **Model Serving** - Dedicated model serving infrastructure (vLLM, TGI)
3. **Vector Database Sharding** - Distributed vector storage
4. **Async Processing** - Background task queue for expensive operations

## Appendix

### File Structure

```
src/
├── agents/
│   ├── circuit_breaker.py      # Service resilience patterns
│   ├── decorators.py           # Performance & resilience decorators
│   ├── graph_context.py        # Execution context & tracing
│   ├── node_config.py          # Runtime configuration management
│   ├── node_metrics.py         # Performance metrics & monitoring
│   ├── tool_registry.py        # Tool management & registration
│   ├── strands_graph_agent.py  # Main 3-node RAG agent
│   ├── strands_graph_agent.py    # Production 3-node RAG agent
│   └── skills/                 # Modular skill implementations
├── config/
│   └── settings.py             # Configuration management
├── mcp/
│   └── mcp_server.py           # Model Context Protocol server
└── tools/
    ├── milvus_client.py        # Vector database client
    ├── ollama_client.py        # LLM client
    └── tool_registry.py        # Global tool registry

api_server.py                   # FastAPI server (main entry point)
chatbots/                       # UI implementations
tests/                          # Comprehensive test suite
docs/                           # Documentation
```

### Key Design Patterns

1. **3-Node Pipeline** - Specialized agents with early exit optimization
2. **Circuit Breaker** - Service resilience and graceful degradation
3. **Decorator Pattern** - Cross-cutting concerns (retry, rate limit, metrics)
4. **Registry Pattern** - Dynamic tool and skill management
5. **Context Object** - Typed execution state management
6. **Strategy Pattern** - Pluggable response caching strategies
7. **Observer Pattern** - Event-driven metrics collection
