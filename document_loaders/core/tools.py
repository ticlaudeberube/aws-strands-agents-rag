"""Tools used by document loader scripts.

Canonical import path for loader-facing OpenSearch/Ollama clients:
`document_loaders.core.tools`.

This package is a standalone ingestion utility. It is intentionally isolated
from the runtime application in ``src/`` (no imports in either direction). The
OpenSearch index body here mirrors the shape of ``src/tools/opensearch_client.py``
so documents indexed by the loader are read correctly by the runtime
``OpenSearchClient.knn_search`` (fields ``vector`` / ``text`` / ``metadata``).
"""

from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# HNSW / vector defaults. Mirror src/tools/opensearch_client.py so the loader and
# the runtime wrapper stay in sync (cosine HNSW, m=30, ef_construction=200).
HNSW_M = 30
HNSW_EF_CONSTRUCTION = 200
VECTOR_DIM = 768
SPACE_TYPE = "cosinesimil"  # OpenSearch cosine similarity space
ENGINE = "nmslib"


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _import_opensearchpy() -> Any:
    """Lazily import ``opensearch-py`` with a clear error if it is missing."""
    try:
        import opensearchpy  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise ImportError(
            "opensearch-py is required for the document loader (OpenSearchVectorDB). "
            "Install it with `pip install opensearch-py`."
        ) from exc
    return opensearchpy


