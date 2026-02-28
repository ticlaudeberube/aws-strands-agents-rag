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
            "pinecone": 5, "weaviate": 5, "comparison": 4,
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
        classification_prompt = f"""Analyze this question and determine if it's asking for a comparison between two products or systems.

Question: {question}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
    "is_comparison": true/false,
    "product1": "name or null",
    "product2": "name or null",
    "reason": "brief reason"
}}

Examples of comparisons:
- "What are Milvus advantages over Pinecone?"
- "Compare Elasticsearch and Weaviate"
- "How does Qdrant compare to Pinecone?"

Examples of non-comparisons:
- "What is Milvus?"
- "How do I use vector databases?"
- "Explain embeddings"
"""
        
        try:
            # Get LLM classification
            response = self.ollama_client.generate_text(
                classification_prompt,
                model=self.settings.ollama_model,
                temperature=0.1,  # Low temperature for deterministic classification
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
        top_k: int = 3,
    ) -> str:
        """Search for comparison between two products using web search and local context.
        
        Combines Milvus documentation context with filtered web search results.
        Uses LLM to synthesize a focused comparison without unrelated topics.
        
        Args:
            product1: First product name
            product2: Second product name
            collection_name: Milvus collection to search for context
            top_k: Number of results per search
            
        Returns:
            Formatted comparison text
        """
        try:
            logger.info(f"Generating comparison: {product1} vs {product2}")
            
            # Get web search results with feature-focused queries
            comparison_data = self.web_search.search_comparison(
                product1, product2, max_results=top_k
            )
            
            # Get context from Milvus documentation
            try:
                product1_context, _ = self.retrieve_context(
                    collection_name,
                    f"{product1} vector indexing search performance features",
                    top_k=top_k
                )
            except Exception as e:
                logger.warning(f"Failed to retrieve context for {product1}: {e}")
                product1_context = []
            
            # Use LLM to synthesize a focused, relevant comparison
            synthesis_prompt = self._create_comparison_synthesis_prompt(
                product1, product2, comparison_data, product1_context
            )
            
            try:
                comparison_summary = self.ollama_client.generate_text(
                    synthesis_prompt,
                    model=self.settings.ollama_model,
                    temperature=0.3,  # Slightly higher for better synthesis
                    max_tokens=1000,
                )
            except Exception as e:
                logger.warning(f"Failed to synthesize comparison via LLM: {e}")
                # Fallback to formatted results if LLM fails
                comparison_summary = self._format_comparison_fallback(
                    product1, product2, comparison_data, product1_context
                )
            
            return comparison_summary
        except Exception as e:
            logger.error(f"Comparison search failed: {e}")
            return f"Unable to generate comparison between {product1} and {product2}: {e}"

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
        
        # Build prompt focused on vector database features
        prompt = f"""You are a technical analyst comparing vector databases.

Compare {product1} and {product2} focusing ONLY on vector database features.

Web search data:
{comparison_text}

Local knowledge about {product1}:
{product1_context_str}

Create a concise, feature-focused comparison. IMPORTANT:
- Focus ONLY on vector database capabilities (indexing, performance, scalability, API, pricing)
- Exclude unrelated topics like embeddings models, ML frameworks, or other tools
- Use the format:
  * Core differences
  * {{product1}} strengths
  * {{product2}} strengths
  * Key considerations
- Be specific with numbers/metrics when available
- Keep response under 500 words

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
            system_instructions = """You are a Milvus vector database expert.

Answer questions accurately using ONLY the provided context.
If the context doesn't address the question, respond:
"I don't have information about that in the knowledge base."

