"""Milvus-based persistent response cache for RAG agent.

This module implements a semantic response cache that:
- Stores question embeddings + LLM responses in Milvus
- Searches for semantically similar cached questions
- Returns cached answers for high-similarity matches
- Validates that cached answers match the entity in the current question
- Reduces LLM generation time for repeated/similar questions
"""

import json
import logging
import time
import re
from typing import Optional, Dict, Tuple, List
from datetime import datetime

logger = logging.getLogger(__name__)


class MilvusResponseCache:
    """Persistent response cache using Milvus vector database."""
    
    CACHE_COLLECTION = "response_cache"
    # COSINE distance in Milvus: ranges from -1.0 to 1.0 (not 0 to 2)
    # - Distance = 1.0: identical vectors (100% similar)
    # - Distance = 0.0: orthogonal vectors (0% similar) 
    # - Distance = -1.0: opposite vectors (-100% similar)
    # Empirically observed for same question, different embedding calls: ~0.99-1.0 (near-perfect match)
    # Use threshold of 0.92 to match same/very similar questions (accounts for embedding variance)
    # This ensures "What is Milvus?" and "What is Milvus?" match (distance 0.99+)
    # While still preventing "What is Pinecone?" from matching Milvus answers
    DISTANCE_THRESHOLD = 0.92  # Match same question (distance >= 0.92 = 92% similar)
    SIMILARITY_THRESHOLD = 0.92  # Kept for backward compatibility but not used
    
    # Common vector database products for entity validation
    VECTOR_DB_PRODUCTS = {
        'milvus', 'pinecone', 'weaviate', 'qdrant', 'elasticsearch',
        'opensearch', 'postgres', 'pgvector', 'chroma', 'faiss',
        'lancedb', 'vald', 'vespa', 'typesense', 'myscale'
    }
    
    def __init__(self, vector_db, embedding_dim: int = 768):
        """Initialize response cache.
        
        Args:
            vector_db: MilvusVectorDB instance
            embedding_dim: Dimension of embeddings (must match other collections)
        """
        self.vector_db = vector_db
        self.embedding_dim = embedding_dim
        self._ensure_collection()
    
    def _extract_main_entity(self, text: str) -> Optional[str]:
        """Extract the main product/entity being asked about.
        
        For questions like "What is Milvus?", extracts "Milvus".
        For questions like "Compare Milvus and Pinecone", extracts "Milvus".
        
        Args:
            text: Question or statement text
        
        Returns:
            The main entity name or None if not found
        """
        text_lower = text.lower()
        
        # Check for vector database product names first (most specific)
        for product in self.VECTOR_DB_PRODUCTS:
            if product in text_lower:
                # Find the original casing from the text
                pattern = re.compile(re.escape(product), re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    return match.group(0)
        
        return None
    
    def _validate_cached_answer_relevance(self, question: str, cached_answer: str, cached_question: str) -> bool:
        """Validate that a cached answer is relevant to the current question.
        
        Checks if the main entity in the current question appears in the cached answer.
        This prevents returning "What is Milvus?" answer when asked "What is Pinecone?"
        
        Args:
            question: Current question
            cached_answer: The cached response text
            cached_question: The original question that was cached
        
        Returns:
            True if answer is likely relevant, False otherwise
        """
        # Extract main entities
        current_entity = self._extract_main_entity(question)
        cached_entity = self._extract_main_entity(cached_question)
        
        logger.debug(f"[CACHE_VALIDATE] Validating - current entity: {current_entity}, cached entity: {cached_entity}")
        
        # If we can't identify entities, assume it's OK (conservative approach)
        # This prevents rejecting valid cached answers just because no entity was extracted
        if not current_entity or not cached_entity:
            logger.debug(f"[CACHE_VALIDATE] Could not extract entities - allowing cache hit (conservative)")
            return True
        
        # If asking about the same entity, ALWAYS accept - no further validation needed
        # e.g., "What is Milvus?" matches "What is Milvus?" answer
        if current_entity.lower() == cached_entity.lower():
            logger.debug(f"[CACHE_VALIDATE] SAME entity ('{current_entity}') - ACCEPTING cache hit")
            return True
        
        # DIFFERENT ENTITIES - need stricter validation
        # e.g., "What is Pinecone?" should not match "What is Milvus?" answer
        answer_lower = cached_answer.lower()
        current_entity_lower = current_entity.lower()
        cached_entity_lower = cached_entity.lower()
        
        # Check if answer mentions the cached entity (good sign - it's the right answer)
        if cached_entity_lower not in answer_lower:
            logger.debug(f"[CACHE_VALIDATE] Different entity: cached answer for '{cached_entity}' doesn't mention it - rejecting")
            return False
        
        # If the CURRENT question's entity appears in the CACHED answer, it's wrong
        # e.g., "What is Pinecone?" shouldn't match Milvus answer that mentions Pinecone
        if current_entity_lower in answer_lower:
            logger.debug(f"[CACHE_VALIDATE] Different entity: Answer mentions '{current_entity}' but is cached for '{cached_entity}' - rejecting")
            return False
        
        logger.debug(f"[CACHE_VALIDATE] Different entity but answer doesn't mention current entity - allowing cache")
        return True
    
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
        question: str,
        question_embedding: List[float],
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        limit: int = 1,
    ) -> Optional[Dict]:
        """Search for cached responses similar to the question.
        
        Args:
            question: The current question text (for entity validation)
            question_embedding: Query embedding vector
            similarity_threshold: Minimum similarity score (0-1) - deprecated, use distance_threshold
            limit: Number of results to return
        
        Returns:
            Dict with cached response or None if no match found
        """
        try:
            # Ensure collection is loaded before searching
            try:
                self.vector_db.client.load_collection(
                    collection_name=self.CACHE_COLLECTION,
                    db_name=self.vector_db.db_name
                )
            except Exception as load_error:
                # Collection might already be loaded, that's OK
                logger.debug(f"Note during load: {load_error}")
            
            results = self.vector_db.search(
                collection_name=self.CACHE_COLLECTION,
                query_embedding=question_embedding,
                limit=limit,
            )
            
            logger.debug(f"[CACHE_DEBUG] Search returned {len(results) if results else 0} results")
            
            if not results:
                logger.debug(f"[CACHE_DEBUG] No results returned from Milvus search")
                logger.info(f"Cache search: No cached responses found for query (empty results)")
                return None
            
            # Extract best match
            best_match = results[0]
            distance = best_match.get("distance", -2)  # COSINE distance between -1 and 1
            metadata = best_match.get("metadata", {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            
            cached_question = metadata.get("question", "")
            logger.debug(f"[CACHE_DEBUG] Best match distance: {distance:.4f}, type: {type(distance)}")
            logger.debug(f"[CACHE_DEBUG] Best match cached question: {cached_question[:60]}")
            logger.debug(f"[CACHE_DEBUG] Threshold: {self.DISTANCE_THRESHOLD:.4f}, Match: {distance >= self.DISTANCE_THRESHOLD}")
            # For Milvus COSINE metric, distance IS the similarity (-1 to 1)
            # No conversion needed: distance = 1.0 means identical, distance = 0.0 means orthogonal
            similarity = distance
            
            logger.info(f"Cache search: distance={distance:.4f}, similarity={similarity:.1%}, threshold={self.DISTANCE_THRESHOLD:.4f}")
            
            # Use distance threshold for matching - HIGHER distances are better matches
            # In Milvus COSINE metric: distance ranges from -1 to 1, where 1.0 = identical
            if distance >= self.DISTANCE_THRESHOLD:
                # Parse cached data
                metadata = best_match.get("metadata", {})
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                cached_question = metadata.get("question", "")
                cached_answer = best_match.get("text", "")
                
                # VALIDATE: Check if cached answer is relevant to current question
                is_relevant = self._validate_cached_answer_relevance(question, cached_answer, cached_question)
                if not is_relevant:
                    logger.info(f"Cache semantically similar but entity mismatch - rejecting cache")
                    return None
                
                cache_entry = {
                    "question": cached_question,
                    "response": cached_answer,
                    "similarity": similarity,
                    "distance": distance,
                    "created_at": metadata.get("created_at", ""),
                    "hit_count": metadata.get("hit_count", 0),
                }
                
                # Parse sources from JSON if stored as string
                sources = metadata.get("sources", [])
                if isinstance(sources, str):
                    try:
                        sources = json.loads(sources)
                    except (json.JSONDecodeError, TypeError):
                        sources = []
                cache_entry["sources"] = sources
                
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
            metadata: Additional metadata (sources list will be JSON-serialized)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare metadata
            if metadata is None:
                metadata = {}
            
            # Convert sources list to JSON string for proper storage/retrieval
            if "sources" in metadata and isinstance(metadata["sources"], list):
                metadata["sources"] = json.dumps(metadata["sources"])
            
            metadata_dict = {
                "question": question,
                "created_at": datetime.now().isoformat(),
                "hit_count": 0,
                **metadata,
            }
            
            # Store in Milvus
            logger.debug(f"[STORE_DEBUG] Attempting to insert into {self.CACHE_COLLECTION}")
            logger.debug(f"[STORE_DEBUG] Question: {question}, Response length: {len(response)}, Embedding length: {len(question_embedding)}")
            
            result = self.vector_db.insert_embeddings(
                collection_name=self.CACHE_COLLECTION,
                embeddings=[question_embedding],
                texts=[response],
                metadata=[metadata_dict],
            )
            
            logger.debug(f"[STORE_DEBUG] Insert result: {result}")
            logger.info(f"✓ Cached response for: {question[:60]}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to store response in cache: {e}", exc_info=True)
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
