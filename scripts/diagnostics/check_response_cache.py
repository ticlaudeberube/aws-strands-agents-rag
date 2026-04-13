#!/usr/bin/env python3
"""
Production Monitoring: Check Response Cache Status
Essential for monitoring cache health in production environments.

Use Cases:
- Verify cache is populated after data loading
- Troubleshoot cache-related performance issues
- Monitor cache collection entity count
"""

import json
import sys

try:
    from src.config.settings import get_settings
    from src.tools.milvus_client import MilvusVectorDB
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Run from project root: python scripts/diagnostics/check_response_cache.py")
    sys.exit(1)


def check_response_cache() -> None:
    """Check response cache collection status and health."""
    print("\n" + "=" * 80)
    print("🔍 RESPONSE CACHE STATUS CHECK")
    print("=" * 80)

    try:
        settings = get_settings()
        db = MilvusVectorDB(
            host=settings.milvus_host,
            port=settings.milvus_port,
            db_name=settings.milvus_db_name,
        )

        cache_collection = settings.response_cache_collection_name

        # Check if collection exists
        collections = db.client.list_collections(db_name=settings.milvus_db_name)
        if cache_collection not in collections:
            print(f"❌ Cache collection '{cache_collection}' NOT found")
            print(f"   Available collections: {collections}")
            print("\n💡 To fix: Run document loader to create cache collection")
            return

        # Load collection and get stats
        db.client.load_collection(collection_name=cache_collection, db_name=settings.milvus_db_name)

        # Get collection stats
        stats = db.client.get_collection_stats(
            collection_name=cache_collection, db_name=settings.milvus_db_name
        )

        entity_count = stats.get("row_count", 0)

        # Query sample records
        results = db.client.query(
            collection_name=cache_collection,
            db_name=settings.milvus_db_name,
            limit=5,
            output_fields=["id", "metadata", "response"],
        )

        print(f"✅ Cache Collection: {cache_collection}")
        print(f"✅ Entity Count: {entity_count}")
        print(f"✅ Embedding Dimension: {settings.response_cache_embedding_dim}")
        print(f"✅ Sample Records: {len(results)}")

        # Analyze cache content
        if results:
            print("\n📋 Sample Cache Contents:")
            for i, result in enumerate(results[:3], 1):
                metadata = result.get("metadata", "{}")
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {"question": "Invalid JSON"}

                question = (
                    metadata.get("question", "Unknown")[:50] + "..."
                    if len(metadata.get("question", "")) > 50
                    else metadata.get("question", "Unknown")
                )
                response_len = len(str(result.get("response", "")))

                print(f"   {i}. Q: {question}")
                print(f"      Response length: {response_len} chars")

        # Check for common test queries
        test_queries = [
            "What is Milvus?",
            "How do I create a collection?",
            "What are vector embeddings?",
        ]

        print("\n🔍 Common Query Cache Check:")
        for query in test_queries:
            found = any(
                query.lower() in str(result.get("metadata", "")).lower() for result in results
            )
            status = "✅" if found else "❌"
            print(f"   {status} '{query}' {'cached' if found else 'not found'}")

        # Health assessment
        print("\n📊 Cache Health Assessment:")
        if entity_count == 0:
            print("   🔴 CRITICAL: Cache is empty - no responses cached")
            print("   💡 Action: Run document loader or check embedding process")
        elif entity_count < 10:
            print("   🟡 WARNING: Very few responses cached")
            print("   💡 Action: Verify document loading completed successfully")
        elif entity_count < 100:
            print("   🟢 GOOD: Moderate cache coverage")
        else:
            print("   🟢 EXCELLENT: Well-populated cache")

        print("\n" + "=" * 80)
        print("✅ RESPONSE CACHE CHECK COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"❌ Error checking response cache: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    check_response_cache()
