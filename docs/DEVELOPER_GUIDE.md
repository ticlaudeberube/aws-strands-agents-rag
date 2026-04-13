# RAG System Developer Guide

## Quick Reference for Using & Extending the RAG System

### 🚀 Getting Started

#### 1. Basic Usage

```python
from src.agents.strands_graph_agent import StrandsGraphRAGAgent
from src.config.settings import Settings

# Initialize agent
settings = Settings()
agent = StrandsGraphRAGAgent(settings)

# Ask a question
answer, sources = agent.answer_question("What is Milvus vector indexing?")
print(f"Answer: {answer}")
print(f"Sources: {len(sources)} documents found")
```

#### 2. API Server Usage

```bash
# Start server
uv run python api_server.py

# Query via API
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": [{"text": "What is Milvus?"}]}],
    "model": "rag-agent",
    "top_k": 5
  }'
```

### 🔧 Core API Reference

#### StrandsGraphRAGAgent Methods

```python
class StrandsGraphRAGAgent:
    def answer_question(
        self,
        question: str,
        collection_name: str = "milvus_docs",
        top_k: int = 5
    ) -> Tuple[str, List[Dict]]:
        """Main RAG pipeline - question to answer with sources."""

    def retrieve_context(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5
    ) -> Tuple[str, List[Dict]]:
        """Just retrieval - get relevant context without generation."""

    def health_check(self) -> Dict[str, Any]:
        """Check system health and component status."""

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for monitoring."""
```

#### FastAPI Endpoints

```python
# Chat completion (OpenAI compatible)
POST /v1/chat/completions
{
    "messages": [{"role": "user", "content": [{"text": "question"}]}],
    "model": "rag-agent",
    "temperature": 0.1,
    "top_k": 5,
    "stream": false,
    "force_web_search": false
}

# List available models
GET /v1/models

# System health
GET /health
{
    "status": "healthy",
    "components": {"milvus": "healthy", "ollama": "healthy"},
    "uptime_seconds": 3600
}

# Performance metrics
GET /metrics
{
    "requests_total": 1250,
    "early_exit_rate": 65.4,
    "average_latency_ms": 324.5,
    "nodes": {"topic_check": {...}, "rag_worker": {...}}
}
```

### 🏗️ Extending the System

#### 1. Adding New Skills

```python
# src/agents/skills/my_custom_skill.py
from src.tools.tool_registry import ToolRegistry, ToolDefinition

class MyCustomSkill:
    """Custom skill for specialized functionality."""

    @staticmethod
    def register_tools(registry: ToolRegistry, agent) -> None:
        """Register custom tools with the system."""

        def my_custom_tool(query: str, param: int = 10) -> dict:
            """Custom tool implementation."""
            # Your custom logic here
            return {"result": f"Processed: {query}", "param": param}

        tool_def = ToolDefinition(
            name="my_custom_tool",
            description="Does custom processing on queries",
            func=my_custom_tool,
            skill_name="custom"
        )

        registry.register_tool(tool_def, node_names=["RAGWorker"])

# Register in __init__.py
from .my_custom_skill import MyCustomSkill
MyCustomSkill.register_tools(get_registry(), agent)
```

#### 2. Custom Node Configuration

```python
from src.agents.node_config import NodeConfig, NodeConfigManager

# Create custom configuration
CUSTOM_WORKER_CONFIG = NodeConfig(
    name="CustomWorker",
    model="llama3.1:70b",           # Larger model for complex tasks
    timeout_seconds=60,              # Longer timeout
    max_retries=5,
    enable_circuit_breaker=True,
    rate_limit_requests_per_minute=50  # Lower rate limit
)

# Apply at runtime
config_manager = NodeConfigManager()
config_manager.register(CUSTOM_WORKER_CONFIG)
```

#### 3. Custom Circuit Breakers

```python
from src.agents.circuit_breaker import CircuitBreaker

class CustomServiceCircuitBreaker(CircuitBreaker):
    """Circuit breaker for your custom service."""

    def __init__(self):
        super().__init__(
            name="CustomService",
            failure_threshold=3,         # Open after 3 failures
            success_threshold=2,         # Close after 2 successes
            timeout_seconds=45.0         # Test recovery after 45s
        )

# Usage
custom_breaker = CustomServiceCircuitBreaker()

try:
    result = custom_breaker.call(your_service_call, *args, **kwargs)
except CircuitBreakerOpen:
    # Handle service unavailable
    return fallback_response()
```

