"""Custom exceptions for Milvus operations."""

class MilvusConnectionError(Exception):
    """Raised when connection to Milvus fails."""
    pass

class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass

class CollectionError(Exception):
    """Raised when collection operations fail."""
    pass

class EmbeddingError(Exception):
    """Raised when embedding operations fail."""
    pass