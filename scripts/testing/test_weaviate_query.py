#!/usr/bin/env python3
"""
Diagnostic test for Weaviate query to check web search functionality.
"""

import asyncio
import logging

from src.agents.strands_graph_agent import StrandsGraphRAGAgent
from src.config.settings import Settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_weaviate_query():
    """Test web search for Weaviate query."""
    logger.info("=" * 80)
    logger.info("TESTING: Weaviate Query with Web Search")
    logger.info("=" * 80)

    # Initialize settings
    settings = Settings()

    # Initialize agent
    agent = StrandsGraphRAGAgent(settings=settings)

    query = "Tell me about Weaviate db"
    logger.info(f"\nQuery: {query}")
    logger.info("-" * 80)

    # Execute query
    result = await agent.answer_question(query)

    logger.info("\n✓ RESPONSE RECEIVED")
    logger.info("-" * 80)
    logger.info(f"Answer length: {len(result['answer'])} chars")
    logger.info(f"Total sources: {len(result['sources'])}")

    # Analyze sources
    logger.info("\nSOURCE TYPES:")
    source_types = {}
    for src in result["sources"]:
        source_type = src.get("source_type", "unknown")
        if source_type not in source_types:
            source_types[source_type] = 0
        source_types[source_type] += 1
        logger.info(f"  - {source_type}: {src.get('title', 'N/A')[:60]}")

    logger.info("\nSOURCE COUNT BY TYPE:")
    for stype, count in source_types.items():
        logger.info(f"  {stype}: {count}")

    # Check for web search results
    web_sources = [s for s in result["sources"] if s.get("source_type") == "web_search"]
    kb_sources = [s for s in result["sources"] if s.get("source_type") == "knowledge_base"]

    logger.info("\n" + "=" * 80)
    if web_sources:
        logger.info(f"✓ WEB SEARCH ACTIVE: {len(web_sources)} web sources found")
        logger.info("\nWEB SOURCES:")
        for src in web_sources:
            logger.info(f"  URL: {src.get('url', 'N/A')}")
            logger.info(f"  Title: {src.get('title', 'N/A')}")
            logger.info(f"  Snippet: {src.get('snippet', 'N/A')[:80]}...")
            logger.info()
    else:
        logger.warning("✗ NO WEB SOURCES FOUND")

    if kb_sources:
        logger.info(f"✓ KB SOURCES: {len(kb_sources)} KB sources found")
        logger.info("\nKB SOURCES (first 3):")
        for src in kb_sources[:3]:
            logger.info(f"  {src.get('title', 'N/A')}")

    # Check answer content
    logger.info("\n" + "=" * 80)
    logger.info("ANSWER CONTENT CHECK:")
    logger.info("-" * 80)

    answer_lower = result["answer"].lower()
    weaviate_mentions = answer_lower.count("weaviate")
    milvus_mentions = answer_lower.count("milvus")

    logger.info(f"'weaviate' mentions in answer: {weaviate_mentions}")
    logger.info(f"'milvus' mentions in answer: {milvus_mentions}")

    if "weaviate" in answer_lower:
        logger.info("✓ ANSWER CONTAINS WEAVIATE")
    else:
        logger.warning("✗ ANSWER DOES NOT CONTAIN WEAVIATE")

    if "milvus" in answer_lower and len(kb_sources) == 0:
        logger.warning("✗ ANSWER CONTAINS MILVUS but no KB sources - likely hallucination")

    logger.info("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_weaviate_query())
