#!/usr/bin/env python3
"""Debug script to trace web search execution in RAG agent."""

import asyncio
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.agents.strands_graph_agent import StrandsGraphRAGAgent  # noqa: E402
from src.config.settings import get_settings  # noqa: E402


async def main() -> None:
    """Main async function to test web search functionality."""
    # Get settings
    settings = get_settings()
    print(f"\n{'=' * 60}")
    print("SETTINGS CHECK")
    print(f"{'=' * 60}")
    print(f"Enable web search: {settings.enable_web_search_supplement}")
    print(
        f"Tavily API key: {settings.tavily_api_key[:20] if settings.tavily_api_key else 'NOT SET'}..."
    )
    print(f"Web search timeout: {settings.web_search_timeout}")

    # Initialize agent
    print(f"\n{'=' * 60}")
    print("INITIALIZING RAG AGENT")
    print(f"{'=' * 60}")
    agent = StrandsGraphRAGAgent(settings=settings)

    # Test question
    question = "Tell me about Pinecone vector database"
    print(f"\n{'=' * 60}")
    print("TESTING WEB SEARCH")
    print(f"{'=' * 60}")
    print(f"Question: {question}\n")

    # Get answer
    result = await agent.answer_question(
        question=question,
        collection_name="milvus_docs",
        top_k=5,
    )
    answer, sources = result if isinstance(result, tuple) else (str(result), [])

    # Display results
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print("\nAnswer:")
    print("------")
    print(answer[:500])
    if len(answer) > 500:
        print(f"... ({len(answer)} total characters)")

    print(f"\n\nSources ({len(sources)} total):")
    print("-----")
    for i, source in enumerate(sources, 1):
        source_type = source.get("source_type", "unknown")
        title = source.get("title", "Unknown")
        url = source.get("url", "No URL")
        print(f"{i}. [{source_type}] {title}")
        if url and url != "No URL":
            print(f"   URL: {url}")

    # Count by source type
    web_sources = [s for s in sources if s.get("source_type") == "web_search"]
    kb_sources = [s for s in sources if s.get("source_type") != "web_search"]

    print("\n\nSource breakdown:")
    print(f"  Web search sources: {len(web_sources)}")
    print(f"  Knowledge base sources: {len(kb_sources)}")

    if len(web_sources) > 0:
        print(f"\n✓ WEB SEARCH IS WORKING - {len(web_sources)} web sources found")
    else:
        print("\n✗ WEB SEARCH NOT WORKING - No web sources in response")


if __name__ == "__main__":
    asyncio.run(main())
    print("\nDiagnosis:")
    print("- Check if TAVILY_API_KEY is set in .env")
    print("- Check if enable_web_search_supplement=True in settings")
    print("- Check if WebSearchClient is being instantiated correctly")
    print("- Check server logs for [RAG_WORKER] web search related messages")
