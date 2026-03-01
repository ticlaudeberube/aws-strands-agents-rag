#!/usr/bin/env python
"""Simple script to add sample documents to Milvus."""

from src.config.settings import Settings
from src.agents.strands_rag_agent import StrandsRAGAgent

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
    cloud dependencies. Models like Qwen2.5:0.5b and Llama can be run locally with Ollama, making it privacy-friendly 
    and cost-effective for local AI applications.""",
    
    """Embeddings are numerical representations of text. They capture semantic meaning in a high-dimensional space. 
    Models like nomic-embed-text convert text into vectors that can be stored in vector databases for similarity search. 
    This enables powerful semantic search capabilities.""",
]

def main():
    print("Initializing RAG Agent...")
    settings = Settings()
    agent = StrandsRAGAgent(settings=settings)
    
    # Drop existing collection to ensure clean state
    print(f"Checking for existing collection '{settings.ollama_collection_name}'...")
    try:
        agent.vector_db.delete_collection(settings.ollama_collection_name)
        print(f"✓ Dropped existing collection")
    except Exception as e:
        print(f"  (Collection didn't exist or already clean: {type(e).__name__})")
    
    # Create new collection with document embedding dimensions
    print(f"Creating collection '{settings.ollama_collection_name}'...")
    try:
        agent.vector_db.create_collection(
            collection_name=settings.ollama_collection_name,
            embedding_dim=settings.embedding_dim,
            index_type="HNSW",
            metric_type="COSINE"
        )
        print(f"✓ Created collection '{settings.ollama_collection_name}'")
    except Exception as e:
        print(f"✗ Error creating collection: {e}")
        raise
    
    print(f"Adding {len(SAMPLE_DOCS)} sample documents...")
    try:
        agent.add_documents(
            collection_name=settings.ollama_collection_name,
            documents=SAMPLE_DOCS
        )
        print("✓ Documents added successfully!")
        print(f"✓ Collection '{settings.ollama_collection_name}' now has {len(SAMPLE_DOCS)} documents")
    except Exception as e:
        print(f"✗ Error adding documents: {e}")
        raise

if __name__ == "__main__":
    main()
