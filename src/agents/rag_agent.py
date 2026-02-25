"""RAG Agent implementation."""

import logging
import time
from typing import List

from src.config import Settings
from src.tools import MilvusVectorDB, OllamaClient

logger = logging.getLogger(__name__)


class RAGAgent:
    """RAG (Retrieval-Augmented Generation) Agent."""

    def __init__(self, settings: Settings):
        """Initialize RAG Agent.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.ollama_client = OllamaClient(host=settings.ollama_host)
        self.vector_db = MilvusVectorDB(
            host=settings.milvus_host,
            port=settings.milvus_port,
            db_name=settings.milvus_db_name,
        )

    def retrieve_context(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
    ) -> List[str]:
        """Retrieve relevant context from vector database.

        Args:
            collection_name: Name of the collection to search
            query: User query/question
            top_k: Number of top results to retrieve

        Returns:
            List of relevant text chunks
        """
        try:
            # Generate embedding for query
            embed_start = time.time()
            query_embedding = self.ollama_client.embed_text(
                query,
                model=self.settings.ollama_embed_model,
            )
            embed_time = time.time() - embed_start
            logger.info(f"Embedding generation took {embed_time:.2f}s")

            # Search in vector database
            search_start = time.time()
            search_results = self.vector_db.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                limit=top_k,
            )
            search_time = time.time() - search_start
            logger.info(f"Vector search took {search_time:.2f}s")

            context = [result["text"] for result in search_results]
            logger.info(f"Retrieved {len(context)} context chunks (embedding: {embed_time:.2f}s, search: {search_time:.2f}s)")
            return context

        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
            raise

    def answer_question(
        self,
        collection_name: str,
        question: str,
        top_k: int = 5,
    ) -> str:
        """Answer a question using RAG approach.

        Args:
            collection_name: Name of the collection to search
            question: User question
            top_k: Number of context chunks to retrieve

        Returns:
            Generated answer
        """
        try:
            start_time = time.time()
            
            # Retrieve relevant context
            retrieval_start = time.time()
            context_chunks = self.retrieve_context(
                collection_name=collection_name,
                query=question,
                top_k=top_k,
            )
            retrieval_time = time.time() - retrieval_start
            logger.info(f"Context retrieval took {retrieval_time:.2f}s")

            # Build RAG prompt
            context_text = "\n".join(
                [f"- {chunk}" for chunk in context_chunks]
            )

            system_instructions = """You are a Milvus documentation assistant. Your ONLY purpose is to answer questions about Milvus based on the provided documentation context.

IMPORTANT RULES:
1. Only answer questions based on the provided Milvus documentation
2. If the question is not related to Milvus or cannot be answered from the context, politely decline and explain that you can only help with Milvus-related questions
3. Do not provide information from general knowledge outside of the provided context
4. If the context doesn't contain relevant information for the question, say so clearly"""

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
            )
            generation_time = time.time() - generation_start
            logger.info(f"Answer generation took {generation_time:.2f}s")
            
            total_time = time.time() - start_time
            logger.info(f"Total response time: {total_time:.2f}s (retrieval: {retrieval_time:.2f}s, generation: {generation_time:.2f}s)")

            return answer

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
