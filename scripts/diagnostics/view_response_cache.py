#!/usr/bin/env python3
"""
Cache Management: View All Cached Q&A Pairs
Critical for understanding what's cached and cache effectiveness.

Use Cases:
- Inspect cached responses for quality
- Debug why certain queries aren't hitting cache
- Monitor cache content for accuracy
"""

import json
import sys
from typing import Optional

try:
    from src.config.settings import get_settings
    from src.tools.milvus_client import MilvusVectorDB
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Run from project root: python scripts/diagnostics/view_response_cache.py")
    sys.exit(1)


def view_response_cache(limit: int = 20, search_query: Optional[str] = None) -> None:
    """View cached Q&A pairs with optional filtering."""
    print("\n" + "=" * 100)
    print("📋 RESPONSE CACHE VIEWER")
    print("=" * 100)

    try:
        settings = get_settings()
        db = MilvusVectorDB(
            host=settings.milvus_host,
            port=settings.milvus_port,
            db_name=settings.milvus_db_name,
        )

        cache_collection = settings.response_cache_collection_name

        # Check collection exists
        collections = db.client.list_collections(db_name=settings.milvus_db_name)
        if cache_collection not in collections:
            print(f"❌ Cache collection '{cache_collection}' not found")
            return

        # Load collection
        db.client.load_collection(collection_name=cache_collection, db_name=settings.milvus_db_name)

        # Query all cached responses
        results = db.client.query(
            collection_name=cache_collection,
            db_name=settings.milvus_db_name,
            limit=limit * 2,  # Get extra to filter
            output_fields=["id", "metadata", "response"],
        )

        if not results:
            print("❌ No cached responses found")
            return

        print(f"✅ Found {len(results)} cached responses")

        # Filter by search query if provided
        if search_query:
            filtered_results = []
            for result in results:
                metadata = result.get("metadata", "{}")
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        continue

                question = metadata.get("question", "")
                response = str(result.get("response", ""))

                if (
                    search_query.lower() in question.lower()
                    or search_query.lower() in response.lower()
                ):
                    filtered_results.append(result)

            results = filtered_results[:limit]
            print(f"🔍 Filtered to {len(results)} results matching '{search_query}'")
        else:
            results = results[:limit]

        print("\n" + "=" * 100)

        # Display cached Q&A pairs
        for i, result in enumerate(results, 1):
            metadata = result.get("metadata", "{}")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = {"question": "Invalid JSON metadata", "timestamp": "unknown"}

            question = metadata.get("question", "No question found")
            timestamp = metadata.get("timestamp", "Unknown time")
            response = str(result.get("response", "No response found"))

            print(f"\n📝 CACHED PAIR #{i}")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"❓ QUESTION: {question}")
            print(f"⏰ TIMESTAMP: {timestamp}")
            print(f"💬 RESPONSE ({len(response)} chars):")

            # Format response for better readability
            if len(response) > 300:
                print(f"   {response[:300]}...")
                print(f"   [... truncated, full length: {len(response)} chars]")
            else:
                # Split long responses into lines
                words = response.split()
                lines = []
                current_line = []
                current_length = 0

                for word in words:
                    if current_length + len(word) + 1 > 80:
                        if current_line:
                            lines.append(" ".join(current_line))
                            current_line = [word]
                            current_length = len(word)
                        else:
                            lines.append(word)  # Single long word
                            current_length = 0
                    else:
                        current_line.append(word)
                        current_length += len(word) + 1

                if current_line:
                    lines.append(" ".join(current_line))

                for line in lines:
                    print(f"   {line}")

            # Check for sources in metadata
            sources = metadata.get("sources", [])
            if sources:
                print(f"\n📚 SOURCES ({len(sources)}):")
                for j, source in enumerate(sources[:3], 1):  # Show first 3 sources
                    doc_text = (
                        source.get("document", "")[:60] + "..."
                        if len(source.get("document", "")) > 60
                        else source.get("document", "No document")
                    )
                    score = source.get("score", "N/A")
                    print(f"   {j}. Score: {score} | {doc_text}")

        # Summary statistics
        print("\n" + "=" * 100)
        print("📊 CACHE STATISTICS")
        print("=" * 100)

        # Analyze question types
        topics = {}
        response_lengths = []

        for result in results:
            metadata = result.get("metadata", "{}")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    continue

            question = metadata.get("question", "").lower()
            response = str(result.get("response", ""))
            response_lengths.append(len(response))

            # Simple topic detection
            if "milvus" in question:
                topics["Milvus"] = topics.get("Milvus", 0) + 1
            elif "vector" in question or "embedding" in question:
                topics["Vectors/Embeddings"] = topics.get("Vectors/Embeddings", 0) + 1
            elif "collection" in question:
                topics["Collections"] = topics.get("Collections", 0) + 1
            elif "search" in question or "query" in question:
                topics["Search/Query"] = topics.get("Search/Query", 0) + 1
            else:
                topics["Other"] = topics.get("Other", 0) + 1

        print("📈 Question Topics:")
        for topic, count in sorted(topics.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(results)) * 100
            print(f"   {topic}: {count} ({percentage:.1f}%)")

        if response_lengths:
            avg_length = sum(response_lengths) / len(response_lengths)
            min_length = min(response_lengths)
            max_length = max(response_lengths)

            print("\n📏 Response Lengths:")
            print(f"   Average: {avg_length:.0f} characters")
            print(f"   Range: {min_length} - {max_length} characters")

        print(
            f"\n✅ Cache review complete - showing {len(results)} of {len(db.client.query(collection_name=cache_collection, db_name=settings.milvus_db_name, limit=10000))} total"
        )

    except Exception as e:
        print(f"❌ Error viewing response cache: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """Main function with command line argument support."""
    import argparse

    parser = argparse.ArgumentParser(description="View cached Q&A pairs")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of responses to show")
    parser.add_argument("--search", type=str, help="Filter responses containing this text")

    args = parser.parse_args()

    view_response_cache(limit=args.limit, search_query=args.search)


if __name__ == "__main__":
    main()
