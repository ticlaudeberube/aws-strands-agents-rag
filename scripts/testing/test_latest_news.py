#!/usr/bin/env python3
"""Test web search for latest vector database news."""

import sys
import time

from src.agents.strands_graph_agent import StrandsGraphRAGAgent
from src.config.settings import Settings


def test_latest_news():
    """Test time-sensitive query with web search."""
    print("Initializing agent...")
    settings = Settings()
    agent = StrandsGraphRAGAgent(settings=settings)

    # Test with the problematic time-sensitive query
    question = "What is the latest vector database news?"
    print(f"Query: {question}")
    print("=" * 80)

    start = time.time()
    answer, sources = agent.answer_question(
        question, collection_name=settings.ollama_collection_name
    )
    elapsed = time.time() - start

    print(f"✓ Answer length: {len(answer)} chars")
    print(f"✓ Sources count: {len(sources)}")
    print(f"✓ Time: {elapsed:.1f}s")
    print()

    # Check source types
    web = [s for s in sources if s.get("source_type") == "web_search"]
    cached = [s for s in sources if s.get("source_type") == "cached"]
    kb = [s for s in sources if s.get("source_type") not in ["web_search", "cached"]]

    print(f"✓ Source types: Web={len(web)}, KB={len(kb)}, Cached={len(cached)}")

    if len(answer) > 100:
        print("\n✓ Answer has substance (>100 chars)")
        print("\nAnswer preview (first 300 chars):")
        print(answer[:300])
        print("...")
    else:
        print(f"\n✗ Answer too short ({len(answer)} chars)")
        print("Full answer:", answer)

    if len(web) > 0:
        print("\n✓ Web sources included:")
        for idx, source in enumerate(web[:3], 1):
            print(f"  [{idx}] {source.get('title', 'Untitled')}")
    else:
        print("\n✗ No web sources found")

    print("\n" + "=" * 80)
    if len(answer) > 200 and len(web) > 0:
        print("✅ TEST PASSED: Web search working, good answer with sources")
    else:
        print("❌ TEST FAILED: Need more answer content and web sources")


if __name__ == "__main__":
    try:
        test_latest_news()
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
