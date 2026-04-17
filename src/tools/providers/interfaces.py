from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class VectorDBProvider(ABC):
    @abstractmethod
    def search(self, collection_name: str, query_embedding: List[float], limit: int = 5) -> List[Dict]:
        """Search the vector database and return results."""
        pass

    @abstractmethod
    def add_documents(self, collection_name: str, documents: List[Dict[str, Any]]) -> None:
        """Add documents to the vector database."""
        pass

    @abstractmethod
    def list_collections(self) -> List[str]:
        """List all available collections."""
        pass

class CacheProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in the cache with optional TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a value from the cache by key."""
        pass
