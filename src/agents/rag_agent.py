"""RAG Agent implementation."""

import logging
import time
from typing import List, Dict, Tuple, Optional
from collections import OrderedDict

from src.config import Settings
from src.tools import MilvusVectorDB, OllamaClient

logger = logging.getLogger(__name__)


class RAGAgent:
    """RAG (Retrieval-Augmented Generation) Agent."""

    def __init__(self, settings: Settings, cache_size: int = None):
        """Initialize RAG Agent.

        Args:
            settings: Application settings
            cache_size: Maximum number of cached items per cache type (uses settings.agent_cache_size if None)
        """
        self.settings = settings
        # Use provided cache_size or fall back to settings configuration
        self.cache_size = cache_size if cache_size is not None else settings.agent_cache_size
        self.ollama_client = OllamaClient(host=settings.ollama_host)
        self.vector_db = MilvusVectorDB(
            host=settings.milvus_host,
            port=settings.milvus_port,
            db_name=settings.milvus_db_name,
        )
        
        # Initialize caches
        self.embedding_cache = OrderedDict()  # query -> embedding vector
        self.search_cache = OrderedDict()  # (collection, query, top_k) -> context chunks
        self.answer_cache = OrderedDict()  # (question, collection, top_k) -> answer
        
        logger.info(f"RAG Agent initialized with cache_size={self.cache_size}")

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
        logger.info("All caches cleared")

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

            # Generate embedding for query (with caching)
            embed_start = time.time()
            if query in self.embedding_cache:
                query_embedding = self.embedding_cache[query]
                logger.info(f"✓ Embedding cache hit")
            else:
                query_embedding = self.ollama_client.embed_text(
                    query,
                    model=self.settings.ollama_embed_model,
                )
                self._add_to_cache(self.embedding_cache, query, query_embedding)
                logger.info(f"✓ Embedding cached")
            
            embed_time = time.time() - embed_start
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
            for result in search_results:
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
                source_info = {
                    "distance": result.get("distance", 0),
                    "metadata": metadata,
                }
                
                # Only include text snippet if no document name is available
                if not doc_name:
                    source_info["text"] = result.get("text", "")[:150]  # First 150 chars
                else:
                    source_info["document_name"] = doc_name
                
                sources.append(source_info)
            
            result_tuple = (context, sources)
            
            # Cache search results
            self._add_to_cache(self.search_cache, cache_key, result_tuple)
            
            logger.info(f"Retrieved {len(context)} context chunks (embedding: {embed_time:.2f}s, search: {search_time:.2f}s)")
            return result_tuple

        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
            raise

    def answer_question(
        self,
        collection_name: str,
        question: str,
        top_k: int = 10,
    ) -> Tuple[str, List[Dict]]:
        """Answer a question using RAG approach.

        Args:
            collection_name: Name of the collection to search
            question: User question
            top_k: Number of context chunks to retrieve

        Returns:
            Tuple of (answer, sources)
        """
        try:
            start_time = time.time()
            
            # Check answer cache first
            cache_key = (question, collection_name, top_k)
            if cache_key in self.answer_cache:
                logger.info(f"✓ Answer cache hit")
                cached_result = self.answer_cache[cache_key]
                logger.info(f"Total response time (cached): {time.time() - start_time:.2f}s")
                return cached_result
            
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
                for i, chunk in enumerate(context_chunks[:2], 1):
                    preview = chunk[:100].replace('\n', ' ')
                    logger.info(f"  Document {i}: {preview}...")

            # Build RAG prompt
            context_text = "\n".join(
                [f"- {chunk}" for chunk in context_chunks]
            )
            
            # If no context found, provide helpful message
            if not context_text.strip():
                context_text = "No documents found in the knowledge base. Please ensure documents have been loaded."

            system_instructions = """You are a Milvus documentation expert. Your purpose is to answer questions about Milvus based on the provided documentation context.

GUIDELINES:
1. Use facts from the provided documentation when available
2. If the information is found in the context, answer clearly and confidently based on it
3. If the information is not covered in the provided documentation, say: "This information is not available in the loaded documentation. You may need to check the official Milvus documentation."
4. Be accurate and factual - avoid speculation
5. If multiple answers are possible, provide the most relevant one based on context

When answering, be helpful and clear."""

            rag_prompt = f"""{system_instructions}

Milvus Documentation Context:
{context_text}

Question: {question}

Answer:"""

            # Generate answer using Ollama
            generation_start = time.time()
            answer = self.ollama_client.generate(
                prompt=rag_prompt,
                model=self.settings.ollama_model,
                temperature=0.1,  # Very low for factual responses, not creative
            )
            generation_time = time.time() - generation_start
            logger.info(f"Answer generation took {generation_time:.2f}s")
            
            # Cache the result with sources
            result_tuple = (answer, sources)
            self._add_to_cache(self.answer_cache, cache_key, result_tuple)
            
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
