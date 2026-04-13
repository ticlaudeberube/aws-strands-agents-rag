"""Integration test fixtures and configuration.

This module provides shared fixtures for integration tests.
Integration tests verify system interactions and may use real services or more realistic mocks.
"""

import os
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
import requests


@pytest.fixture
def test_project_root() -> Path:
    """Provide path to project root."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def test_data_dir(test_project_root: Path) -> Path:
    """Provide path to test data directory."""
    test_data = test_project_root / "tests" / "fixtures"
    test_data.mkdir(parents=True, exist_ok=True)
    return test_data


@pytest.fixture
def integration_settings(test_project_root: Path):
    """Provide integration test settings."""
    settings = MagicMock()
    settings.OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    settings.MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
    settings.MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
    settings.EMBEDDING_MODEL = "nomic-embed-text"
    settings.FAST_MODEL = "qwen2.5:0.5b"
    settings.POWERFUL_MODEL = "llama3.1:8b"
    settings.MAX_TOKENS = 2000
    settings.RETRIEVAL_TOP_K = 5
    settings.CONFIDENCE_THRESHOLD = 0.3
    settings.CACHE_ENABLED = True
    settings.RESPONSE_CACHE_SIZE = 1000
    return settings


@pytest.fixture(autouse=True)
def integration_env_vars(test_project_root: Path):
    """Set up environment for integration tests."""
    env = {
        "MILVUS_HOST": "localhost",
        "MILVUS_PORT": "19530",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "TAVILY_API_KEY": "test-key-integration",
        "ENABLE_WEB_SEARCH": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        yield


@pytest.fixture
def mock_streaming_response():
    """Provide mock streaming response for integration tests."""
    async def async_generator():
        chunks = [
            b"data: " + b'{"type": "text", "content": "The "}' + b"\n\n",
            b"data: " + b'{"type": "text", "content": "answer "}' + b"\n\n",
            b"data: " + b'{"type": "text", "content": "is..."}' + b"\n\n",
        ]
        for chunk in chunks:
            yield chunk
    return async_generator


@pytest.fixture
def sample_documents() -> list[dict]:
    """Provide sample documentation for testing."""
    return [
        {
            "id": "doc_1",
            "title": "Milvus Quick Start",
            "content": "Milvus is a vector database...",
            "embedding": [0.1] * 768,
        },
        {
            "id": "doc_2",
            "title": "Vector Indexing",
            "content": "Vector indexing improves search performance...",
            "embedding": [0.2] * 768,
        },
    ]


@pytest.fixture
def sample_user_query() -> str:
    """Provide sample user query for testing."""
    return "What is Milvus and how does it work?"


@pytest.fixture
def api_server_available() -> bool:
    """Check if API server is running and available."""
    api_base = os.getenv("API_BASE", "http://localhost:8000")
    try:
        response = requests.get(f"{api_base}/health", timeout=2)
        return response.status_code == 200
    except (requests.ConnectionError, requests.Timeout):
        return False


def pytest_collection_modifyitems(config, items):
    """Skip API endpoint tests if API server is not running."""
    api_base = os.getenv("API_BASE", "http://localhost:8000")
    server_available = False
    try:
        response = requests.get(f"{api_base}/health", timeout=2)
        server_available = response.status_code == 200
    except (requests.ConnectionError, requests.Timeout):
        server_available = False
    
    if not server_available:
        skip_marker = pytest.mark.skip(reason="API server not running on localhost:8000")
        for item in items:
            # Skip tests that make HTTP requests to the API
            if "endpoint" in item.nodeid or "Endpoint" in item.nodeid:
                item.add_marker(skip_marker)