#### 4. Custom Metrics Collection

```python
from src.agents.node_metrics import NodeMetrics, GraphMetrics

# Create custom metrics
class CustomMetrics:
    def __init__(self):
        self.custom_counter = 0
        self.custom_timer = 0.0

    def record_custom_operation(self, duration_ms: float, success: bool):
        """Record custom operation metrics."""
        self.custom_counter += 1
        self.custom_timer += duration_ms

    def to_dict(self) -> dict:
        return {
            "custom_operations": self.custom_counter,
            "average_custom_time": self.custom_timer / max(1, self.custom_counter)
        }

# Integrate with system metrics
graph_metrics.custom_metrics = CustomMetrics()
```

### 🎛️ Configuration Patterns

#### Environment Variables

```python
# Custom settings in .env
CUSTOM_MODEL_ENDPOINT=http://localhost:8080
CUSTOM_TIMEOUT_SECONDS=30
ENABLE_CUSTOM_FEATURE=true

# Access in code
from src.config.settings import Settings
settings = Settings()
if settings.enable_custom_feature:
    # Use custom feature
    pass
```

#### Runtime Configuration Updates

```python
from src.agents.node_config import NodeConfigManager

# Update node config at runtime
config_manager = NodeConfigManager()
success = config_manager.update(
    node_name="RAGWorker",
    timeout_seconds=45,
    max_retries=5
)

if success:
    logger.info("Configuration updated successfully")
```

### 🔍 Monitoring & Debugging

#### Performance Monitoring

```python
# Get real-time metrics
metrics = agent.get_metrics()

print(f"Early exit rate: {metrics['early_exit_rate']:.1f}%")
print(f"Average latency: {metrics['average_latency_ms']:.1f}ms")

# Node-specific metrics
for node_name, node_metrics in metrics['nodes'].items():
    print(f"{node_name}: {node_metrics['success_rate']:.1f}% success rate")
```

#### Execution Tracing

```python
# Enable detailed tracing
from src.agents.graph_context import GraphContext, ExecutionTrace

context = GraphContext(question="test question")
# Execute pipeline...

# Analyze execution trace
trace = context.execution_trace
print(f"Total time: {trace.to_dict()['total_duration_ms']:.1f}ms")
print(f"Early exit: {trace.early_exit}")

for node_name, timing in trace.timings.items():
    print(f"{node_name}: {timing.duration_ms:.1f}ms")
```

#### Health Monitoring

```python
# Check system health
health = agent.health_check()

if health['status'] != 'healthy':
    for component, status in health['components'].items():
        if status != 'healthy':
            logger.warning(f"Component {component} is {status}")
```

### 🧪 Testing Patterns

#### Unit Tests

```python
import pytest
from src.agents.strands_graph_agent import StrandsGraphRAGAgent

@pytest.fixture
def test_agent():
    """Create test agent with mock dependencies."""
    return create_test_agent_with_mocks()

def test_topic_validation(test_agent):
    """Test topic checker behavior."""
    # Test in-scope question
    result = test_agent._topic_check_node({"question": "What is Milvus?"})
    assert result.is_valid

    # Test out-of-scope question
    result = test_agent._topic_check_node({"question": "What is Paris?"})
    assert not result.is_valid
    assert result.category == "out_of_scope"
```

#### Integration Tests

```python
@pytest.mark.integration
def test_end_to_end_pipeline():
    """Test complete RAG pipeline."""
    agent = StrandsGraphRAGAgent(test_settings)

    answer, sources = agent.answer_question("What is Milvus vector indexing?")

    assert answer is not None
    assert len(sources) > 0
    assert any("milvus" in s.get("text", "").lower() for s in sources)
```

#### Performance Tests

