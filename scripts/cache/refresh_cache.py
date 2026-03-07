#!/usr/bin/env python3
"""Clear response cache and reload from data/responses.json"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import get_settings
from src.tools import MilvusVectorDB, OllamaClient
import json
from tqdm import tqdm
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize
vector_db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=settings.milvus_db_name,
    user=settings.milvus_user,
    password=settings.milvus_password,
)
ollama = OllamaClient(host=settings.ollama_host, timeout=settings.ollama_timeout)

cache_col = settings.response_cache_collection_name

print("=" * 80)
print("CACHE REFRESH: Clear and Reload from data/responses.json")
print("=" * 80)

# Step 1: Clear old cache
print(f"\n1️⃣  Clearing old cache collection: {cache_col}...")
try:
    vector_db.delete_collection(cache_col)
    print("   ✓ Cleared")
except Exception as e:
    logger.debug(f"Could not delete (might not exist): {e}")
    print("   ℹ️  Collection may not exist yet")

# Step 2: Load Q&A pairs
print("\n2️⃣  Loading Q&A pairs from data/responses.json...")
try:
    with open("data/responses.json") as f:
        data = json.load(f)
        qa_pairs = data.get("qa_pairs", [])
    print(f"   ✓ Loaded {len(qa_pairs)} Q&A pairs")
except Exception as e:
    print(f"   ❌ Error loading: {e}")
    sys.exit(1)

# Step 3: Create collection and insert
print("\n3️⃣  Generating embeddings and loading cache...")
embeddings = []
texts = []
metadata_list = []

for qa in tqdm(qa_pairs, desc="Processing"):
    question = qa.get("question", "").strip()
    answer = qa.get("answer", "").strip()

    if not question or not answer:
        continue

    # Generate embedding
    emb = ollama.embed_text(question, model=settings.ollama_embed_model)
    embeddings.append(emb)
    texts.append(answer)
    metadata_list.append({"question": question, "source": "data/responses.json"})

print(f"\n4️⃣  Creating collection and inserting {len(embeddings)} entries...")
try:
    # Create collection first
    vector_db.create_collection(
        collection_name=cache_col,
        embedding_dim=settings.response_cache_embedding_dim,
    )
    print("   ✓ Created collection")

    # Then insert
    vector_db.insert_embeddings(
        collection_name=cache_col,
        embeddings=embeddings,
        texts=texts,
        metadata=metadata_list,
    )
    print(f"   ✓ Inserted {len(embeddings)} entries")
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ CACHE REFRESH COMPLETE")
print("=" * 80)
print(f"\nCache collection: {cache_col}")
print(f"Entries loaded: {len(embeddings)} Q&A pairs from data/responses.json")
print("All cached responses will use the current Q&A pair answers.")
print("\nNote: Restart your chatbot/API process to use the updated cache.\n")
