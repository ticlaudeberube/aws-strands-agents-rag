#!/usr/bin/env python3
"""Script to clear the RAG Agent's local semantic response cache.

Usage:
    python scripts/cache/clear_cache.py

Local Mode is OpenSearch-backed. This deletes all documents from the local
OpenSearch ``rag-cache`` index (the Layer 4 semantic response cache). The
in-process L1/L2/L3 caches are per-process and cleared by restarting the
server, so they are not addressed here.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.settings import get_settings
from src.tools.opensearch_client import OpenSearchClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Clear the local OpenSearch semantic response cache."""
    logger.info("=" * 60)
    logger.info("RAG Agent Cache Clearing Utility")
    logger.info("=" * 60)

    try:
        settings = get_settings()
        logger.info("Loading settings...")
        logger.info(
            "  OpenSearch (local %s:%s)",
            settings.opensearch_local_host,
            settings.opensearch_local_port,
        )
        logger.info(f"  Ollama: {settings.ollama_host}")
        logger.info(f"  Cache index: {settings.opensearch_cache_index}")

        client = OpenSearchClient.for_local(settings)
        cache_index = settings.opensearch_cache_index

        logger.info("\nClearing semantic response cache (%s)...", cache_index)
        client.client.delete_by_query(
            index=cache_index,
            body={"query": {"match_all": {}}},
            conflicts="proceed",
            refresh=True,
        )

        logger.info("\n" + "=" * 60)
        logger.info("✓ Semantic response cache cleared successfully!")
        logger.info("=" * 60)
        return 0

    except Exception as e:
        logger.error(f"Error clearing caches: {e}", exc_info=True)
        logger.info("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
