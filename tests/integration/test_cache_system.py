#!/usr/bin/env python3
"""Debug script to test cache lookup for 'What is Milvus?' question."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import get_settings
from src.tools.milvus_client import MilvusVectorDB
from src.tools.ollama_client import OllamaClient
from src.tools.response_cache import MilvusResponseCache

settings = get_settings()
vector_db = MilvusVectorDB()
ollama_client = OllamaClient()
response_cache = MilvusResponseCache(vector_db, embedding_dim=settings.response_cache_embedding_dim)

print("=" * 70)
print("CACHE LOOKUP TEST: 'What is Milvus?'")
print("=" * 70)

# Step 1: Check cache collection exists and has data
print("\n[Step 1] Checking cache collection...")
try:
    collections = vector_db.list_collections()
    print(f"Available collections: {collections}")

    if settings.response_cache_collection_name in collections:
        stats = vector_db.client.get_collection_stats(settings.response_cache_collection_name)
        print(f"✓ Cache collection '{settings.response_cache_collection_name}' exists")
        print(f"  Documents in cache: {stats['row_count']}")
    else:
        print(f"✗ Cache collection '{settings.response_cache_collection_name}' NOT FOUND")
        sys.exit(1)
except Exception as e:
    print(f"✗ Error checking collections: {e}")
    sys.exit(1)

# Step 2: Embed the question
print("\n[Step 2] Embedding question...")
question = "What is Milvus?"
try:
    embedding = ollama_client.embed_text(question)
    print(f"✓ Generated embedding (dim={len(embedding)})")
    print(f"  First 5 values: {embedding[:5]}")
except Exception as e:
    print(f"✗ Error generating embedding: {e}")
    sys.exit(1)

# Step 3: Search cache
print("\n[Step 3] Searching cache...")
try:
    cached_response = response_cache.search_cache(question, embedding)
    if cached_response:
        print("✓ CACHE HIT!")
        print(f"  Question: {cached_response.get('question', '')[:60]}")
        answer = cached_response.get("response", "")
        print(f"  Answer: {answer[:100]}...")
        print(f"  Similarity: {cached_response.get('similarity', 0):.2%}")
        print(f"  Distance: {cached_response.get('distance', 0):.4f}")
        print(f"  Sources: {len(cached_response.get('sources', []))} items")
    else:
        print("✗ CACHE MISS - no match found in cache")
except Exception as e:
    print(f"✗ Error searching cache: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Step 4: Direct Milvus search to see similarity scores
print("\n[Step 4] Direct Milvus search for debugging...")
try:
    results = vector_db.search(settings.response_cache_collection_name, embedding, limit=5)

    if results and len(results) > 0:
        print(f"✓ Found {len(results)} results from Milvus:")
        for i, hit in enumerate(results):
            distance = hit.get("distance", 0)
            print(f"  [{i + 1}] Distance: {distance:.4f}")
            if distance < 1.0:
                print(f"      ^ Would be cached if threshold >= {distance:.2f}")
    else:
        print("✗ No results from Milvus")
except Exception as e:
    print(f"✗ Error in direct search: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 70)
print("CACHE THRESHOLD SETTING: {:.2f}".format(settings.response_cache_threshold))
print("=" * 70)
