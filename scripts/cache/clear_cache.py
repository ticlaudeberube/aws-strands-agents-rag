#!/usr/bin/env python3
"""Script to clear all RAG Agent caches.

Usage:
    python scripts/clear_cache.py

This will clear:
- Embedding cache (query embeddings)
- Search cache (retrieval results)
- response cache (generated answers)
- Response cache (semantic matching cache)
"""

import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.settings import get_settings
from src.agents.strands_graph_agent import StrandsGraphRAGAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Clear all caches in the RAG Agent."""
    logger.info("=" * 60)
    logger.info("RAG Agent Cache Clearing Utility")
    logger.info("=" * 60)

    try:
        # Get settings
        settings = get_settings()
        logger.info("Loading settings...")
        logger.info(f"  Milvus: {settings.milvus_host}:{settings.milvus_port}")
        logger.info(f"  Ollama: {settings.ollama_host}")
        logger.info(f"  Database: {settings.milvus_db_name}")

        # Initialize RAG Agent
        logger.info("\nInitializing RAG Agent...")
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                agent = StrandsGraphRAGAgent(settings=settings)
                break
            except RuntimeError as e:
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(f"Connection attempt {retry_count} failed, retrying in 2s...")
                    import time

                    time.sleep(2)
                else:
                    logger.error(f"Failed to connect after {max_retries} attempts: {e}")
                    raise

        # Log cache sizes before clearing
        logger.info("\nCache sizes before clearing:")
        logger.info(f"  Embedding cache: {len(agent.embedding_cache)} items")
        logger.info(f"  Search cache: {len(agent.search_cache)} items")
        logger.info(f"  response cache: {len(agent.answer_cache)} items")

        if agent.response_cache:
            try:
                response_cache_count = agent.response_cache.get_cache_size()
                logger.info(f"  Response cache: {response_cache_count} items")
            except AttributeError:
                logger.info("  Response cache: (size unknown)")
        else:
            logger.info("  Response cache: (not available)")

        # Clear caches
        logger.info("\nClearing all caches...")
        agent.clear_caches()

        # Verify caches are cleared
        logger.info("\nCache sizes after clearing:")
        logger.info(f"  Embedding cache: {len(agent.embedding_cache)} items")
        logger.info(f"  Search cache: {len(agent.search_cache)} items")
        logger.info(f"  response cache: {len(agent.answer_cache)} items")

        if agent.response_cache:
            try:
                response_cache_count = agent.response_cache.get_cache_size()
                logger.info(f"  Response cache: {response_cache_count} items")
            except AttributeError:
                logger.info("  Response cache: (cleared)")

        logger.info("\n" + "=" * 60)
        logger.info("✓ All caches cleared successfully!")
        logger.info("=" * 60)
        return 0

    except Exception as e:
        logger.error(f"Error clearing caches: {e}", exc_info=True)
        logger.info("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
