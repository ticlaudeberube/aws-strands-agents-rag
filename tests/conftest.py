"""Pytest configuration and shared fixtures."""

import os
import socket
import sys
from functools import lru_cache
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Hypothesis profiles
#
# Property-based tests (feature: serverless-deployment) can be slow when run
# with Hypothesis' default of 100 examples per property across dozens of
# properties. We register named profiles and select one via the
# HYPOTHESIS_PROFILE environment variable so the suite runs fast locally while
# still allowing a thorough CI run.
#
#   fast  (default) -> 20 examples, no deadline  -> quick local iteration
#   dev             -> 50 examples               -> balanced
#   ci              -> 200 examples              -> thorough pre-merge run
#
# Override at runtime, e.g.:
#   HYPOTHESIS_PROFILE=ci pytest
# ---------------------------------------------------------------------------
try:
    from hypothesis import HealthCheck, settings

    settings.register_profile("fast", max_examples=20, deadline=None)
    settings.register_profile("dev", max_examples=50, deadline=None)
    settings.register_profile(
        "ci",
        max_examples=200,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "fast"))
except ImportError:
    # Hypothesis not installed yet; property tests will add it as a dependency.
    pass

from src.config.settings import Settings
from src.mcp.mcp_server import RAGAgentMCPServer

# ---------------------------------------------------------------------------
# Live vector-DB availability detection
#
# Integration tests that need a live vector database are skipped automatically
# when the server is unreachable. This keeps the suite (and the pre-push
# pytest hook) green on machines without a running backend. The local backend
# is OpenSearch.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if a TCP connection to ``host:port`` succeeds.

    Result is cached per (host, port) so we probe at most once per session.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def vector_db_available() -> bool:
    """Whether a live local vector database (OpenSearch) is reachable."""
    try:
        settings = Settings()
        return _tcp_reachable(settings.opensearch_local_host, settings.opensearch_local_port)
    except Exception:
        return False


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_vector_db: mark test as requiring a reachable local vector database; "
        "skipped automatically when the backend is unavailable.",
    )


_INTEGRATION_DIR = Path(__file__).parent.resolve() / "integration"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip vector-DB-dependent tests when the server is unreachable.

    Applies to any test marked `requires_vector_db` or `integration`, and to any
    test located under tests/integration/ (path-based, so it does not depend
    on marker-application ordering across conftests).
    """
    if vector_db_available():
        return

    skip_vector_db = pytest.mark.skip(
        reason="Vector DB (OpenSearch) not reachable; skipping vector-DB-dependent test"
    )
    for item in items:
        in_integration_dir = False
        try:
            item_path = Path(str(item.fspath)).resolve()
            in_integration_dir = (
                _INTEGRATION_DIR in item_path.parents or item_path == _INTEGRATION_DIR
            )
        except Exception:
            in_integration_dir = False

        if (
            "requires_vector_db" in item.keywords
            or "integration" in item.keywords
            or in_integration_dir
        ):
            item.add_marker(skip_vector_db)


@pytest.fixture
def test_settings():
    """Create test settings."""
    return Settings(
        ollama_host="http://localhost:11434",
        ollama_timeout=30,
        ollama_pool_size=5,
        agent_cache_size=100,
    )


@pytest.fixture
def mcp_server(test_settings):
    """Create an MCP server for testing."""
    try:
        server = RAGAgentMCPServer(test_settings)
        yield server
    finally:
        # Cleanup
        try:
            if hasattr(server, "close"):
                server.close()
        except Exception as e:
            print(f"Cleanup error: {e}")


@pytest.fixture
def mock_embedding():
    """Create a mock embedding vector."""
    return [0.1] * 384  # 384-dimensional embedding


@pytest.fixture
def sample_documents():
    """Create sample documents for testing."""
    return [
        "Milvus is a vector database for AI applications.",
        "It supports fast similarity search on large-scale datasets.",
        "Milvus can be deployed on cloud or on-premises.",
        "The vector database uses HNSW or IVF indexes for fast search.",
        "Embeddings are converted to vectors using neural networks.",
    ]
