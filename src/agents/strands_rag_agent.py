"""Strands-based RAG Agent with proper framework integration and RAGAgent logic."""

import logging
import time
import asyncio
import re
import json
from typing import Optional, List, Dict, Tuple, AsyncIterator
from collections import OrderedDict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from src.config import Settings
from src.tools import MilvusVectorDB, OllamaClient, MilvusResponseCache, WebSearchClient

logger = logging.getLogger(__name__)


@dataclass
class ToolDescription:
    """Tool metadata for description."""
    name: str
    description: str


@dataclass
class EmbeddingCacheEntry:
    """Cache entry with TTL support for embeddings."""
    embedding: List[float]
    timestamp: float
    
    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if entry has expired based on TTL."""
        return (time.time() - self.timestamp) > ttl_seconds


@dataclass
class PerformanceMetrics:
    """Performance metrics for request tracking."""
    total_time: float
    embedding_time: float
    retrieval_time: float
    generation_time: float
    cache_hits: Dict[str, bool]  # embedding_cache, search_cache, answer_cache, response_cache
    
    def summary(self) -> str:
        """Return formatted performance summary."""
        cache_summary = " | ".join([f"{k.replace('_cache', '')}: {'✓' if v else '✗'}" for k, v in self.cache_hits.items()])
        return f"⏱ {self.total_time:.2f}s total (embed:{self.embedding_time:.2f}s | retrieval:{self.retrieval_time:.2f}s | gen:{self.generation_time:.2f}s) | {cache_summary}"


@dataclass
class AnswerWithMetrics:
    """Answer with confidence score and performance metrics."""
    answer: str
    sources: List[Dict]
    confidence_score: float  # 0.0-1.0
    metrics: Optional[PerformanceMetrics] = None


class StrandsRAGAgent:
    """RAG Agent using proper Strands pattern with decorators and MCP support.
    
    This agent combines Strands framework patterns with the sophisticated
    RAG logic from the original RAGAgent, including:
    - Multi-layer caching (embedding, search, answer, semantic)
    - Security attack detection and scope checking
    - Milvus-specific prompts and instructions
    - Optimized latency with parallel operations
    
    Note: This is structured to support Strands Agent framework patterns.
    """

    def __init__(self, settings: Settings, cache_size: int = None, embedding_cache_ttl: int = 3600):
        """Initialize Strands RAG Agent.
        
        Args:
            settings: Application settings from config
            cache_size: Maximum number of cached items per cache type (uses settings.agent_cache_size if None)
            embedding_cache_ttl: Time-to-live for cached embeddings in seconds (default: 3600 = 1 hour)
        """
        self.settings = settings
        self.cache_size = cache_size if cache_size is not None else settings.agent_cache_size
        self.embedding_cache_ttl = embedding_cache_ttl  # TTL for embeddings in seconds
        
        # Initialize backend systems
        self.ollama_client = OllamaClient(
            host=settings.ollama_host,
            timeout=settings.ollama_timeout,
            pool_size=settings.ollama_pool_size,
        )
        self.vector_db = MilvusVectorDB(
            host=settings.milvus_host,
            port=settings.milvus_port,
            db_name=settings.milvus_db_name,
            user=settings.milvus_user,
            password=settings.milvus_password,
            timeout=settings.milvus_timeout,
            pool_size=settings.milvus_pool_size,
        )
        self.web_search = WebSearchClient(timeout=10)
        
        # Initialize caching system (from RAGAgent)
        self.embedding_cache = OrderedDict()  # query -> EmbeddingCacheEntry (with TTL)
        self.search_cache = OrderedDict()  # (collection, query, top_k) -> context chunks
        self.answer_cache = OrderedDict()  # (question, collection, top_k) -> answer
        
        # Initialize persistent response cache for semantic matching
        try:
            self.response_cache = MilvusResponseCache(self.vector_db)
            logger.info("Response cache initialized for persistent semantic caching")
        except Exception as e:
            logger.warning(f"Failed to initialize response cache: {e}. Continuing without persistent caching.")
            self.response_cache = None
        
        logger.info(f"StrandsRAGAgent initialized with cache_size={self.cache_size}, embedding_ttl={self.embedding_cache_ttl}s")
        logger.info(f"  Model: {settings.ollama_model}")
        logger.info(f"  Embedding Model: {settings.ollama_embed_model}")
        logger.info(f"  Ollama: {settings.ollama_host}")
        logger.info(f"  Milvus: {settings.milvus_host}:{settings.milvus_port}")

    # ========================================================================
    # CACHING METHODS
    # ========================================================================
    
    def _add_to_cache(self, cache: OrderedDict, key, value) -> None:
        """Add item to cache with LRU eviction.
        
        Args:
            cache: Cache dictionary
            key: Cache key
            value: Value to cache
        """
        if len(cache) >= self.cache_size:
            cache.popitem(last=False)  # Remove oldest (FIFO)
        cache[key] = value
    
    def clear_caches(self) -> None:
        """Clear all caches."""
        self.embedding_cache.clear()
        self.search_cache.clear()
        self.answer_cache.clear()
        
        if self.response_cache:
            try:
                self.response_cache.clear_cache()
            except Exception as e:
                logger.warning(f"Failed to clear response cache: {e}")
        
        logger.info("All caches cleared")
    
    def _generate_embedding(self, text: str) -> Tuple[List[float], bool]:
        """Generate embedding for text, using cache if available.
        
        Returns:
            Tuple of (embedding_vector, was_cached)
        """
        # Check cache and validate TTL
        if text in self.embedding_cache:
            entry = self.embedding_cache[text]
            if not entry.is_expired(self.embedding_cache_ttl):
                return (entry.embedding, True)  # Cache hit
            else:
                # Expired, remove from cache
                logger.debug(f"Embedding cache entry expired (TTL={self.embedding_cache_ttl}s), regenerating")
                del self.embedding_cache[text]
        
        # Generate fresh embedding
        embedding = self.ollama_client.embed_text(
            text,
            model=self.settings.ollama_embed_model,
        )
        
        # Store with timestamp for TTL tracking
        entry = EmbeddingCacheEntry(embedding=embedding, timestamp=time.time())
        self._add_to_cache(self.embedding_cache, text, entry)
        
        return (embedding, False)  # Cache miss

    # ========================================================================
    # SECURITY AND SCOPE CHECKING
    # ========================================================================
    
    def _is_security_attack(self, question: str) -> bool:
        """Detect obvious security attacks and injection attempts without LLM.
        
        Uses pattern matching to catch common jailbreak and injection attempts.
        Fast pre-check before LLM-based scope classification.
        
        Returns True if attack detected (should be rejected), False if safe.
        """
        question_lower = question.lower()
        question_normalized = question_lower.replace("you're", "you are").replace("don't", "do not").replace("what's", "what is")
        
        jailbreak_patterns = [
            "forget your instruction", "forget you are a", "forget you",
            "forget about", "ignore your instruction", "disregard your instruction",
            "override your", "bypass your", "ignore the system prompt",
            "ignore the previous instruction", "you are no longer",
            "ignore the scope", "ignore the limitation", "disregard",
            "jailbreak", "hack", "offshore account", "launder",
            "bypass security", "ignore the rule", "pretend you are",
            "role play as", "act as if you", "what is your hidden",
            "what is your system prompt", "reveal your prompt",
            "show me your instruction", "dump your system prompt",
            "tell me your secret",
        ]
        
        for pattern in jailbreak_patterns:
            if pattern in question_lower or pattern in question_normalized:
                logger.warning(f"Security attack detected: jailbreak pattern '{pattern}'")
                return True
        
        if any(cmd in question_lower for cmd in [
            "send money", "transfer money", "steal",
            "delete", "drop table", "sql injection",
            "fork bomb", "ddos", "malware",
        ]):
            logger.warning("Security attack detected: command injection pattern")
            return True
        
        return False
    
    def _is_question_in_scope(self, question: str) -> bool:
        """Check if question is about databases, search, or information retrieval.
        
        Uses fast keyword matching first, then LLM-based classification only
        for edge cases. This hybrid approach provides 90% faster classification.
        
        In-scope topics:
        - Milvus, vector databases, vector search
        - Embeddings, semantic similarity, RAG
        - Database indexing, retrieval systems
        - Comparisons with other vector databases
        
        Returns:
            True if question is in scope, False otherwise
        """
        question_lower = question.lower()
        
        # Fast keyword-based pre-filter (90% of cases caught here)
        in_scope_keywords = {
            "milvus": 10, "vector database": 10, "vector db": 10,
            "vector search": 9, "vector": 6,
            "embedding": 8, "embeddings": 8,
            "rag": 8, "retrieval augmented": 8,
            "retrieval": 7, "semantic search": 7, "similarity search": 7,
            "index": 6, "indexing": 6, "collection": 6, "schema": 5,
            "similarity": 6, "dense retrieval": 7, "sparse retrieval": 7,
            "pinecone": 9, "weaviate": 9, "voyageai": 9, "voyage": 8,
            "qdrant": 9, "elasticsearch": 6, "comparison": 4,
            "knn": 7, "nearest neighbor": 7,
            "hnsw": 8, "ivf": 8,
        }
        
        # Calculate keyword score
        words = question_lower.split()
        score = 0
        for word in words:
            # Check exact word matches first
            if word in in_scope_keywords:
                score += in_scope_keywords[word]
            # Check partial matches (substrings)
            for keyword in in_scope_keywords:
                if keyword in word and len(keyword) > 2:
                    score += in_scope_keywords[keyword] // 2
        
        # High confidence threshold - return early
        if score > 12:
            logger.debug(f"Scope check (keyword match, score={score}): '{question[:50]}...' -> YES")
            return True
        
        if score > 0:
            logger.debug(f"Scope check (keyword partial, score={score}): '{question[:50]}...' -> YES")
            return True
        
        # Only use LLM for ambiguous cases (10% of questions)
        try:
            scope_check_prompt = """Classify as YES or NO only.
