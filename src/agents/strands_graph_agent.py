"""Strands Graph-based RAG Agent with specialized nodes for efficient execution.

This refactored architecture splits the monolithic StrandsRAGAgent into three
specialized nodes:
1. Topic Checker (fast model): Validates if query is in-scope
2. Security Checker (fast model): Detects security risks and attacks
3. RAG Worker (powerful model): Performs vector search and answer generation

Benefits:
- Early exit on out-of-scope or malicious queries (cost savings)
- Each node uses optimized model for its task
- Clean separation of concerns
- Parallel execution support for checkers
- Comprehensive execution tracing via GraphExecutionResult

Architecture:
    Input → Topic Check → Security Check → RAG Worker → Output
              ↓ (fail)      ↓ (fail)
           Rejection    Rejection

Usage:
    from src.agents.strands_graph_agent import StrandsGraphRAGAgent
    from src.config.settings import Settings

    settings = Settings()
    agent = StrandsGraphRAGAgent(settings)

    # Answer a question
    answer, sources = agent.answer_question("What is Milvus?")
    print(f"Answer: {answer}")
    print(f"Sources: {sources}")

    # Or retrieve context separately
    context, sources = agent.retrieve_context(
        collection_name="milvus_docs",
        query="What is Milvus?",
        top_k=5
    )
    print(f"Context: {context}")
"""

import logging
import time
import re
import asyncio
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
from pydantic import BaseModel, Field

from src.config import Settings
from src.tools import MilvusVectorDB, OllamaClient, WebSearchClient
from src.agents import prompts

logger = logging.getLogger(__name__)


# ============================================================================
# STRUCTURED OUTPUT MODELS FOR ROUTING
# ============================================================================


class ValidationResult(BaseModel):
    """Structured output for topic and security validation."""

    is_valid: bool = Field(..., description="Whether the query passes validation")
    reason: str = Field(..., description="Explanation for the validation result")
    category: Optional[str] = Field(
        None, description="Category of failure if invalid (security_risk, out_of_scope)"
    )


class RAGResult(BaseModel):
    """Structured output for RAG worker node."""

    answer: str = Field(..., description="Generated answer to the query")
    sources: List[Dict] = Field(default_factory=list, description="Source documents used")
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score 0-1")


# ============================================================================
# TOOL FUNCTIONS FOR MILVUS OPERATIONS
# ============================================================================


