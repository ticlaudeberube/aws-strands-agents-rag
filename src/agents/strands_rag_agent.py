"""Strands-based RAG Agent with proper framework integration and RAGAgent logic."""

import logging
import time
import asyncio
from typing import Optional, List, Dict, Tuple, AsyncIterator
from collections import OrderedDict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from src.config import Settings
from src.tools import MilvusVectorDB, OllamaClient, MilvusResponseCache

logger = logging.getLogger(__name__)


@dataclass
class ToolDescription:
    """Tool metadata for description."""
    name: str
    description: str


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

    def __init__(self, settings: Settings, cache_size: int = None):
        """Initialize Strands RAG Agent.
        
        Args:
            settings: Application settings from config
            cache_size: Maximum number of cached items per cache type (uses settings.agent_cache_size if None)
        """
        self.settings = settings
        self.cache_size = cache_size if cache_size is not None else settings.agent_cache_size
        
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
        
        # Initialize caching system (from RAGAgent)
        self.embedding_cache = OrderedDict()  # query -> embedding vector
        self.search_cache = OrderedDict()  # (collection, query, top_k) -> context chunks
        self.answer_cache = OrderedDict()  # (question, collection, top_k) -> answer
        
        # Initialize persistent response cache for semantic matching
        try:
            self.response_cache = MilvusResponseCache(self.vector_db)
            logger.info("Response cache initialized for persistent semantic caching")
        except Exception as e:
            logger.warning(f"Failed to initialize response cache: {e}. Continuing without persistent caching.")
            self.response_cache = None
        
        logger.info(f"StrandsRAGAgent initialized with cache_size={self.cache_size}")
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
        
        Includes: Milvus, vector databases, vector search, embeddings, RAG, semantic search,
                  database indexing, similarity search, etc.
        
        Uses keyword matching for fast, reliable scope detection.
        """
        question_lower = question.lower()
        
        # Keywords that indicate the question is in scope
        in_scope_keywords = [
            "milvus", "vector database", "vector search", "vector", "embedding",
            "rag", "retrieval", "semantic search", "similarity search", 
            "index", "collection", "database", "search", "hnsw", "ivf",
            "distance", "metric", "schema", "field", "query", "retrieval",
            "llm", "language model", "aigc", "information retrieval"
        ]
        
        # Check if any keyword is in the question
        for keyword in in_scope_keywords:
            if keyword in question_lower:
                logger.debug(f"Scope check: '{question[:50]}...' -> YES (matched '{keyword}')")
                return True
        
        # If no keywords matched, try LLM-based check as fallback
        try:
            scope_check_prompt = """You are a question classifier. Respond with ONLY "YES" or "NO".

Is this question about any of these topics:
- Vector databases or vector search
- Embeddings or semantic similarity
- RAG (Retrieval-Augmented Generation)
- Information retrieval or database indexing
- Machine learning with vector operations

Question: {question}

Respond with only "YES" or "NO":"""
            
            response = self.ollama_client.generate(
                prompt=scope_check_prompt.format(question=question),
                model=self.settings.ollama_model,
                temperature=0.0,
                max_tokens=5,
            ).strip().upper()
            
            is_in_scope = response.startswith("YES")
            logger.debug(f"LLM scope check: '{question[:50]}...' -> {response}")
            return is_in_scope
            
        except Exception as e:
            logger.warning(f"LLM scope check failed: {e}. Defaulting to True for safety.")
            return True

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
            query_embedding = self._generate_embedding(query)
            embed_time = time.time() - embed_start
            
            if query in self.embedding_cache:
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

            context = [result["text"] for result in search_results]
            
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
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate an answer using retrieved context.
        
        This tool uses the LLM to synthesize an answer based on the
        provided context and the original question. Uses Milvus-specific
        system instructions and RAG prompting.
        
        Args:
            question: The user's question
            context: Retrieved context from knowledge base
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
            
            # Build RAG prompt with Milvus system instructions
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
            
            # If no context provided, use helpful message
            if not context or not context.strip():
                context = "No documents found in the knowledge base. Please ensure documents have been loaded."
            
            rag_prompt = f"""{system_instructions}

Context from Milvus documentation:
{context}

User question: {question}

Please answer based on the provided context:"""
            
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
        collection_name: str = "default",
        top_k: int = 5,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, List[Dict]]:
        """Complete RAG pipeline: retrieve context and generate answer.
        
        This is the main entry point that orchestrates the full RAG flow with:
        - Security attack detection
        - Question scope checking
        - Multi-layer caching (embedding, search, answer, semantic)
        - Context retrieval and answer generation
        
        For direct invocation:
            answer, sources = agent.answer_question("What is Milvus?")
        
        Args:
            question: The user's question
            collection_name: Collection to search in (default: "default")
            top_k: Number of context chunks to retrieve (default: 5)
            temperature: LLM temperature (default: 0.1 for factual answers)
            max_tokens: Max tokens in response (default: from settings)
            
        Returns:
            Tuple of (answer_text, sources_list)
        """
        start_time = time.time()
        sources = []
        
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
            
            # Check answer cache first (exact match)
            cache_key = (question, collection_name, top_k)
            if cache_key in self.answer_cache:
                logger.info(f"✓ Answer cache hit (exact match)")
                cached_result = self.answer_cache[cache_key]
                total_time = time.time() - start_time
                logger.info(f"Total response time (cached): {total_time:.2f}s")
                return cached_result
            
            # Generate embedding for semantic cache check
            embed_start = time.time()
            question_embedding = self._generate_embedding(question)
            
            if question in self.embedding_cache:
                logger.info(f"✓ Embedding cache hit for response cache check")
            
            embed_time = time.time() - embed_start
            logger.debug(f"Embedding check took {embed_time:.2f}s")
            
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
            
            # Retrieve relevant context
            retrieval_start = time.time()
            context_chunks, sources = self.retrieve_context(
                collection_name=collection_name,
                query=question,
                top_k=top_k,
            )
            retrieval_time = time.time() - retrieval_start
            logger.info(f"Context retrieval took {retrieval_time:.2f}s")
            
            # Build context text for LLM
            context_text = "\n".join([f"- {chunk}" for chunk in context_chunks])
            
            logger.debug(f"RAG Prompt Context ({len(context_text)} chars)")
            
            # Generate answer using LLM
            generation_start = time.time()
            answer = self.generate_answer(
                question=question,
                context=context_text,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            generation_time = time.time() - generation_start
            logger.info(f"Answer generation took {generation_time:.2f}s")
            logger.debug(f"Generated answer: {answer[:200]}...")
            
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
                            }
                        )
                        logger.info(f"✓ Response cached for future semantic matches")
                    else:
                        logger.info(f"Skipping cache for rejection message")
                except Exception as e:
                    logger.warning(f"Failed to cache response: {e}")
            
            total_time = time.time() - start_time
            logger.info(f"Total response time: {total_time:.2f}s")
            
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
