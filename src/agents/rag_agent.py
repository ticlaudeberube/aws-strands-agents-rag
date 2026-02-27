"""RAG Agent implementation."""

import logging
import time
import asyncio
from typing import List, Dict, Tuple, Optional, AsyncIterator
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from src.config import Settings
from src.tools import MilvusVectorDB, OllamaClient, MilvusResponseCache

logger = logging.getLogger(__name__)


class RAGAgent:
    """RAG (Retrieval-Augmented Generation) Agent with optimizations for latency."""

    def __init__(self, settings: Settings, cache_size: int = None):
        """Initialize RAG Agent.

        Args:
            settings: Application settings
            cache_size: Maximum number of cached items per cache type (uses settings.agent_cache_size if None)
        """
        self.settings = settings
        # Use provided cache_size or fall back to settings configuration
        self.cache_size = cache_size if cache_size is not None else settings.agent_cache_size
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
        
        # Initialize caches
        self.embedding_cache = OrderedDict()  # query -> embedding vector
        self.search_cache = OrderedDict()  # (collection, query, top_k) -> context chunks
        self.answer_cache = OrderedDict()  # (question, collection, top_k) -> answer
        
        # Thread pool for parallel operations
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Initialize persistent response cache
        try:
            self.response_cache = MilvusResponseCache(self.vector_db)
            logger.info("Response cache initialized for persistent semantic caching")
        except Exception as e:
            logger.warning(f"Failed to initialize response cache: {e}. Continuing without persistent caching.")
            self.response_cache = None
        
        logger.info(f"RAG Agent initialized with cache_size={self.cache_size}")
        logger.info(f"Using model: {self.settings.ollama_model} (optimized for latency)")


    def _add_to_cache(self, cache: OrderedDict, key, value) -> None:
        """Add item to cache with LRU eviction.

        Args:
            cache: Cache dictionary
            key: Cache key
            value: Value to cache
        """
        # Remove oldest item if cache is full
        if len(cache) >= self.cache_size:
            cache.popitem(last=False)  # Remove oldest (FIFO)
        
        cache[key] = value

    def clear_caches(self) -> None:
        """Clear all caches."""
        self.embedding_cache.clear()
        self.search_cache.clear()
        self.answer_cache.clear()
        
        # Clear persistent response cache if available
        if self.response_cache:
            try:
                self.response_cache.clear_cache()
            except Exception as e:
                logger.warning(f"Failed to clear response cache: {e}")
        
        logger.info("All caches cleared")

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text, using cache if available."""
        if text in self.embedding_cache:
            return self.embedding_cache[text]
        
        embedding = self.ollama_client.embed_text(
            text,
            model=self.settings.ollama_embed_model,
        )
        self._add_to_cache(self.embedding_cache, text, embedding)
        return embedding

    def _is_security_attack(self, question: str) -> bool:
        """Detect obvious security attacks and injection attempts without LLM.
        
        Uses pattern matching to catch common jailbreak and injection attempts.
        Fast pre-check before LLM-based scope classification.
        
        Returns True if attack detected (should be rejected), False if safe.
        """
        question_lower = question.lower()
        # Remove common contractions to match more patterns
        question_normalized = question_lower.replace("you're", "you are").replace("don't", "do not").replace("what's", "what is")
        
        # Common jailbreak patterns
        jailbreak_patterns = [
            "forget your instruction",
            "forget you are a",
            "forget you",
            "forget about",
            "ignore your instruction",
            "disregard your instruction",
            "override your",
            "bypass your",
            "ignore the system prompt",
            "ignore the previous instruction",
            "you are no longer",
            "ignore the scope",
            "ignore the limitation",
            "disregard",
            "jailbreak",
            "hack",
            "offshore account",
            "launder",
            "bypass security",
            "ignore the rule",
            "pretend you are",
            "role play as",
            "act as if you",
            "what is your hidden",
            "what is your system prompt",
            "reveal your prompt",
            "show me your instruction",
            "dump your system prompt",
            "tell me your secret",
        ]
        
        # Check for jailbreak patterns
        for pattern in jailbreak_patterns:
            if pattern in question_lower or pattern in question_normalized:
                logger.warning(f"Security attack detected: jailbreak pattern '{pattern}' in question")
                logger.debug(f"Full question: {question}")
                return True
        
        # Command injection patterns
        if any(cmd in question_lower for cmd in [
            "send money", "transfer money", "steal",
            "delete", "drop table", "sql injection",
            "fork bomb", "ddos", "malware",
        ]):
            logger.warning(f"Security attack detected: command injection pattern in question")
            logger.debug(f"Full question: {question}")
            return True
        
        return False

    def _is_question_in_scope(self, question: str) -> bool:
        """Use LLM to determine if question is about databases, search, or information retrieval.
        
        Quick classification: in-scope vs out-of-scope.
        Prevents expensive retrieval on clearly unrelated questions.
        Includes: Milvus, vector databases, vector search, embeddings, RAG, semantic search,
                  database indexing, similarity search, etc.
        """
        try:
            scope_check_prompt = """You are a question classifier. Respond with ONLY "YES" or "NO".

