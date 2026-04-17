"""Tools used by document loader scripts.

Canonical import path for loader-facing Milvus/Ollama clients:
`document_loaders.core.tools`.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import requests
from pymilvus import MilvusClient  # type: ignore[import-untyped]
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class MilvusVectorDB:
    """Minimal Milvus wrapper for document loader workflows."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db_name: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[int] = None,
        pool_size: Optional[int] = None,
    ):
        self.host = host or os.getenv("MILVUS_HOST", "localhost")
        self.port = port or _get_env_int("MILVUS_PORT", 19530)
        self.db_name = db_name or os.getenv("MILVUS_DB_NAME", "default")
        self.timeout = timeout or _get_env_int("MILVUS_TIMEOUT", 30)
        self.pool_size = pool_size or _get_env_int("MILVUS_POOL_SIZE", 10)

        default_user = os.getenv("MILVUS_USER", "root")
        default_password = os.getenv("MILVUS_PASSWORD", "Milvus")
        resolved_user = user or default_user
        resolved_password = password or default_password

        uri = f"http://{self.host}:{self.port}"

        try:
            self.client = MilvusClient(
                uri=uri,
                user=resolved_user,
                password=resolved_password,
                pool_size=self.pool_size,
            )
            logger.info("Connected to Milvus at %s", uri)
        except Exception as auth_error:
            logger.warning(
                "Milvus auth connection failed, retrying without credentials: %s", auth_error
            )
            try:
                self.client = MilvusClient(uri=uri, pool_size=self.pool_size)
                logger.info("Connected to Milvus at %s without auth", uri)
            except Exception as connection_error:
                raise RuntimeError(
                    f"Milvus connection failed at {self.host}:{self.port}. "
                    "Make sure Milvus is running."
                ) from connection_error

        self._ensure_database()

    def _ensure_database(self) -> None:
        try:
            databases = self.client.list_databases()
            if self.db_name not in databases:
                self.client.create_database(db_name=self.db_name)
            self.client.using_database(self.db_name)
        except Exception as error:
            logger.warning("Could not verify/switch Milvus database '%s': %s", self.db_name, error)

    def create_collection(
        self,
        collection_name: str,
        embedding_dim: Optional[int] = None,
        index_type: Optional[str] = None,
        metric_type: Optional[str] = None,
    ) -> bool:
        dimension = embedding_dim or _get_env_int("EMBEDDING_DIM", 768)
        resolved_index_type = index_type or os.getenv("MILVUS_INDEX_TYPE", "HNSW")
        resolved_metric_type = metric_type or os.getenv("MILVUS_METRIC_TYPE", "COSINE")

        if collection_name in self.client.list_collections(db_name=self.db_name):
            logger.info("Collection %s already exists", collection_name)
            return False

        index_params: Dict[str, Any] = {
            "metric_type": resolved_metric_type,
            "index_type": resolved_index_type,
        }

        if resolved_index_type == "HNSW":
            index_params["params"] = {
                "M": _get_env_int("MILVUS_HNSW_M", 16),
                "efConstruction": _get_env_int("MILVUS_HNSW_EF_CONSTRUCTION", 200),
            }
        elif resolved_index_type == "IVF_FLAT":
            index_params["params"] = {
                "nlist": _get_env_int("MILVUS_IVF_NLIST", 1024),
            }

        self.client.create_collection(
            collection_name=collection_name,
            dimension=dimension,
            metric_type=resolved_metric_type,
            primary_field_name="id",
            vector_field_name="vector",
            id_type="int",
            db_name=self.db_name,
            index_params=index_params,
        )
        logger.info("Created collection %s", collection_name)
        return True

    def insert_embeddings(
        self,
        collection_name: str,
        embeddings: List[List[float]],
        texts: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> List[int]:
        if metadata is None:
            metadata = [{"source": "unknown"} for _ in texts]

        data = []
        base_id = int(time.time() * 1000) % (2**31 - 1)

        for idx, (embedding, text, item_metadata) in enumerate(zip(embeddings, texts, metadata)):
            document_name = item_metadata.get("document_name") or item_metadata.get("filename", "")
            source = item_metadata.get("source", "unknown")
            metadata_json = json.dumps(item_metadata)

            unique_id = base_id + idx + random.randint(1, 999)
            unique_id = abs(unique_id) % (2**31 - 1)
            if unique_id == 0:
                unique_id = 1

            data.append(
                {
                    "id": unique_id,
                    "vector": embedding,
                    "text": text,
                    "document_name": document_name,
                    "source": source,
                    "metadata": metadata_json,
                }
            )

        logger.info(f"[LOADER_INSERT] Inserting {len(data)} documents into {collection_name} (db: {self.db_name})")
        result = self.client.insert(
            collection_name=collection_name, data=data, db_name=self.db_name
        )
        logger.info(f"[LOADER_INSERT] Insert result: {result}")

        try:
            flush_result = self.client.flush(collection_name=collection_name, db_name=self.db_name)
            logger.info(f"[LOADER_INSERT] Flush result: {flush_result}")
        except Exception as flush_error:
            logger.warning("Could not flush collection %s: %s", collection_name, flush_error)

        insert_count = result.get("insert_count", [])
        if isinstance(insert_count, list):
            return insert_count
        return []

    def delete_collection(self, collection_name: str) -> bool:
        self.client.drop_collection(collection_name=collection_name, db_name=self.db_name)
        return True

    def list_collections(self) -> List[str]:
        return self.client.list_collections(db_name=self.db_name)  # type: ignore[no-any-return]


class OllamaClient:
    """Minimal Ollama client for embeddings and model availability checks."""

    def __init__(
        self,
        host: Optional[str] = None,
        timeout: Optional[int] = None,
        pool_size: Optional[int] = None,
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

    def is_available(self, timeout: Optional[int] = None) -> bool:
        request_timeout = timeout if timeout is not None else self.timeout
        try:
            response = self.session.get(self.tags_endpoint, timeout=request_timeout)
            return response.status_code == 200  # type: ignore[no-any-return]
        except Exception:
            return False

    def get_available_models(self, timeout: Optional[int] = None) -> List[str]:
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
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> List[float]:
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
        texts: List[str],
        model: Optional[str] = None,
        batch_size: int = 32,
        max_workers: Optional[int] = None,
    ) -> List[Optional[List[float]]]:
        del batch_size

        if not texts:
            return []

        workers = max_workers or 4
        embeddings: List[Optional[List[float]]] = [None] * len(texts)

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


__all__ = ["MilvusVectorDB", "OllamaClient"]
