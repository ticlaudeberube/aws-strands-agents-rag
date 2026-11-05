"""Tests for the create_rag_graph Local-Mode vector-backend branching.

Phase 1 adds an OpenSearch sub-branch to the local path. These tests assert the
wiring for `local_vector_backend == "opensearch"` (OpenSearch client as both
vector_store and semantic_cache, Ollama llm, cache per REDIS_CACHE_ENABLED,
kb_index = rag-kb) and guard that the default Milvus branch is unchanged.

Backends are injected so no live Ollama/OpenSearch/Milvus/Redis is needed.
"""

from __future__ import annotations

from typing import Any

from src.agents.strands_graph_agent import create_rag_graph
from src.config.settings import Settings
from src.tools.in_memory_cache import InMemoryCache
from src.tools.opensearch_client import OpenSearchClient


class _FakeOllama:
    def embed_text(self, _text: str, model: str | None = None) -> list[float]:
        return [0.0] * 8

    def generate(self, prompt: str, **_kwargs: Any) -> str:
        return "answer"


class _FakeOSTransport:
    """Minimal opensearch-py stand-in (no network)."""

    def search(self, index: str, body: dict) -> dict:
        return {"hits": {"hits": []}}

    class _Indices:
        def exists(self, index: str) -> bool:
            return True

        def create(self, index: str, body: dict) -> None:
            return None

    indices = _Indices()


def _opensearch_client() -> OpenSearchClient:
    settings = Settings()
    return OpenSearchClient(settings=settings, client=_FakeOSTransport())


def _local_opensearch_settings(redis_enabled: bool = False) -> Settings:
    s = Settings()
    s.deployment_mode = "local"
    s.local_vector_backend = "opensearch"
    s.redis_cache_enabled = redis_enabled
    return s


def test_local_opensearch_wires_client_as_vector_store_and_cache() -> None:
    graph = create_rag_graph(
        _local_opensearch_settings(),
        ollama_client=_FakeOllama(),  # type: ignore[arg-type]
        opensearch_client=_opensearch_client(),
    )
    backends = graph["backends"]
    # Same OpenSearchClient serves KB retrieval and the L4 semantic cache.
    assert isinstance(backends["vector_store"], OpenSearchClient)
    assert backends["semantic_cache"] is backends["vector_store"]
    # LLM is Ollama (the injected fake), not Bedrock.
    assert isinstance(backends["llm"], _FakeOllama)
    # KB index is the OpenSearch index, not the Milvus collection name.
    assert graph["kb_index"] == "rag-kb"
    assert graph["deployment_mode"] == "local"


def test_local_opensearch_uses_inmemory_cache_by_default() -> None:
    graph = create_rag_graph(
        _local_opensearch_settings(redis_enabled=False),
        ollama_client=_FakeOllama(),  # type: ignore[arg-type]
        opensearch_client=_opensearch_client(),
    )
    assert isinstance(graph["backends"]["cache"], InMemoryCache)


def test_local_opensearch_uses_redis_when_enabled() -> None:
    from src.tools.redis_cache import RedisCache

    graph = create_rag_graph(
        _local_opensearch_settings(redis_enabled=True),
        ollama_client=_FakeOllama(),  # type: ignore[arg-type]
        opensearch_client=_opensearch_client(),
        redis_cache=RedisCache.for_local(Settings()),
    )
    assert isinstance(graph["backends"]["cache"], RedisCache)


def test_local_milvus_branch_unchanged_regression() -> None:
    # Default local backend is milvus; wiring must be Milvus + MilvusResponseCache
    # + InMemory + "milvus_docs", exactly as before this feature. Patch the
    # Milvus clients (matching the existing suite) so no live Milvus is needed.
    from unittest.mock import patch

    settings = Settings()
    settings.deployment_mode = "local"
    settings.local_vector_backend = "milvus"  # explicit (default is now opensearch)

    with (
        patch("src.agents.strands_graph_agent.MilvusVectorDB"),
        patch("src.agents.strands_graph_agent.OllamaClient"),
        patch("src.agents.strands_graph_agent.MilvusResponseCache") as mock_cache,
        patch("src.agents.strands_graph_agent.Agent"),
    ):
        graph = create_rag_graph(settings=settings)

    backends = graph["backends"]
    assert backends["vector_store"] is not None
    assert isinstance(backends["cache"], InMemoryCache)
    # L4 cache is the Milvus-backed response cache (the patched class instance).
    assert backends["semantic_cache"] is mock_cache.return_value
    assert graph["kb_index"] == "milvus_docs"