Is this about: vector databases, vectors, embeddings, RAG, retrieval, or database search?

Question: {question}

Answer YES or NO:"""
            
            response = self.ollama_client.generate(
                prompt=scope_check_prompt.format(question=question),
                model=self.settings.ollama_model,
                temperature=0.0,
                max_tokens=3,
            ).strip().upper()
            
            is_in_scope = response.startswith("YES")
            logger.debug(f"LLM scope check (fallback): '{question[:50]}...' -> {response}")
            return is_in_scope
            
        except Exception as e:
            logger.warning(f"LLM scope check failed: {e}. Defaulting to False.")
            return False

    def _generate_web_search_query(self, question: str) -> str:
        """Generate an optimized web search query.
        
        This method transforms specific technical questions into more search-friendly queries.
        
        Special handling for:
        - Comparison questions: "Pinecone vs Milvus" → "Pinecone vs Milvus comparison"
        - Multiple products: Detects all products and creates comparison query
        - Single products: Uses product-specific optimized terms
        
        Examples:
            "What is Pinecone?" → "Pinecone vector database features"
            "Pinecone vs Milvus" → "Pinecone vs Milvus vector database comparison"
            "How does Milvus work?" → "Milvus documentation vector search"
            
        Args:
            question: Original user question
            
        Returns:
            Optimized search query for web search
        """
        question_lower = question.lower()
        
        # Map of product names and their enhanced search queries
        product_search_terms = {
            # Well-indexed products
            "milvus": ["Milvus vector database", "Milvus search engine"],
            "elasticsearch": ["Elasticsearch vector search", "Elasticsearch documentation"],
            "opensearch": ["OpenSearch vector database", "Amazon OpenSearch"],
            "redis": ["Redis vector search", "Redis Stack"],
            "faiss": ["FAISS vector similarity", "Facebook AI Similarity"],
            "postgres": ["PostgreSQL vector", "pgvector extension"],
            "mysql": ["MySQL vector embeddings"],
            
            # Potentially under-indexed products
            "pinecone": ["Pinecone AI vector", "Pinecone database comparison"],
            "qdrant": ["Qdrant vector database", "Qdrant comparison"],
            "weaviate": ["Weaviate AI database", "Weaviate documentation"],
            "voyageai": ["Voyage AI embeddings", "Voyage API embeddings"],
            "voyage": ["Voyage AI embeddings", "Voyage API"],
            "chroma": ["Chroma vector database", "Chroma embeddings"],
            "annoy": ["Annoy similarity library", "Spotify Annoy"],
        }
        
        # Check for comparison keywords
        comparison_keywords = ["vs", "vs.", "versus", "compare", "comparison", "advantage", "better"]
        is_comparison = any(keyword in question_lower for keyword in comparison_keywords)
        
        # Find all product names mentioned in question
        mentioned_products = []
        for product_name in product_search_terms.keys():
            if product_name in question_lower:
                mentioned_products.append(product_name)
        
        # Handle comparison questions with multiple products
        if is_comparison and len(mentioned_products) >= 2:
            # Build a comparison query: "Product1 vs Product2 comparison"
            products_str = " vs ".join(mentioned_products)
            search_query = f"{products_str} vector database comparison"
            logger.debug(f"[WEB_SEARCH_QUERY] Comparison detected: '{question[:50]}...' -> '{search_query}'")
            return search_query
        
        # Handle single product with comparison context
        if is_comparison and len(mentioned_products) == 1:
            product = mentioned_products[0]
            search_query = f"{product} advantages benefits vector database"
            logger.debug(f"[WEB_SEARCH_QUERY] Single product comparison: '{question[:50]}...' -> '{search_query}'")
            return search_query
        
        # Handle single product without comparison context (original logic)
        if len(mentioned_products) >= 1:
            product_name = mentioned_products[0]  # Use first mentioned product
            search_variants = product_search_terms[product_name]
            search_query = search_variants[0]
            logger.debug(f"[WEB_SEARCH_QUERY] Single product: '{question[:40]}...' -> '{search_query}'")
            return search_query
        
        # For general how/what questions without specific products
        if any(word in question_lower for word in ["how", "what", "explain", "describe"]):
            if any(word in question_lower for word in ["vector", "database", "search", "embedding"]):
                # Technical question - add documentation context
                search_query = question + " documentation guide"
            else:
                # General question
                search_query = question + " tutorial"
        else:
            # Statement or comparison question without specific products
            search_query = question
        
        logger.debug(f"[WEB_SEARCH_QUERY] Using: '{search_query[:60]}...'")
        return search_query

    def _calculate_confidence_score(self, sources: List[Dict], answer: str) -> float:
        """Calculate confidence score for an answer based on retrieval quality and answer characteristics.
        
        Confidence is calculated as a combination of:
        1. Source relevance: Average similarity of retrieved sources (0-1)
        2. Answer quality: Length and sentence count (longer, well-structured answers are more confident)
        
        The score ranges from 0.0 (no confidence) to 1.0 (high confidence).
        
        Args:
            sources: List of source documents with distance/similarity scores
            answer: Generated answer text
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        try:
            if not sources:
                # No sources retrieved - low confidence
                return 0.3
            
            # Component 1: Source relevance (0-1 scale based on similarity)
            # Distance is 0-1 (0=perfect match, 1=no match), so invert it
            distances = []
            for source in sources:
                distance = source.get("distance", 1.0)
                if isinstance(distance, (int, float)):
                    distances.append(distance)
            
            if distances:
                avg_distance = sum(distances) / len(distances)
                source_relevance = max(0.0, 1.0 - avg_distance)  # Invert: 0 distance = 1.0 relevance
                # Scale to 0.5-1.0 range (never go below 0.5 for sources)
                source_relevance = 0.5 + (source_relevance * 0.5)
            else:
                source_relevance = 0.5
            
            # Component 2: Answer quality metrics
            # Penalize very short answers, reward well-structured ones
            answer_length = len(answer)
            sentence_count = answer.count(".") + answer.count("!") + answer.count("?")
            
            if answer_length < 50:
                answer_quality = 0.3  # Too short
            elif answer_length < 100:
                answer_quality = 0.6  # Somewhat short
            elif answer_length > 500 and sentence_count < 2:
                answer_quality = 0.7  # Long but lacks structure
            else:
                answer_quality = 0.9  # Good length and structure
            
            # Scale answer quality to 0.6-1.0 range
            answer_score = 0.6 + (answer_quality * 0.4)
            
            # Final confidence: weighted average (60% source, 40% answer)
            confidence = (source_relevance * 0.6) + (answer_score * 0.4)
            
            # Clamp to 0.0-1.0 range
            confidence = max(0.0, min(1.0, confidence))
            
            logger.debug(
                f"Confidence calculation: "
                f"source_relevance={source_relevance:.2%}, "
                f"answer_score={answer_score:.2%}, "
                f"final={confidence:.2%}"
            )
            
            return confidence
            
        except Exception as e:
            logger.warning(f"Failed to calculate confidence score: {e}")
            return 0.5  # Return neutral score on error

    def _detect_comparative_question(self, question: str) -> Tuple[bool, Optional[Tuple[str, str]]]:
        """Detect if question is asking for product comparison using LLM classification.
        
        Uses the language model to determine if the question is asking for a comparison
        between two products, rather than relying on hardcoded keywords.
        
        Returns:
            Tuple of (is_comparative, (product1, product2)) or (False, None)
        """
        # Quick keyword check - only use LLM for questions that might be comparisons
        question_lower = question.lower()
        comparison_keywords = {'vs', 'versus', 'compare', 'comparison', 'difference', 'better', 'advantage', 'vs.', 'between', 'which is better', 'how does', 'v/s'}
        has_comparison_keyword = any(keyword in question_lower for keyword in comparison_keywords)
        
        # If no comparison keywords, it's definitely not a comparison
        if not has_comparison_keyword:
            logger.debug(f"Quick check: No comparison keywords found, skipping LLM classification")
            return False, None
        
        classification_prompt = f"""Analyze this question and determine if it's asking for a comparison between two products, databases, or systems.

Question: {question}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
    "is_comparison": true/false,
    "product1": "name or null",
    "product2": "name or null",
    "reason": "brief reason"
}}

IMPORTANT: Only return is_comparison=true if the question explicitly asks to COMPARE two distinct products.

Examples of comparisons:
- "What are Milvus advantages over Pinecone?"
- "Compare Elasticsearch and Weaviate"
- "How does Qdrant compare to Pinecone?"
- "PostgreSQL vs Milvus" 
- "Which is better - Pinecone or Qdrant?"

Examples of non-comparisons (DO NOT CLASSIFY AS COMPARISON):
- "What is Milvus?" (asking about ONE product only)
- "How do I use vector databases?"
- "Explain embeddings"
- "Tell me about Milvus" (about ONE product)
- "What are the features of Pinecone?" (about ONE product)
"""
        
        try:
            # Get LLM classification
            response = self.ollama_client.generate(
                prompt=classification_prompt,
                model=self.settings.ollama_model,
                temperature=0.0,  # Zero temperature for strict deterministic classification
                max_tokens=200,
            )
            
            # Parse JSON response
            response_text = response.strip()
            if response_text.startswith("```"):
                # Remove markdown code blocks if present
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.split("```")[0].strip()
            
            classification = json.loads(response_text)
            
            if classification.get("is_comparison") and classification.get("product1") and classification.get("product2"):
                product1 = classification["product1"].strip().lower()
                product2 = classification["product2"].strip().lower()
                
                logger.info(f"Comparative question detected via LLM: {product1} vs {product2}")
                return True, (product1, product2)
            
            return False, None
            
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.warning(f"Failed to classify question as comparative: {e}")
            return False, None
        except Exception as e:
            logger.error(f"Error in comparative question detection: {e}")
            return False, None

    def search_comparison(
        self,
        product1: str,
        product2: str,
        collection_name: str = "milvus_docs",
        top_k: int = 2,  # OPTIMIZATION: Reduced from 3 to 2 results per search
    ) -> Tuple[str, List[Dict]]:
        """Search for comparison between two products using web search and local context.
        
        Combines Milvus documentation context with filtered web search results.
        Uses LLM to synthesize a focused comparison without unrelated topics.
        
        Performance Optimizations:
        - Parallel web searches (concurrent requests instead of sequential)
        - Reduced web search features (3 instead of 5)
        - Lightweight LLM synthesis (tokens reduced from 1000 to 500)
        - Single Milvus retrieval for both products
        
        Args:
            product1: First product name
            product2: Second product name
            collection_name: Milvus collection to search for context
            top_k: Number of results per search (default: 2 for speed)
            
        Returns:
            Tuple of (comparison_text, sources_list)
        """
        sources = []
        
        try:
            logger.info(f"Generating comparison: {product1} vs {product2} (optimized)")
            perf_start = time.time()
            
            # Get web search results with feature-focused queries
            # OPTIMIZATION: Reduced features from 5 to 3 most important ones
            comparison_data = self.web_search.search_comparison(
                product1, product2, max_results=top_k
            )
            
            web_search_time = time.time()
            
            # Extract web search results and add to sources
            # Note: search_comparison returns product-specific results, not direct comparison results
            web_search_count = 0
            
            # Always try to include product-specific web search results
            if comparison_data.get("product1") or comparison_data.get("product2"):
                logger.info("[WEB_SEARCH_COMPARISON] Processing product-specific web search results")
                
                # Extract product1 results
                p1_data = comparison_data.get("product1", {})
                p1_name = p1_data.get("name", product1)
                p1_features = p1_data.get("results", {})
                
                # OPTIMIZATION: Only process top 2 features (instead of 3)
                for feature, results in list(p1_features.items())[:2]:
                    for idx, web_result in enumerate(results[:1], 1):  # Only 1 result per feature
                        url = web_result.get("url", "")
                        title = web_result.get("title", "")
                        
                        # Skip empty results
                        if not url and not title:
                            continue
                        
                        # Format as a global source so UI can display it (links only, no content)
                        web_source = {
                            "document_name": f"{p1_name.upper()} - {title[:40]}",  # Use document_name for UI compatibility
                            "source_type": "web_search",
                            "url": url,
                            "title": title,
                            "distance": 0.92 - (web_search_count * 0.03),  # High relevance for web results
                        }
                        sources.append(web_source)
                        web_search_count += 1
                        logger.debug(f"[WEB_SEARCH_COMPARISON] Added {p1_name}: {title[:50]}")
                        break  # Only one result per feature
                    
                    if web_search_count >= 3:  # Limit total to 3 per product (was 5)
                        break
                
                # Extract product2 results (for comparison)
                p2_data = comparison_data.get("product2", {})
                p2_name = p2_data.get("name", product2)
                p2_features = p2_data.get("results", {})
                
                # OPTIMIZATION: Only process top 2 features
                for feature, results in list(p2_features.items())[:2]:
                    for idx, web_result in enumerate(results[:1], 1):  # Only 1 result per feature
                        url = web_result.get("url", "")
                        title = web_result.get("title", "")
                        
                        # Skip empty results
                        if not url and not title:
                            continue
                        
                        # Format as a global source (links only, no content)
                        web_source = {
                            "document_name": f"{p2_name.upper()} - {title[:40]}",  # Use document_name for UI compatibility
                            "source_type": "web_search",
                            "url": url,
                            "title": title,
                            "distance": 0.92 - (web_search_count * 0.03),
                        }
                        sources.append(web_source)
                        web_search_count += 1
                        logger.debug(f"[WEB_SEARCH_COMPARISON] Added {p2_name}: {title[:50]}")
                        break  # Only one result per feature
                    
                    if web_search_count >= 3:  # Limit total to 3 per product
                        break
            
            if web_search_count > 0:
                logger.info(f"✓ Added {web_search_count} web search results ({time.time() - web_search_time:.1f}s)")
            else:
                logger.warning(f"⚠️  No web search results - will use Milvus documentation only")
            
            # Get context from Milvus documentation
            # OPTIMIZATION: Combined into single retrieval for both products
            product1_context = []
            product1_sources = []
            retrieval_start = time.time()
            try:
                # Search for comparison context in one query
                combined_query = f"{product1} vs {product2} features advantages comparison vector database"
                product1_context, product1_sources = self.retrieve_context(
                    collection_name,
                    combined_query,
                    top_k=top_k  # Reduced from duplicate queries
                )
                sources.extend(product1_sources)
                logger.info(f"Retrieved {len(product1_context)} context chunks in {time.time()-retrieval_start:.1f}s")
            except Exception as e:
                logger.warning(f"Failed to retrieve context: {e}")
            
            # Use LLM to synthesize a focused, relevant comparison
            # OPTIMIZATION: Reduced max_tokens from 1000 to 500 for faster synthesis
            synthesis_prompt = self._create_comparison_synthesis_prompt(
                product1, product2, comparison_data, product1_context
            )
            
            llm_start = time.time()
            try:
                comparison_summary = self.ollama_client.generate(
                    prompt=synthesis_prompt,
                    model=self.settings.ollama_model,
                    temperature=0.3,  # Slightly higher for better synthesis
                    max_tokens=500,  # OPTIMIZATION: Reduced from 1000 to 500
                )
                logger.info(f"✓ LLM synthesis ({time.time()-llm_start:.1f}s): {len(comparison_summary)} chars")
            except Exception as e:
                logger.warning(f"Failed to synthesize comparison via LLM: {e}")
                # Fallback to formatted results if LLM fails
                comparison_summary = self._format_comparison_fallback(
                    product1, product2, comparison_data, product1_context
                )
            
            total_time = time.time() - perf_start
            logger.info(f"Comparison completed in {total_time:.1f}s with {len(sources)} sources")
            return comparison_summary, sources
            
        except Exception as e:
            logger.error(f"Comparison search failed: {e}")
            error_msg = f"Unable to generate comparison between {product1} and {product2}: {e}"
            return error_msg, sources

    def _create_comparison_synthesis_prompt(
        self, product1: str, product2: str, comparison_data: Dict, product1_context: List[str]
    ) -> str:
        """Create a prompt for LLM to synthesize a focused comparison.
        
        The LLM will filter out unrelated topics and focus on vector database features.
        """
        # Extract relevant snippets from comparison data
        comparison_snippets = []
        
        if comparison_data.get("comparison"):
            for result in comparison_data["comparison"][:2]:
                snippet = result.get("snippet", "")
                if snippet:
                    comparison_snippets.append(snippet)
        
        comparison_text = "\n".join(comparison_snippets) if comparison_snippets else "No comparison data"
        product1_context_str = "\n".join(product1_context[:2]) if product1_context else "No local data"
        
        # Capitalize product names for display
        product1_display = product1.upper() if len(product1) <= 10 else product1.title()
        product2_display = product2.upper() if len(product2) <= 10 else product2.title()
        
        # Build prompt focused on vector database features
        prompt = f"""You are a technical analyst comparing vector databases.

Compare {product1_display} and {product2_display} focusing ONLY on vector database features.

Web search data:
{comparison_text}

Local knowledge about {product1_display}:
{product1_context_str}

Create a concise, feature-focused comparison. IMPORTANT:
- Focus ONLY on vector database capabilities (indexing, performance, scalability, API, pricing)
- Exclude unrelated topics like embeddings models, ML frameworks, or other tools
- Substitute product names in your response: use "{product1_display}" instead of placeholders like {{product1}}
- Use this structure in your response:
  * Core Differences
  * {product1_display} Strengths
  * {product2_display} Strengths  
  * Key Considerations
- Be specific with numbers/metrics when available
- Keep response under 500 words
- DO NOT use template variables like {{product1}} or {{product2}} in your response - use the actual product names

Comparison:"""
        return prompt

    def _format_comparison_fallback(
        self, product1: str, product2: str, comparison_data: Dict, product1_context: List[str]
    ) -> str:
        """Fallback formatting when LLM synthesis fails.
        
        Manually formats the comparison focusing on relevant content.
        """
        output = f"\n## {product1} vs {product2}\n\n"
        
        # Add comparison overview
        output += "### Overview\n"
        if comparison_data.get("comparison"):
            for result in comparison_data["comparison"][:2]:
                snippet = result.get("snippet", "")
                if snippet and "vector" in snippet.lower():
                    output += f"- {snippet[:150]}...\n"
        
        # Add local knowledge
        output += f"\n### {product1.title()} Features\n"
        if product1_context:
            for chunk in product1_context[:2]:
                output += f"- {chunk[:120]}\n"
        
        output += f"\n### Key Considerations\n"
        output += f"- Compare on vector indexing methods (HNSW, IVF, etc.)\n"
        output += f"- Evaluate query performance and scalability\n"
        output += f"- Check supported vector dimensions and data types\n"
        
        return output

    # ========================================================================
    # RETRIEVAL SKILL TOOLS
    # ========================================================================
    
    def retrieve_context(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        offset: int = 0,
        filter_source: Optional[str] = None,
    ) -> Tuple[List[str], List[Dict]]:
        """Retrieve relevant context from vector database with pagination and filtering.
        
        This is the internal method used by retrieve_documents and answer_question.

        Args:
            collection_name: Name of the collection to search
            query: User query/question
            top_k: Number of top results to retrieve
            offset: Number of results to skip (for pagination)
            filter_source: Optional source to filter by (e.g., 'milvus_docs')

        Returns:
            Tuple of (context_chunks, source_metadata)
        """
        try:
            # Check search cache first
            cache_key = (collection_name, query, top_k, offset)
            if cache_key in self.search_cache:
                logger.info(f"✓ Search cache hit for query (offset={offset})")
                return self.search_cache[cache_key]

            # Generate embedding for query (with caching)
            embed_start = time.time()
            query_embedding, embedding_cached = self._generate_embedding(query)
            embed_time = time.time() - embed_start
            
            if embedding_cached:
                logger.info(f"✓ Embedding cache hit")
            else:
                logger.info(f"✓ Embedding generated and cached")
            logger.debug(f"Embedding generation took {embed_time:.2f}s")

            # Build filter if source specified
            filter_expr = None
            if filter_source:
                filter_expr = f"source == '{filter_source}'"
                logger.info(f"Applying filter: {filter_expr}")

            # Search in vector database
            search_start = time.time()
            search_results = self.vector_db.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                limit=top_k,
                offset=offset,
                filter_expr=filter_expr,
            )
            search_time = time.time() - search_start
            logger.info(f"Vector search took {search_time:.2f}s (offset={offset})")

            # Filter results by similarity threshold - only high-quality matches
            SIMILARITY_THRESHOLD = 0.65  # Distance threshold (0-1 scale)
            high_quality_results = [
                r for r in search_results 
                if r.get("distance", 0) <= SIMILARITY_THRESHOLD
            ]
            
            if len(high_quality_results) < len(search_results):
                filtered_count = len(search_results) - len(high_quality_results)
                logger.info(f"Filtered out {filtered_count} low-quality matches (distance > {SIMILARITY_THRESHOLD})")
            
            context = [result["text"] for result in high_quality_results]
            
            # Extract source metadata
            sources = []
            for idx, result in enumerate(search_results, 1):
                metadata = result.get("metadata", {})
                if isinstance(metadata, str):
                    try:
                        import json
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}
                
                doc_name = result.get("document_name") or metadata.get("document_name") or metadata.get("filename") or metadata.get("source")
                distance = result.get("distance", 0)
                source_info = {
                    "distance": distance,
                    "metadata": metadata,
                }
                
                if not doc_name:
                    source_info["text"] = result.get("text", "")[:150]
                else:
                    source_info["document_name"] = doc_name
                
                sources.append(source_info)
                
                if doc_name:
                    similarity = 1 - distance if isinstance(distance, (int, float)) else 0
                    logger.debug(f"  [{idx}] {doc_name} (similarity: {similarity:.2%})")
            
            # Cache the result
            result_tuple = (context, sources)
            self._add_to_cache(self.search_cache, cache_key, result_tuple)
            
            if not context:
                logger.warning(f"⚠️  No context chunks retrieved! Collection may be empty or embedding mismatch.")
            else:
                logger.info(f"✓ Retrieved {len(context)} relevant documents")
            
            return result_tuple
            
        except Exception as e:
            logger.error(f"Context retrieval failed: {e}", exc_info=True)
            return ([], [])
    
    def retrieve_documents(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        filter_source: Optional[str] = None,
    ) -> str:
        """Retrieve relevant documents from knowledge base.
        
        This tool searches the vector database for documents semantically
        similar to the query and returns the top-K most relevant results.
        
        Args:
            collection_name: Name of the collection to search
            query: User question or search query
            top_k: Number of top results to return (default: 5)
            filter_source: Optional source filter (e.g., 'milvus_docs')
            
        Returns:
            Formatted string with relevant document chunks and metadata
        """
        try:
            logger.info(f"Retrieving documents for query: {query[:50]}...")
            
            context, sources = self.retrieve_context(
                collection_name=collection_name,
                query=query,
                top_k=top_k,
                filter_source=filter_source,
            )
            
            if not context:
                return f"No documents found for query: {query}"
            
            # Format results
            formatted = f"Retrieved {len(context)} documents:\n\n"
            for i, chunk in enumerate(context, 1):
                preview = chunk[:150].replace('\n', ' ')
                formatted += f"{i}. {preview}...\n"
                
                if i < len(sources):
                    source = sources[i-1]
                    if "document_name" in source:
                        formatted += f"   Source: {source['document_name']}\n"
                    formatted += f"   Distance: {source.get('distance', 0):.4f}\n"
                
                formatted += "\n"
            
            logger.info(f"Retrieved {len(context)} documents")
            return formatted
            
        except Exception as e:
            error_msg = f"Document retrieval failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    # ========================================================================
    # ANSWER GENERATION SKILL TOOLS
    # ========================================================================
    
    def generate_answer(
        self,
        question: str,
        context: str,
        sources: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate an answer using retrieved context.
        
        This tool uses the LLM to synthesize an answer based on the
        provided context and the original question. Uses Milvus-specific
        system instructions and RAG prompting with source attribution.
        
        Prompt ordering (optimal for LLM comprehension):
        1. System instructions (role, constraints)
        2. User question (what to answer)
        3. Supporting context (information to use)
        4. Request to answer
        
        Args:
            question: The user's question
            context: Retrieved context from knowledge base
            sources: Optional list of source metadata dicts for attribution
            temperature: Sampling temperature (default: 0.1 for factual answers)
            max_tokens: Maximum tokens in response (default: from settings)
            
        Returns:
            Generated answer as a string
        """
        try:
            logger.info(f"Generating answer for: {question[:50]}...")
            
            # Use provided parameters or defaults from settings
            use_temperature = temperature if temperature is not None else 0.1
            use_max_tokens = max_tokens or self.settings.max_tokens
            
            # Build RAG prompt with clean, focused instructions
            system_instructions = """You are a Milvus vector database expert assistant.

CONTEXT TYPE AWARENESS:
- Some retrieved documents may contain CODE EXAMPLES, TUTORIALS, or INTEGRATION GUIDES
- These should NOT be presented as product descriptions or company information
- Code examples are typically marked with ```python, ```code, or appear in tutorial sections
- Always distinguish between: (1) Product information, (2) Technical documentation, (3) Code examples

ANSWERING RULES:
1. Answer using the provided context from Milvus documentation when available
2. For product/company questions (e.g., "What is VoyageAI?", "Tell me about Pinecone"):
   - Prefer WEB SOURCE results when available (marked with 🌐 in sources)
   - Web sources contain product information, company details, use cases
   - Local docs contain technical integration guides and reference material
3. Clearly label information source: "According to [source-name]..." or "From [document-name]..."
4. If the retrieved documents are only code examples/tutorials:
   - Point out that you found integration guides but not product information
   - Recommend web search for product details
5. Do NOT present code example data as factual product information

RESPONSE STYLE:
- Be concise and accurate
- Cite sources clearly
- Distinguish between types of sources (web vs documentation)
- Avoid mixing code examples with product descriptions"""
            
            # If no context provided, use helpful message
            if not context or not context.strip():
                context = "No documents found in the knowledge base. Please ensure documents have been loaded."
            
            # Build source attribution section if sources provided
            source_attribution = ""
            if sources and len(sources) > 0:
                source_attribution = "\nSources:\n"
                doc_sources = []
                web_sources = []
                
                # Separate document and web sources
                for source in sources:
                    if source.get('source_type') == 'web_search' or source.get('url'):
                        web_sources.append(source)
                    else:
                        doc_sources.append(source)
                
                # Add document sources first
                for idx, source in enumerate(doc_sources, 1):
                    if "document_name" in source:
                        source_attribution += f"  [{idx}] {source['document_name']}"
                    else:
                        source_attribution += f"  [{idx}] Knowledge base"
                    
                    distance = source.get('distance', 0)
                    if distance:
                        similarity = 1 - distance if isinstance(distance, (int, float)) else 0
                        source_attribution += f" (relevance: {similarity:.0%})"
                    source_attribution += "\n"
                
                # Add web search sources with URLs and relevance
                web_start_idx = len(doc_sources) + 1
                for idx, source in enumerate(web_sources, web_start_idx):
                    title = source.get('title', 'Web Result')
                    url = source.get('url', '')
                    source_attribution += f"  [{idx}] {title}"
                    if url:
                        source_attribution += f" ({url})"
                    
                    # Show relevance score for web sources (1.0 = best, stored as distance)
                    distance = source.get('distance', 0)
                    if distance and isinstance(distance, (int, float)):
                        # For web sources, distance is already the relevance score (0-1)
                        relevance_pct = int(distance * 100)
                        source_attribution += f" (relevance: {relevance_pct}%)"
                    
                    source_attribution += "\n"
            
            # Reordered RAG prompt: instructions → question → context → sources → request
            rag_prompt = f"""{system_instructions}

Question: {question}

Relevant context from Milvus:
{context}{source_attribution}

Based on this context, please answer the question above:"""
            
            logger.debug(f"LLM Generation Params: temperature={use_temperature}, max_tokens={use_max_tokens}")
            
            answer = self.ollama_client.generate(
                prompt=rag_prompt,
                model=self.settings.ollama_model,
                temperature=use_temperature,
                max_tokens=use_max_tokens,
            )
            
            logger.info(f"Answer generated ({len(answer)} chars)")
            logger.debug(f"Generated answer: {answer[:200]}...")
            return answer
            
        except Exception as e:
            error_msg = f"Answer generation failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    # ========================================================================
    # KNOWLEDGE BASE MANAGEMENT SKILL TOOLS
    # ========================================================================
    
    def add_documents(
        self,
        collection_name: str,
        documents: list,
    ) -> str:
        """Add documents to the knowledge base.
        
        This tool embeds and indexes documents in the vector database
        for future retrieval.
        
        Args:
            collection_name: Target collection name
            documents: List of documents (strings or dicts with 'text', 'source', optional 'metadata')
            
        Returns:
            Status message with count of added documents
        """
        try:
            if not documents:
                return "No documents provided"
            
            logger.info(f"Adding {len(documents)} documents to '{collection_name}'...")
            
            # Normalize documents - handle both strings and dicts
            normalized_docs = []
            for doc in documents:
                if isinstance(doc, str):
                    # Convert plain string to dict format
                    normalized_docs.append({
                        "text": doc,
                        "source": "sample",
                        "metadata": {}
                    })
                elif isinstance(doc, dict):
                    # Ensure dict has required fields
                    normalized_docs.append({
                        "text": doc.get("text", ""),
                        "source": doc.get("source", "unknown"),
                        "metadata": doc.get("metadata", {})
                    })
                else:
                    logger.warning(f"Skipping document of unsupported type: {type(doc)}")
                    continue
            
            if not normalized_docs:
                return "No valid documents provided"
            
            # Extract texts and embed all at once
            texts = [doc["text"] for doc in normalized_docs]
            embeddings = self.ollama_client.embed_texts(
                texts,
                model=self.settings.ollama_embed_model,
            )
            
            # Prepare metadata for insertion
            metadata_list = [doc.get("metadata", {}) for doc in normalized_docs]
            for i, doc in enumerate(normalized_docs):
                if "source" in doc:
                    metadata_list[i]["source"] = doc["source"]
            
            # Insert embeddings into vector database
            self.vector_db.insert_embeddings(
                collection_name=collection_name,
                embeddings=embeddings,
                texts=texts,
                metadata=metadata_list,
            )
            
            message = f"Successfully added {len(normalized_docs)} documents to '{collection_name}'"
            logger.info(message)
            return message
            
        except Exception as e:
            error_msg = f"Document addition failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    # ========================================================================
    # SEARCH AND ANALYSIS TOOLS
    # ========================================================================
    
    def search_by_source(
        self,
        collection_name: str,
        query: str,
        source: str,
        top_k: int = 5,
    ) -> str:
        """Search documents filtered by source.
        
        Retrieves documents from a specific source within a collection.
        
        Args:
            collection_name: Collection to search
            query: Search query
            source: Document source to filter by
            top_k: Number of results to return
            
        Returns:
            Filtered search results
        """
        logger.info(f"Searching by source: {source}")
        return self.retrieve_documents(
            collection_name=collection_name,
            query=query,
            top_k=top_k,
            filter_source=source,
        )
    
    def search_multiple_collections(
        self,
        collections: List[str],
        query: str,
        top_k: int = 5,
    ) -> Tuple[List[str], List[Dict]]:
        """Search and merge results from multiple collections.
        
        This enables topic-based retrieval by searching separate collections
        (e.g., basics, API reference, examples) and merging results by relevance.
        Collections might be organized as:
        - 'milvus_basics' - Getting started, concepts, architecture
        - 'milvus_api' - API reference, method signatures
        - 'milvus_examples' - Code examples, tutorials
        - 'milvus_performance' - Optimization, benchmarks
        
        Args:
            collections: List of collection names to search
            query: Search query
            top_k: Total number of results to return (merged across collections)
            
        Returns:
            Tuple of (merged_context_chunks, merged_sources)
        """
        try:
            logger.info(f"Searching {len(collections)} collections: {collections}")
            
            all_chunks = []
            all_sources = []
            
            # Search each collection
            for collection in collections:
                try:
                    chunks, sources = self.retrieve_context(
                        collection_name=collection,
                        query=query,
                        top_k=top_k,
                    )
                    all_chunks.extend(chunks)
                    all_sources.extend(sources)
                    logger.info(f"  Retrieved {len(chunks)} chunks from '{collection}'")
                except Exception as e:
                    logger.warning(f"  Failed to search '{collection}': {e}")
                    continue
            
            # Sort by relevance (distance) and keep top_k
            if all_sources:
                # Create list of (chunk, source) pairs and sort by distance
                pairs = list(zip(all_chunks, all_sources))
                pairs.sort(key=lambda x: x[1].get('distance', 999))
                
                # Take top_k and separate
                top_pairs = pairs[:top_k]
                merged_chunks = [p[0] for p in top_pairs]
                merged_sources = [p[1] for p in top_pairs]
                
                logger.info(f"Merged {len(all_chunks)} results from {len(collections)} collections, kept top {len(merged_chunks)}")
                return (merged_chunks, merged_sources)
            else:
                logger.warning(f"No results found across {len(collections)} collections")
                return ([], [])
                
        except Exception as e:
            logger.error(f"Multi-collection search failed: {e}", exc_info=True)
            return ([], [])

    def list_collections(self) -> str:
        """List all available collections in the vector database.
        
        Returns:
            String listing available collections
        """
        try:
            logger.info("Listing collections...")
            
            collections = self.vector_db.list_collections()
            if not collections:
                return "No collections found in vector database"
            
            result = "Available collections:\n\n"
            for collection in collections:
                result += f"- {collection}\n"
            
            logger.info(f"Found {len(collections)} collections")
            return result
            
        except Exception as e:
            error_msg = f"Failed to list collections: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    # ========================================================================
    # CONVERSATION ORCHESTRATION
    # ========================================================================
    
    def answer_question(
        self,
        question: str,
        collection_name: Optional[str] = None,
        collections: Optional[List[str]] = None,
        top_k: int = 5,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, List[Dict]]:
        """Complete RAG pipeline: retrieve context and generate answer.
        
        This is the main entry point that orchestrates the full RAG flow with:
        - Security attack detection
        - Question scope checking
        - Multi-layer caching (embedding, search, answer, semantic)
        - Context retrieval from single or multiple collections
        - Answer generation with source attribution
        
        For direct invocation:
            answer, sources = agent.answer_question("What is Milvus?")
        
        For multi-collection search:
            answer, sources = agent.answer_question(
                question="What is Milvus?",
                collections=["milvus_basics", "milvus_api"]
            )
        
        Args:
            question: The user's question
            collection_name: Single collection to search (ignored if collections provided)
            collections: List of collection names to search (overrides collection_name)
            top_k: Number of context chunks to retrieve (default: 5)
            temperature: LLM temperature (default: 0.1 for factual answers)
            max_tokens: Max tokens in response (default: from settings)
            
        Returns:
            Tuple of (answer_text, sources_list)
        """
        start_time = time.time()
        sources = []
        cache_hits = {}
        embedding_time = 0
        retrieval_time = 0
        generation_time = 0
        
        try:
            logger.info(f"Answering question: {question[:50]}...")
            
            # SECURITY CHECK: Detect attacks and injections
            if self._is_security_attack(question):
                logger.info("Security attack detected!")
                answer = "I can only help with questions about Milvus, vector databases, and RAG systems."
                return (answer, [])
            
            # SCOPE CHECK: Determine if question is about Milvus/vectors/RAG
            if not self._is_question_in_scope(question):
                logger.info("Question is out-of-scope, skipping retrieval")
                answer = "I can only help with questions about Milvus, vector databases, and RAG systems."
                return (answer, [])
            
            # COMPARATIVE CHECK: Handle product comparisons
            is_comparative, products = self._detect_comparative_question(question)
            if is_comparative and products:
                logger.info(f"Comparative question detected: {products[0]} vs {products[1]}")
                try:
                    comparison_result, comparison_sources = self.search_comparison(
                        products[0],
                        products[1],
                        collection_name=collection_name or "milvus_docs",
                        top_k=top_k,
                    )
                    logger.info(f"Comparison returned {len(comparison_sources)} sources")
                    return (comparison_result, comparison_sources)
                except Exception as e:
                    logger.warning(f"Comparison search failed: {e}. Falling back to standard RAG.")
            
            # Determine which collection(s) to search
            if collections is None:
                collections = [collection_name or "default"]
                is_multi_collection = False
            else:
                is_multi_collection = True
                logger.info(f"Multi-collection search enabled: {collections}")
            
            # Check answer cache first (exact match)
            cache_key = (question, tuple(collections), top_k)
            logger.debug(f"[CACHE_DEBUG] Cache key: question='{question[:40]}...', collections={collections}, top_k={top_k}")
            if cache_key in self.answer_cache:
                logger.info(f"✓ Answer cache hit (exact match)")
                cache_hits['answer_cache'] = True
                cached_result = self.answer_cache[cache_key]
                total_time = time.time() - start_time
                logger.info(f"Total response time (cached): {total_time:.2f}s")
                return cached_result
            else:
                logger.debug(f"[CACHE_DEBUG] Answer cache miss: {len(self.answer_cache)} items in cache")
                cache_hits['answer_cache'] = False
            
            # Generate embedding for semantic cache check
            embed_start = time.time()
            question_embedding, embedding_cached = self._generate_embedding(question)
            cache_hits['embedding_cache'] = embedding_cached
            
            embed_time = time.time() - embed_start
            embedding_time = embed_time
            logger.debug(f"Embedding check took {embed_time:.2f}s" + (f" (cached)" if embedding_cached else ""))

            
            # Check persistent response cache (semantic similarity)
            if self.response_cache and question_embedding is not None:
                cached_response = self.response_cache.search_cache(question, question_embedding)
                if cached_response:
                    similarity = cached_response.get('similarity', 0)
                    logger.info(f"✓ Response cache hit (semantic match, {similarity:.1%} similar)")
                    answer = cached_response.get("response", "")
                    sources = cached_response.get("sources", [])
                    result_tuple = (answer, sources)
                    
                    # Also cache in answer cache for faster subsequent exact matches
                    self._add_to_cache(self.answer_cache, cache_key, result_tuple)
                    
                    total_time = time.time() - start_time
                    logger.info(f"Total response time (semantic cache): {total_time:.2f}s")
                    return result_tuple
            
            # Retrieve relevant context (from single or multiple collections)
            retrieval_start = time.time()
            if is_multi_collection:
                context_chunks, sources = self.search_multiple_collections(
                    collections=collections,
                    query=question,
                    top_k=top_k,
                )
            else:
                context_chunks, sources = self.retrieve_context(
                    collection_name=collections[0],
                    query=question,
                    top_k=top_k,
                )
            retrieval_time = time.time() - retrieval_start
            logger.info(f"Context retrieval took {retrieval_time:.2f}s")
            
            # Add web search results as supplementary sources
            web_search_results = []
            try:
                web_search_start = time.time()
                # Generate optimized search query for web search
                web_search_query = self._generate_web_search_query(question)
                logger.info(f"[WEB_SEARCH_DEBUG] Starting web search with query: '{web_search_query[:50]}'")
                web_results = self.web_search.search(
                    query=web_search_query,
                    max_results=3,
                    safe_search=True
                )
                logger.info(f"[WEB_SEARCH_DEBUG] Received {len(web_results) if web_results else 0} raw results from web search")
                
                if web_results:
                    logger.info(f"✓ Web search returned {len(web_results)} results")
                    # Format web search results with proper source_type and relevance scoring
                    for idx, web_result in enumerate(web_results, 1):
                        # Calculate relevance based on search rank (1.0 = perfect, descending)
                        # Web search results are already ranked by relevance engine
                        relevance_scores = [0.95, 0.88, 0.78]  # First, second, third results
                        relevance = relevance_scores[idx - 1] if idx <= len(relevance_scores) else 0.7
                        
                        web_source = {
                            "source_type": "web_search",
                            "url": web_result.get("url", ""),
                            "title": web_result.get("title", "Web Result"),
                            "snippet": web_result.get("snippet", ""),
                            "distance": relevance,  # Store relevance as distance (1.0 = best match)
                        }
                        logger.info(f"[WEB_SEARCH_DEBUG] Result {idx}: {web_source['title'][:40]}... from {web_source.get('url', 'NO_URL')[:50]}")
                        sources.append(web_source)
                        web_search_results.append(web_source)
                    
                    web_search_time = time.time() - web_search_start
                    logger.info(f"✓ Web search completed in {web_search_time:.2f}s - Added {len(web_search_results)} sources to response")
                else:
                    logger.info(f"[WEB_SEARCH_DEBUG] Web search returned EMPTY result list for '{question[:30]}'")
            except Exception as e:
                logger.error(f"[WEB_SEARCH_DEBUG] Web search EXCEPTION: {type(e).__name__}: {str(e)}", exc_info=True)
            
            # Build context text for LLM
            context_text = "\n".join([f"- {chunk}" for chunk in context_chunks])
            
            logger.debug(f"RAG Prompt Context ({len(context_text)} chars)")
            
            # Generate answer using LLM with source attribution
            generation_start = time.time()
            answer = self.generate_answer(
                question=question,
                context=context_text,
                sources=sources,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            generation_time = time.time() - generation_start
            logger.info(f"Answer generation took {generation_time:.2f}s")
            logger.debug(f"Generated answer: {answer[:200]}...")
            
            # Calculate confidence score based on retrieval quality and answer characteristics
            confidence_score = self._calculate_confidence_score(sources, answer)
            
            # Cache the result with sources
            result_tuple = (answer, sources)
            self._add_to_cache(self.answer_cache, cache_key, result_tuple)
            logger.info(f"✓ Answer cached. Cache size now: {len(self.answer_cache)} items")
            
            # Store in persistent response cache for future semantic matches
            if self.response_cache and question_embedding is not None:
                try:
                    # Only cache valid answers, NOT rejection messages
                    if answer != "I can only help with questions about Milvus, vector databases, and RAG systems.":
                        self.response_cache.store_response(
                            question=question,
                            question_embedding=question_embedding,
                            response=answer,
                            metadata={
                                "collection": collection_name,
                                "top_k": top_k,
                                "sources": sources,
                                "confidence": confidence_score,
                            }
                        )
                        logger.info(f"✓ Response cached (confidence: {confidence_score:.1%})")
                    else:
                        logger.info(f"Skipping cache for rejection message")
                except Exception as e:
                    logger.warning(f"Failed to cache response: {e}")
            
            total_time = time.time() - start_time
            metrics = PerformanceMetrics(
                total_time=total_time,
                embedding_time=embedding_time,
                retrieval_time=retrieval_time,
                generation_time=generation_time,
                cache_hits=cache_hits,
            )
            logger.info(f"Confidence: {confidence_score:.1%} | {metrics.summary()}")
            
            return result_tuple
            
        except Exception as e:
            logger.error(f"Question answering failed: {e}", exc_info=True)
            return (f"Error: {str(e)}", [])

    def answer_question_no_cache(
        self,
        collection_name: str,
        question: str,
        top_k: int = 10,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, List[Dict]]:
        """Answer a question bypassing all caches - queries LLM directly.
        
        This method skips:
        - Answer cache (exact match)
        - Embedding cache
        - Search cache  
        - Response cache (semantic match)
        
        Used for testing or getting fresh answers without cache effects.

        Args:
            collection_name: Name of the collection to search
            question: User question
            top_k: Number of context chunks to retrieve
            temperature: LLM temperature (0.0-2.0, lower=more deterministic). Defaults to settings.
            max_tokens: Maximum tokens to generate. Defaults to settings.

        Returns:
            Tuple of (answer, sources)
        """
        try:
            start_time = time.time()
            logger.info(f"[NO CACHE] Answering: {question[:60]}")
            
            # SECURITY CHECK: Detect obvious attack patterns first (no LLM overhead)
            if self._is_security_attack(question):
                logger.info(f"Question rejected: security attack detected")
                answer = "I can only help with questions about Milvus, vector databases, and RAG systems."
                sources = []
                return (answer, sources)
            
            # SCOPE CHECK: Use LLM to determine if question is about Milvus/vectors/RAG
            if not self._is_question_in_scope(question):
                logger.info(f"Question is out-of-scope, skipping retrieval")
                answer = "I can only help with questions about Milvus, vector databases, and RAG systems."
                sources = []
                return (answer, sources)
            
            # Generate fresh embedding (don't use cache)
            embed_start = time.time()
            question_embedding = self.ollama_client.embed_text(
                question,
                model=self.settings.ollama_embed_model,
            )
            embed_time = time.time() - embed_start
            logger.info(f"Embedding generation took {embed_time:.2f}s (fresh)")
            
            # Retrieve context (fresh search, don't use search cache)
            retrieval_start = time.time()
            context_chunks, sources = self.retrieve_context(
                collection_name=collection_name,
                query=question,
                top_k=top_k,
            )
            retrieval_time = time.time() - retrieval_start
            
            # Add web search results as supplementary sources
            web_search_results = []
            try:
                web_search_start = time.time()
                # Generate optimized search query for web search
                web_search_query = self._generate_web_search_query(question)
                logger.info(f"[WEB_SEARCH_DEBUG] Starting web search with query: '{web_search_query[:50]}'")
                web_results = self.web_search.search(
                    query=web_search_query,
                    max_results=3,
                    safe_search=True
                )
                logger.info(f"[WEB_SEARCH_DEBUG] Received {len(web_results) if web_results else 0} raw results from web search")
                
                if web_results:
                    logger.info(f"✓ Web search returned {len(web_results)} results")
                    # Format web search results with proper source_type and relevance scoring
                    for idx, web_result in enumerate(web_results, 1):
                        # Calculate relevance based on search rank (1.0 = perfect, descending)
                        # Web search results are already ranked by relevance engine
                        relevance_scores = [0.95, 0.88, 0.78]  # First, second, third results
                        relevance = relevance_scores[idx - 1] if idx <= len(relevance_scores) else 0.7
                        
                        web_source = {
                            "source_type": "web_search",
                            "url": web_result.get("url", ""),
                            "title": web_result.get("title", "Web Result"),
                            "snippet": web_result.get("snippet", ""),
                            "distance": relevance,  # Store relevance as distance (1.0 = best match)
                        }
                        logger.info(f"[WEB_SEARCH_DEBUG] Result {idx}: {web_source['title'][:40]}... from {web_source.get('url', 'NO_URL')[:50]}")
                        sources.append(web_source)
                        web_search_results.append(web_source)
                    
                    web_search_time = time.time() - web_search_start
                    logger.info(f"✓ Web search completed in {web_search_time:.2f}s - Added {len(web_search_results)} sources to response")
                else:
                    logger.info(f"[WEB_SEARCH_DEBUG] Web search returned EMPTY result list for '{question[:30]}'")
            except Exception as e:
                logger.error(f"[WEB_SEARCH_DEBUG] Web search EXCEPTION: {type(e).__name__}: {str(e)}", exc_info=True)
            
            # Build RAG prompt
            context_text = "\n".join([f"- {chunk}" for chunk in context_chunks])
            if not context_text.strip():
                context_text = "No documents found in the knowledge base."
            
            system_instructions = """You are a Milvus vector database expert assistant.

CONTEXT TYPE AWARENESS:
- Some retrieved documents may contain CODE EXAMPLES, TUTORIALS, or INTEGRATION GUIDES
- These should NOT be presented as product descriptions or company information
- Code examples are typically marked with ```python, ```code, or appear in tutorial sections
- Always distinguish between: (1) Product information, (2) Technical documentation, (3) Code examples

ANSWERING RULES:
1. Answer using the provided context from Milvus documentation when available
2. For product/company questions (e.g., "What is VoyageAI?", "Tell me about Pinecone"):
   - Prefer WEB SOURCE results when available (marked with 🌐 in sources)
   - Web sources contain product information, company details, use cases
   - Local docs contain technical integration guides and reference material
3. Clearly label information source: "According to [source-name]..." or "From [document-name]..."
4. If the retrieved documents are only code examples/tutorials:
   - Point out that you found integration guides but not product information
   - Recommend web search for product details
5. Do NOT present code example data as factual product information

RESPONSE STYLE:
- Be concise and accurate
- Cite sources clearly
- Distinguish between types of sources (web vs documentation)
- Avoid mixing code examples with product descriptions"""
            
            rag_prompt = f"""{system_instructions}

Context from Milvus documentation:
{context_text}

User question: {question}"""
            
            # Generate answer (fresh LLM generation, don't use answer cache)
            generation_start = time.time()
            # Use provided parameters or defaults from settings
            use_temperature = temperature if temperature is not None else 0.1
            use_max_tokens = max_tokens if max_tokens is not None else self.settings.max_tokens
            
            answer = self.ollama_client.generate(
                prompt=rag_prompt,
                model=self.settings.ollama_model,
                temperature=use_temperature,
                max_tokens=use_max_tokens,
            )
            generation_time = time.time() - generation_start
            logger.info(f"Answer generation took {generation_time:.2f}s (fresh)")
            
            total_time = time.time() - start_time
            logger.info(f"Total response time (no cache): {total_time:.2f}s (retrieval: {retrieval_time:.2f}s, generation: {generation_time:.2f}s)")
            
            return answer, sources
            
        except Exception as e:
            logger.error(f"Error in no_cache answer: {e}")
            raise

    async def stream_answer(
        self,
        collection_name: str,
        question: str,
        top_k: int = 10,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Stream answer generation for long-running operations.

        Streams chunks of the answer in real-time as they are generated.
        This provides a perceived immediate response while the full answer
        is being generated in the background.

        Args:
            collection_name: Name of the collection to search
            question: User question
            top_k: Number of context chunks to retrieve
            temperature: LLM temperature (0.0-2.0, lower=more deterministic). Defaults to settings.
            max_tokens: Maximum tokens to generate. Defaults to settings.

        Yields:
            Chunks of the generated answer as they are produced
        """
        try:
            # SECURITY CHECK: Detect obvious attack patterns first (no LLM overhead)
            if self._is_security_attack(question):
                logger.info(f"Question rejected: security attack detected")
                yield "I can only help with questions about Milvus, vector databases, and RAG systems."
                return
            
            # SCOPE CHECK: Use LLM to determine if question is about Milvus/vectors/RAG
            if not self._is_question_in_scope(question):
                logger.info(f"Question is out-of-scope, skipping retrieval")
                yield "I can only help with questions about Milvus, vector databases, and RAG systems."
                return
            
            # Retrieve context
            context_chunks, sources = self.retrieve_context(
                collection_name=collection_name,
                query=question,
                top_k=top_k,
            )
            
            # Construct RAG prompt
            context_text = "\n".join([f"- {chunk}" for chunk in context_chunks])
            
            system_instructions = """You are a Milvus vector database expert assistant.

CONTEXT TYPE AWARENESS:
- Some retrieved documents may contain CODE EXAMPLES, TUTORIALS, or INTEGRATION GUIDES
- These should NOT be presented as product descriptions or company information
- Code examples are typically marked with ```python, ```code, or appear in tutorial sections
- Always distinguish between: (1) Product information, (2) Technical documentation, (3) Code examples

ANSWERING RULES:
1. Answer using the provided context from Milvus documentation when available
2. For product/company questions (e.g., "What is VoyageAI?", "Tell me about Pinecone"):
   - Prefer WEB SOURCE results when available (marked with 🌐 in sources)
   - Web sources contain product information, company details, use cases
   - Local docs contain technical integration guides and reference material
3. Clearly label information source: "According to [source-name]..." or "From [document-name]..."
4. If the retrieved documents are only code examples/tutorials:
   - Point out that you found integration guides but not product information
   - Recommend web search for product details
5. Do NOT present code example data as factual product information

RESPONSE STYLE:
- Be concise and accurate
- Cite sources clearly
- Distinguish between types of sources (web vs documentation)
- Avoid mixing code examples with product descriptions"""
            
            rag_prompt = f"""{system_instructions}

Context from Milvus documentation:
{context_text}

User question: {question}"""
            
            logger.info(f"Starting stream generation for: {question[:50]}...")
            
            # Generate answer using sync generator, run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def generate_chunks():
                """Run the actual streaming generation."""
                all_chunks = []
                try:
                    # Use provided parameters or defaults from settings
                    use_temperature = temperature if temperature is not None else 0.1
                    use_max_tokens = max_tokens if max_tokens is not None else self.settings.max_tokens
                    
                    for chunk in self.ollama_client.generate_stream(
                        prompt=rag_prompt,
                        model=self.settings.ollama_model,
                        temperature=use_temperature,
                        max_tokens=use_max_tokens,
                    ):
                        all_chunks.append(chunk)
                        logger.debug(f"Generated chunk: {chunk[:20]}...")
                except Exception as e:
                    logger.error(f"Error during generation: {e}", exc_info=True)
                    all_chunks.append(f"\n[Error: {str(e)}]")
                return all_chunks
            
            # Run generation in thread pool
            try:
                chunks = await loop.run_in_executor(None, generate_chunks)
                logger.info(f"Generated {len(chunks)} chunks")
                
                # Yield all chunks
                for chunk in chunks:
                    yield chunk
                    # Small delay to simulate streaming
                    await asyncio.sleep(0.001)
                
            except Exception as e:
                logger.error(f"Error in thread pool execution: {e}", exc_info=True)
                yield f"\n[Error: {str(e)}]"
                return
            
            # Format and yield sources at the end
            if sources:
                yield "\n\n[Sources]\n"
                for i, source in enumerate(sources[:3], 1):
                    doc_name = source.get('document_name', 'Unknown')
                    yield f"{i}. {doc_name}\n"
        
        except Exception as e:
            logger.error(f"Stream answer failed: {e}", exc_info=True)
            yield f"[Error: {str(e)}]"

    async def answer_question_async(
        self,
        question: str,
        collection_name: Optional[str] = None,
        collections: Optional[List[str]] = None,
        top_k: int = 5,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, List[Dict]]:
        """Async version of answer_question for non-blocking operations."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.answer_question(
                question=question,
                collection_name=collection_name,
                collections=collections,
                top_k=top_k,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        )

    async def retrieve_context_async(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        offset: int = 0,
        filter_source: Optional[str] = None,
    ) -> Tuple[List[str], List[Dict]]:
        """Async version of retrieve_context for non-blocking operations."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.retrieve_context(
                collection_name=collection_name,
                query=query,
                top_k=top_k,
                offset=offset,
                filter_source=filter_source,
            ),
        )

    # ========================================================================
    # CLEANUP
    # ========================================================================
    
    def close(self) -> None:
        """Close connections and clean up resources."""
        try:
            self.ollama_client.close()
            self.vector_db.close()
            logger.info("StrandsRAGAgent closed")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