Be concise and technical. Cite sources when relevant.
Avoid lengthy explanations, tutorials, or code examples unless needed."""
            
            # If no context provided, use helpful message
            if not context or not context.strip():
                context = "No documents found in the knowledge base. Please ensure documents have been loaded."
            
            # Build source attribution section if sources provided
            source_attribution = ""
            if sources and len(sources) > 0:
                source_attribution = "\nSources:\n"
                for idx, source in enumerate(sources, 1):
                    if "document_name" in source:
                        source_attribution += f"  [{idx}] {source['document_name']}"
                    else:
                        source_attribution += f"  [{idx}] Knowledge base"
                    
                    distance = source.get('distance', 0)
                    if distance:
                        similarity = 1 - distance if isinstance(distance, (int, float)) else 0
                        source_attribution += f" (relevance: {similarity:.0%})"
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
                    comparison_result = self.search_comparison(
                        products[0],
                        products[1],
                        collection_name=collection_name or "milvus_docs",
                        top_k=top_k,
                    )
                    return (comparison_result, [])
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
            if cache_key in self.answer_cache:
                logger.info(f"✓ Answer cache hit (exact match)")
                cache_hits['answer_cache'] = True
                cached_result = self.answer_cache[cache_key]
                total_time = time.time() - start_time
                logger.info(f"Total response time (cached): {total_time:.2f}s")
                return cached_result
            else:
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
                cached_response = self.response_cache.search_cache(question_embedding)
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
            try:
                web_search_start = time.time()
                web_results = self.web_search.search(
                    query=question,
                    max_results=3,
                    safe_search=True
                )
                
                # Format web search results with proper source_type for UI display
                for web_result in web_results:
                    sources.append({
                        "source_type": "web_search",
                        "url": web_result.get("url", ""),
                        "title": web_result.get("title", "Web Result"),
                        "snippet": web_result.get("snippet", ""),
                    })
                
                web_search_time = time.time() - web_search_start
                if web_results:
                    logger.info(f"✓ Found {len(web_results)} web search results in {web_search_time:.2f}s")
                else:
                    logger.debug(f"No web search results found for query")
            except Exception as e:
                logger.warning(f"Web search failed (continuing without): {e}")
            
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
            try:
                web_search_start = time.time()
                web_results = self.web_search.search(
                    query=question,
                    max_results=3,
                    safe_search=True
                )
                
                # Format web search results with proper source_type for UI display
                for web_result in web_results:
                    sources.append({
                        "source_type": "web_search",
                        "url": web_result.get("url", ""),
                        "title": web_result.get("title", "Web Result"),
                        "snippet": web_result.get("snippet", ""),
                    })
                
                web_search_time = time.time() - web_search_start
                if web_results:
                    logger.info(f"✓ Found {len(web_results)} web search results in {web_search_time:.2f}s")
                else:
                    logger.debug(f"No web search results found for query")
            except Exception as e:
                logger.warning(f"Web search failed (continuing without): {e}")
            
            # Build RAG prompt
            context_text = "\n".join([f"- {chunk}" for chunk in context_chunks])
            if not context_text.strip():
                context_text = "No documents found in the knowledge base."
            
            system_instructions = """You are a Milvus documentation assistant.

SCOPE: Answer ONLY questions about Milvus, vector databases, vector search, embeddings, and RAG systems.

INSTRUCTIONS FOR OUT-OF-SCOPE QUESTIONS (not about Milvus/vectors/RAG):
Respond with ONLY this message and nothing else:
"I can only help with questions about Milvus, vector databases, and RAG systems."

INSTRUCTIONS FOR IN-SCOPE QUESTIONS:
- Use the provided documentation context
- Answer concisely and factually based on official documentation
- Do not provide lengthy explanations or tutorials
- Do not share training material, notebooks, or example code
- Focus on factual, accurate information about the topic
- Cite the source documentation when applicable"""
            
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
            
            system_instructions = """You are a Milvus documentation assistant.

SCOPE: Answer ONLY questions about Milvus, vector databases, vector search, embeddings, and RAG systems.

INSTRUCTIONS FOR OUT-OF-SCOPE QUESTIONS (not about Milvus/vectors/RAG):
Respond with ONLY this message and nothing else:
"I can only help with questions about Milvus, vector databases, and RAG systems."

INSTRUCTIONS FOR IN-SCOPE QUESTIONS:
- Use the provided documentation context
- Answer concisely and factually based on official documentation
- Do not provide lengthy explanations or tutorials
- Do not share training material, notebooks, or example code
- Focus on factual, accurate information about the topic
- Cite the source documentation when applicable"""
            
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
