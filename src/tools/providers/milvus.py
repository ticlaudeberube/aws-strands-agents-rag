from typing import Any

from src.tools.milvus_client import MilvusVectorDB

from .interfaces import VectorDBProvider


class MilvusVectorDBProvider(VectorDBProvider):
    """Provider interface implementation for Milvus vector database."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db_name: str | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: int | None = None,
        pool_size: int | None = None,
    ):
        # Pass all arguments positionally to match MilvusVectorDB signature
        self._milvus = MilvusVectorDB(
            host,
            port,
            db_name,
            user,
            password,
            timeout,
            pool_size,
        )

    def search(
        self, collection_name: str, query_embedding: list[float], limit: int = 5
    ) -> list[dict]:
        return self._milvus.search(collection_name, query_embedding, limit)

    def add_documents(self, collection_name: str, documents: list[dict[str, Any]]) -> None:
        embeddings = [doc["vector"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadata = [doc.get("metadata", {}) for doc in documents]
        self._milvus.insert_embeddings(collection_name, embeddings, texts, metadata)

    def list_collections(self) -> list[str]:
        return self._milvus.list_collections()


class MilvusCacheProvider:
    """Provider interface implementation for Milvus-based response cache."""

    def __init__(self, milvus_response_cache):
        # TODO: Type hint with MilvusResponseCache if import cycle is resolved
        self._cache = milvus_response_cache

    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        pass

    def delete(self, key: str) -> None:
        pass
