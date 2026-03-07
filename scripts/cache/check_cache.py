#!/usr/bin/env python3
"""Quick cache status check."""

from src.config.settings import get_settings
from src.tools import MilvusVectorDB
import json

settings = get_settings()
db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=settings.milvus_db_name,
)

print("\n" + "=" * 80)
print("CACHE STATUS CHECK")
print("=" * 80)

try:
    # Check cache collection
    collections = db.client.list_collections(db_name=settings.milvus_db_name)
    cache_col = settings.response_cache_collection_name

    if cache_col not in collections:
        print(f"\n❌ Cache collection '{cache_col}' NOT found")
        print(f"   Available: {collections}")
        exit(1)

    db.client.load_collection(collection_name=cache_col, db_name=settings.milvus_db_name)
    results = db.client.query(
        collection_name=cache_col, db_name=settings.milvus_db_name, limit=10000
    )

    count = len(results) if results else 0

    print(f"\n✅ Cache collection: {cache_col}")
    print(f"✅ Cached items: {count}")
    print(f"✅ Embedding dimension: {settings.response_cache_embedding_dim}")

    # Check for "What is Milvus?"
    milvus_found = False
    for r in results:
        meta = r.get("metadata", {})
        if isinstance(meta, str):
            meta = json.loads(meta)
        if "What is Milvus?" in meta.get("question", ""):
            milvus_found = True
            break

    if milvus_found:
        print("✅ 'What is Milvus?' in cache")
    else:
        print("❌ 'What is Milvus?' NOT in cache")

    print("\n" + "=" * 80)
    print("✅ CACHE IS READY TO USE")
    print("=" * 80)
    print("\nNow run your test or chatbot (make sure to restart the process):")
    print("  python test_manual_query.py")
    print("  python chatbots/interactive_chat.py")
    print()

except Exception as e:
    print(f"\n❌ Error: {e}")
    exit(1)
