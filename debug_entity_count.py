#!/usr/bin/env python3
"""Check entity count in the collection directly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.tools.milvus_client import MilvusVectorDB
from src.config.settings import get_settings

settings = get_settings()
vector_db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=settings.milvus_db_name,
)

collection_name = settings.response_cache_collection_name

try:
    # Load collection
    vector_db.client.load_collection(
        collection_name=collection_name, db_name=settings.milvus_db_name
    )

    # Get entity count by querying
    all_entities = vector_db.client.query(
        collection_name=collection_name,
        db_name=settings.milvus_db_name,
        output_fields=["id"],
        limit=10000,
    )
    entity_count = len(all_entities) if all_entities else 0
    print(f"Entity count in {collection_name}: {entity_count}")

    # Try different query approaches
    print("\n1. Try query with no expr:")
    results = vector_db.client.query(
        collection_name=collection_name,
        db_name=settings.milvus_db_name,
        output_fields=["id"],
        limit=10,
    )
    print(f"   Result: {len(results) if results else 0} entities")

    print("\n2. Try query with expr='id >= 0':")
    results = vector_db.client.query(
        collection_name=collection_name,
        db_name=settings.milvus_db_name,
        expr="id >= 0",
        output_fields=["id"],
        limit=10,
    )
    print(f"   Result: {len(results) if results else 0} entities")

    print("\n3. Try get all with Milvus info:")
    collection_info = vector_db.client.describe_collection(
        collection_name=collection_name, db_name=settings.milvus_db_name
    )
    print(f"   Collection info: {collection_info}")

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