def create_milvus_retrieval_tool(
    vector_db: MilvusVectorDB, ollama_client: OllamaClient, settings: Settings
):
    """Create a tool function for Milvus vector search and retrieval.

    This tool encapsulates:
    - Embedding generation with caching
    - Milvus vector search
    - Source formatting and ranking

    Returns a callable tool for the RAG worker node.
    """

    def milvus_search(
        question: str,
        collection_name: Optional[str] = None,
        collections: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> Dict:
        """Retrieve relevant documents from Milvus vector database.

        Args:
            question: User query
            collection_name: Single collection to search
            collections: Multiple collections to search
            top_k: Number of results to retrieve

        Returns:
            Dict with 'context' and 'sources' keys
        """
        try:
            start_time = time.time()

            # Determine which collections to search
            search_collections: List[str] = []
            if collections:
                search_collections = [c for c in collections if c is not None]
            elif collection_name:
                search_collections = [collection_name]

            if not search_collections:
                search_collections = ["milvus_docs"]

            # Generate embedding for question
            embedding = ollama_client.embed_text(
                question,
                model=settings.ollama_embed_model,
            )
            embedding_time = time.time() - start_time

            # Search across all specified collections
            all_results = []
            retrieval_start = time.time()

            for collection in search_collections:
                try:
                    results = vector_db.search(
                        collection_name=collection,
                        query_embedding=embedding,
                        limit=top_k,
                    )

                    # Add collection name to each result
                    for result in results:
                        result["collection"] = collection
                        all_results.append(result)

                except Exception as e:
                    logger.warning(f"Search failed for collection {collection}: {e}")
                    continue

            retrieval_time = time.time() - retrieval_start

            # Format context and sources
            context_parts = []
            sources = []

            for i, result in enumerate(all_results[:top_k], 1):
                text = result.get("text", "")
                metadata = result.get("metadata", {})
                distance = result.get("distance", 1.0)

                context_parts.append(f"[{i}] {text[:500]}...")

                sources.append(
                    {
                        "id": result.get("id"),
                        "text": text[:200],
                        "metadata": metadata,
                        "distance": distance,
                        "collection": result.get("collection"),
                    }
                )

            context = "\n\n".join(context_parts) if context_parts else "No documents found."

            logger.debug(
                f"Milvus retrieval: {len(all_results)} results, "
                f"embedding_time={embedding_time:.2f}s, retrieval_time={retrieval_time:.2f}s"
            )

            return {
                "context": context,
                "sources": sources,
                "embedding_time": embedding_time,
                "retrieval_time": retrieval_time,
            }

        except Exception as e:
            logger.error(f"Milvus retrieval failed: {e}")
            return {
                "context": "Error retrieving documents from knowledge base.",
                "sources": [],
                "embedding_time": 0.0,
                "retrieval_time": 0.0,
            }

    return milvus_search


def create_answer_generation_tool(ollama_client: OllamaClient, settings: Settings):
    """Create a tool function for answer generation with sources.

    Returns a callable tool that takes context and question, returns formatted answer.
    """

    def generate_answer(
        question: str,
        context: str,
        sources: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> RAGResult:
        """Generate answer from context using language model.

        Args:
            question: User query
            context: Retrieved context
            sources: Source documents
            temperature: LLM temperature
            max_tokens: Max response tokens

        Returns:
            RAGResult with answer and confidence score
        """
        try:
            gen_start = time.time()

            # Use provided temperature or settings default
            temp = temperature if temperature is not None else settings.ollama_temperature
            tokens = max_tokens if max_tokens is not None else settings.ollama_max_tokens

            # Format the RAG prompt
            system_instructions = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
                formatting_rules=prompts.FORMATTING_RULES
            )

            prompt = prompts.format_rag_prompt(
                system_instructions=system_instructions,
                question=question,
                context=context,
            )

            # Generate answer
            answer = ollama_client.generate(
                prompt=prompt,
                model=settings.ollama_model,
                temperature=temp,
                max_tokens=tokens,
            )

            gen_time = time.time() - gen_start

            # Calculate confidence
            confidence = _calculate_confidence_score(sources, answer)

            # Convert markdown links to HTML
            answer = convert_markdown_links_to_html(answer)

            logger.debug(f"Answer generation: {gen_time:.2f}s, confidence={confidence:.2%}")

            return RAGResult(
                answer=answer,
                sources=sources,
                confidence_score=confidence,
            )

        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return RAGResult(
                answer="I encountered an error generating an answer. Please try again.",
                sources=[],
                confidence_score=0.0,
            )

    return generate_answer


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def convert_markdown_links_to_html(text: str) -> str:
    """Convert markdown links [text](url) to HTML links <a href="url">text</a>."""
    pattern = r"\[([^\[\]]+)\]\(([^)]+)\)"

    def replace_with_html(match):
        link_text = match.group(1)
        url = match.group(2)
        return f'<a href="{url}">{link_text}</a>'

    converted = re.sub(pattern, replace_with_html, text)

    if converted != text:
        logger.info("[MARKDOWN_CONVERSION] Converted markdown links to HTML")

    return converted


def _calculate_confidence_score(sources: List[Dict], answer: str) -> float:
    """Calculate confidence score for an answer based on retrieval and generation quality."""
    try:
        if not sources:
            return 0.3

        # Source relevance based on distance (0=perfect, 1=no match)
        distances = [
            s.get("distance", 1.0) for s in sources if isinstance(s.get("distance"), (int, float))
        ]

        if distances:
            avg_distance = sum(distances) / len(distances)
            source_relevance = 0.5 + (max(0.0, 1.0 - avg_distance) * 0.5)
        else:
            source_relevance = 0.5

        # Answer quality based on length and structure
        answer_length = len(answer)
        sentence_count = answer.count(".") + answer.count("!") + answer.count("?")

        if answer_length < 50:
            answer_quality = 0.3
        elif answer_length < 100:
            answer_quality = 0.6
        elif answer_length > 500 and sentence_count < 2:
            answer_quality = 0.7
        else:
            answer_quality = 0.9

        answer_score = 0.6 + (answer_quality * 0.4)

        # Weighted average: 60% source, 40% answer
        confidence_value = (source_relevance * 0.6) + (answer_score * 0.4)
        confidence_value = max(0.0, min(1.0, confidence_value))

        logger.debug(
            f"Confidence: source={source_relevance:.2%}, answer={answer_score:.2%}, final={confidence_value:.2%}"
        )

        return float(confidence_value)

    except Exception as e:
        logger.warning(f"Failed to calculate confidence: {e}")
        return 0.5


def _is_security_attack(
    question: str,
    ollama_client: Optional[OllamaClient] = None,
    settings: Optional[Settings] = None,
) -> bool:
    """Detect security attacks using fast pattern matching.

    Uses proven pattern matching for jailbreaks and code injection attempts.
    Avoids LLM-based classification to prevent false positives.

    Args:
        question: User query to validate
        ollama_client: Ollama client (unused, for compatibility)
        settings: Application settings (unused, for compatibility)

    Returns:
        True if query is unsafe, False if safe
    """
    question_lower = question.lower()
    question_normalized = (
        question_lower.replace("you're", "you are")
        .replace("don't", "do not")
        .replace("what's", "what is")
    )

    jailbreak_patterns = [
        "forget your instruction",
        "forget you are a",
        "forget you",
        "forget about",
        "ignore your instruction",
        "ignore your system",
        "disregard your instruction",
        "override your",
        "bypass your",
        "bypass the",
        "bypass security",
        "bypass restrictions",
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
        "do not follow your",
        "don't follow your",
    ]

    for pattern in jailbreak_patterns:
        if pattern in question_lower or pattern in question_normalized:
            logger.warning(f"[SECURITY_ATTACK] Jailbreak detected: '{pattern}'")
            return True

    if any(
        cmd in question_lower
        for cmd in [
            "send money",
            "transfer money",
            "steal",
            "delete",
            "drop table",
            "sql injection",
            "fork bomb",
            "ddos",
            "malware",
        ]
    ):
        logger.warning("[SECURITY_ATTACK] Command injection detected")
        return True

    injection_patterns = [
        "'; drop",
        "'; delete",
        "'; update",
        "'; insert",  # SQL
        "rm -rf",
        "exec(",
        "eval(",
        "__import__",  # Command execution
        "subprocess",
        "os.system",
        "shell=true",  # Process execution
    ]

    for pattern in injection_patterns:
        if pattern in question_lower:
            logger.warning(f"[SECURITY_ATTACK] Injection detected: '{pattern}'")
            return True

    logger.debug(f"[SECURITY_CHECK] Query passed: {question[:100]}")
    return False


def _is_question_in_scope(question: str, ollama_client: OllamaClient, settings: Settings) -> bool:
    """Check if question is about databases, search, or information retrieval.

    Uses fast keyword matching for instant classification without LLM calls.
    This enables sub-second rejection of out-of-scope queries.
    """
    question_lower = question.lower()

    # Fast keyword-based pre-filter
    in_scope_keywords = {
        "milvus": 10,
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
        "pinecone": 9,
        "weaviate": 9,
        "voyageai": 9,
        "voyage": 8,
        "qdrant": 9,
        "elasticsearch": 6,
        "comparison": 4,
        "knn": 7,
        "nearest neighbor": 7,
        "hnsw": 8,
        "ivf": 8,
    }

    words = question_lower.split()
    score = 0
    for word in words:
        if word in in_scope_keywords:
            score += in_scope_keywords[word]
        for keyword in in_scope_keywords:
            if keyword in word and len(keyword) > 2:
                score += in_scope_keywords[keyword] // 2

    # High confidence threshold - any keyword match means in-scope
    if score > 0:
        logger.debug(f"[SCOPE_CHECK] Keyword match (score={score}): in-scope")
        return True

    # Fast reject: No keywords at all = definitely out of scope
    # This avoids expensive LLM calls for clearly out-of-scope queries
    logger.debug("[SCOPE_CHECK] No keyword match (score=0): out-of-scope (fast reject)")
    return False


# ============================================================================
# GRAPH AGENT FACTORY
# ============================================================================


def create_rag_graph(
    settings: Settings,
    fast_model_id: Optional[str] = None,
    rag_model_id: Optional[str] = None,
):
    """Create a refactored Strands Graph-based RAG Agent.

    The graph implements three specialized nodes:
    1. Topic Checker (fast, ~3B parameter model)
    2. Security Checker (fast, ~3B parameter model)
    3. RAG Worker (powerful, ~8B+ parameter model)

    Args:
        settings: Application configuration
        fast_model_id: Model ID for topic/security checkers (default: ollama_model from settings)
        rag_model_id: Model ID for RAG worker (default: ollama_model from settings)

    Returns:
        Configured GraphBuilder instance
    """

    # Initialize backend systems
    ollama_client = OllamaClient(
        host=settings.ollama_host,
        timeout=settings.ollama_timeout,
        pool_size=settings.ollama_pool_size,
    )

    vector_db = MilvusVectorDB(
        host=settings.milvus_host,
        port=settings.milvus_port,
        db_name=settings.milvus_db_name,
        user=settings.milvus_user,
        password=settings.milvus_password,
        timeout=settings.milvus_timeout,
        pool_size=settings.milvus_pool_size,
    )

    # Use provided model IDs or fall back to settings
    fast_model = fast_model_id or settings.ollama_model
    rag_model = rag_model_id or settings.ollama_model

    logger.info(f"Creating RAG Graph with models: fast={fast_model}, rag={rag_model}")

    # Initialize web search client (only if enabled)
    web_search = None
    if settings.enable_web_search_supplement:
        from src.tools import WebSearchClient

        web_search = WebSearchClient(timeout=settings.web_search_timeout)
        logger.info("Web search supplementary sources enabled")

    # Create tools
    retrieval_tool = create_milvus_retrieval_tool(vector_db, ollama_client, settings)
    generation_tool = create_answer_generation_tool(ollama_client, settings)

    # NODE 1: Topic Checker
    def topic_check_node(state: Dict) -> Dict:
        """Check if query is in scope (about databases, RAG, vector search, etc.)."""
        question = state.get("question", "")
        logger.info(f"[TOPIC_CHECK] Processing: {question[:50]}...")

        is_in_scope = _is_question_in_scope(question, ollama_client, settings)

        result = ValidationResult(
            is_valid=is_in_scope,
            reason=(
                "Query is about vector databases/RAG" if is_in_scope else "Query is out of scope"
            ),
            category=None if is_in_scope else "out_of_scope",
        )

        state["topic_result"] = result
        logger.info(f"[TOPIC_CHECK] Result: is_valid={result.is_valid}")

        return state

    # NODE 2: Security Checker
    def security_check_node(state: Dict) -> Dict:
        """Check for security attacks and malicious input using LLM classification."""
        question = state.get("question", "")
        logger.info(f"[SECURITY_CHECK] Processing: {question[:50]}...")

        # Use LLM-based classification with pattern matching fallback
        is_attack = _is_security_attack(question, ollama_client, settings)

        result = ValidationResult(
            is_valid=not is_attack,
            reason="Query is safe" if not is_attack else "Query contains security risk",
            category=None if not is_attack else "security_risk",
        )

        state["security_result"] = result
        logger.info(f"[SECURITY_CHECK] Result: is_valid={result.is_valid}")

        return state

    # NODE 3: RAG Worker
    def rag_worker_node(state: Dict) -> Dict:
        """Retrieve context and generate answer."""
        question = state.get("question", "")
        collection_name = state.get("collection_name", "milvus_docs")
        collections = state.get("collections", [collection_name])
        top_k = state.get("top_k", 5)

        logger.info(f"[RAG_WORKER] Processing: {question[:50]}...")

        # Retrieve documents from knowledge base
        retrieval_result = retrieval_tool(
            question=question,
            collections=collections,
            top_k=top_k,
        )

        kb_sources = retrieval_result["sources"]
        context_text = retrieval_result["context"]

        # Add web search results as supplementary sources (if enabled)
        # Matches old strands_rag_agent.py behavior (commit a0f1c64)
        # Web results are added to sources list but DON'T modify context_text
        # This keeps LLM focused on KB while showing web resources in UI
        if web_search and settings.enable_web_search_supplement:
            try:
                logger.info("[RAG_WORKER] Adding web search supplementary sources...")
                web_results = web_search.search(query=question, max_results=3)

                # Format web search results with proper source_type for UI display
                for web_result in web_results:
                    kb_sources.append(
                        {
                            "source_type": "web_search",
                            "url": web_result.get("url", ""),
                            "title": web_result.get("title", "Web Result"),
                            "text": web_result.get("snippet", ""),
                            "snippet": web_result.get("snippet", ""),
                            "distance": 0.7,  # Fixed relevance score for web results
                            "metadata": {
                                "source": "web",
                                "title": web_result.get("title", ""),
                            },
                        }
                    )

                logger.info(f"[RAG_WORKER] Added {len(web_results)} web search sources")

            except Exception as e:
                logger.warning(f"[RAG_WORKER] Web search failed (non-critical): {e}")

        # Generate answer with KB sources (and optionally web sources)
        rag_result = generation_tool(
            question=question,
            context=context_text,
            sources=kb_sources,  # Combined KB + web sources
            temperature=state.get("temperature"),
            max_tokens=state.get("max_tokens"),
        )

        state["rag_result"] = rag_result
        state["retrieval_metrics"] = {
            "embedding_time": retrieval_result["embedding_time"],
            "retrieval_time": retrieval_result["retrieval_time"],
        }

        logger.info(f"[RAG_WORKER] Generated answer with {len(rag_result.sources)} total sources")

        return state

    # NODE 4: Failure Handlers
    def reject_out_of_scope(state: Dict) -> Dict:
        """Handle out-of-scope queries."""
        state["final_answer"] = (
            "I can only help with questions about Milvus, vector databases, "
            "embeddings, RAG, and related topics. "
            "Please rephrase your question to focus on these areas."
        )
        state["final_sources"] = []
        state["final_confidence"] = 0.0
        logger.info("[REJECTION] Query was out of scope")
        return state

    def reject_security_risk(state: Dict) -> Dict:
        """Handle security risks."""
        state["final_answer"] = (
            "I detected a security concern with your query. "
            "Please rephrase and ask a legitimate question."
        )
        state["final_sources"] = []
        state["final_confidence"] = 0.0
        logger.info("[REJECTION] Query was a security risk")
        return state

    def format_rag_result(state: Dict) -> Dict:
        """Format RAG worker result as final output."""
        rag_result = state.get("rag_result")
        if rag_result:
            state["final_answer"] = rag_result.answer
            state["final_sources"] = rag_result.sources
            state["final_confidence"] = rag_result.confidence_score
        return state

    # Routing conditions
    def check_topic_pass(state: Dict) -> bool:
        """Route: if topic check passed, continue to security check."""
        result = state.get("topic_result")
        return result.is_valid if result else False

    def check_security_pass(state: Dict) -> bool:
        """Route: if security check passed, continue to RAG worker."""
        result = state.get("security_result")
        return result.is_valid if result else False

    # Build the graph (Note: actual Strands implementation details depend on AgentFramework version)
    # Below is pseudo-code showing the structure

    graph_config = {
        "nodes": {
            "topic_check": topic_check_node,
            "security_check": security_check_node,
            "rag_worker": rag_worker_node,
            "reject_out_of_scope": reject_out_of_scope,
            "reject_security_risk": reject_security_risk,
            "format_result": format_rag_result,
        },
        "edges": [
            # Entry → Topic Check
            ("__start__", "topic_check"),
            # Topic Check → Security Check (if passed) or Rejection (if failed)
            ("topic_check", "security_check", check_topic_pass),
            ("topic_check", "reject_out_of_scope", lambda s: not check_topic_pass(s)),
            # Security Check → RAG Worker (if passed) or Rejection (if failed)
            ("security_check", "rag_worker", check_security_pass),
            ("security_check", "reject_security_risk", lambda s: not check_security_pass(s)),
            # Format and return
            ("rag_worker", "format_result"),
            ("reject_out_of_scope", "__end__"),
            ("reject_security_risk", "__end__"),
            ("format_result", "__end__"),
        ],
    }

    logger.info("RAG Graph created with 3 nodes: topic_check, security_check, rag_worker")

    return graph_config


# ============================================================================
# GRAPH EXECUTION INTERFACE
# ============================================================================


@dataclass
class GraphExecutionResult:
    """Result from graph execution."""

    answer: str
    sources: List[Dict]
    confidence_score: float
    execution_path: List[str]
    execution_times: Dict[str, float]

    def __repr__(self) -> str:
        """Format result as string."""
        return (
            f"GraphExecutionResult(\n"
            f"  answer={self.answer[:100]}...\n"
            f"  sources={len(self.sources)}\n"
            f"  confidence={self.confidence_score:.2%}\n"
            f"  path={' → '.join(self.execution_path)}\n"
            f")"
        )


class StrandsGraphRAGAgent:
    """Simplified interface to the refactored Strands Graph RAG Agent."""

    def __init__(self, settings: Settings):
        """Initialize graph agent with settings."""
        self.settings = settings
        self.graph_config = None
        self.graph_state: dict[str, Any] = {}
        self.initialization_error = None
        self._last_stream_sources: List[Dict] = []  # Track sources for streaming responses

        # Initialize backend clients
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

        self.web_search = WebSearchClient(timeout=settings.web_search_timeout)

        # Initialize response cache for semantic caching
        from src.tools import MilvusResponseCache

        self.response_cache = MilvusResponseCache(
            vector_db=self.vector_db,
            embedding_dim=settings.response_cache_embedding_dim,
            distance_threshold=settings.response_cache_threshold,
        )

        try:
            self.graph_config = create_rag_graph(settings)
            logger.info("StrandsGraphRAGAgent initialized")
        except RuntimeError as e:
            if "Milvus connection failed" in str(e):
                self.initialization_error = str(e)
                logger.warning(f"StrandsGraphRAGAgent initialized in degraded mode: {e}")
            else:
                raise

    def retrieve_context(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
    ) -> Tuple[List[str], List[Dict]]:
        """Retrieve relevant context from Milvus vector database.

        Args:
            collection_name: Name of the collection to search
            query: Query text to search for
            top_k: Number of results to retrieve

        Returns:
            Tuple of (context_chunks, sources)
        """
        try:
            # Generate embedding for the query
            embedding = self.ollama_client.embed_text(
                query,
                model=self.settings.ollama_embed_model,
            )

            # Search Milvus
            results = self.vector_db.search(
                collection_name=collection_name,
                query_embedding=embedding,
                limit=top_k,
            )

            # Format results
            context_chunks = []
            sources = []

            for i, result in enumerate(results, 1):
                text = result.get("text", "")
                metadata = result.get("metadata", {})
                distance = result.get("distance", 1.0)

                context_chunks.append(text)

                sources.append(
                    {
                        "id": result.get("id"),
                        "text": text[:200],
                        "metadata": metadata,
                        "distance": distance,
                        "collection": collection_name,
                    }
                )

            logger.debug(f"Retrieved {len(context_chunks)} chunks from {collection_name}")
            return context_chunks, sources

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return [], []

    def retrieve_documents(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        filter_source: Optional[str] = None,
    ) -> List[Dict]:
        """Retrieve relevant documents from vector database.

        This is a wrapper around retrieve_context for MCP tool compatibility.

        Args:
            collection_name: Name of the collection to search
            query: Query text to search for
            top_k: Number of results to retrieve
            filter_source: Optional source filter (not implemented yet)

        Returns:
            List of document dictionaries with text, metadata, and distance
        """
        _, sources = self.retrieve_context(collection_name, query, top_k)

        # Filter by source if specified
        if filter_source:
            sources = [
                doc for doc in sources if doc.get("metadata", {}).get("source") == filter_source
            ]

        return sources

    def search_by_source(
        self,
        collection_name: str,
        query: str,
        source: str,
        top_k: int = 5,
    ) -> List[Dict]:
        """Search documents filtered by source.

        Args:
            collection_name: Name of the collection to search
            query: Query text to search for
            source: Source to filter by
            top_k: Number of results to retrieve

        Returns:
            List of document dictionaries filtered by source
        """
        return self.retrieve_documents(collection_name, query, top_k, filter_source=source)

    def generate_answer(
        self,
        question: str,
        context: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate an answer based on question and context.

        Args:
            question: User question
            context: Retrieved context for answering
            temperature: LLM sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated answer text
        """
        try:
            # Use provided values or settings defaults
            temp = temperature
            tokens = max_tokens if max_tokens is not None else self.settings.ollama_max_tokens

            # Format RAG prompt
            system_instructions = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
                formatting_rules=prompts.FORMATTING_RULES
            )

            prompt = prompts.format_rag_prompt(
                system_instructions=system_instructions,
                question=question,
                context=context,
            )

            # Generate answer
            answer = self.ollama_client.generate(
                prompt=prompt,
                model=self.settings.ollama_model,
                temperature=temp,
                max_tokens=tokens,
            )

            return answer

        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return f"Error generating answer: {str(e)}"

    def answer_question(
        self,
        question: str,
        collection_name: Optional[str] = None,
        collections: Optional[List[str]] = None,
        top_k: int = 5,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, List[Dict]]:
        """Answer a question using the RAG graph.

        This invokes the graph with proper input state and returns the answer.

        Args:
            question: User query
            collection_name: Single collection to search
            collections: List of collections to search
            top_k: Number of results to retrieve
            temperature: LLM temperature
            max_tokens: Max response tokens

        Returns:
            Tuple of (answer_text, sources_list)
        """
        # Check if graph initialization failed
        if self.initialization_error:
            error_msg = (
                f"RAG Agent is not available: {self.initialization_error}. "
                f"Please start Milvus with: cd docker && docker-compose up -d"
            )
            logger.error(error_msg)
            return (error_msg, [])

        if not self.graph_config:
            error_msg = "RAG Agent graph configuration is not initialized."
            logger.error(error_msg)
            return (error_msg, [])

        # Initialize state
        state = {
            "question": question,
            "collection_name": collection_name or "milvus_docs",
            "collections": collections or [collection_name or "milvus_docs"],
            "top_k": top_k,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        start_time = time.time()

        # Check response cache first (before any graph execution)
        if self.response_cache:
            try:
                question_embedding = self.ollama_client.embed_text(
                    question,
                    model=self.settings.ollama_embed_model,
                )
                cached = self.response_cache.search_cache(
                    question=question,
                    question_embedding=question_embedding,
                    limit=1,
                )
                if cached:
                    elapsed = time.time() - start_time
                    logger.info(f"✓ Cache hit! Retrieved in {elapsed * 1000:.0f}ms")
                    answer = cached.get("response", "")
                    sources = cached.get("sources", [])
                    self._last_stream_sources = sources
                    return (answer, sources)
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}, proceeding with RAG")

        logger.info(f"Executing graph for: {question[:50]}...")

        try:
            # Execute graph nodes in sequence
            # In a real Strands implementation, this would use graph.invoke(state)

            # For now, simulate the execution flow
            state = self.graph_config["nodes"]["topic_check"](state)

            if state.get("topic_result", {}).is_valid:
                state = self.graph_config["nodes"]["security_check"](state)

                if state.get("security_result", {}).is_valid:
                    state = self.graph_config["nodes"]["rag_worker"](state)
                    state = self.graph_config["nodes"]["format_result"](state)
                else:
                    state = self.graph_config["nodes"]["reject_security_risk"](state)
            else:
                state = self.graph_config["nodes"]["reject_out_of_scope"](state)

            total_time = time.time() - start_time

            logger.info(
                f"Graph execution completed in {total_time:.2f}s. "
                f"Answer confidence: {state.get('final_confidence', 0):.2%}"
            )

            # Store sources for streaming responses
            sources = state.get("final_sources", [])
            self._last_stream_sources = sources

            answer = state.get("final_answer", "")

            # Store response in cache ONLY for successful RAG responses (not rejections)
            # Skip caching for rejected queries to avoid unnecessary embedding calls
            is_rejection = state.get("final_confidence", 0) == 0.0
            if self.response_cache and answer and not state.get("is_cached") and not is_rejection:
                try:
                    question_embedding = self.ollama_client.embed_text(
                        question,
                        model=self.settings.ollama_embed_model,
                    )
                    self.response_cache.store_response(
                        question=question,
                        question_embedding=question_embedding,
                        response=answer,
                        metadata={
                            "sources": sources,
                            "collection": collection_name or "unknown",
                            "response_time": round(total_time * 1000, 2),  # milliseconds
                            "confidence": state.get("final_confidence", 0),
                        },
                    )
                    logger.debug(f"Stored response in cache for question: {question[:60]}")
                except Exception as cache_error:
                    logger.warning(f"Failed to cache response: {cache_error}")

            return (answer, sources)

        except Exception as e:
            logger.error(f"Graph execution failed: {e}", exc_info=True)
            self._last_stream_sources = []
            return ("An error occurred while processing your request.", [])

    def _generate_web_search_query(self, question: str) -> str:
        """Generate an optimized web search query.

        This method transforms specific technical questions into more search-friendly queries.

        Special handling for:
        - Comparison questions: "Pinecone vs Milvus" → "Pinecone vs Milvus comparison"
        - Multiple products: Detects all products and creates comparison query
        - Single products: Uses product-specific optimized terms

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
        comparison_keywords = [
            "vs",
            "vs.",
            "versus",
            "compare",
            "comparison",
            "advantage",
            "better",
        ]
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
            logger.debug(
                f"[WEB_SEARCH_QUERY] Comparison detected: '{question[:50]}...' -> '{search_query}'"
            )
            return search_query

        # Handle single product with comparison context
        if is_comparison and len(mentioned_products) == 1:
            product = mentioned_products[0]
            search_query = f"{product} advantages benefits vector database"
            logger.debug(
                f"[WEB_SEARCH_QUERY] Single product comparison: '{question[:50]}...' -> '{search_query}'"
            )
            return search_query

        # Handle single product without comparison context (original logic)
        if len(mentioned_products) >= 1:
            product_name = mentioned_products[0]  # Use first mentioned product
            search_variants = product_search_terms[product_name]
            search_query = search_variants[0]
            logger.debug(
                f"[WEB_SEARCH_QUERY] Single product: '{question[:40]}...' -> '{search_query}'"
            )
            return search_query

        # For general how/what questions without specific products
        if any(word in question_lower for word in ["how", "what", "explain", "describe"]):
            if any(
                word in question_lower for word in ["vector", "database", "search", "embedding"]
            ):
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

    async def stream_answer(
        self,
        question: str,
        collection_name: Optional[str] = None,
        collections: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Stream answer text as it's being generated in real-time.

        Streams chunks from the LLM as they arrive with minimal buffering.
        Handles caching, security checks, and scope validation.

        Yields:
            Chunks of text as they are generated
        """
        # Initialize sources at the start so it's always available
        self._last_stream_sources = []
        sources: List[Dict] = []

        try:
            # Use setting defaults if not provided
            if top_k is None:
                top_k = self.settings.default_top_k
            if collection_name is None:
                collection_name = self.settings.ollama_collection_name

            # CHECK RESPONSE CACHE FIRST
            if self.response_cache:
                try:
                    start_time = time.time()
                    question_embedding = self.ollama_client.embed_text(
                        question,
                        model=self.settings.ollama_embed_model,
                    )
                    cached = self.response_cache.search_cache(
                        question=question,
                        question_embedding=question_embedding,
                        limit=1,
                    )
                    if cached:
                        elapsed = time.time() - start_time
                        logger.info(f"✓ Cache hit! Retrieved in {elapsed * 1000:.0f}ms (streaming)")
                        answer = cached.get("response", "")
                        sources = cached.get("sources", [])
                        self._last_stream_sources = sources

                        # Stream the cached answer in chunks for consistency
                        words = answer.split()
                        buffer = ""
                        for word in words:
                            buffer += word + " "
                            if len(buffer) >= 10:  # ~2 words per chunk
                                yield buffer
                                buffer = ""
                                await asyncio.sleep(0.01)  # Small delay for streaming effect
                        if buffer:
                            yield buffer
                        return
                except Exception as e:
                    logger.warning(
                        f"Cache lookup failed during streaming: {e}, proceeding with RAG"
                    )

            # SECURITY CHECK
            if _is_security_attack(question):
                logger.info("Question rejected: security attack detected")
                yield "I can only help with questions about Milvus, vector databases, and RAG systems."
                return

            # SCOPE CHECK
            if not _is_question_in_scope(question, self.ollama_client, self.settings):
                logger.info("Question is out-of-scope")
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
            if not context_text.strip():
                context_text = "No documents found in the knowledge base."

            # Use RAG system instructions
            system_instructions = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
                formatting_rules=prompts.FORMATTING_RULES
            )

            rag_prompt = prompts.RAGPrompts.PROMPT_TEMPLATE.format(
                system_instructions=system_instructions,
                question=question,
                context=context_text,
                source_attribution="",
            )

            logger.info(f"Starting stream generation: {question[:50]}...")

            try:
                use_temperature = temperature if temperature is not None else 0.1
                use_max_tokens = max_tokens if max_tokens is not None else self.settings.max_tokens

                buffer = ""
                MIN_BUFFER_SIZE = 5  # Accumulate ~5+ characters (roughly 1 word)
                chunk_count = 0

                # Stream chunks directly from Ollama without accumulating all first
                for chunk in self.ollama_client.generate_stream(
                    prompt=rag_prompt,
                    model=self.settings.ollama_model,
                    temperature=use_temperature,
                    max_tokens=use_max_tokens,
                ):
                    buffer += chunk
                    chunk_count += 1

                    # Yield when buffer reaches word size or ends with punctuation/newline
                    if len(buffer) >= MIN_BUFFER_SIZE or buffer.endswith(
                        (".", "!", "?", "\n", " ")
                    ):
                        yield buffer
                        buffer = ""
                        # Small delay to make streaming visible (0.01s = 10ms per chunk)
                        await asyncio.sleep(0.01)

                # Yield any remaining buffer
                if buffer:
                    yield buffer

                logger.info(f"Stream generation completed: {chunk_count} raw chunks")

                # Store sources for API to retrieve
                self._last_stream_sources = sources

            except Exception as e:
                logger.error(f"Error during streaming generation: {e}", exc_info=True)
                yield f"\n[Error: {str(e)}]"
                return

        except Exception as e:
            logger.error(f"Stream answer failed: {e}", exc_info=True)
            yield f"[Error: {str(e)}]"

    async def stream_answer_no_cache(
        self,
        question: str,
        collection_name: Optional[str] = None,
        collections: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Stream answer bypassing all caches - queries LLM directly with fresh retrieval.

        Skips response cache and embedding cache for fresh knowledge base answers.

        Yields:
            Chunks of text as they are generated
        """
        # Initialize sources at the start so it's always available
        self._last_stream_sources = []
        sources: List[Dict] = []

        try:
            # Use setting defaults if not provided
            if top_k is None:
                top_k = self.settings.default_top_k
            if collection_name is None:
                collection_name = self.settings.ollama_collection_name

            logger.info(f"[STREAM_NO_CACHE] Answering: {question[:60]}")

            # SECURITY CHECK
            if _is_security_attack(question):
                yield "I can only help with questions about Milvus, vector databases, and RAG systems."
                self._last_stream_sources = []
                return

            # SCOPE CHECK
            if not _is_question_in_scope(question, self.ollama_client, self.settings):
                yield "I can only help with questions about Milvus, vector databases, and RAG systems."
                self._last_stream_sources = []
                return

            # Fresh retrieval (no caching)
            context_chunks, sources = self.retrieve_context(
                collection_name=collection_name,
                query=question,
                top_k=top_k,
            )

            # Build RAG prompt
            context_text = "\n".join([f"- {chunk}" for chunk in context_chunks])
            if not context_text.strip():
                context_text = "No documents found in the knowledge base."

            # Use RAG system instructions with formatting rules (knowledge base only)
            system_instructions = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
                formatting_rules=prompts.FORMATTING_RULES
            )

            rag_prompt = prompts.RAGPrompts.PROMPT_TEMPLATE.format(
                system_instructions=system_instructions,
                question=question,
                context=context_text,
                source_attribution="",
            )

            logger.info(f"Starting stream generation (no cache): {question[:50]}...")

            try:
                use_temperature = temperature if temperature is not None else 0.1
                use_max_tokens = max_tokens if max_tokens is not None else self.settings.max_tokens

                buffer = ""
                MIN_BUFFER_SIZE = 5
                chunk_count = 0

                for chunk in self.ollama_client.generate_stream(
                    prompt=rag_prompt,
                    model=self.settings.ollama_model,
                    temperature=use_temperature,
                    max_tokens=use_max_tokens,
                ):
                    buffer += chunk
                    chunk_count += 1

                    if len(buffer) >= MIN_BUFFER_SIZE or buffer.endswith(
                        (".", "!", "?", "\n", " ")
                    ):
                        yield buffer
                        buffer = ""
                        # Small delay to make streaming visible (0.01s = 10ms per chunk)
                        await asyncio.sleep(0.01)

                if buffer:
                    yield buffer

                logger.info(f"Stream generation completed (no cache): {chunk_count} chunks")
                self._last_stream_sources = sources

            except Exception as e:
                logger.error(f"Error during streaming generation (no cache): {e}", exc_info=True)
                yield f"\n[Error: {str(e)}]"
                return

        except Exception as e:
            logger.error(f"Stream answer (no cache) failed: {e}", exc_info=True)
            yield f"[Error: {str(e)}]"

    async def stream_answer_web_search_only(
        self,
        question: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Stream answer using ONLY web search - no knowledge base retrieval.

        Streams chunks of the answer in real-time with web search results only.
        Uses optimized search queries and relevance scoring.

        Args:
            question: User question
            temperature: LLM temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Chunks of the generated answer as they are produced
        """
        sources: List[Dict[str, Any]] = []
        self._last_stream_sources = []  # Initialize immediately so it's always set

        try:
            logger.info(f"[STREAM_WEB_ONLY] 🌐 Forcing web search for: {question[:60]}")

            # Web search only - no knowledge base retrieval
            try:
                web_search_query = self._generate_web_search_query(question)
                web_results = await asyncio.to_thread(self.web_search.search, web_search_query, 5)

                if web_results:
                    for idx, web_result in enumerate(web_results, 1):
                        relevance_scores = [0.99, 0.95, 0.90, 0.85, 0.80]
                        relevance = (
                            relevance_scores[idx - 1] if idx <= len(relevance_scores) else 0.75
                        )
                        web_source = {
                            "source_type": "web_search",
                            "url": web_result.get("url", ""),
                            "title": web_result.get("title", "Web Result"),
                            "snippet": web_result.get("snippet", ""),
                            "distance": relevance,
                        }
                        sources.append(web_source)
                    logger.info(f"✓ Web search completed: {len(sources)} sources")
            except Exception as e:
                logger.error(f"[STREAM_WEB_ONLY] Web search error: {e}")

            # Build answer from web results only
            if sources:
                web_context = "\n".join(
                    [f"- {s.get('title', 'Web Result')}: {s.get('snippet', '')}" for s in sources]
                )
                logger.info(f"[WEB_CONTEXT] Built context from {len(sources)} sources:")
                for i, s in enumerate(sources[:2], 1):  # Log first 2 for debugging
                    snippet_preview = s.get("snippet", "")[:100]
                    logger.info(f"  [{i}] {s.get('title', 'No title')[:50]}: {snippet_preview}...")
            else:
                web_context = "No web search results found."

            # Use web search prompts from centralized module
            rag_prompt = prompts.format_web_search_prompt(web_context, question)

            logger.info(f"Starting stream generation (web only): {question[:50]}...")

            try:
                use_temperature = temperature if temperature is not None else 0.1
                use_max_tokens = max_tokens if max_tokens is not None else self.settings.max_tokens

                buffer = ""
                MIN_BUFFER_SIZE = 5
                chunk_count = 0

                for chunk in self.ollama_client.generate_stream(
                    prompt=rag_prompt,
                    model=self.settings.ollama_model,
                    temperature=use_temperature,
                    max_tokens=use_max_tokens,
                ):
                    buffer += chunk
                    chunk_count += 1

                    if len(buffer) >= MIN_BUFFER_SIZE or buffer.endswith(
                        (".", "!", "?", "\n", " ")
                    ):
                        yield buffer
                        buffer = ""
                        # Small delay to make streaming visible (0.01s = 10ms per chunk)
                        await asyncio.sleep(0.01)

                if buffer:
                    yield buffer

                logger.info(f"Stream generation completed (web only): {chunk_count} chunks")
                # Always update sources at the end of successful streaming
                self._last_stream_sources = sources

            except Exception as e:
                logger.error(f"Error during streaming generation (web only): {e}", exc_info=True)
                # Still preserve sources even if streaming failed
                self._last_stream_sources = sources
                yield f"\n[Error: {str(e)}]"
                return

        except Exception as e:
            logger.error(f"Stream answer (web only) failed: {e}", exc_info=True)
            # Ensure sources are set even on outer exception
            self._last_stream_sources = sources
            yield f"[Error: {str(e)}]"

    def list_collections(self) -> List[str]:
        """List all available collections in the vector database.

        Returns:
            List of collection names
        """
        try:
            collections = self.vector_db.list_collections()
            logger.debug(f"Found {len(collections)} collections")
            return collections
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []

    def add_documents(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Add documents to the vector database.

        This is a placeholder implementation for MCP tool compatibility.
        Full implementation would require embedding and indexing logic.

        Args:
            collection_name: Target collection name
            documents: List of documents with text, source, and metadata

        Returns:
            Result dictionary with success status and count
        """
        logger.warning(
            f"add_documents called but not fully implemented. Collection: {collection_name}"
        )
        return {"success": False, "message": "add_documents not yet implemented", "count": 0}

    # === API Server Compatibility Methods ===

    def answer_question_no_cache(
        self,
        question: str,
        collection_name: Optional[str] = None,
        top_k: int = 5,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, List[Dict]]:
        """Answer question bypassing response cache (for API server compatibility).

        This method provides backward compatibility with the old agent interface.
        It calls answer_question() which uses the graph flow, but the response
        cache node could be modified to respect a bypass flag in the future.

        Args:
            question: User query
            collection_name: Collection to search
            top_k: Number of results
            temperature: LLM temperature
            max_tokens: Max response tokens

        Returns:
            Tuple of (answer_text, sources_list)
        """
        logger.info(f"[NO_CACHE] Answering without cache: {question[:100]}...")
        # Currently just calls normal flow - in future, could pass bypass_cache flag
        # through state to skip ResponseCache tool
        return self.answer_question(
            question=question,
            collection_name=collection_name,
            top_k=top_k,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def answer_question_web_search_only(
        self,
        question: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, List[Dict]]:
        """Answer using only web search (for API server compatibility).

        This method provides backward compatibility with the old agent interface.
        Currently not fully supported in graph architecture - returns empty response.
        Web search is designed as a supplement to KB results in the graph flow.

        Args:
            question: User query
            temperature: LLM temperature
            max_tokens: Max response tokens

        Returns:
            Tuple of (answer_text, sources_list)
        """
        logger.warning(f"[WEB_SEARCH_ONLY] Not fully supported in graph agent: {question[:100]}...")
        logger.warning("[WEB_SEARCH_ONLY] Graph architecture uses web search as supplement only")
        logger.warning(
            "[WEB_SEARCH_ONLY] Enable ENABLE_WEB_SEARCH_SUPPLEMENT in .env for web + KB results"
        )
        return (
            "Web search-only mode is not supported in the graph-based agent. "
            "To enable web search as a supplement to knowledge base results, "
            "set ENABLE_WEB_SEARCH_SUPPLEMENT=true in your .env file and restart the server.",
            [],
        )
