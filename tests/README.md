# Testing Guide

This directory contains the test suite for the AWS Strands Agents RAG system.

**Status**: ✅ All 77 tests passing (100% pass rate)  
**Coverage**: 48% (619/1303 statements)  
**Last Updated**: March 5, 2026

## Test Suite Overview

| File | Tests | Purpose |
|------|-------|---------|
| **test_strands_graph_agent.py** | 41 | Core graph agent (security, scope, RAG) |
| **test_api_server.py** | 11 | FastAPI server endpoints |
| **test_configuration_consistency.py** | 14 | Configuration and settings validation |
| **test_ollama_client.py** | 10 | Ollama LLM client operations |
| **test_web_search_streaming.py** | 1 | Web search integration |

## Setup

### Install Test Dependencies

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Or using uv
uv pip install -r requirements-test.txt
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Tests with Coverage Report

```bash
pytest --cov=src --cov-report=html --cov-report=term
```

### Run Specific Test File

```bash
pytest tests/test_rag_agent.py
```

### Run Specific Test Class

```bash
pytest tests/test_rag_agent.py::TestRAGAgentInit
```

### Run Specific Test

```bash
pytest tests/test_rag_agent.py::TestRAGAgentInit::test_init_with_settings
```

### Run Tests in Parallel

```bash
pytest -n auto  # Uses all CPU cores
pytest -n 4     # Uses 4 workers
```

### Run Tests with Timeout

```bash
pytest --timeout=10  # 10 second timeout per test
```

### Run Only Unit Tests

```bash
pytest -m unit
```

### Run Only Integration Tests (when available)

```bash
pytest -m integration
```

### Run Async Tests Only

```bash
pytest -m async
```

## Test Structure

```
tests/
├── __init__.py                           # Package marker
├── conftest.py                           # Shared fixtures and configuration
├── README.md                             # This file
├── test_strands_graph_agent.py          # Graph agent core tests (41 tests)
├── test_api_server.py                   # API server endpoint tests (11 tests)
├── test_configuration_consistency.py    # Configuration validation tests (14 tests)
├── test_ollama_client.py               # OllamaClient tests (10 tests)
└── test_web_search_streaming.py        # Web search integration test (1 test)
```

**Removed Files (Deprecated)**:
- `test_security.py` - Old monolithic agent tests (merged into test_strands_graph_agent.py)
- `test_rag_agent.py` - Old monolithic agent tests (replaced by graph agent tests)
- `test_comparative_detection.py` - Tested method not in new architecture

## Test Categories

### Graph Agent Tests (41 tests)
Core functionality tests for the 3-node graph architecture:
- **Security Detection** (10 tests): Jailbreak, injection, command detection
- **Scope Detection** (8 tests): Keyword matching, LLM fallback, product handling
- **Rejection Paths** (3 tests): Out-of-scope and security rejection flows
- **Response Validation** (4 tests): Format and structure verification
- **Performance** (1 test): Latency validation
- **Graph Configuration** (3 tests): Node setup and structure
- **Edge Cases** (6 tests): Special characters, unicode, long text
- **Full Pipeline** (2 tests): End-to-end integration

### API Server Tests (11 tests)
- Health check endpoints
- Chat completion requests
- Request/response validation
- Error handling

### Configuration Tests (14 tests)
- Settings loading from environment
- Pydantic model validation
- Configuration consistency

### Ollama Client Tests (10 tests)
- Text embedding
- Text generation
- Streaming operations

### Unit Tests (`test_*_unit.py`)
- Test individual components in isolation
- Use mocks for external dependencies
- Fast execution
- No external service dependencies

### Integration Tests (`test_*_integration.py`)
- Test multiple components working together
- Require actual services (Ollama, Milvus)
- Slower execution
- Test real data flows

### Async Tests
Marked with `@pytest.mark.asyncio` for async/await functionality.

## Fixtures

Common fixtures available in `conftest.py`:

- `test_settings`: Test configuration with default values
- `mock_embedding`: Sample 384-dimensional embedding vector
- `sample_documents`: Sample Milvus-related documents

## Examples

### Test OllamaClient Connection Pooling

```python
def test_ollama_connection_pooling(test_settings):
    """Test that OllamaClient uses connection pooling."""
    client = OllamaClient(
        host=test_settings.ollama_host,
        timeout=test_settings.ollama_timeout,
        pool_size=test_settings.ollama_pool_size,
    )
    assert client.pool_size == test_settings.ollama_pool_size
```

### Test Cache Eviction

```python
def test_rag_cache_eviction(test_settings):
    """Test that RAGAgent evicts old cache entries."""
    agent = RAGAgent(test_settings, cache_size=2)
    # Add items and verify eviction
```

## Mock Strategy

- **Ollama Client**: Mock network requests using `unittest.mock`
- **Milvus Client**: Mock database operations
- **API Endpoints**: Use `TestClient` from FastAPI
- **Settings**: Use test fixtures with known values

## Debugging Tests

### Verbose Output

```bash
pytest -vv
```

### Show Print Statements

```bash
pytest -s
```

### Drop into Debugger on Failure

```bash
pytest --pdb
```

### Run Last Failed Test

```bash
pytest --lf
```

## Performance Testing

Current test suite should complete in < 30 seconds for unit tests.

To profile test execution:

```bash
pytest --durations=10  # Show 10 slowest tests
```

## CI/CD Integration

For GitHub Actions or other CI systems:

```yaml
- name: Run tests with coverage
  run: pytest --cov=src --cov-report=xml --cov-report=term
```

## Coverage Report

Current coverage breakdown (48% overall - 619/1303 statements):

### High Coverage (70%+)
- ✅ src/config/settings.py - **100%**
- ✅ src/agents/__init__.py - **100%**
- ✅ src/agents/skills/answer_generation_skill.py - **78%**
- ✅ src/agents/skills/knowledge_base_skill.py - **78%**
- ✅ src/agents/prompts.py - **74%**
- ✅ src/tools/ollama_client.py - **68%**

### Moderate Coverage (50-69%)
- ⚠️ src/agents/strands_graph_agent.py - **52%** (main agent)
- ⚠️ src/agents/skills/retrieval_skill.py - **64%**
- ⚠️ src/tools/tool_registry.py - **63%**

### Low Coverage (<50%)
- ❌ src/tools/web_search.py - **47%**
- ❌ src/tools/milvus_client.py - **27%**
- ❌ src/mcp/mcp_server.py - **18%**
- ❌ src/tools/response_cache.py - **13%**

Generate coverage report:

```bash
pytest --cov=src --cov-report=html --cov-report=term-missing
```

## Coverage Goals

Target coverage metrics:
- Overall: > 80%
- Core modules (RAGAgent, Clients): > 90%
- API endpoints: > 85%
- Overall: > 80%
- Core modules (RAGAgent, Clients): > 90%
- API endpoints: > 85%

Generate coverage report:

```bash
pytest --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

## Adding New Tests

1. Create test file following pattern: `test_*.py`
2. Use fixtures from `conftest.py`
3. Mark with appropriate markers: `@pytest.mark.unit`, `@pytest.mark.async`
4. Run tests before committing: `pytest`

## Continuous Integration

Tests are automatically run on:
- Pull requests
- Commits to main branch
- Manual workflow dispatch

See `.github/workflows/` for CI configuration.
