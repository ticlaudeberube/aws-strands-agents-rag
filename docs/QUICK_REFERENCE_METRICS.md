# Quick Reference: Using Integrated Infrastructure

## Accessing Metrics from Your Application

### Via Python Code

```python
from src.agents.strands_graph_agent import graph_metrics

# Get all metrics
metrics = graph_metrics.get_metrics()
print(f"Total requests: {metrics['request_count']}")
print(f"Early exit rate: {metrics['early_exit_rate']:.1%}")

# Per-node metrics
for node_name, node_data in metrics.get('node_metrics', {}).items():
    print(f"{node_name}: {node_data['success_rate']:.1%} success rate")

# Example output:
# topic_check: 98.5% success rate
# security_check: 100.0% success rate
# rag_worker: 95.2% success rate
```

### Via API Endpoint

```bash
# Get current metrics
curl http://localhost:8000/metrics | python -m json.tool

# Reset metrics (starts fresh)
curl -X POST http://localhost:8000/metrics/reset

# Example response:
{
  "start_time": 1776045107.34975,
  "request_count": 42,
  "total_duration_ms": 62340.0,
  "error_count": 3,
  "early_exit_count": 15,
  "early_exit_rate": 0.357,
  "node_metrics": {
    "topic_check": {
      "node_name": "topic_check",
      "execution_count": 42,
      "success_count": 40,
      "failure_count": 2,
      "avg_duration_ms": 85.5,
      "success_rate": 0.952
    },
    "security_check": {
      "node_name": "security_check",
      "execution_count": 40,
      "success_count": 40,
      "failure_count": 0,
      "avg_duration_ms": 52.0,
      "success_rate": 1.0
    },
    "rag_worker": {
      "node_name": "rag_worker",
      "execution_count": 35,
      "success_count": 33,
      "failure_count": 2,
      "avg_duration_ms": 1250.0,
      "success_rate": 0.943
    }
  }
}
```

## Understanding Circuit Breaker States

### Healthy Milvus

```python
# Circuit breaker is CLOSED (normal state)
milvus_cb.is_open()  # Returns False
milvus_cb.record_success()  # Normal operation

# Queries flow through normally
documents = milvus_search(question="What is Milvus?")  # ✓ Returns results
```

### Milvus Experiencing Issues

```python
# After 5+ failures, circuit breaker transitions to OPEN
milvus_cb.is_open()  # Returns True
milvus_cb.state  # "OPEN"

# Further queries are rejected immediately
if milvus_cb.is_open():
    logger.warning("Milvus unavailable - skipping search")
    documents = []  # Fast-fail without attempting database call
```

### Recovery Phase

```python
# After 30 seconds (recovery_timeout), circuit breaker enters HALF_OPEN
milvus_cb.state  # "HALF_OPEN"

# Test query succeeds → circuit breaker closes
milvus_cb.record_success()
milvus_cb.state  # "CLOSED" - back to normal

# Test query fails → circuit breaker reopens
milvus_cb.record_failure()
milvus_cb.state  # "OPEN" - protection engages again
```

## Retry Behavior

### Automatic Retry on Transient Failures

```python
# Scenario: Ollama is temporarily overloaded
# Attempt 1: Fails (connection timeout)
# → Delays 500ms
# Attempt 2: Fails (temporary unavailable)
# → Delays 1000ms
# Attempt 3: Succeeds (Ollama recovered)
# → Returns answer

embedding = ollama_client.embed_text(question)  # Retried transparently
```

### Retry Exhaustion

```python
# Scenario: Embedding model permanently unavailable
# Attempt 1: Fails
# → Delays 500ms
# Attempt 2: Fails
# → Delays 1000ms
# Attempt 3: Fails
# → Delays 2000ms
# Attempt 4: Fails
# → Raises exception (max_retries exceeded)

# Exception propagates with context:
# src.agents.decorators.MaxRetriesExceededError:
#   Failed after 3 retries: Connection refused to Ollama
```

## Monitoring Guidelines

### What Success Rates Mean

