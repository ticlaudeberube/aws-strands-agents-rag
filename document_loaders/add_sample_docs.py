#!/usr/bin/env python
"""Simple script to add sample documents to OpenSearch."""

import sys
from pathlib import Path

# Ensure project root is importable when running as a script:
# python document_loaders/add_sample_docs.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from document_loaders.core.tools import OllamaClient, OpenSearchVectorDB
from document_loaders.local_settings import get_loader_settings

# Sample documents about Milvus
SAMPLE_DOCS = [
    """Milvus is a cloud-native vector database designed for storing and querying massive-scale embedding vectors.
    It was developed by Zilliz and is open source. Milvus enables efficient similarity search on high-dimensional
    embeddings and is widely used in AI applications like recommendation systems and semantic search.""",
    """Vector databases like Milvus are optimized for operations on vector data. They support fast approximate
    nearest neighbor (ANN) search algorithms. This makes them ideal for large-scale machine learning applications
    where you need to find similar items quickly.""",
    """Milvus uses distributed architecture and can scale horizontally. It supports multiple indexing algorithms
    including IVF, HNSW, and SCANN for efficient similarity search. The system is designed to handle billions of
    vectors with millisecond-level query latency.""",
    """RAG stands for Retrieval-Augmented Generation. It combines retrieval and generation - first retrieving
    relevant documents from a knowledge base, then using them as context for generating responses. This approach
    allows language models to provide more accurate and contextual answers.""",
    """Ollama is a local LLM runner that allows you to run large language models on your own hardware without
    cloud dependencies. Models like qwen2.5:0.5b and Llama can be run locally with Ollama, making it privacy-friendly
    and cost-effective for local AI applications.""",
    """Embeddings are numerical representations of text. They capture semantic meaning in a high-dimensional space.
    Models like nomic-embed-text convert text into vectors that can be stored in vector databases for similarity search.
    This enables powerful semantic search capabilities.""",
]


def main():
    print("Initializing standalone loader clients...")
    settings = get_loader_settings()
    index_name = settings.opensearch_kb_index
    vector_db = OpenSearchVectorDB(
        host=settings.opensearch_local_host,
        port=settings.opensearch_local_port,
    )
    ollama_client = OllamaClient(
        host=settings.ollama_host,
        timeout=settings.ollama_timeout,
        pool_size=settings.ollama_pool_size,
    )

    # Drop existing index to ensure clean state
    print(f"Checking for existing index '{index_name}'...")
    try:
        if vector_db.delete_index(index_name):
            print("✓ Dropped existing index")
        else:
            print("  (Index didn't exist or already clean)")
    except Exception as e:
        print(f"  (Could not drop index: {type(e).__name__})")

    # Create new index with document embedding dimensions
    print(f"Creating index '{index_name}'...")
    try:
        vector_db.ensure_index(index_name, embedding_dim=settings.embedding_dim)
        print(f"✓ Created index '{index_name}'")
    except Exception as e:
        print(f"✗ Error creating index: {e}")
        raise

    print(f"Adding {len(SAMPLE_DOCS)} sample documents...")
    try:
        embeddings = ollama_client.embed_texts(
            texts=SAMPLE_DOCS,
            model=settings.ollama_embed_model,
            batch_size=settings.embedding_batch_size,
            max_workers=4,
        )

        valid_embeddings = [emb for emb in embeddings if emb is not None]
        if len(valid_embeddings) != len(SAMPLE_DOCS):
            raise RuntimeError("Failed to generate embeddings for all sample documents")

        metadata = [{"source": "sample"} for _ in SAMPLE_DOCS]

        vector_db.index_documents(
            index_name=index_name,
            embeddings=valid_embeddings,
            texts=SAMPLE_DOCS,
            metadata=metadata,
        )

        print("✓ Documents added successfully!")
        print(f"✓ Index '{index_name}' now has {len(SAMPLE_DOCS)} documents")
    except Exception as e:
        print(f"✗ Error adding documents: {e}")
        raise


if __name__ == "__main__":
    main()