class OpenSearchVectorDB:
    """Minimal OpenSearch wrapper for document loader workflows.

    Connects to a local, plain-HTTP OpenSearch container (no TLS, no auth,
    security plugin disabled) and indexes document chunks as
    ``{vector, text, metadata}`` so the runtime ``OpenSearchClient`` can read
    them back via k-NN search.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
    ):
        self.host = host or os.getenv("OPENSEARCH_LOCAL_HOST", "localhost")
        self.port = port or _get_env_int("OPENSEARCH_LOCAL_PORT", 9200)

        opensearchpy = _import_opensearchpy()
        try:
            self.client = opensearchpy.OpenSearch(
                hosts=[{"host": self.host, "port": self.port}],
                http_auth=None,
                use_ssl=False,
                verify_certs=False,
                ssl_show_warn=False,
            )
            logger.info("Connected to OpenSearch at http://%s:%d", self.host, self.port)
        except Exception as connection_error:
            raise RuntimeError(
                f"OpenSearch connection failed at {self.host}:{self.port}. "
                "Make sure the local OpenSearch container is running."
            ) from connection_error

    def _index_body(self, embedding_dim: int) -> dict[str, Any]:
        """Build a 768-dim HNSW cosine k-NN index body.

        Mirrors ``src/tools/opensearch_client.py`` ``_knn_index_body`` so the
        runtime wrapper reads indexed documents correctly.
        """
        return {
            "settings": {"index": {"knn": True}},
            "mappings": {
                "properties": {
                    "vector": {
                        "type": "knn_vector",
                        "dimension": embedding_dim,
                        "method": {
                            "name": "hnsw",
                            "space_type": SPACE_TYPE,
                            "engine": ENGINE,
                            "parameters": {
                                "m": _get_env_int("VECTORDB_HNSW_M", HNSW_M),
                                "ef_construction": _get_env_int(
                                    "VECTORDB_HNSW_EF_CONSTRUCTION", HNSW_EF_CONSTRUCTION
                                ),
                            },
                        },
                    },
                    "text": {"type": "text"},
                    "metadata": {"type": "object", "enabled": True},
                }
            },
        }

    def ensure_index(self, index_name: str, embedding_dim: int = VECTOR_DIM) -> bool:
        """Create the k-NN index if it does not already exist.

        Returns ``True`` if the index was created, ``False`` if it already
        existed.
        """
        if self.client.indices.exists(index=index_name):
            logger.info("Index %s already exists", index_name)
            return False

        self.client.indices.create(index=index_name, body=self._index_body(embedding_dim))
        logger.info("Created OpenSearch index %s (dim=%d)", index_name, embedding_dim)
        return True

    def index_documents(
        self,
        index_name: str,
        embeddings: list[list[float]],
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
    ) -> int:
        """Bulk-index document chunks as ``{vector, text, metadata}``.

        Each document gets a generated id. A single refresh is issued at the end
        so the documents are immediately searchable. Returns the number of
        documents indexed.
        """
        if metadata is None:
            metadata = [{"source": "unknown"} for _ in texts]

        opensearchpy = _import_opensearchpy()

        actions = []
        for embedding, text, item_metadata in zip(embeddings, texts, metadata):
            actions.append(
                {
                    "_index": index_name,
                    "_id": uuid.uuid4().hex,
                    "_source": {
                        "vector": embedding,
                        "text": text,
                        "metadata": item_metadata or {},
                    },
                }
            )

        if not actions:
            return 0

        logger.info("[LOADER_INDEX] Indexing %d documents into %s", len(actions), index_name)
        success, errors = opensearchpy.helpers.bulk(
            self.client, actions, refresh=True, stats_only=False
        )
        if errors:
            logger.warning("[LOADER_INDEX] %d document(s) failed to index", len(errors))
        logger.info("[LOADER_INDEX] Indexed %d documents into %s", success, index_name)
        return int(success)

    def delete_index(self, index_name: str) -> bool:
        """Delete an index if it exists. Returns ``True`` when a delete ran."""
        if not self.client.indices.exists(index=index_name):
            return False
        self.client.indices.delete(index=index_name)
        logger.info("Deleted OpenSearch index %s", index_name)
        return True

    def list_indexes(self) -> list[str]:
        """List all non-system index names."""
        indices = self.client.indices.get(index="*")
        return [name for name in indices if not name.startswith(".")]

    def count(self, index_name: str) -> int:
        """Return the number of documents in an index (0 if it does not exist)."""
        if not self.client.indices.exists(index=index_name):
            return 0
        result = self.client.count(index=index_name)
        return int(result.get("count", 0))


class OllamaClient:
    """Minimal Ollama client for embeddings and model availability checks."""

    def __init__(
        self,
        host: str | None = None,
        timeout: int | None = None,
        pool_size: int | None = None,
    ):
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.timeout = timeout or _get_env_int("OLLAMA_TIMEOUT", 30)
        self.pool_size = pool_size or _get_env_int("OLLAMA_POOL_SIZE", 10)

        self.embedding_endpoint = f"{self.host}/api/embeddings"
        self.tags_endpoint = f"{self.host}/api/tags"

        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "DELETE", "POST"],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=self.pool_size,
            pool_maxsize=self.pool_size,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def is_available(self, timeout: int | None = None) -> bool:
        request_timeout = timeout if timeout is not None else self.timeout
        try:
            response = self.session.get(self.tags_endpoint, timeout=request_timeout)
            return response.status_code == 200  # type: ignore[no-any-return]
        except Exception:
            return False

    def get_available_models(self, timeout: int | None = None) -> list[str]:
        request_timeout = timeout if timeout is not None else self.timeout
        try:
            response = self.session.get(self.tags_endpoint, timeout=request_timeout)
            response.raise_for_status()
            payload = response.json()
            return [model.get("name", "") for model in payload.get("models", [])]
        except Exception as error:
            logger.error("Failed to get models from Ollama: %s", error)
            return []

    def embed_text(
        self,
        text: str,
        model: str | None = None,
        timeout: int | None = None,
    ) -> list[float]:
        resolved_model = model or os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:v1.5")
        request_timeout = timeout if timeout is not None else self.timeout

        try:
            response = self.session.post(
                self.embedding_endpoint,
                json={"prompt": text, "model": resolved_model},
                timeout=request_timeout,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("embedding", [])  # type: ignore[no-any-return]
        except requests.exceptions.ConnectionError as error:
            raise RuntimeError(
                f"Ollama connection failed. Is Ollama running at {self.host}?"
            ) from error
        except requests.exceptions.Timeout as error:
            raise RuntimeError(
                f"Ollama request timed out. Try: ollama pull {resolved_model}"
            ) from error
        except requests.exceptions.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                raise RuntimeError(
                    f"Model '{resolved_model}' not found. Run: ollama pull {resolved_model}"
                ) from error
            raise

    def embed_texts(
        self,
        texts: list[str],
        model: str | None = None,
        batch_size: int = 32,
        max_workers: int | None = None,
    ) -> list[list[float] | None]:
        del batch_size

        if not texts:
            return []

        workers = max_workers or 4
        embeddings: list[list[float] | None] = [None] * len(texts)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_index = {
                executor.submit(self.embed_text, text, model): index
                for index, text in enumerate(texts)
            }
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                embeddings[index] = future.result()  # type: ignore[assignment]

        return embeddings  # type: ignore[return-value]

    def close(self) -> None:
        self.session.close()


__all__ = ["OpenSearchVectorDB", "OllamaClient"]
