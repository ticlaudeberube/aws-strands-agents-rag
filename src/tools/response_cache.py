"""Milvus-based persistent response cache for RAG agent.

This module implements a semantic response cache that:
- Stores question embeddings + LLM responses in Milvus
- Searches for semantically similar cached questions
- Returns cached answers for high-similarity matches
- Reduces LLM generation time for repeated/similar questions
"""

import json
import logging
import time
from typing import Optional, Dict, Tuple, List
from datetime import datetime

logger = logging.getLogger(__name__)


class MilvusResponseCache:
    """Persistent response cache using Milvus vector database."""
    
    CACHE_COLLECTION = "response_cache"
    # COSINE distance in Milvus: higher values indicate better matches
    # Empirically observed:
    # - Exact match (identical text): ~1.0
    # - Similar rephrasing: ~0.91-0.92
    # - Unrelated question using same terms: ~0.90
    # Use threshold of 0.90 to accept semantically similar questions
    DISTANCE_THRESHOLD = 0.90  # Accept similar questions (distance >= 0.90)
    SIMILARITY_THRESHOLD = 0.90  # Kept for backward compatibility but not used
    
    def __init__(self, vector_db, embedding_dim: int = 768):
        """Initialize response cache.
        
        Args:
            vector_db: MilvusVectorDB instance
            embedding_dim: Dimension of embeddings (must match other collections)
        """
        self.vector_db = vector_db
        self.embedding_dim = embedding_dim
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Create response cache collection if it doesn't exist."""
        try:
            collections = self.vector_db.client.list_collections(
                db_name=self.vector_db.db_name
            )
            
            if self.CACHE_COLLECTION in collections:
                logger.info(f"✓ Response cache collection exists: {self.CACHE_COLLECTION}")
                return
            
            # Create cache collection
            self.vector_db.create_collection(
                collection_name=self.CACHE_COLLECTION,
                embedding_dim=self.embedding_dim,
                index_type="HNSW",
                metric_type="COSINE",
            )
            logger.info(f"✓ Created response cache collection: {self.CACHE_COLLECTION}")
            
        except Exception as e:
            logger.error(f"Failed to create/verify response cache: {e}")
            raise
    
    def search_cache(
        self,
        question_embedding: List[float],
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        limit: int = 1,
    ) -> Optional[Dict]:
        """Search for cached responses similar to the question.
        
        Args:
            question_embedding: Query embedding vector
            similarity_threshold: Minimum similarity score (0-1) - deprecated, use distance_threshold
            limit: Number of results to return
        
        Returns:
            Dict with cached response or None if no match found
        """
        try:
            results = self.vector_db.search(
                collection_name=self.CACHE_COLLECTION,
                query_embedding=question_embedding,
                limit=limit,
            )
            
            if not results:
                return None
            
            # Extract best match
            best_match = results[0]
            distance = best_match.get("distance", 2)  # COSINE distance between 0 and 2
            # Convert distance to similarity for logging: similarity = 1 - (distance / 2)
            # This ranges from 1.0 (identical) to -1.0 (opposite)
            similarity = 1 - (distance / 2) if distance >= 0 else -1
            
            logger.info(f"Cache search: distance={distance:.4f}, similarity={similarity:.1%}")
            
            # Use distance threshold for matching - HIGHER distances are better matches
            # In Milvus COSINE metric: 1.0 = identical, lower values = less similar
            if distance >= self.DISTANCE_THRESHOLD:
                # Parse cached data
                metadata = best_match.get("metadata", {})
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                cache_entry = {
                    "question": metadata.get("question", ""),
                    "response": best_match.get("text", ""),
                    "similarity": similarity,
                    "distance": distance,
                    "created_at": metadata.get("created_at", ""),
                    "hit_count": metadata.get("hit_count", 0),
                    "sources": metadata.get("sources", []),  # Retrieve sources from metadata
                }
                
                logger.info(f"✓ Cache HIT ({similarity:.1%} similar, distance={distance:.4f})")
                logger.info(f"  Cached question: {cache_entry['question'][:60]}")
                
                return cache_entry
            else:
                logger.debug(f"Cache miss (distance {distance:.4f} < {self.DISTANCE_THRESHOLD}, too different)")
                return None
                
        except Exception as e:
            logger.warning(f"Cache search failed: {e}")
            return None
    
    def store_response(
        self,
        question: str,
        question_embedding: List[float],
        response: str,
        metadata: Dict = None,
    ) -> bool:
        """Store question + response in cache.
        
        Args:
            question: Original question text
            question_embedding: Question embedding vector
            response: LLM response
            metadata: Additional metadata
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare metadata
            if metadata is None:
                metadata = {}
            
            metadata_dict = {
                "question": question,
                "created_at": datetime.now().isoformat(),
                "hit_count": 0,
                **metadata,
            }
            
            # Store in Milvus
            self.vector_db.insert_embeddings(
                collection_name=self.CACHE_COLLECTION,
                embeddings=[question_embedding],
                texts=[response],
                metadata=[metadata_dict],
            )
            
            logger.info(f"✓ Cached response for: {question[:60]}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to store response in cache: {e}")
            return False
    
    def increment_hit_count(self, cached_entry: Dict):
        """Track cache hit statistics (optional enhancement)."""
        # This is a placeholder for future analytics
        # In production, you might track hit counts in a separate metrics collection
        pass
    
    def clear_cache(self) -> bool:
        """Clear all cached responses.
        
        Returns:
            True if successful
        """
        try:
            self.vector_db.delete_collection(self.CACHE_COLLECTION)
            logger.info(f"✓ Cleared response cache")
            self._ensure_collection()
            return True
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics.
        
        Returns:
            Dict with cache statistics
        """
        try:
            results = self.vector_db.client.query(
                collection_name=self.CACHE_COLLECTION,
                db_name=self.vector_db.db_name,
            )
            
            return {
                "collection": self.CACHE_COLLECTION,
                "cached_responses": len(results) if results else 0,
                "similarity_threshold": self.SIMILARITY_THRESHOLD,
            }
        except Exception as e:
            return {
                "error": str(e),
                "collection": self.CACHE_COLLECTION,
            }
