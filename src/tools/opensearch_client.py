"""OpenSearch Serverless vector store + Layer 4 semantic cache (Serverless Mode).

This module provides :class:`OpenSearchClient`, the serverless-mode replacement
for the local :class:`~src.tools.milvus_client.MilvusVectorDB` (knowledge base
retrieval + document indexing) and :class:`~src.tools.response_cache.MilvusResponseCache`
(Layer 4 semantic response cache). It wraps the ``opensearch-py`` library against
an Amazon OpenSearch Serverless collection endpoint.

Two indexes mirror the two local Milvus collections (see the design document,
section "3b. OpenSearchClient"):

- ``rag-kb``    — knowledge base documents (768-dim k-NN HNSW, cosine).
                  Local equivalent: ``milvus_rag_collection``.
- ``rag-cache`` — Layer 4 semantic response cache (768-dim k-NN HNSW, cosine).
                  Local equivalent: the Milvus ``response_cache`` collection.

Both indexes use the HNSW algorithm with ``m=30`` / ``ef_construction=200`` and
cosine similarity, matching the existing Milvus HNSW configuration
(Requirements 4.1, 4.6).

The class conforms structurally to the :class:`~src.tools.interfaces.VectorStore`
and :class:`~src.tools.interfaces.SemanticCache` protocols so the
``create_rag_graph`` factory can inject it into the shared Strands graph without
the node logic branching on deployment mode.

Local-mode import safety
-------------------------
``opensearch-py`` is a serverless-only dependency. The import is guarded so this
module imports cleanly in local mode even when the package is not installed:
the ``opensearchpy`` symbols are imported lazily and a missing dependency only
raises when an :class:`OpenSearchClient` is actually constructed, never at
module import time.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.config.settings import Settings

logger = logging.getLogger(__name__)

__all__ = ["OpenSearchClient"]

# HNSW parameters mirroring the local Milvus configuration (Requirements 4.1, 4.6).
HNSW_M = 30
HNSW_EF_CONSTRUCTION = 200
VECTOR_DIM = 768
SPACE_TYPE = "cosinesimil"  # OpenSearch cosine similarity space


def _import_opensearchpy() -> Any:
    """Lazily import ``opensearch-py``.

    Imported inside this helper (rather than at module top) so the module can be
    imported in local mode without the serverless-only ``opensearch-py``
    dependency installed. Raises a clear error only when an OpenSearch client is
    actually constructed.
    """
    try:
        import opensearchpy  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise ImportError(
            "opensearch-py is required for serverless mode (OpenSearchClient). "
            "Install it with `pip install opensearch-py`. It is not needed in "
            "local mode."
        ) from exc
    return opensearchpy


class OpenSearchClient:
    """OpenSearch Serverless vector store + semantic cache client.

    Serverless-mode implementation of both the :class:`VectorStore` and
    :class:`SemanticCache` protocols. Backs the ``rag-kb`` knowledge base index
    and the ``rag-cache`` Layer 4 semantic cache index.
    """

    def __init__(
        self,
        settings: "Settings | None" = None,
        client: Any = None,
    ) -> None:
        """Initialize the OpenSearch client.

        Args:
            settings: Application settings. When omitted, loaded via
                ``get_settings()``. Provides the endpoint and index names
                (``opensearch_endpoint`` / ``opensearch_kb_index`` /
                ``opensearch_cache_index``) and the vector dimension
                (``bedrock_pca_target_dim``).
            client: Optional pre-constructed ``opensearchpy.OpenSearch`` instance
                (useful for tests and Lambda cold-start reuse). When omitted, a
                client is constructed from ``settings``.
        """
        if settings is None:
            from src.config.settings import get_settings

            settings = get_settings()

        self.settings = settings
        self.endpoint = settings.opensearch_endpoint
        self.kb_index = settings.opensearch_kb_index
        self.cache_index = settings.opensearch_cache_index
        self.vector_dim = settings.bedrock_pca_target_dim or VECTOR_DIM

        if client is not None:
            self.client = client
        else:
            self.client = self._build_client()

    def _build_client(self) -> Any:
        """Construct an ``opensearchpy.OpenSearch`` client for the endpoint."""
        opensearchpy = _import_opensearchpy()

        if not self.endpoint:
            raise ValueError(
                "settings.opensearch_endpoint is not configured; it is required "
                "to construct an OpenSearchClient in serverless mode."
            )

        host = self.endpoint.replace("https://", "").replace("http://", "").rstrip("/")

        auth = self._build_auth(opensearchpy)

        return opensearchpy.OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=opensearchpy.RequestsHttpConnection,
            pool_maxsize=20,
        )

    def _build_auth(self, opensearchpy: Any) -> Any:
        """Build SigV4 auth for OpenSearch Serverless (service ``aoss``).

        Falls back to ``None`` when AWS SigV4 helpers are unavailable so that an
        explicitly injected ``client`` path is never blocked.
        """
        try:
            import boto3  # type: ignore[import-untyped]
            from opensearchpy import AWSV4SignerAuth  # type: ignore[import-untyped]
        except ImportError:  # pragma: no cover - optional at runtime
            logger.warning(
                "boto3/AWSV4SignerAuth unavailable; constructing OpenSearch client "
                "without SigV4 auth. Provide a pre-built client for tests."
            )
            return None

        region = getattr(self.settings, "aws_region", None) or "us-east-1"
        credentials = boto3.Session().get_credentials()
        return AWSV4SignerAuth(credentials, region, "aoss")

    # ------------------------------------------------------------------
    # VectorStore protocol
    # ------------------------------------------------------------------
    def knn_search(
        self,
        index: str,
        query_vector: list[float],
        k: int = 10,
    ) -> list[dict]:
        """k-NN search over ``index`` using HNSW (m=30, ef_construction=200), cosine.

        Returns up to ``k`` documents ranked **non-increasing** by cosine
        similarity score (highest similarity first), matching the local Milvus
        result shape: ``{"id", "text", "metadata", "distance"}`` where
        ``distance`` carries the cosine similarity score (Requirements 4.2).
        """
        body = {
            "size": k,
            "query": {
                "knn": {
                    "vector": {
                        "vector": query_vector,
                        "k": k,
                    }
                }
            },
        }

        response = self.client.search(index=index, body=body)
        hits = (response or {}).get("hits", {}).get("hits", [])

        results: list[dict] = []
        for hit in hits:
            source = hit.get("_source", {}) or {}
            metadata = source.get("metadata", {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            results.append(
                {
                    "id": hit.get("_id"),
                    "text": source.get("text", ""),
                    "metadata": metadata,
                    "distance": hit.get("_score", 0.0),
                }
            )

        # OpenSearch returns hits ordered by _score descending, but guarantee the
        # contract explicitly: non-increasing by score (descending cosine sim).
        results.sort(key=lambda item: item.get("distance", 0.0), reverse=True)
        return results

    def index_document(
        self,
        index: str,
        doc_id: str,
        vector: list[float],
        text: str,
        metadata: dict,
    ) -> None:
        """Index a single document chunk into ``index`` (upsert by ``doc_id``)."""
        document = {
            "vector": vector,
            "text": text,
            "metadata": metadata or {},
        }
        self.client.index(index=index, id=doc_id, body=document, refresh=True)
        logger.debug("Indexed document %s into %s", doc_id, index)

    # ------------------------------------------------------------------
    # SemanticCache protocol
    # ------------------------------------------------------------------
    def search_semantic_cache(
        self,
        query_vector: list[float],
        threshold: float = 0.92,
    ) -> dict | None:
        """Cosine-similarity search of the ``rag-cache`` Layer 4 cache.

        Returns the best cache entry as a dict when its cosine similarity is at
        or above ``threshold`` (default 0.92), otherwise ``None`` (cache miss).
        The returned shape mirrors the local semantic cache entry:
        ``{"question", "response", "sources", "similarity", "distance"}``.
        """
        body = {
            "size": 1,
            "query": {
                "knn": {
                    "vector": {
                        "vector": query_vector,
                        "k": 1,
                    }
                }
            },
        }

        response = self.client.search(index=self.cache_index, body=body)
        hits = (response or {}).get("hits", {}).get("hits", [])
        if not hits:
            return None

        best = hits[0]
        score = best.get("_score", 0.0)
        if score < threshold:
            logger.debug("Semantic cache miss: score %.4f < threshold %.4f", score, threshold)
            return None

        source = best.get("_source", {}) or {}
        sources = source.get("sources", [])
        if isinstance(sources, str):
            try:
                sources = json.loads(sources)
            except (json.JSONDecodeError, TypeError):
                sources = []

        return {
            "question": source.get("question", ""),
            "response": source.get("answer", ""),
            "sources": sources,
            "similarity": score,
            "distance": score,
        }

    def store_semantic_cache(
        self,
        question: str,
        query_vector: list[float],
        answer: str,
        sources: list[dict],
    ) -> None:
        """Upsert a cache entry into the ``rag-cache`` Layer 4 cache index."""
        document = {
            "question": question,
            "vector": query_vector,
            "answer": answer,
            "sources": sources or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.client.index(index=self.cache_index, body=document, refresh=True)
        logger.debug("Stored semantic cache entry for: %s", question[:60])

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------
    def _knn_index_body(self, extra_properties: dict | None = None) -> dict:
        """Build the index creation body for a 768-dim HNSW cosine k-NN index."""
        properties: dict[str, Any] = {
            "vector": {
                "type": "knn_vector",
                "dimension": self.vector_dim,
                "method": {
                    "name": "hnsw",
                    "space_type": SPACE_TYPE,
                    "engine": "nmslib",
                    "parameters": {
                        "m": HNSW_M,
                        "ef_construction": HNSW_EF_CONSTRUCTION,
                    },
                },
            },
            "text": {"type": "text"},
            "metadata": {"type": "object", "enabled": True},
        }
        if extra_properties:
            properties.update(extra_properties)

        return {
            "settings": {"index": {"knn": True}},
            "mappings": {"properties": properties},
        }

    def ensure_indexes(self) -> None:
        """Create the ``rag-kb`` and ``rag-cache`` indexes if they do not exist."""
        if not self.client.indices.exists(index=self.kb_index):
            self.client.indices.create(index=self.kb_index, body=self._knn_index_body())
            logger.info("Created OpenSearch KB index: %s", self.kb_index)

        if not self.client.indices.exists(index=self.cache_index):
            cache_body = self._knn_index_body(
                extra_properties={
                    "question": {"type": "text"},
                    "answer": {"type": "text"},
                    "sources": {"type": "object", "enabled": True},
                    "created_at": {"type": "date"},
                }
            )
            self.client.indices.create(index=self.cache_index, body=cache_body)
            logger.info("Created OpenSearch cache index: %s", self.cache_index)