Is this question about any of these topics, even if it uses general phrasing:
- Milvus vector database and its features
- Vector databases, vector search, or vector indexing
- Embeddings, encoding, or vector representations
- RAG (Retrieval-Augmented Generation) systems
- Semantic search or similarity search
- Database performance, optimization, or best practices related to search/retrieval
- Database indexing, collection management, or schema design
- Information retrieval concepts and systems
- Data structures or algorithms for similarity search (HNSW, IVF, etc.)

Note: Classify as YES if the question relates to database decisions, operations, or features 
(e.g., "Should I use indexes?" is about database indexing decisions, so YES).

Question: {question}

Respond with only "YES" or "NO":"""
            
            response = self.ollama_client.generate(
                prompt=scope_check_prompt.format(question=question),
                model=self.settings.ollama_model,
                temperature=0.0,  # Deterministic for classification
                max_tokens=5,  # Just need one word
            ).strip().upper()
            
            is_in_scope = response.startswith("YES")
            logger.debug(f"Scope check: '{question[:50]}...' -> {response} (in_scope={is_in_scope})")
            return is_in_scope
            
        except Exception as e:
            logger.warning(f"Scope check failed: {e}. Proceeding with retrieval.")
            return True  # Default to in-scope on error


    def retrieve_context(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        offset: int = 0,
        filter_source: Optional[str] = None,
    ) -> Tuple[List[str], List[Dict]]:
        """Retrieve relevant context from vector database with pagination and filtering.

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

            # Parallel: Generate embedding for query (with caching)
            embed_start = time.time()
            query_embedding = self._generate_embedding(query)
            embed_time = time.time() - embed_start
            
            if query in self.embedding_cache:
                logger.info(f"✓ Embedding cache hit")
            else:
                logger.info(f"✓ Embedding generated and cached")
            logger.info(f"Embedding generation took {embed_time:.2f}s")

            # Build filter expression if source specified
            filter_expr = None
            if filter_source:
                filter_expr = f"source == '{filter_source}'"
                logger.info(f"Applying filter: {filter_expr}")

            # Search in vector database with pagination
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

            context = [result["text"] for result in search_results]
            
            # Extract source metadata - use document name if available
            sources = []
            for idx, result in enumerate(search_results, 1):
                metadata = result.get("metadata", {})
                # Try to parse metadata if it's a JSON string
                if isinstance(metadata, str):
                    try:
                        import json
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}
                
                # Build source info with document name if available
                doc_name = result.get("document_name") or metadata.get("document_name") or metadata.get("filename") or metadata.get("source")
                distance = result.get("distance", 0)
                source_info = {
                    "distance": distance,
                    "metadata": metadata,
                }
                
                # Only include text snippet if no document name is available
                if not doc_name:
                    source_info["text"] = result.get("text", "")[:150]  # First 150 chars
                else:
                    source_info["document_name"] = doc_name
                
                sources.append(source_info)
                
                # Debug logging: Show each retrieved chunk with details
                text_preview = result.get("text", "")[:80].replace('\n', ' ')
                logger.debug(f"  [{idx}] Distance: {distance:.4f} | Doc: {doc_name or 'N/A'} | Text: {text_preview}...")
            
            result_tuple = (context, sources)
            
            # Cache search results
            self._add_to_cache(self.search_cache, cache_key, result_tuple)
            
            logger.info(f"Retrieved {len(context)} context chunks (embedding: {embed_time:.2f}s, search: {search_time:.2f}s)")
            if context:
                logger.debug(f"Query: '{query[:60]}...' Retrieved from {collection_name}")
            return result_tuple

        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
            raise

    def answer_question(
        self,
        collection_name: str,
        question: str,
        top_k: int = 3,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, List[Dict]]:
        """Answer a question using RAG approach.

        Args:
            collection_name: Name of the collection to search
            question: User question
            top_k: Number of context chunks to retrieve (default: 3 for optimal latency; increase to 5-10 for better accuracy)
            temperature: LLM temperature (0.0-2.0, lower=more deterministic). Defaults to settings.
            max_tokens: Maximum tokens to generate. Defaults to settings.

        Returns:
            Tuple of (answer, sources)
        """
        try:
            start_time = time.time()
            logger.info(f"Processing question: '{question[:70]}...'")
            logger.debug(f"Parameters: collection={collection_name}, top_k={top_k}, temperature={temperature}, max_tokens={max_tokens}")
            
            # SECURITY CHECK: Detect obvious attack patterns first (no LLM overhead)
            if self._is_security_attack(question):
                logger.info(f"Question rejected: security attack detected")
                answer = "I can only help with questions about Milvus, vector databases, and RAG systems."
                sources = []
                return (answer, sources)
            
            # SCOPE CHECK: Use LLM to determine if question is about Milvus/vectors/RAG
            # This saves database queries and latency for injection attempts and unrelated questions
            if not self._is_question_in_scope(question):
                logger.info(f"Question is out-of-scope, skipping retrieval")
                logger.debug(f"Out-of-scope detection triggered for: '{question}'")
                answer = "I can only help with questions about Milvus, vector databases, and RAG systems."
                sources = []
                return (answer, sources)
            
            # Check answer cache first (exact match)
            cache_key = (question, collection_name, top_k)
            if cache_key in self.answer_cache:
                logger.info(f"✓ Answer cache hit (exact match)")
                cached_result = self.answer_cache[cache_key]
                total_time = time.time() - start_time
                logger.info(f"Total response time (cached): {total_time:.2f}s")
                logger.debug(f"Cache hit for question: '{question[:60]}...'")
                return cached_result
            
            # Generate embedding for semantic cache check (optimized helper)
            embed_start = time.time()
            question_embedding = self._generate_embedding(question)
            
            # Check if we got embedding from cache
            if question in self.embedding_cache:
                logger.info(f"✓ Embedding cache hit for response cache check")
            
            embed_time = time.time() - embed_start
            
            # Check persistent response cache (semantic similarity)
            if self.response_cache and question_embedding is not None:
                cached_response = self.response_cache.search_cache(question_embedding)
                if cached_response:
                    similarity = cached_response.get('similarity', 0)
                    logger.info(f"✓ Response cache hit (semantic match, {similarity:.1%} similar)")
                    logger.debug(f"Semantic cache matched on: {cached_response.get('question', '')[:60]}...")
                    answer = cached_response.get("response", "")
                    sources = cached_response.get("sources", [])
                    result_tuple = (answer, sources)
                    # Also cache in answer cache for faster subsequent exact matches
                    self._add_to_cache(self.answer_cache, cache_key, result_tuple)
                    total_time = time.time() - start_time
                    logger.info(f"Total response time (semantic cache): {total_time:.2f}s")
                    return result_tuple
            # Retrieve relevant context
            retrieval_start = time.time()
            context_chunks, sources = self.retrieve_context(
                collection_name=collection_name,
                query=question,
                top_k=top_k,
            )
            retrieval_time = time.time() - retrieval_start
            logger.info(f"Context retrieval took {retrieval_time:.2f}s")
            
            # Debug: Show what was retrieved
            if not context_chunks:
                logger.warning(f"⚠️  No context chunks retrieved! Collection may be empty or embedding mismatch.")
            else:
                logger.info(f"✓ Retrieved {len(context_chunks)} relevant documents")
                for i, chunk in enumerate(context_chunks, 1):
                    preview = chunk[:100].replace('\n', ' ')
                    logger.debug(f"  Chunk {i}: {preview}...")
                
                # Log sources with similarity scores
                if sources:
                    logger.debug(f"Sources and similarity scores:")
                    for i, source in enumerate(sources, 1):
                        doc_name = source.get("document_name", "Unknown")
                        distance = source.get("distance", 0)
                        similarity = 1 - distance if isinstance(distance, (int, float)) else 0
                        logger.debug(f"  [{i}] {doc_name} (similarity: {similarity:.2%})")

            # Build RAG prompt
            context_text = "\n".join(
                [f"- {chunk}" for chunk in context_chunks]
            )
            
            # Debug: Log prompt construction
            logger.debug(f"RAG Prompt Context ({len(context_text)} chars):")
            logger.debug(f"---\n{context_text[:300]}\n---")
            
            # If no context found, provide helpful message
            if not context_text.strip():
                context_text = "No documents found in the knowledge base. Please ensure documents have been loaded."

            system_instructions = """You are a Milvus documentation assistant.

SCOPE: Answer ONLY questions about Milvus, vector databases, vector search, embeddings, and RAG systems.

OUT-OF-SCOPE RESPONSE (use for ANY question not about Milvus/vectors/RAG):
Respond with ONLY this message and nothing else:
"I can only help with questions about Milvus, vector databases, and RAG systems."

IN-SCOPE RESPONSE:
- Use the provided documentation context
- Answer concisely and factually based on official documentation
- Do not provide lengthy explanations or tutorials
- Do not share training material, notebooks, or example code
- Focus on factual, accurate information about the topic
- Cite the source documentation when applicable"""

            rag_prompt = f"""{system_instructions}

Context from Milvus documentation:
{context_text}

User question: {question}

Please answer based on the provided context:"""

            # Generate answer using Ollama
            generation_start = time.time()
            # Use provided parameters or defaults from settings
            use_temperature = temperature if temperature is not None else 0.1
            use_max_tokens = max_tokens if max_tokens is not None else self.settings.max_tokens
            
            logger.debug(f"LLM Generation Params: temperature={use_temperature}, max_tokens={use_max_tokens}, model={self.settings.ollama_model}")
            
            answer = self.ollama_client.generate(
                prompt=rag_prompt,
                model=self.settings.ollama_model,
                temperature=use_temperature,
                max_tokens=use_max_tokens,
            )
            generation_time = time.time() - generation_start
            logger.info(f"Answer generation took {generation_time:.2f}s")
            logger.debug(f"Generated answer ({len(answer)} chars): {answer[:200]}...")
            
            # Cache the result with sources
            result_tuple = (answer, sources)
            self._add_to_cache(self.answer_cache, cache_key, result_tuple)
            
            # Store in persistent response cache for future semantic matches
            if self.response_cache and question_embedding is not None:
                try:
                    # IMPORTANT: Only cache valid answers, NOT rejection messages
                    # Don't cache if answer is the generic rejection message
                    if answer != "I can only help with questions about Milvus, vector databases, and RAG systems.":
                        self.response_cache.store_response(
                            question=question,
                            question_embedding=question_embedding,
                            response=answer,
                            metadata={
                                "collection": collection_name,
                                "top_k": top_k,
                                "sources": sources,
                            }
                        )
                        logger.info(f"✓ Response cached for future semantic matches")
                    else:
                        logger.info(f"Skipping cache for rejection message")
                except Exception as e:
                    logger.warning(f"Failed to cache response: {e}")
            
            total_time = time.time() - start_time
            logger.info(f"Total response time: {total_time:.2f}s (retrieval: {retrieval_time:.2f}s, generation: {generation_time:.2f}s)")

            return result_tuple

        except Exception as e:
            logger.error(f"Failed to answer question: {e}")
            raise

    def add_documents(
        self,
        collection_name: str,
        documents: List[str],
    ) -> bool:
        """Add documents to the knowledge base.

        Args:
            collection_name: Name of the collection
            documents: List of documents to add

        Returns:
            True if successful
        """
        try:
            # Ensure collection exists
            self.vector_db.create_collection(
                collection_name=collection_name,
                embedding_dim=self.settings.embedding_dim,
            )

            # Generate embeddings for documents
            embeddings = self.ollama_client.embed_texts(
                texts=documents,
                model=self.settings.ollama_embed_model,
            )

            # Insert into vector database
            self.vector_db.insert_embeddings(
                collection_name=collection_name,
                embeddings=embeddings,
                texts=documents,
                metadata=[{"source": "user_upload"} for _ in documents],
            )

            logger.info(f"Added {len(documents)} documents to {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            raise
    
    def search_by_source(
        self,
        collection_name: str,
        question: str,
        source: str = None,
        top_k: int = 5,
    ) -> Tuple[List[str], List[Dict]]:
        """Answer a question searching only a specific source.

        Args:
            collection_name: Name of the collection
            question: User question
            source: Source to filter by (e.g., 'milvus_docs')
            top_k: Number of context chunks to retrieve

        Returns:
            Tuple of (context_chunks, sources)
        """
        return self.retrieve_context(
            collection_name=collection_name,
            query=question,
            top_k=top_k,
            filter_source=source,
        )
    
    def paginated_search(
        self,
        collection_name: str,
        question: str,
        page: int = 0,
        page_size: int = 5,
    ) -> Tuple[List[str], List[Dict], int]:
        """Retrieve context with pagination support.

        Args:
            collection_name: Name of the collection
            question: User question
            page: Page number (0-indexed)
            page_size: Results per page

        Returns:
            Tuple of (context_chunks, sources, estimated_total)
        """
        offset = page * page_size
        context, sources = self.retrieve_context(
            collection_name=collection_name,
            query=question,
            top_k=page_size,
            offset=offset,
        )
        
        # Estimate total (would need separate count query for exact number)
        estimated_total = (page + 1) * page_size + 1
        
        return context, sources, estimated_total

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
            
            # Build RAG prompt
            context_text = "\n".join([f"- {chunk}" for chunk in context_chunks])
            if not context_text.strip():
                context_text = "No documents found in the knowledge base."
            
            system_instructions = """You are a Milvus documentation assistant.

SCOPE: Answer ONLY questions about Milvus, vector databases, vector search, embeddings, and RAG systems.

OUT-OF-SCOPE RESPONSE (use for ANY question not about Milvus/vectors/RAG):
Respond with ONLY this message and nothing else:
"I can only help with questions about Milvus, vector databases, and RAG systems."

IN-SCOPE RESPONSE:
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

    # =========================================================================
    # Async Methods for Non-Blocking Operations
    # =========================================================================
    
    async def answer_question_async(
        self,
        collection_name: str,
        question: str,
        top_k: int = 10,
    ) -> Tuple[str, List[Dict]]:
        """Answer a question asynchronously using RAG approach.

        Args:
            collection_name: Name of the collection to search
            question: User question
            top_k: Number of context chunks to retrieve

        Returns:
            Tuple of (answer, sources)
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(
                executor,
                self.answer_question,
                collection_name,
                question,
                top_k,
            )
    
    async def retrieve_context_async(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        offset: int = 0,
        filter_source: Optional[str] = None,
    ) -> Tuple[List[str], List[Dict]]:
        """Retrieve context asynchronously.

        Args:
            collection_name: Name of the collection to search
            query: User query/question
            top_k: Number of top results to retrieve
            offset: Number of results to skip (for pagination)
            filter_source: Optional source to filter by

        Returns:
            Tuple of (context_chunks, source_metadata)
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(
                executor,
                self.retrieve_context,
                collection_name,
                query,
                top_k,
                offset,
                filter_source,
            )
    
    async def add_documents_async(
        self,
        collection_name: str,
        documents: List[str],
    ) -> bool:
        """Add documents to the knowledge base asynchronously.

        Args:
            collection_name: Name of the collection
            documents: List of documents to add

        Returns:
            True if successful
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(
                executor,
                self.add_documents,
                collection_name,
                documents,
            )
    
    async def stream_answer(
        self,
        collection_name: str,
        question: str,
        top_k: int = 10,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
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
            
            # Retrieve context asynchronously
            context_chunks, sources = await self.retrieve_context_async(
                collection_name=collection_name,
                query=question,
                top_k=top_k,
            )
            
            # Construct RAG prompt
            context_text = "\n".join([f"- {chunk}" for chunk in context_chunks])
            
            rag_prompt = f"""You are a Milvus documentation assistant.

SCOPE: Answer ONLY questions about Milvus, vector databases, vector search, embeddings, and RAG systems.

OUT-OF-SCOPE RESPONSE (use for ANY question not about Milvus/vectors/RAG):
Respond with ONLY this message and nothing else:
"I can only help with questions about Milvus, vector databases, and RAG systems."

IN-SCOPE RESPONSE:
- Use the provided documentation context
- Answer concisely and factually based on official documentation
- Do not provide lengthy explanations or tutorials
- Do not share training material, notebooks, or example code
- Focus on factual, accurate information about the topic
- Cite the source documentation when applicable

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