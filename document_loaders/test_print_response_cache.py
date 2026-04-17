#!/usr/bin/env python3
"""Test script to retrieve and print all entities from the response_cache collection in Milvus."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from document_loaders.core.tools import MilvusVectorDB
from document_loaders.local_settings import get_loader_settings

settings = get_loader_settings()
vector_db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=settings.milvus_db_name,
)

collection_name = settings.response_cache_collection_name

print(f"Querying all entities from collection: {collection_name} (db: {settings.milvus_db_name})")

try:
    vector_db.client.load_collection(collection_name=collection_name, db_name=settings.milvus_db_name)
    results = vector_db.client.query(
        collection_name=collection_name,
        db_name=settings.milvus_db_name,
        output_fields=["id", "text", "metadata"],
        limit=100,
    )
    print(f"Found {len(results)} entities in {collection_name}:")
    for i, entity in enumerate(results):
        print(f"Entity {i+1}: {entity}")
except Exception as e:
    print(f"Error querying Milvus: {e}")
