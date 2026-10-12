"""Unit tests for shared backend Protocols and adapters (task 1.3).

These tests verify that:
- The existing local clients conform to the shared Protocols (structurally,
  directly or via the thin adapter shims).
- The adapter shims relay calls to the wrapped clients without altering
  behavior (verified against lightweight fakes, no Milvus required).
"""

from __future__ import annotations

import pytest

from src.tools.in_memory_cache import InMemoryCache
from src.tools.interfaces import (
    CacheBackend,
    LLMClient,
    SemanticCache,
    SemanticCacheAdapter,
    VectorStore,
    VectorStoreAdapter,
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


@pytest.mark.unit
def test_vector_store_adapter_conforms_to_vector_store():
    """VectorStoreAdapter wrapping any vector DB satisfies VectorStore."""
    adapter = VectorStoreAdapter(vector_db=_FakeVectorDB())
    assert isinstance(adapter, VectorStore)


@pytest.mark.unit
def test_semantic_cache_adapter_conforms_to_semantic_cache():
    """SemanticCacheAdapter wrapping any response cache satisfies SemanticCache."""
    adapter = SemanticCacheAdapter(response_cache=_FakeResponseCache())
    assert isinstance(adapter, SemanticCache)


# --------------------------------------------------------------------------- #
# Adapter relay behavior (behavior-preserving shims)                          #
# --------------------------------------------------------------------------- #
class _FakeVectorDB:
    """Records calls to assert the adapter relays without transformation."""

    def __init__(self):
        self.search_calls: list[dict] = []
        self.insert_calls: list[dict] = []

    def search(self, collection_name, query_embedding, limit=5):
        self.search_calls.append(
            {"collection_name": collection_name, "query_embedding": query_embedding, "limit": limit}
        )
        return [{"id": 1, "text": "doc", "metadata": {}, "distance": 0.9}]

    def insert_embeddings(self, collection_name, embeddings, texts, metadata):
        self.insert_calls.append(
            {
                "collection_name": collection_name,
                "embeddings": embeddings,
                "texts": texts,
                "metadata": metadata,
            }
        )


class _FakeResponseCache:
    """Records calls to assert the adapter relays without transformation."""

    def __init__(self):
        self.search_calls: list[dict] = []
        self.store_calls: list[dict] = []

    def search_cache(self, question, question_embedding, similarity_threshold=0.92, limit=1):
        self.search_calls.append(
            {
                "question": question,
                "question_embedding": question_embedding,
                "similarity_threshold": similarity_threshold,
            }
        )
        return {"question": question, "response": "cached"}

    def store_response(self, question, question_embedding, response, metadata=None):
        self.store_calls.append(
            {
                "question": question,
                "question_embedding": question_embedding,
                "response": response,
                "metadata": metadata,
            }
        )
        return True


@pytest.mark.unit
def test_vector_store_adapter_knn_search_relays_to_search():
    fake = _FakeVectorDB()
    adapter = VectorStoreAdapter(fake)

    results = adapter.knn_search(index="rag-kb", query_vector=[0.1, 0.2], k=7)

    assert results == [{"id": 1, "text": "doc", "metadata": {}, "distance": 0.9}]
    assert fake.search_calls == [
        {"collection_name": "rag-kb", "query_embedding": [0.1, 0.2], "limit": 7}
    ]


@pytest.mark.unit
def test_vector_store_adapter_index_document_relays_and_preserves_doc_id():
    fake = _FakeVectorDB()
    adapter = VectorStoreAdapter(fake)

    adapter.index_document(
        index="rag-kb",
        doc_id="abc-123",
        vector=[0.3, 0.4],
        text="chunk text",
        metadata={"source": "s3://x"},
    )

    assert len(fake.insert_calls) == 1
    call = fake.insert_calls[0]
    assert call["collection_name"] == "rag-kb"
    assert call["embeddings"] == [[0.3, 0.4]]
    assert call["texts"] == ["chunk text"]
    # doc_id preserved inside metadata without dropping existing keys
    assert call["metadata"] == [{"doc_id": "abc-123", "source": "s3://x"}]


@pytest.mark.unit
def test_semantic_cache_adapter_search_relays_to_search_cache():
    fake = _FakeResponseCache()
    adapter = SemanticCacheAdapter(fake)

    out = adapter.search_semantic_cache(
        question="What is Milvus?", query_vector=[0.1], threshold=0.92
    )

    assert out == {"question": "What is Milvus?", "response": "cached"}
    assert fake.search_calls == [
        {"question": "What is Milvus?", "question_embedding": [0.1], "similarity_threshold": 0.92}
    ]


@pytest.mark.unit
def test_semantic_cache_adapter_store_relays_with_sources_metadata():
    fake = _FakeResponseCache()
    adapter = SemanticCacheAdapter(fake)

    sources = [{"url": "https://x", "timestamp": "2024-01-01"}]
    adapter.store_semantic_cache(
        question="What is Milvus?",
        query_vector=[0.1],
        answer="A vector DB.",
        sources=sources,
    )

    assert len(fake.store_calls) == 1
    call = fake.store_calls[0]
    assert call["question"] == "What is Milvus?"
    assert call["question_embedding"] == [0.1]
    assert call["response"] == "A vector DB."
    assert call["metadata"] == {"sources": sources}
