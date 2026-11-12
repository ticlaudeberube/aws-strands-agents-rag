"""Shared backend interfaces (Protocols) for the dual-mode deployment.

This module defines the abstract backend *roles* that the Strands graph is
written against, so that the ``create_rag_graph`` dual-mode factory can inject
either Local Mode backends (``OllamaClient`` + ``OpenSearchClient`` +
``InMemoryCache``) or Serverless Mode backends (``BedrockClient`` +
``OpenSearchClient`` + ``RedisCache``) without the routing ever branching on
deployment mode.

The Protocols mirror the "Components and Interfaces" section of the
serverless-deployment design document:

- :class:`LLMClient`      -> ``generate`` / ``embed_text``
- :class:`VectorStore`    -> ``knn_search`` / ``index_document``
- :class:`CacheBackend`   -> ``get/set_embedding`` / ``get/set_search_results``
- :class:`SemanticCache`  -> ``search_semantic_cache`` / ``store_semantic_cache``

These are structural (``typing.Protocol``) types: concrete classes conform by
shape, with no explicit inheritance required. ``@runtime_checkable`` is applied
so ``isinstance(obj, LLMClient)`` can be used in tests and defensive checks.
``OllamaClient`` matches :class:`LLMClient` and ``OpenSearchClient`` matches
:class:`VectorStore` / :class:`SemanticCache` structurally.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = [
    "LLMClient",
    "VectorStore",
    "CacheBackend",
    "SemanticCache",
]


@runtime_checkable
class LLMClient(Protocol):
    """LLM inference + embedding backend.

    Local Mode: ``OllamaClient`` (``llama3.2:3b`` / ``nomic-embed-text:v1.5``).
    Serverless Mode: ``BedrockClient`` (``claude-3-haiku`` / ``titan-embed-text-v1``).
    """

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        stream: bool = False,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> str:
        """Generate answer text for ``prompt`` and return it as a string."""
        ...

    def embed_text(
        self,
        text: str,
        model: str | None = None,
        timeout: int | None = None,
    ) -> list[float]:
        """Return an embedding vector for ``text``."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Vector store backend for KB retrieval and document indexing.

    Both modes: ``OpenSearchClient``.
    """

    def knn_search(
        self,
        index: str,
        query_vector: list[float],
        k: int = 10,
        filters: dict | None = None,
        query_text: str | None = None,
    ) -> list[dict]:
        """Search using vector similarity, optionally combined with lexical ranking.

        ``query_text`` requests hybrid retrieval when supported by the backend.
        Backends should preserve the meaning of ``distance`` for consumers that
        use it as a vector-relevance score.
        """
        ...


@runtime_checkable
class CacheBackend(Protocol):
    """Layer 2/3 cache backend (embeddings + search results).

    Local Mode: ``InMemoryCache`` (process-local dicts, L2 TTL honored).
    Serverless Mode: ``RedisCache`` (ElastiCache, L2 TTL 3600s / L3 TTL 86400s).
    """

    def get_embedding(self, cache_key: str) -> list[float] | None:
        """Layer 2: retrieve a cached embedding vector, or ``None`` on miss."""
        ...

    def set_embedding(self, cache_key: str, vector: list[float]) -> None:
        """Layer 2: store an embedding vector (honoring the configured TTL)."""
        ...

    def get_search_results(self, cache_key: str) -> list[dict] | None:
        """Layer 3: retrieve cached search results, or ``None`` on miss."""
        ...

    def set_search_results(self, cache_key: str, results: list[dict]) -> None:
        """Layer 3: store search results."""
        ...


@runtime_checkable
class SemanticCache(Protocol):
    """Layer 4 semantic response cache backend.

    Both modes: ``OpenSearchClient`` (``rag-cache`` index).
    """

    def search_semantic_cache(
        self,
        question: str,
        query_vector: list[float],
        threshold: float = 0.92,
    ) -> dict | None:
        """Cosine-similarity search of the semantic cache; ``None`` on miss."""
        ...

    def store_semantic_cache(
        self,
        question: str,
        query_vector: list[float],
        answer: str,
        sources: list[dict],
    ) -> None:
        """Upsert a cache entry into the semantic cache."""
        ...
