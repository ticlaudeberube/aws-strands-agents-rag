"""Unit tests for shared backend Protocols.

Verifies that the local clients conform structurally to the shared Protocols.
The Milvus adapter shims were removed with the Milvus engine; both modes now
use OpenSearch directly, which conforms to VectorStore/SemanticCache by shape.
"""

from __future__ import annotations

import pytest

from src.tools.in_memory_cache import InMemoryCache
from src.tools.interfaces import (
    CacheBackend,
    LLMClient,
)
from src.tools.ollama_client import OllamaClient


# --------------------------------------------------------------------------- #
# Protocol conformance                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_ollama_client_conforms_to_llm_client():
    """OllamaClient conforms to the LLMClient protocol (generate + embed_text)."""
    client = OllamaClient(host="http://localhost:11434")
    assert isinstance(client, LLMClient)


@pytest.mark.unit
def test_in_memory_cache_conforms_to_cache_backend():
    """InMemoryCache conforms to the CacheBackend protocol."""
    cache = InMemoryCache(ttl=3600)
    assert isinstance(cache, CacheBackend)