```python
@pytest.mark.performance
def test_early_exit_performance():
    """Test early exit optimization."""
    agent = StrandsGraphRAGAgent(test_settings)

    # Measure out-of-scope query (early exit)
    start = time.time()
    agent.answer_question("What is the weather?")
    early_exit_time = time.time() - start

    # Should be < 200ms (much faster than full pipeline)
    assert early_exit_time < 0.2
```

### 🚀 Common Usage Patterns

#### 1. Batch Processing

```python
questions = [
    "What is Milvus?",
    "How does vector indexing work?",
    "What are the benefits of RAG?"
]

results = []
for question in questions:
    answer, sources = agent.answer_question(question)
    results.append({
        "question": question,
        "answer": answer,
        "source_count": len(sources)
    })
```

#### 2. Custom Response Processing

```python
def process_rag_response(answer: str, sources: List[Dict]) -> dict:
    """Custom response processing."""

    # Extract metadata
    confidence_scores = [s.get("distance", 1.0) for s in sources]
    avg_confidence = 1.0 - (sum(confidence_scores) / len(confidence_scores))

    # Format sources
    formatted_sources = []
    for source in sources:
        formatted_sources.append({
            "title": source.get("metadata", {}).get("title", "Unknown"),
            "url": source.get("metadata", {}).get("url", ""),
            "relevance": 1.0 - source.get("distance", 1.0)
        })

    return {
        "answer": answer,
        "confidence": avg_confidence,
        "sources": formatted_sources,
        "source_count": len(sources)
    }
```

#### 3. Error Handling

```python
try:
    answer, sources = agent.answer_question(question)

    if not answer:
        return {"error": "No answer generated", "type": "generation_failed"}

    if not sources:
        return {"warning": "Answer generated without sources", "answer": answer}

    return {"answer": answer, "sources": sources}

except Exception as e:
    logger.error(f"RAG pipeline failed: {e}")
    return {
        "error": "RAG pipeline failed",
        "details": str(e),
        "type": "pipeline_error"
    }
```

### 📊 Performance Optimization Tips

#### 1. Model Selection

```python
# Fast models for validation (100-500M params)
VALIDATION_MODELS = ["qwen2.5:0.5b", "phi3:mini", "gemma2:2b"]

# Powerful models for generation (7B+ params)
GENERATION_MODELS = ["llama3.1:8b", "qwen2.5:14b", "mistral:7b"]
```

#### 2. Caching Strategy

```python
# Enable all caching layers
ENABLE_RESPONSE_CACHING=true      # Cache complete responses
ENABLE_EMBEDDING_CACHING=true     # Cache question embeddings
ENABLE_SEARCH_CACHING=true        # Cache search results
RESPONSE_CACHE_SIZE=1000          # Number of cached responses
```

#### 3. Concurrent Processing

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def process_questions_concurrently(questions: List[str], max_workers=5):
    """Process multiple questions concurrently."""

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        loop = asyncio.get_event_loop()

        tasks = [
            loop.run_in_executor(executor, agent.answer_question, question)
            for question in questions
        ]

        results = await asyncio.gather(*tasks)
        return results
```

### 🔧 Troubleshooting

#### Common Issues

1. **Milvus Connection Failed**
   ```bash
   # Check Milvus status
   cd docker && docker-compose ps

   # Restart Milvus
   docker-compose restart milvus-standalone
   ```

2. **Ollama Model Not Found**
   ```bash
   # List available models
   ollama list

   # Pull required models
   ollama pull qwen2.5:0.5b
   ollama pull nomic-embed-text
   ```

3. **High Latency**
   ```python
   # Check metrics
   metrics = agent.get_metrics()
   print(f"Early exit rate: {metrics['early_exit_rate']:.1f}%")

   # Should be >50% for good performance
   # If low, check question classification accuracy
   ```

4. **Memory Issues**
   ```python
   # Monitor memory usage
   import psutil

   memory = psutil.virtual_memory()
   print(f"Memory usage: {memory.percent}%")

   # If high, consider:
   # - Smaller models
   # - Reduced cache sizes
   # - Batch size limits
   ```

This developer guide provides the essential patterns and APIs for working with the RAG system. For detailed architecture information, see [`IMPLEMENTATION_ARCHITECTURE.md`](IMPLEMENTATION_ARCHITECTURE.md).
