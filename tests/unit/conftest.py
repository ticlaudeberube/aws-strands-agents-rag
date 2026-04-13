"""Unit test fixtures and configuration.

This module provides shared fixtures for unit tests.
Unit tests are isolated, fast, and use mocks for dependencies.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_settings():
    """Provide mock settings for unit tests."""
    settings = MagicMock()
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    settings.MILVUS_HOST = "localhost"
    settings.MILVUS_PORT = 19530
    settings.EMBEDDING_MODEL = "nomic-embed-text"
    settings.FAST_MODEL = "qwen2.5:0.5b"
    settings.POWERFUL_MODEL = "llama3.1:8b"
    settings.MAX_TOKENS = 2000
    settings.RETRIEVAL_TOP_K = 5
    settings.CONFIDENCE_THRESHOLD = 0.3
    return settings


@pytest.fixture
def mock_ollama_client():
    """Provide mock Ollama client for unit tests."""
    client = MagicMock()
    client.embed = MagicMock(return_value=[0.1] * 768)
    client.generate = MagicMock(return_value="Mock response")
    return client


@pytest.fixture
def mock_milvus_client():
    """Provide mock Milvus client for unit tests."""
    client = MagicMock()
    client.search = MagicMock(return_value=[
        {"doc_id": "1", "score": 0.95, "text": "Mock document 1"},
        {"doc_id": "2", "score": 0.92, "text": "Mock document 2"},
    ])
    return client


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables for all unit tests."""
    with patch.dict(os.environ, {
        "MILVUS_HOST": "localhost",
        "MILVUS_PORT": "19530",
        "OLLAMA_BASE_URL": "http://localhost:11434",
    }):
        yield
