"""Shared backend interfaces (Protocols) for the dual-mode deployment.

This module defines the abstract backend *roles* that the Strands graph is
written against, so that the ``create_rag_graph`` dual-mode factory can inject
either Local Mode backends (``OllamaClient`` + ``MilvusVectorDB`` +
``InMemoryCache`` + ``MilvusResponseCache``) or Serverless Mode backends
(``BedrockClient`` + ``OpenSearchClient`` + ``RedisCache`` + OpenSearch
``rag-cache``) without the node logic ever branching on deployment mode.

The Protocols mirror the "Components and Interfaces" section of the
serverless-deployment design document:

- :class:`LLMClient`      -> ``generate`` / ``embed_text``
- :class:`VectorStore`    -> ``knn_search`` / ``index_document``
- :class:`CacheBackend`   -> ``get/set_embedding`` / ``get/set_search_results``
- :class:`SemanticCache`  -> ``search_semantic_cache`` / ``store_semantic_cache``

These are structural (``typing.Protocol``) types: concrete classes conform by
shape, with no explicit inheritance required. ``@runtime_checkable`` is applied
so ``isinstance(obj, LLMClient)`` can be used in tests and defensive checks.

Local-mode conformance notes
-----------------------------
``OllamaClient`` already matches :class:`LLMClient` structurally. The vector
store and semantic cache clients use method names from the existing local
codebase (``search`` / ``insert_embeddings`` and ``search_cache`` /
``store_response``); thin, behavior-preserving adapter shims
(:class:`VectorStoreAdapter`, :class:`SemanticCacheAdapter`) expose them under
the design's canonical protocol names without changing the underlying clients.
"""

from __future__ import annotations

from typing import Any, Protocol, cast, runtime_checkable

__all__ = [
    "LLMClient",
    "VectorStore",
    "CacheBackend",
    "SemanticCache",
    "VectorStoreAdapter",
    "SemanticCacheAdapter",
]


@runtime_checkable
class LLMClient(Protocol):
    """LLM inference + embedding backend.

    Local Mode: ``OllamaClient`` (``qwen2.5:0.5b`` / ``nomic-embed-text:v1.5``).
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

    Local Mode: ``MilvusVectorDB`` (via :class:`VectorStoreAdapter`).
    Serverless Mode: ``OpenSearchClient``.
    """

    def knn_search(
        self,
        index: str,
        query_vector: list[float],
        k: int = 10,
    ) -> list[dict]:
        """k-NN search; results ranked non-increasing by similarity score."""
        ...

    def index_document(
        self,
        index: str,
        doc_id: str,
        vector: list[float],
        text: str,
        metadata: dict,
    ) -> None:
        """Index a single document chunk into ``index``."""
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

    Local Mode: ``MilvusResponseCache`` (via :class:`SemanticCacheAdapter`).
    Serverless Mode: ``OpenSearchClient`` (``rag-cache`` index).
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


class VectorStoreAdapter:
    """Thin, behavior-preserving adapter exposing an existing local vector DB
    (``MilvusVectorDB``) under the :class:`VectorStore` protocol.

    This adapter only renames/relays calls to the wrapped client. It does NOT
    change retrieval behavior: ``knn_search`` delegates to the wrapped client's
    ``search`` (preserving its ranking and result shape), and
    ``index_document`` delegates to ``insert_embeddings`` for a single chunk.
    """

    def __init__(self, vector_db: Any):
        """Wrap an existing vector-DB client (e.g. ``MilvusVectorDB``)."""
        self._vector_db = vector_db

    @property
    def vector_db(self) -> Any:
        """Access the wrapped client (for code that needs native methods)."""
        return self._vector_db

    def knn_search(
        self,
        index: str,
        query_vector: list[float],
        k: int = 10,
    ) -> list[dict]:
        """k-NN search delegating to the wrapped client's ``search``.

        ``index`` maps to the collection name; ``k`` maps to ``limit``.
        """
        results = self._vector_db.search(
            collection_name=index,
            query_embedding=query_vector,
            limit=k,
        )
        return cast("list[dict]", results)

    def index_document(
        self,
        index: str,
        doc_id: str,
        vector: list[float],
        text: str,
        metadata: dict,
    ) -> None:
        """Index a single chunk via the wrapped client's ``insert_embeddings``.

        The provided ``doc_id`` is preserved inside the chunk metadata so it is
        not lost; the local client manages its own primary-key assignment.
        """
        chunk_metadata = {"doc_id": doc_id, **(metadata or {})}
        self._vector_db.insert_embeddings(
            collection_name=index,
            embeddings=[vector],
            texts=[text],
            metadata=[chunk_metadata],
        )


class SemanticCacheAdapter:
    """Thin, behavior-preserving adapter exposing an existing local semantic
    cache (``MilvusResponseCache``) under the :class:`SemanticCache` protocol.

    ``search_semantic_cache`` delegates to ``search_cache`` and
    ``store_semantic_cache`` delegates to ``store_response``; neither changes
    the underlying entity-validation or threshold behavior of the wrapped
    client.
    """

    def __init__(self, response_cache: Any):
        """Wrap an existing semantic cache client (e.g. ``MilvusResponseCache``)."""
        self._response_cache = response_cache

    @property
    def response_cache(self) -> Any:
        """Access the wrapped client (for code that needs native methods)."""
        return self._response_cache

    def search_semantic_cache(
        self,
        question: str,
        query_vector: list[float],
        threshold: float = 0.92,
    ) -> dict | None:
        """Delegate to the wrapped client's ``search_cache``.

        The wrapped client applies its own configured distance threshold and
        entity validation; ``threshold`` is passed through as the similarity
        threshold for backward compatibility.
        """
        result = self._response_cache.search_cache(
            question=question,
            question_embedding=query_vector,
            similarity_threshold=threshold,
        )
        return cast("dict | None", result)

    def store_semantic_cache(
        self,
        question: str,
        query_vector: list[float],
        answer: str,
        sources: list[dict],
    ) -> None:
        """Delegate to the wrapped client's ``store_response``.

        ``sources`` is carried in metadata, matching the existing local
        storage format (the wrapped client JSON-serializes the sources list).
        """
        self._response_cache.store_response(
            question=question,
            question_embedding=query_vector,
            response=answer,
            metadata={"sources": sources},
        )