```
Node Success Rate Interpretation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
topic_check:     98%+  = Normal (1-2% rejects out-of-scope queries)
                 < 80% = Possible keyword matching issue
                 < 50% = Bug suspected

security_check:  99%+  = Normal (< 1% security threat detections)
                 < 95% = Possible pattern matching issue
                 < 70% = Bug suspected

rag_worker:      90%+  = Healthy (some queries legitimately fail)
                 70-90% = Review answer generation issues
                 < 50% = Milvus/Ollama connection problems
```

### Alerting Rules

```python
# Example alerting logic (in monitoring system):

if metrics['early_exit_rate'] > 0.5:
    alert("High early exit rate - possible topic check issue")

if metrics['node_metrics']['rag_worker']['success_rate'] < 0.7:
    alert("RAG worker failing frequently - check Milvus/Ollama")

if metrics['error_count'] > 100:
    alert("High error count - system stability concern")

if metrics['request_count'] > 10000 and metrics['early_exit_rate'] < 0.3:
    alert("Low early exit rate - possible topic check too permissive")
```

## Advanced: Accessing Circuit Breaker Directly

```python
from src.agents.circuit_breaker import MilvusCircuitBreaker

# In custom code:
milvus_cb = MilvusCircuitBreaker(
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=30,      # Try recovery after 30 seconds
    success_threshold=2       # Close after 2 successes in HALF_OPEN
)

# Check state
if milvus_cb.is_open():
    log.warning("Circuit is open - Milvus unavailable")

# Manual state transitions
milvus_cb.record_success()  # Helps transition to CLOSED
milvus_cb.record_failure()  # Helps transition to OPEN
milvus_cb.reset()           # Manually reset to CLOSED (use carefully!)

# Check detailed state
state = milvus_cb.get_state()
# Returns: {"state": "CLOSED", "failures": 0, "successes": 0, ...}
```

## Configuration (Future)

When runtime configuration is activated:

```python
from src.agents.node_config import node_config_manager

# Update retry count for embedding generation
node_config_manager.update("topic_check", {
    "max_retries": 5,      # Increase from default 3
    "timeout_seconds": 10   # Increase from default 5
})

# Changes apply immediately (no restart needed)
```

## Troubleshooting

### High Circuit Breaker Trips

```
Symptom: milvus_cb.is_open() returning True frequently
Causes:
  - Milvus container crashed
  - Network connectivity issue
  - Milvus out-of-memory
  - High query load

Fix:
  1. Check Milvus container: docker ps | grep milvus
  2. Check logs: docker logs <milvus_container>
  3. Restart if needed: docker restart <milvus_container>
  4. Circuit breaker will auto-recover after recovery_timeout
```

### High Retry Rates

```
Symptom: Embeddings/generation frequently retry
Causes:
  - Ollama container overloaded
  - Network latency spike
  - Insufficient memory for model

Fix:
  1. Check Ollama status: ollama list
  2. Check system resources: free -h, top
  3. Reduce concurrent requests if possible
  4. Increase Ollama resources: docker update --memory=8g <container>
```

### Metrics Not Updating

```
Symptom: /metrics endpoint shows old data
Causes:
  - No requests since last reset
  - Metrics instance not global
  - API server not recording

Fix:
  1. Send a test request: curl -X POST http://localhost:8000/chat \
       -H "Content-Type: application/json" \
       -d '{"message":"test"}'
  2. Check metrics: curl http://localhost:8000/metrics
  3. If still old, reset: curl -X POST http://localhost:8000/metrics/reset
```

## Integration in Tests

```python
from src.agents.strands_graph_agent import graph_metrics
import pytest

@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test."""
    graph_metrics.reset()
    yield
    # Cleanup after test

def test_topic_check_metrics():
    """Verify metrics are recorded correctly."""
    # Reset first
    graph_metrics.reset()

    # Execute a query through the agent
    # ... (use agent.answer_question)

    # Check metrics were recorded
    metrics = graph_metrics.get_metrics()
    assert metrics['request_count'] > 0
    assert 'topic_check' in metrics['node_metrics']
    assert metrics['node_metrics']['topic_check']['execution_count'] > 0
```

---

**Last Updated**: April 12, 2026
**Status**: Tested and integrated into local Strands usage
