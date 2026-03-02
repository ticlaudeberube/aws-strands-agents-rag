"""Milvus client connection management."""

from typing import Optional
from pymilvus import MilvusClient
from .config import get_milvus_config
from .exceptions import MilvusConnectionError

# Global client instance - initialized lazily
_client: Optional[MilvusClient] = None


def get_client(db_name: Optional[str] = None) -> MilvusClient:
    """Get Milvus client with lazy initialization and connection validation.

    Args:
        db_name: Optional database name to use. If not provided, uses config default.
    """
    global _client
    if _client is None:
        try:
            config = get_milvus_config()
            _client = MilvusClient(uri=config.uri, token=config.token)
            # Use provided db_name or config default
            _db_name = db_name or config.db_name
            if _db_name != "default":
                # Ensure database exists
                if _db_name not in _client.list_databases():
                    _client.create_database(db_name=_db_name)
                _client.using_database(_db_name)
            # Test connection
            _client.list_databases()
        except Exception as e:
            raise MilvusConnectionError(f"Failed to connect to Milvus: {e}")
    return _client


def reset_client() -> None:
    """Reset client connection (useful for testing)."""
    global _client
    _client = None
