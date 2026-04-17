from abc import ABC, abstractmethod
from typing import Any


class VectorDBProvider(ABC):
    @abstractmethod
    def search(
        self, collection_name: str, query_embedding: list[float], limit: int = 5
    ) -> list[dict]:
        """Search the vector database and return results."""
        pass

    @abstractmethod
    def add_documents(self, collection_name: str, documents: list[dict[str, Any]]) -> None:
        """Add documents to the vector database."""
        pass

    @abstractmethod
    def list_collections(self) -> list[str]:
        """List all available collections."""
        pass


class CacheProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Get a value from the cache by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in the cache with optional TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a value from the cache by key."""
        pass
