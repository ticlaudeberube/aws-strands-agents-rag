#!/usr/bin/env python3
"""Debug cache functionality to diagnose why cache hits aren't working."""

import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Load env first
load_dotenv()

from src.config.settings import get_settings
from src.tools import MilvusVectorDB, OllamaClient, MilvusResponseCache

def main():
    settings = get_settings()
    
    print("\n" + "="*70)
    print("CACHE DEBUG SCRIPT")
    print("="*70)
    
    # Initialize components
    print("\n1. Initializing components...")
    vector_db = MilvusVectorDB(
        host=settings.milvus_host,
        port=settings.milvus_port,
        db_name=settings.milvus_db_name,
    )
    print(f"   ✓ MilvusVectorDB connected to {settings.milvus_host}:{settings.milvus_port}")
    
    ollama_client = OllamaClient(host=settings.ollama_host)
    print(f"   ✓ OllamaClient connected to {settings.ollama_host}")
    
    response_cache = MilvusResponseCache(vector_db)
    print(f"   ✓ MilvusResponseCache initialized")
    
    # Check if cache collection exists
    print("\n2. Checking cache collection...")
    try:
        collections = vector_db.client.list_collections(db_name=settings.milvus_db_name)
        if "response_cache" in collections:
            print(f"   ✓ response_cache collection exists")
        else:
            print(f"   ✗ response_cache collection NOT found")
            print(f"     Available collections: {collections}")
    except Exception as e:
        print(f"   ✗ Error listing collections: {e}")
        return
    
    # Try to load cache with pre-generated responses
    print("\n3. Loading pre-generated responses...")
    responses_path = Path(__file__).parent / "data" / "responses.json"
    if not responses_path.exists():
        print(f"   ✗ responses.json not found at {responses_path}")
        return
    
    with open(responses_path) as f:
        data = json.load(f)
    
    qa_pairs = data.get("qa_pairs", [])
    print(f"   ✓ Loaded {len(qa_pairs)} Q&A pairs from responses.json")
    
    if not qa_pairs:
        print("   ✗ No Q&A pairs found!")
        return
    
    # Test with first Q&A pair
    first_qa = qa_pairs[0]
    test_question = first_qa["question"]
    test_answer = first_qa["answer"]
    
    print(f"\n4. Test Q&A:")
    print(f"   Q: {test_question[:60]}...")
    print(f"   A: {test_answer[:80]}...")
    
    # Generate embedding
    print("\n5. Generating embedding for test question...")
    try:
        embedding = ollama_client.embed_text(test_question, model=settings.ollama_embed_model)
        print(f"   ✓ Embedding generated ({len(embedding)} dimensions)")
    except Exception as e:
        print(f"   ✗ Error generating embedding: {e}")
        return
    
    # Store in cache
    print("\n6. Storing answer in cache...")
    try:
        success = response_cache.store_response(
            question=test_question,
            question_embedding=embedding,
            response=test_answer,
            metadata={"source": "test", "collection": settings.ollama_collection_name}
        )
        print(f"   {'✓' if success else '✗'} store_response returned: {success}")
        time.sleep(1)  # Give Milvus time to store
    except Exception as e:
        print(f"   ✗ Error storing response: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Search cache immediately
    print("\n7. Searching cache immediately after storing...")
    try:
        result = response_cache.search_cache(test_question, embedding)
        if result:
            print(f"   ✓ Cache HIT!")
            print(f"     Question: {result['question'][:60]}...")
            print(f"     Similarity: {result.get('similarity', 'N/A'):.1%}")
            print(f"     Distance: {result.get('distance', 'N/A'):.4f}")
        else:
            print(f"   ✗ Cache MISS - search_cache returned None")
    except Exception as e:
        print(f"   ✗ Error searching cache: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Try searching with slightly different question
    print("\n8. Testing with rephrase of same question...")
    similar_question = "What exactly is Milvus?"
    try:
        embedding2 = ollama_client.embed_text(similar_question, model=settings.ollama_embed_model)
        result2 = response_cache.search_cache(similar_question, embedding2)
        if result2:
            print(f"   ✓ Cache HIT for similar question!")
            print(f"     Similarity: {result2.get('similarity', 'N/A'):.1%}")
        else:
            print(f"   ✗ Cache MISS for similar question")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Check what's actually in the cache
    print("\n9. Checking cache contents...")
    try:
        # Try to query all documents in response_cache collection
        vector_db.client.load_collection(
            collection_name="response_cache",
            db_name=settings.milvus_db_name
        )
        
        # Query without filter to see how many entities exist
        results = vector_db.client.query(
            collection_name="response_cache",
            db_name=settings.milvus_db_name,
        )
        
        print(f"   ✓ Cache has {len(results)} entries")
        
        if results and len(results) > 0:
            first = results[0]
            print(f"     First entry ID: {first.get('id', 'N/A')}")
            if 'metadata' in first:
                meta = first['metadata']
                if isinstance(meta, str):
                    meta = json.loads(meta)
                print(f"     First entry question: {meta.get('question', 'N/A')[:60]}...")
    except Exception as e:
        print(f"   ✗ Error querying cache: {e}")
    
    print("\n" + "="*70)
    print("DEBUG COMPLETE")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
