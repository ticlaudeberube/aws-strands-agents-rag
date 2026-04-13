#!/usr/bin/env python3
"""Load pre-generated Q&A pairs into response cache for instant lookup.

This script loads question-answer pairs with their embeddings into Milvus
response_cache collection, enabling instant semantic cache hits for common questions.

Usage: python document_loaders/sync_responses_cache.py
"""

import json
import logging
import sys
from pathlib import Path

# Add parent directory to path BEFORE imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from document_loaders.core.tools import MilvusVectorDB, OllamaClient
from document_loaders.local_settings import get_loader_settings

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

settings = get_loader_settings()
vector_db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=settings.milvus_db_name,
)
ollama_client = OllamaClient(
    host=settings.ollama_host,
    timeout=settings.ollama_timeout,
)


def load_responses_cache():
    """Load pre-generated Q&A pairs into response cache.

    Always runs to sync responses into the cache.
    """
    try:
        with open("./data/responses.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ Error: ./data/responses.json not found")
        print("   Please create with format:")
        print("   {")
        print('     "qa_pairs": [')
        print("       {")
        print('         "question": "What is Milvus?",')
        print('         "answer": "Milvus is a vector database...",')
        print('         "collection": "milvus_rag_collection"')
        print("       }")
        print("     ]")
        print("   }")
        return

    qa_pairs = data.get("qa_pairs", [])
    if not qa_pairs:
        print("❌ No Q&A pairs found in responses.json")
        return

    # Use configured collection name for all Q&A pairs
    collection_name = settings.ollama_collection_name
    print(f"Using collection: {collection_name}")

    # Clear and recreate response_cache collection to prevent duplicates
    cache_collection = settings.response_cache_collection_name
    try:
        collections = vector_db.list_collections()
        if cache_collection in collections:
            print(f"Clearing existing {cache_collection} collection...")
            vector_db.delete_collection(cache_collection)
            print(f"✓ Cleared {cache_collection}")

        print(f"Creating {cache_collection} collection...")
        vector_db.create_collection(
            collection_name=cache_collection,
            embedding_dim=settings.response_cache_embedding_dim,
        )
        print(f"✓ Created {cache_collection}")
    except Exception as e:
        print(f"Warning: Could not clear/create {cache_collection}: {e}")

    print(f"\nLoading {len(qa_pairs)} Q&A pairs into {cache_collection}...")
    print("=" * 70)
    logger.info(f"Processing {len(qa_pairs)} Q&A pairs from responses.json")

    embeddings = []
    texts = []
    metadata_list = []
    skipped_count = 0

    for qa in tqdm(qa_pairs, desc="Generating embeddings"):
        question = qa.get("question", "")
        answer = qa.get("answer", "")
        sources = qa.get("sources", [])  # Get sources from Q&A pair

        # Only require non-empty question (empty answers are intentional - trigger web search)
        if not question:
            logger.warning(f"Skipping Q&A pair with no question")
            skipped_count += 1
            continue

        # Generate question embedding
        question_embedding = ollama_client.embed_text(
            question,
            model=settings.ollama_embed_model,
        )

        embeddings.append(question_embedding)
        texts.append(answer)
        metadata_list.append(
            {
                "question": question,
                "collection": collection_name,
                "source": "pregenerated",
                "sources": sources,  # Store sources in metadata
            }
        )

    if not embeddings:
        logger.error("No valid Q&A pairs to insert")
        print("❌ No valid Q&A pairs to insert")
        return

    # Insert into response_cache
    print(f"\nInserting {len(embeddings)} Q&A pairs into {cache_collection}...")
    logger.info(f"Collection: {collection_name}")
    logger.info(f"Embeddings generated: {len(embeddings)}")
    logger.info(f"Skipped pairs: {skipped_count}")

    try:
        vector_db.insert_embeddings(
            collection_name=cache_collection,
            embeddings=embeddings,
            texts=texts,
            metadata=metadata_list,
        )
        inserted_count = len(embeddings)
        logger.info(f"✓ Successfully inserted {inserted_count} Q&A pairs into {cache_collection}")
        logger.info(
            f"  Success rate: {inserted_count}/{len(qa_pairs)} ({(inserted_count / len(qa_pairs) * 100):.1f}%)"
        )
        print(f"✓ Successfully inserted {inserted_count} Q&A pairs")
        print(f"  {cache_collection} is now ready for semantic matching")
    except Exception as e:
        logger.error(f"Failed to insert Q&A pairs: {e}")
        print(f"❌ Failed to insert Q&A pairs: {e}")
        return

    print("\n" + "=" * 70)
    print("✓ Responses cache population complete!")
    print(f"  Questions cached: {len(embeddings)}")
    print(f"  Similarity threshold: {settings.response_cache_threshold:.0%}")

    logger.info("=" * 70)
    logger.info("CACHE SYNC STATISTICS")
    logger.info("=" * 70)
    logger.info(f"Total Q&A pairs loaded: {len(qa_pairs)}")
    logger.info(f"Valid pairs processed: {len(embeddings)}")
    logger.info(f"Invalid/skipped pairs: {skipped_count}")
    logger.info(f"Successfully inserted: {len(embeddings)}")
    logger.info(f"Collection: {collection_name}")
    logger.info(f"Cache type: {cache_collection} (semantic similarity)")
    logger.info(f"Similarity threshold: {settings.response_cache_threshold:.2f}")
    logger.info("=" * 70)

    logger.info("✓ Cache sync complete - responses are now available for semantic matching!")


if __name__ == "__main__":
    load_responses_cache()
