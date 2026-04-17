from typing import Any, Dict, List, Optional

from src.tools.milvus_client import MilvusVectorDB

from .interfaces import VectorDBProvider


class MilvusVectorDBProvider(VectorDBProvider):
    """Provider interface implementation for Milvus vector database."""
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

    def search(self, collection_name: str, query_embedding: List[float], limit: int = 5) -> List[Dict]:
        return self._milvus.search(collection_name, query_embedding, limit)

    def add_documents(self, collection_name: str, documents: List[Dict[str, Any]]) -> None:
        embeddings = [doc["vector"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadata = [doc.get("metadata", {}) for doc in documents]
        self._milvus.insert_embeddings(collection_name, embeddings, texts, metadata)

    def list_collections(self) -> List[str]:
        return self._milvus.list_collections()


class MilvusCacheProvider:
    """Provider interface implementation for Milvus-based response cache."""
    def __init__(self, milvus_response_cache):
        # TODO: Type hint with MilvusResponseCache if import cycle is resolved
        self._cache = milvus_response_cache

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        pass

    def delete(self, key: str) -> None:
        pass
