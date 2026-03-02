"""Collection operations for Milvus."""

from typing import Any, Dict, List, Tuple
import os
from pymilvus import MilvusException  # type: ignore[import-untyped]
from .client import get_client
from .exceptions import CollectionError
from .embeddings import EmbeddingProvider


def create_collection(
    collection_name: str | None,
    dimension: int = 1536,
    metric_type: str = "COSINE",
    consistency_level: str = "Session",
    auto_index: bool = True,
) -> None:
    """Create or recreate a collection.

    Args:
        auto_index: If True, creates collection with automatic index.
                   If False, creates collection without index (you must create index separately).
    """
    if not collection_name:
        raise CollectionError("collection_name is required")

    try:
        client = get_client()
        if client.has_collection(collection_name=collection_name):
            client.drop_collection(collection_name=collection_name)

        if auto_index:
            # Simple method - creates collection with automatic index
            client.create_collection(
                collection_name=collection_name,
                dimension=dimension,
                metric_type=metric_type,
                consistency_level=consistency_level,
            )
        else:
            # Schema method - creates collection without index
            from pymilvus import DataType

            schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
            schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
            schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dimension)
            schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
            schema.add_field(field_name="subject", datatype=DataType.VARCHAR, max_length=100)

            client.create_collection(collection_name=collection_name, schema=schema)

        print(
            f"Collection - {collection_name} - created successfully {'with auto-index' if auto_index else 'without index'}"
        )
    except MilvusException as e:
        raise CollectionError(f"Failed to create collection '{collection_name}': {e}")


def drop_collection(collection_name: str | None) -> None:
    """Drop a collection."""
    if not collection_name:
        raise CollectionError("collection_name is required")

    try:
        client = get_client()
        client.drop_collection(collection_name=collection_name)
        print(f"Collection - {collection_name} - dropped successfully")
    except MilvusException as e:
        raise CollectionError(f"Failed to drop collection '{collection_name}': {e}")


def has_collection(collection_name: str) -> bool:
    """Check if collection exists."""
    client = get_client()
    return bool(client.has_collection(collection_name=collection_name))  # type: ignore[no-any-return]


def insert_data(collection_name: str, data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Insert data into collection."""
    client = get_client()
    result = client.insert(collection_name=collection_name, data=data)
    return result if isinstance(result, dict) else {}  # type: ignore[no-any-return]


def vectorize_documents(collection_name: str, docs: List[str]) -> Tuple[Dict[str, Any], int]:
    """Vectorize documents using Ollama and insert into collection."""
    # Get embedding dimension from the environment or use default
    embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5")

    # Generate embeddings using Ollama
    embedding_provider = EmbeddingProvider()
    vectors = embedding_provider.embed_text(docs, provider="ollama", model=embedding_model)

    # Handle single vs batch vectors
    if not isinstance(vectors[0], list):
        vectors = [vectors]

    dimension = len(vectors[0])
    print(f"Embedding dimension: {dimension}")

    # Create collection with correct dimensions
    create_collection(collection_name, dimension=dimension)

    # Prepare data
    data = [
        {"id": i, "vector": vectors[i], "text": docs[i], "subject": "history"}
        for i in range(len(vectors))
    ]

    print("Data has", len(data), "entities, each with fields:", data[0].keys())
    print("Vector dim:", len(data[0]["vector"]))

    # Insert data
    res = insert_data(collection_name, data)
    return res, dimension
