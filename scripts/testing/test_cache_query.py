#!/usr/bin/env python3
"""Test cache query to diagnose empty results issue."""

import sys
import json

sys.path.insert(0, ".")

from src.config.settings import get_settings
from src.tools.milvus_client import MilvusVectorDB

settings = get_settings()
vdb = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=settings.milvus_db_name,
)

collection_name = settings.response_cache_collection_name
print(f"Testing collection: {collection_name}")
print(f"Database: {settings.milvus_db_name}")
print("=" * 70)

# Test 1: Check if collection exists
collections = vdb.list_collections()
print(f"\n1. Collections in Milvus: {collections}")
print(f"   response_cache exists: {collection_name in collections}")

if collection_name not in collections:
    print(f"\n❌ Collection '{collection_name}' does not exist!")
    sys.exit(1)

# Test 2: Query with filter
print("\n2. Querying with filter='id > 0'...")
try:
    results = vdb.client.query(
        collection_name=collection_name,
        db_name=settings.milvus_db_name,
        filter="id > 0",
        output_fields=["id", "text", "metadata"],
        limit=10,
    )
    print(f"   ✓ Query successful: {len(results)} results")

    if results:
        for i, r in enumerate(results[:3]):
            meta = r.get("metadata", "{}")
            if isinstance(meta, str):
                meta = json.loads(meta)
            question = meta.get("question", "N/A")
            text = r.get("text", "")[:100]
            print(f"\n   Result {i + 1}:")
            print(f"   - ID: {r.get('id')}")
            print(f"   - Question: {question[:60]}")
            print(f"   - Answer: {text}...")
    else:
        print("   ⚠️ Query returned 0 results (collection might be empty)")

except Exception as e:
    print(f"   ❌ Query failed: {e}")
    import traceback

    traceback.print_exc()

# Test 3: Get collection stats
print("\n3. Collection statistics:")
try:
    stats = vdb.client.describe_collection(collection_name, db_name=settings.milvus_db_name)
    print(f"   Collection info: {stats}")
except Exception as e:
    print(f"   Failed to get stats: {e}")

print("\n" + "=" * 70)
print("Test complete!")
