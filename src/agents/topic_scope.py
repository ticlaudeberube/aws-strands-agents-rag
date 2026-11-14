"""Fast keyword-based scope classification for RAG requests."""

import logging
import re

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_ANSWER = (
    "I can help with questions about vector databases, vector search, embeddings, and RAG."
)


def is_question_in_scope(question: str) -> bool:
    """Return whether a question is about databases, search, or information retrieval."""
    question_lower = question.lower()

    # Keep the vocabulary aligned with the knowledge bases this application supports.
    in_scope_keywords = {
        "vector database": 10,
        "vector db": 10,
        "vector search": 9,
        "vector": 6,
        "embedding": 8,
        "embeddings": 8,
        "rag": 8,
        "retrieval augmented": 8,
        "retrieval": 7,
        "semantic search": 7,
        "similarity search": 7,
        "index": 6,
        "indexing": 6,
        "collection": 6,
        "schema": 5,
        "similarity": 6,
        "dense retrieval": 7,
        "sparse retrieval": 7,
        "knn": 7,
        "nearest neighbor": 7,
        "comparison": 4,
        "milvus": 9,
        "pinecone": 9,
        "weaviate": 9,
        "qdrant": 9,
        "voyageai": 9,
        "voyage": 8,
        "elasticsearch": 6,
        "opensearch": 6,
        "redis": 6,
        "faiss": 7,
        "chroma": 8,
        "annoy": 7,
        "postgres": 5,
        "pgvector": 8,
        "mysql": 5,
        "hnsw": 8,
        "ivf": 8,
    }

    matched = [
        keyword
        for keyword in in_scope_keywords
        if re.search(rf"\b{re.escape(keyword)}\b", question_lower)
    ]
    if matched:
        logger.debug("[SCOPE_CHECK] Keyword match (matched=%s): in-scope", matched)
        return True

    logger.debug("[SCOPE_CHECK] No keyword match: out-of-scope (fast reject)")
    return False
