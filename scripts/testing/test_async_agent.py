#!/usr/bin/env python3
"""Test async agent with latest vector database news query."""

import asyncio
import sys

from src.agents.strands_graph_agent import StrandsGraphRAGAgent
from src.config.settings import Settings


async def test_async_agent():
    """Test the async agent with time-sensitive query."""
    print("Initializing async agent...")
    settings = Settings()
    agent = StrandsGraphRAGAgent(settings=settings)

    question = "What is the latest vector database news?"
    print(f"Query: {question}")
    print("=" * 80)

    # Call the async method
    answer, sources = await agent.answer_question(
        question=question, collection_name=settings.ollama_collection_name
    )

    print(f"✓ Answer length: {len(answer)} chars")
    print(f"✓ Sources count: {len(sources)}")
    print()

    # Check source types
    web = [s for s in sources if s.get("source_type") == "web_search"]
    cached = [s for s in sources if s.get("source_type") == "cached"]
    kb = [s for s in sources if s.get("source_type") not in ["web_search", "cached"]]

    print(f"✓ Source types: Web={len(web)}, KB={len(kb)}, Cached={len(cached)}")

    if len(answer) > 100:
        print("\n✓ Answer has substance (>100 chars)")
        print("\nAnswer preview:")
        print(answer[:500])
        if len(answer) > 500:
            print("...")
    else:
        print(f"\n✗ Answer too short ({len(answer)} chars):")
        print(answer)

    if len(web) > 0:
        print("\n✓ Web sources included:")
        for idx, source in enumerate(web[:2], 1):
            print(f"  [{idx}] {source.get('title', 'Untitled')}")
    else:
        print("\n✗ No web sources (but expected some for time-sensitive query)")

    print("\n" + "=" * 80)
    if len(answer) > 100 and len(web) > 0:
        print("✅ TEST PASSED: Agent working with async API!")
    else:
        print("⚠️  Partial success: Please check logs above")


if __name__ == "__main__":
    try:
        asyncio.run(test_async_agent())
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
