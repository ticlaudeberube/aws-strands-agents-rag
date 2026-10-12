#!/usr/bin/env python3
"""Direct test of list_all_cached_questions method to identify the issue."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.tools.milvus_client import MilvusVectorDB
from src.config.settings import get_settings

settings = get_settings()

# Create Milvus client with settings
vector_db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=settings.milvus_db_name,
)

print("Settings:")
print(f"  Milvus host: {settings.milvus_host}")
print(f"  Milvus port: {settings.milvus_port}")
print(f"  Milvus DB: {settings.milvus_db_name}")
print(f"  Response cache collection: {settings.response_cache_collection_name}")
print()

# Test list_all_cached_questions
print("Testing list_all_cached_questions...")
try:
    questions = vector_db.list_all_cached_questions(
        collection_name=settings.response_cache_collection_name, limit=100
    )
    print("✓ Method succeeded")
    print(f"  Questions returned: {len(questions)}")
    if questions:
        print("  First 3 questions:")
        for q in questions[:3]:
            print(f"    - ID: {q.get('id')}, Question: {q.get('question', '')[:60]}")
    else:
        print("  ❌ NO QUESTIONS RETURNED")
except Exception as e:
    print(f"❌ Method failed: {e}")
    import traceback

    traceback.print_exc()

# Also test the raw Milvus query to see what's in the collection
print("\nTesting raw Milvus query...")
try:
    collections = vector_db.client.list_collections(db_name=settings.milvus_db_name)
    print(f"Collections in db '{settings.milvus_db_name}': {collections}")

    if settings.response_cache_collection_name in collections:
        print(f"✓ Collection {settings.response_cache_collection_name} exists")

        # Try to query directly
        try:
            vector_db.client.load_collection(
                collection_name=settings.response_cache_collection_name,
                db_name=settings.milvus_db_name,
            )
            print("✓ Collection loaded")
        except Exception as e:
            print(f"Note: Collection load: {e}")

        # Try raw query
        raw_results = vector_db.client.query(
            collection_name=settings.response_cache_collection_name,
            db_name=settings.milvus_db_name,
            output_fields=["id", "text", "metadata"],
            limit=100,
        )
        print(f"Raw Milvus query returned {len(raw_results) if raw_results else 0} results")
        if raw_results:
            print(f"First result: {raw_results[0]}")
    else:
        print(f"❌ Collection {settings.response_cache_collection_name} NOT FOUND")
        print(f"  Available collections: {collections}")
except Exception as e:
    print(f"❌ Raw query failed: {e}")
    import traceback

    traceback.print_exc()

print("\nDone.")
