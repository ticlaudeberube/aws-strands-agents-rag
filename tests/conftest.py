"""Pytest configuration and shared fixtures."""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import Settings
from src.agents.strands_rag_agent import StrandsRAGAgent
from src.mcp.mcp_server import RAGAgentMCPServer


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
    """Create a StrandsRAGAgent for testing."""
    try:
        agent = StrandsRAGAgent(test_settings)
        yield agent
    finally:
        # Cleanup
        try:
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
