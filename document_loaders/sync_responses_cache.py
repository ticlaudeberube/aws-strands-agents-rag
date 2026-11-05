#!/usr/bin/env python3
"""Load pre-generated Q&A pairs into the OpenSearch response cache.

This script loads question-answer pairs with their embeddings into the
OpenSearch ``rag-cache`` index, enabling instant semantic cache hits for common
questions. The documents are shaped like the runtime
``src/tools/opensearch_client.py`` cache entries (``question`` / ``vector`` /
``answer`` / ``sources`` / ``created_at``) so the runtime
``OpenSearchClient.search_semantic_cache`` reads them correctly.

Usage: python document_loaders/sync_responses_cache.py
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path BEFORE imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from document_loaders.core.tools import OllamaClient, OpenSearchVectorDB
from document_loaders.local_settings import get_loader_settings

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

settings = get_loader_settings()
cache_index = settings.opensearch_cache_index
vector_db = OpenSearchVectorDB(
    host=settings.opensearch_local_host,
    port=settings.opensearch_local_port,
)
ollama_client = OllamaClient(
    host=settings.ollama_host,
    timeout=settings.ollama_timeout,
)


def _ensure_cache_index(embedding_dim: int) -> None:
    """Create the ``rag-cache`` index with cache-shaped fields if absent.

    Mirrors src/tools/opensearch_client.py's cache index body: the base k-NN
    body plus ``question`` / ``answer`` / ``sources`` / ``created_at``.
    """
    if vector_db.client.indices.exists(index=cache_index):
        return

    body = vector_db._index_body(embedding_dim)
    body["mappings"]["properties"].update(
        {
            "question": {"type": "text"},
            "answer": {"type": "text"},
            "sources": {"type": "object", "enabled": True},
            "created_at": {"type": "date"},
        }
    )
    vector_db.client.indices.create(index=cache_index, body=body)
    logger.info("Created OpenSearch cache index: %s", cache_index)


def load_responses_cache():
    """Load pre-generated Q&A pairs into the response cache.

    Always runs to sync responses into the cache.
    """
    try:
        with open("./data/responses.json", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ Error: ./data/responses.json not found")
        print("   Please create with format:")
        print("   {")
        print('     "qa_pairs": [')
        print("       {")
        print('         "question": "What is Milvus?",')
        print('         "answer": "Milvus is a vector database...",')
        print('         "sources": []')
        print("       }")
        print("     ]")
        print("   }")
        return

    qa_pairs = data.get("qa_pairs", [])
    if not qa_pairs:
        print("❌ No Q&A pairs found in responses.json")
        return

    print(f"Using cache index: {cache_index}")

    # Clear and recreate the cache index to prevent duplicates
    try:
        if vector_db.delete_index(cache_index):
            print(f"✓ Cleared {cache_index}")
        _ensure_cache_index(settings.response_cache_embedding_dim)
        print(f"✓ Created {cache_index}")
    except Exception as e:
        print(f"Warning: Could not clear/create {cache_index}: {e}")

    print(f"\nLoading {len(qa_pairs)} Q&A pairs into {cache_index}...")
    print("=" * 70)
    logger.info(f"Processing {len(qa_pairs)} Q&A pairs from responses.json")

    documents = []
    skipped_count = 0

    for qa in tqdm(qa_pairs, desc="Generating embeddings"):
        question = qa.get("question", "")
        answer = qa.get("answer", "")
        sources = qa.get("sources", [])  # Get sources from Q&A pair

        # Only require non-empty question (empty answers are intentional - trigger web search)
        if not question:
            logger.warning("Skipping Q&A pair with no question")
            skipped_count += 1
            continue

        # Generate question embedding
        question_embedding = ollama_client.embed_text(
            question,
            model=settings.ollama_embed_model,
        )

        documents.append(
            {
                "question": question,
                "vector": question_embedding,
                "answer": answer,
                "sources": sources,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    if not documents:
        logger.error("No valid Q&A pairs to insert")
        print("❌ No valid Q&A pairs to insert")
        return

    # Index into the cache index
    print(f"\nIndexing {len(documents)} Q&A pairs into {cache_index}...")
    logger.info(f"Embeddings generated: {len(documents)}")
    logger.info(f"Skipped pairs: {skipped_count}")

    try:
        for doc in documents:
            vector_db.client.index(index=cache_index, body=doc)
        vector_db.client.indices.refresh(index=cache_index)
        inserted_count = len(documents)
        logger.info(f"✓ Successfully inserted {inserted_count} Q&A pairs into {cache_index}")
        logger.info(
            f"  Success rate: {inserted_count}/{len(qa_pairs)} ({(inserted_count / len(qa_pairs) * 100):.1f}%)"
        )
        print(f"✓ Successfully inserted {inserted_count} Q&A pairs")
        print(f"  {cache_index} is now ready for semantic matching")
    except Exception as e:
        logger.error(f"Failed to insert Q&A pairs: {e}")
        print(f"❌ Failed to insert Q&A pairs: {e}")
        return

    print("\n" + "=" * 70)
    print("✓ Responses cache population complete!")
    print(f"  Questions cached: {len(documents)}")
    print(f"  Similarity threshold: {settings.response_cache_threshold:.0%}")

    logger.info("=" * 70)
    logger.info("CACHE SYNC STATISTICS")
    logger.info("=" * 70)
    logger.info(f"Total Q&A pairs loaded: {len(qa_pairs)}")
    logger.info(f"Valid pairs processed: {len(documents)}")
    logger.info(f"Invalid/skipped pairs: {skipped_count}")
    logger.info(f"Successfully inserted: {len(documents)}")
    logger.info(f"Cache index: {cache_index} (semantic similarity)")
    logger.info(f"Similarity threshold: {settings.response_cache_threshold:.2f}")
    logger.info("=" * 70)

    logger.info("✓ Cache sync complete - responses are now available for semantic matching!")


if __name__ == "__main__":
    load_responses_cache()
