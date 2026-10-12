"""Pytest configuration and shared fixtures."""

import socket
import sys
from functools import lru_cache
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.strands_graph_agent import StrandsGraphRAGAgent
from src.config.settings import Settings
from src.mcp.mcp_server import RAGAgentMCPServer

# ---------------------------------------------------------------------------
# Milvus availability detection
#
# Integration tests that need a live Milvus server are skipped automatically
# when the server is unreachable. This keeps the suite (and the pre-push
# pytest hook) green on machines without a running Milvus, instead of failing
# with "Milvus connection failed at localhost:19530".
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _milvus_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if a TCP connection to the Milvus server succeeds.

    Result is cached per (host, port) so we probe at most once per session.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def milvus_available() -> bool:
    """Check whether the configured Milvus server is reachable."""
    try:
        settings = Settings()
        return _milvus_reachable(settings.milvus_host, settings.milvus_port)
    except Exception:
        return False


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_milvus: mark test as requiring a reachable Milvus server; "
        "skipped automatically when Milvus is unavailable.",
    )


_INTEGRATION_DIR = Path(__file__).parent.resolve() / "integration"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip Milvus-dependent tests when the server is unreachable.

    Applies to any test marked `requires_milvus` or `integration`, and to any
    test located under tests/integration/ (path-based, so it does not depend
    on marker-application ordering across conftests).
    """
    if milvus_available():
        return

    skip_milvus = pytest.mark.skip(
        reason="Milvus server not reachable; skipping Milvus-dependent test"
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
            "requires_milvus" in item.keywords
            or "integration" in item.keywords
            or in_integration_dir
        ):
            item.add_marker(skip_milvus)


@pytest.fixture
def test_settings():
    """Create test settings."""
    return Settings(
        ollama_host="http://localhost:11434",
        ollama_timeout=30,
        ollama_pool_size=5,
        milvus_host="localhost",
        milvus_port=19530,
        milvus_user="root",
        milvus_password="Milvus",
        milvus_timeout=30,
        milvus_pool_size=10,
        milvus_db_name="test_db",
        agent_cache_size=100,
    )


@pytest.fixture
def strands_agent(test_settings):
    """Create a StrandsGraphRAGAgent for testing."""
    try:
        agent = StrandsGraphRAGAgent(test_settings)
        yield agent
    finally:
        # Cleanup
        try:
            if hasattr(agent, "close"):
                agent.close()
        except Exception as e:
            print(f"Cleanup error: {e}")


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
