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

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from strands import Agent
from strands.tools import tool

from src.agents import prompts
from src.config import Settings
from src.tools import MilvusResponseCache, MilvusVectorDB, OllamaClient, WebSearchClient

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

    def replace_with_html(match: Any) -> str:
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


def _is_web_result_relevant_to_milvus(
    web_result: Dict[str, str],
) -> bool:
    """Check if a web search result is relevant to Milvus/vector databases.
    
    Prevents hallucinations by filtering out irrelevant web search results
    (e.g., Power Apps Collections, Postman documentation) when falling back
    to web search.
    
    Args:
        web_result: Web search result with title, snippet, url fields
        
    Returns:
        True if result appears relevant to Milvus/vector databases, False otherwise
    """
    title = web_result.get("title", "").lower()
    snippet = web_result.get("snippet", "").lower()
    url = web_result.get("url", "").lower()
    
    # Irrelevant domain patterns that should be filtered out
    irrelevant_patterns = [
        "power apps",
        "postman",
        "microsoft learn",
        "api.postman",
        "postman.com",
        "powerplatform",
        "learn.microsoft",
        "jacey duprie",  # Personal blog, not authoritative
    ]
    
    # Relevant domain patterns
    relevant_patterns = [
        "milvus",
        "vector database",
        "vector search",
        "embedding",
        "retrieval",
        "similarity search",
        "pinecone",
        "weaviate",
        "qdrant",
        "chroma",
        "faiss",
    ]
    
    # Check if result contains irrelevant patterns
    combined_text = f"{title} {snippet} {url}"
    for pattern in irrelevant_patterns:
        if pattern in combined_text:
            logger.debug(f"[WEB_RELEVANCE] Filtered out irrelevant result: {pattern} found in {title[:50]}")
            return False
    
    # Check if result contains at least one relevant pattern
    has_relevant = any(pattern in combined_text for pattern in relevant_patterns)
    if not has_relevant:
        logger.debug(f"[WEB_RELEVANCE] Filtered out non-relevant result: {title[:60]}")
        return False
    
    return True


def _is_competitor_database_query(question: str) -> bool:
    """Check if question is specifically about competitor vector databases not covered in our KB.
    
    These queries require web search to provide accurate information.
    When web search is unavailable, we should return a proper "not available" message
    instead of hallucinating information from the Milvus knowledge base.
    """
    question_lower = question.lower()
    
    # Competitor databases with common typos/variations
    # Simple competitor detection - just core names (KISS principle)
    competitor_patterns = {
        "pinecone": ["pinecone"],
        "weaviate": ["weaviate"], 
        "qdrant": ["qdrant"],
        "chroma": ["chroma", "chromadb"],
        "voyageai": ["voyageai"],
        "elasticsearch": ["elasticsearch"],
        "opensearch": ["opensearch"],
        "redis": ["redis"],
        "pgvector": ["pgvector"],
        "supabase": ["supabase"],
        "neon": ["neon"]
    }
    
    # Check for direct competitor mentions in questions asking for information  
    info_requesting_patterns = [
        "what is", "tell me about", "tell me more about", "explain", "describe", 
        "how does", "features of", "benefits of", "capabilities of",
        "pricing", "documentation", "getting started with", "about",
        # Additional patterns for more comprehensive detection
        "features", "capabilities", "advantages", "benefits", "pros", "cons",
        "performance", "scalability", "security", "api", "sdk", "tutorial",
        "guide", "setup", "install", "configure", "use", "work with"
    ]
    
    has_info_request = any(pattern in question_lower for pattern in info_requesting_patterns)
    
    # Check for any competitor pattern matches
    detected_competitor = None
    for competitor, variations in competitor_patterns.items():
        for variation in variations:
            if variation in question_lower:
                detected_competitor = competitor
                break
        if detected_competitor:
            break
    
    # Enhanced logic: Detect standalone competitor queries OR competitor + tech terms
    is_standalone_competitor_query = (
        detected_competitor and has_info_request and 
        "milvus" not in question_lower and "compare" not in question_lower and "vs" not in question_lower
    )
    
    # Additional check: Competitor + database/vector/search terms (even without info request patterns)
    tech_terms = ["database", "vector", "search", "index", "embedding", "similarity", "query", "storage"]
    is_competitor_tech_query = (
        detected_competitor and 
        any(tech_term in question_lower for tech_term in tech_terms) and
        "milvus" not in question_lower and "compare" not in question_lower and "vs" not in question_lower
    )
    
    if is_standalone_competitor_query or is_competitor_tech_query:
        query_type = "info-request" if is_standalone_competitor_query else "tech-specific"
        logger.info(f"[COMPETITOR_DETECTION] Detected competitor database query ({query_type}): {detected_competitor} (from: {question[:60]})")
        return True
        
    return False


def _create_web_search_unavailable_message(message_type: str = 'standard') -> Dict[str, str]:
    """Create standardized web search unavailable messages.
    
    Args:
        message_type: Type of message - 'standard'/'competitor' (same message), 'kb_fallback', or 'stream_note'
        
    Returns:
        Dictionary with 'text' and 'metadata' keys for system message
    """
    # DRY: Use the same message for all cases to maintain consistency
    standard_message = "Web search features are currently unavailable due to API quota or authentication issues. Please try again later."
    
    messages = {
        'standard': standard_message,
        'competitor': standard_message,  # Same message for consistency
        'kb_fallback': "Web search features are currently unavailable due to API quota or authentication issues. The following response is based only on our knowledge base.",
        'stream_note': "**Note:** Web search features are currently unavailable due to API quota or authentication issues. This response is based only on the knowledge base."
    }
    
    # Use consistent metadata type for standard and competitor cases  
    metadata_types = {
        'standard': 'web_search_unavailable',
        'competitor': 'web_search_unavailable',  # Same type for consistency
        'kb_fallback': 'web_search_unavailable',
        'stream_note': 'web_search_unavailable'
    }
    
    return {
        'text': messages[message_type],
        'metadata': f'{{"source": "system", "type": "{metadata_types[message_type]}"}}',
        'source_type': 'system_message',
        'url': ''
    }


def _create_no_web_results_message(message_type: str) -> Dict[str, str]:
    """Create standardized no web results messages.
    
    Args:
        message_type: Type of message - 'standard' or 'competitor'
        
    Returns:
        Dictionary with 'text' and 'metadata' keys for system message
    """
    messages = {
        'standard': 'No current information found. Web search returned no results for this time-sensitive query.',
        'competitor': 'No current information about this external service could be found. Our knowledge base focuses on Milvus documentation.'
    }
    
    metadata_types = {
        'standard': 'no_web_results',
        'competitor': 'no_web_results_competitor'
    }
    
    return {
        'text': messages[message_type],
        'metadata': f'{{"source": "system", "type": "{metadata_types[message_type]}"}}',
        'source_type': 'system_message',
        'url': ''
    }


def _is_question_in_scope(question: str, ollama_client: OllamaClient, settings: Settings) -> bool:
    """Check if question is about databases, search, or information retrieval.

    Uses fast keyword matching for instant classification without LLM calls.
    This enables sub-second rejection of out-of-scope queries.
    """
    question_lower = question.lower()

    # Fast keyword-based pre-filter
    # Includes all major vector database and information retrieval products
    in_scope_keywords = {
        # Core concepts
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
        "knn": 7,
        "nearest neighbor": 7,
        "comparison": 4,
        # Vector database products
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
        # Index techniques
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
    milvus_client: Optional[MilvusVectorDB] = None,
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
        milvus_client: Optional pre-initialized Milvus client (creates new if None)

    Returns:
        Configured GraphBuilder instance
    """

    # Initialize backend systems
    ollama_client = OllamaClient(
        host=settings.ollama_host,
        timeout=settings.ollama_timeout,
        pool_size=settings.ollama_pool_size,
    )

    vector_db = milvus_client or MilvusVectorDB(
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

        # Determine if we should fetch web search results
        # Triggers: (1) time-sensitive query (has "latest", "recent", etc), (2) manual supplement enabled,
        #           (3) empty cache fallback, (4) KB confidence is low, (5) competitor database query
        is_time_sensitive = state.get("is_time_sensitive", False)
        
        # Check if this is a competitor database query that requires web search
        is_competitor_query = _is_competitor_database_query(question)
        
        should_add_web_supplement = (
            settings.enable_web_search_supplement or is_time_sensitive
        )  # Auto-enable for time-sensitive
        should_add_web_fallback = state.get("enable_web_search_fallback", False) or is_competitor_query

        logger.info(
            f"[RAG_WORKER_WEB_SEARCH_DEBUG] is_time_sensitive={is_time_sensitive}, "
            f"is_competitor_query={is_competitor_query}, "
            f"should_add_web_supplement={should_add_web_supplement}, "
            f"should_add_web_fallback={should_add_web_fallback}, "
            f"web_search available={web_search is not None}"
        )

        # Add web search results as supplementary sources or fallback
        if web_search and (should_add_web_supplement or should_add_web_fallback):
            try:
                if should_add_web_fallback:
                    logger.info(
                        "[RAG_WORKER] Triggering web search fallback (empty cache or low KB confidence)..."
                    )
                else:
                    logger.info("[RAG_WORKER] Adding web search supplementary sources...")

                # ENHANCEMENT: Add Milvus context to web search query in fallback mode
                # This prevents hallucinations by ensuring Tavily returns Milvus-specific results
                # instead of generic results about Power Apps, Postman, etc.
                if should_add_web_fallback:
                    web_search_query = f"Milvus vector database {question}"
                    logger.info(
                        f"[RAG_WORKER_WEB_SEARCH] Enhanced fallback query: {web_search_query}"
                    )
                else:
                    web_search_query = question  # Use question directly for supplement mode
                
                web_results, web_search_status = web_search.search(query=web_search_query, max_results=3)

                # Check if web search is unavailable due to API issues
                if web_search_status == 'api_unavailable':
                    logger.warning("[RAG_WORKER] Web search features unavailable due to API quota/authentication issues")
                    
                    # For competitor database queries: return only system message, don't use KB
                    if is_competitor_query:
                        logger.info("[RAG_WORKER] Competitor database query with web search unavailable - returning only system message")
                        system_message = _create_web_search_unavailable_message()
                        
                        # Return state with only system message, no KB fallback for competitors
                        rag_result = RAGResult(
                            answer="",  # Empty content - system message will display in UI
                            sources=[system_message],
                            confidence_score=0.0
                        )
                        state["rag_result"] = rag_result
                        state["retrieval_metrics"] = {
                            "embedding_time": retrieval_result["embedding_time"],
                            "retrieval_time": retrieval_result["retrieval_time"],
                        }
                        return state
                    # For time-sensitive queries: return ONLY system error message, no KB fallback
                    elif is_time_sensitive:
                        logger.info("[RAG_WORKER] Time-sensitive query with web search failure - returning only system message")
                        system_message = _create_web_search_unavailable_message('standard')
                        
                        # Return state with only system message
                        rag_result = RAGResult(
                            answer="",  # Empty content - system message will display in UI
                            sources=[system_message],
                            confidence_score=0.0
                        )
                        state["rag_result"] = rag_result
                        state["retrieval_metrics"] = {
                            "embedding_time": retrieval_result["embedding_time"],
                            "retrieval_time": retrieval_result["retrieval_time"],
                        }
                        return state
                    else:
                        # For non-time-sensitive, non-competitor queries: add system message and continue with KB
                        kb_sources.append(_create_web_search_unavailable_message('kb_fallback'))
                elif len(web_results) == 0:
                    logger.info("[RAG_WORKER] Web search returned no results")
                    
                    # For competitor database queries with no web results: return informative message
                    if is_competitor_query:
                        logger.info("[RAG_WORKER] Competitor database query with no web results - returning informative message")
                        system_message = _create_no_web_results_message('competitor')
                        
                        # Return state with only informative message
                        rag_result = RAGResult(
                            answer="",  # Empty content - system message will display in UI
                            sources=[system_message],
                            confidence_score=0.0
                        )
                        state["rag_result"] = rag_result
                        state["retrieval_metrics"] = {
                            "embedding_time": retrieval_result["embedding_time"],
                            "retrieval_time": retrieval_result["retrieval_time"],
                        }
                        return state
                    # For time-sensitive queries with no web results: return system guidance message
                    elif is_time_sensitive:
                        logger.info("[RAG_WORKER] Time-sensitive query with no web results - returning guidance message")
                        system_message = _create_no_web_results_message('standard')
                        
                        # Return state with only system message
                        rag_result = RAGResult(
                            answer="",  # Empty content - system message will display in UI
                            sources=[system_message],
                            confidence_score=0.0
                        )
                        state["rag_result"] = rag_result
                        state["retrieval_metrics"] = {
                            "embedding_time": retrieval_result["embedding_time"],
                            "retrieval_time": retrieval_result["retrieval_time"],
                        }
                        return state

                # Build context from web results
                web_context_parts = []
                
                # VALIDATION: Filter web results for relevance (prevent hallucinations)
                # In fallback mode, only use results that are relevant to Milvus/vector DBs
                if web_search_status == 'api_unavailable':
                    # Skip web result processing since API is unavailable
                    pass  
                elif should_add_web_fallback:
                    filtered_results = [
                        r for r in web_results 
                        if _is_web_result_relevant_to_milvus(r)
                    ]
                    if len(filtered_results) < len(web_results):
                        logger.info(
                            f"[RAG_WORKER_WEB_SEARCH] Filtered {len(web_results)} results → "
                            f"{len(filtered_results)} relevant results"
                        )
                    web_results = filtered_results

                # Format web search results with proper source_type for UI display
                for idx, web_result in enumerate(web_results, 1):
                    snippet = web_result.get("snippet", "")
                    title = web_result.get("title", "Web Result")

                    # Add to context text
                    web_context_parts.append(f"[Web Result {idx}] {title}\n{snippet}\n")

                    # Add to sources list
                    kb_sources.append(
                        {
                            "source_type": "web_search",
                            "url": web_result.get("url", ""),
                            "title": title,
                            "text": snippet,
                            "snippet": snippet,
                            "distance": 0.7,  # Fixed relevance score for web results
                            "metadata": {
                                "source": "web",
                                "title": title,
                            },
                        }
                    )

                # If fallback mode, rebuild context from web results
                if should_add_web_fallback:
                    context_text = "\n".join(web_context_parts)
                    
                    # SAFEGUARD: If no relevant web results found in fallback mode, return "not found" response
                    # This prevents hallucinations when falling back to web search with no results
                    if not web_context_parts:
                        logger.warning(
                            "[RAG_WORKER] ⚠️ Web search fallback found NO relevant results - "
                            "returning 'not found' response to prevent hallucinations"
                        )
                        context_text = "No relevant information found in knowledge base or web search."
                    
                    logger.info(
                        f"[RAG_WORKER] Rebuilt context from {len(web_results)} web results (fallback)"
                    )
                elif is_time_sensitive:
                    # For time-sensitive queries, prioritize web results but include KB context too
                    web_ctx = "\n".join(web_context_parts)
                    context_text = (
                        web_ctx + "\n\nAdditional context from knowledge base:\n" + context_text
                        if context_text
                        else web_ctx
                    )
                    logger.info(
                        "[RAG_WORKER] Prioritized web search context for time-sensitive query"
                    )
                else:
                    # Supplement mode: append web context to KB context
                    context_text = (
                        context_text + "\n" + "\n".join(web_context_parts)
                        if context_text
                        else "\n".join(web_context_parts)
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
        # Use the same web search unavailable message for consistency
        # Many out-of-scope queries are legitimate questions that would benefit from web search
        web_unavailable_msg = _create_web_search_unavailable_message()
        state["final_answer"] = web_unavailable_msg['text']
        state["final_sources"] = []
        state["final_confidence"] = 0.0
        logger.info("[REJECTION] Out-of-scope query → returning web search unavailable message")
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

    # Build the graph with real Strands agent instances and routing functions
    # Actual execution uses agent.invoke() calls with conditional routing

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

    # ========================================================================
    # BUILD STRANDS AGENTS FOR EACH NODE
    # ========================================================================

    # AGENT 1: Topic Checker Agent
    topic_agent = Agent(
        name="TopicChecker",
        system_prompt=prompts.ScopeCheckPrompts.SYSTEM_INSTRUCTIONS,
        model=fast_model,
        tools=[],  # No tools needed
    )

    # AGENT 2: Security Checker Agent
    security_agent = Agent(
        name="SecurityChecker",
        system_prompt=prompts.SecurityCheckPrompts.SYSTEM_INSTRUCTIONS,
        model=fast_model,
        tools=[],  # No tools needed
    )

    # AGENT 3: RAG Worker Agent with Tools
    @tool
    def search_knowledge_base(
        question: str, collections: List[str], top_k: int = 5
    ) -> Dict[str, Any]:
        """Search the knowledge base for relevant documents."""
        logger.info(f"Searching KB with: {question[:50]}...")
        result: Dict[str, Any] = retrieval_tool(question, collections, top_k)  # type: ignore
        return result

    @tool
    def generate_response(
        question: str, context: str, sources: List[Dict], temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """Generate an answer based on context and sources."""
        logger.info(f"Generating answer for: {question[:50]}...")
        result: Dict[str, Any] = generation_tool(question, context, sources, temperature)  # type: ignore
        return result

    rag_agent = Agent(
        name="RAGWorker",
        system_prompt=prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
            formatting_rules=prompts.FORMATTING_RULES
        ),
        model=rag_model,
        tools=[search_knowledge_base, generate_response],
    )

    # ========================================================================
    # RETURN CONFIG WITH REAL STRANDS AGENTS
    # ========================================================================

    graph_config = {
        "strands_agents": {
            "topic_agent": topic_agent,
            "security_agent": security_agent,
            "rag_agent": rag_agent,
        },
        "nodes": {
            "topic_check": topic_check_node,
            "security_check": security_check_node,
            "rag_worker": rag_worker_node,
            "reject_out_of_scope": reject_out_of_scope,
            "reject_security_risk": reject_security_risk,
            "format_result": format_rag_result,
        },
        "routing_functions": {
            "check_topic_pass": check_topic_pass,
            "check_security_pass": check_security_pass,
        },
    }

    logger.info(
        "✓ RAG Graph created with Strands agents: "
        "TopicChecker → SecurityChecker → RAGWorker (3-node architecture)"
    )

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
        # Load environment variables from .env file before initializing clients
        load_dotenv()

        self.settings = settings
        self.graph_config: Optional[Dict[str, Any]] = None
        self.graph_state: Dict[str, Any] = {}
        self.initialization_error: Optional[str] = None
        self._last_stream_sources: List[Dict] = []  # Track sources for streaming responses

        # Type annotations for client attributes
        self.vector_db: Optional[MilvusVectorDB] = None
        self.web_search: Optional[WebSearchClient] = None
        self.response_cache: Optional[MilvusResponseCache] = None

        # Initialize backend clients
        self.ollama_client = OllamaClient(
            host=settings.ollama_host,
            timeout=settings.ollama_timeout,
            pool_size=settings.ollama_pool_size,
        )

        try:
            self.vector_db = MilvusVectorDB(
                host=settings.milvus_host,
                port=settings.milvus_port,
                db_name=settings.milvus_db_name,
                user=settings.milvus_user,
                password=settings.milvus_password,
                timeout=settings.milvus_timeout,
                pool_size=settings.milvus_pool_size,
            )
        except RuntimeError as e:
            if "Milvus connection failed" in str(e):
                self.initialization_error = str(e)
                logger.warning(f"Milvus connection failed, initializing in degraded mode: {e}")
                self.vector_db = None  # Mark as unavailable
            else:
                raise

        # Initialize web search client only if vector_db is available
        self.web_search = None
        if self.vector_db and settings.enable_web_search_supplement:
            self.web_search = WebSearchClient(timeout=settings.web_search_timeout)

        # Initialize response cache only if vector_db is available
        self.response_cache = None
        if self.vector_db:
            self.response_cache = MilvusResponseCache(
                vector_db=self.vector_db,
                embedding_dim=settings.response_cache_embedding_dim,
                distance_threshold=settings.response_cache_threshold,
            )

        try:
            self.graph_config = create_rag_graph(settings, milvus_client=self.vector_db)
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
        # Check if vector_db is available
        if not self.vector_db:
            logger.warning("[RETRIEVE_CONTEXT] Vector DB unavailable - returning empty context")
            return [], []

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
                # Defensive coding: ensure result is a dictionary
                if not isinstance(result, dict):
                    logger.warning(f"Unexpected result type: {type(result)}, skipping")
                    continue
                    
                text = result.get("text", "")
                metadata = result.get("metadata", {})
                
                # Handle metadata that might be stored as JSON string
                if isinstance(metadata, str):
                    try:
                        import json
                        metadata = json.loads(metadata)
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                        
                distance = result.get("distance", 1.0)

                context_chunks.append(text)

                # Build source object - URL is optional, only for web sources
                source = {
                    "source_type": "knowledge_base",  # Label as KB source (not web)
                    "id": result.get("id"),
                    "text": text[:200],
                    "document_name": metadata.get("document_name", ""),
                    "metadata": metadata,
                    "distance": distance,
                    "collection": collection_name,
                }

                # Only include URL if present (for web search sources)
                url = (
                    metadata.get("url")
                    or metadata.get("source_url")
                    or metadata.get("document_url")
                )
                if url:
                    source["url"] = url

                sources.append(source)

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

    async def answer_question(
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
            # In degraded mode (e.g., Milvus down), try web search if available
            if "Milvus" in self.initialization_error and self.web_search:
                logger.warning(
                    f"[DEGRADED_MODE] {self.initialization_error} - using web search fallback"
                )
                # Continue to web search
            else:
                error_msg = f"RAG Agent is not available: {self.initialization_error}"
                logger.error(error_msg)
                return (error_msg, [])

        if not self.graph_config:
            error_msg = "RAG Agent graph configuration is not initialized."
            logger.error(error_msg)
            return (error_msg, [])

        # NOTE: Time-sensitive check moved to happen AFTER topic validation
        # This ensures off-topic queries are rejected properly before checking time-sensitivity

        state = {"question": question, "enable_web_search_fallback": True}

        # CRITICAL: Check competitor queries BEFORE cache - they need web search first
        is_competitor_query = _is_competitor_database_query(question)
        if is_competitor_query:
            logger.info(f"[COMPETITOR_QUERY] Detected competitor database query in answer_question: {question[:50]}...")
            
            # For competitor queries, web search is REQUIRED - check availability first
            if not self.web_search:
                logger.warning("[COMPETITOR_QUERY] Web search unavailable - returning error message")
                error_dict = _create_web_search_unavailable_message()
                return error_dict['text'], [error_dict]

            # Test web search availability by attempting a search
            try:
                web_search_query = self._generate_web_search_query(question)
                web_results, web_search_status = self.web_search.search(query=web_search_query, max_results=3)
                
                if web_search_status == 'api_unavailable':
                    logger.warning("[COMPETITOR_QUERY] Web search API unavailable - returning error message")
                    error_dict = _create_web_search_unavailable_message()
                    return error_dict['text'], [error_dict]
            except Exception as e:
                logger.warning(f"[COMPETITOR_QUERY] Web search test failed: {e} - returning error message")
                error_dict = _create_web_search_unavailable_message()
                return error_dict['text'], [error_dict]

            # Web search is available - continue with processing (skip cache)
            logger.info("[COMPETITOR_QUERY] Web search available - continuing with web search processing")

        # Pre-declare time-sensitive variable for use throughout method
        is_time_sensitive = self._is_time_sensitive_query(question)

        # Initialize state
        state = {
            "question": question,
            "collection_name": collection_name or "milvus_docs",
            "collections": collections or [collection_name or "milvus_docs"],
            "top_k": top_k,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "is_time_sensitive": is_time_sensitive,  # Time-sensitive flag
            "is_competitor_query": is_competitor_query,  # Competitor query flag
            "enable_web_search_fallback": False,  # Separate flag: triggered when cache is EMPTY
            "is_empty_cache_fallback": False,  # Track if this is an empty cache fallback (not a true cache hit)
        }

        start_time = time.time()

        # Check response cache first (before any graph execution)
        # Skip cache for time-sensitive queries and competitor queries
        if self.response_cache and not is_time_sensitive and not is_competitor_query:
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
                    answer = cached.get("response", "")
                    sources = cached.get("sources", [])

                    logger.info(
                        f"[CACHE_HIT_DEBUG] Cached answer length: {len(answer)}, sources: {len(sources)}"
                    )
                    logger.info(f"[CACHE_HIT_DEBUG] Cached answer empty? {not answer.strip()}")

                    # FALLBACK: If cached answer is EMPTY, trigger web search instead of returning empty
                    if not answer.strip():
                        logger.info(
                            f"⚠ Cache hit but answer is EMPTY - triggering web search fallback for: {question[:60]}"
                        )
                        # Clear sources so web search results can be used instead
                        sources = []
                        answer = ""
                        # Set fallback flag and continue to graph execution
                        state["enable_web_search_fallback"] = True
                        state["is_empty_cache_fallback"] = (
                            True  # Track that this is a fallback, not cached
                        )
                        logger.info("[CACHE_HIT_DEBUG] Flag set, continuing to graph execution...")
                        # Do NOT return here - continue to graph execution below
                    else:
                        # Cached answer has content - return it immediately
                        logger.info(f"✓ Cache hit! Retrieved in {elapsed * 1000:.0f}ms")
                        # Mark cached sources so API can identify this as a cached response
                        for source in sources:
                            source["source_type"] = "cached"
                        self._last_stream_sources = sources
                        state["is_empty_cache_fallback"] = False  # This IS a true cache hit
                        logger.info("[CACHE_HIT_DEBUG] Returning cached answer (NOT empty)")
                        return (answer, sources)
                        # Only reaches here if answer is not empty
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}, proceeding with RAG")

        logger.info(f"Executing Strands graph for: {question[:50]}...")

        try:
            # Get Strands agents from graph config
            topic_agent = self.graph_config["strands_agents"]["topic_agent"]
            security_agent = self.graph_config["strands_agents"]["security_agent"]
            rag_agent = self.graph_config["strands_agents"]["rag_agent"]

            routing_funcs = self.graph_config["routing_functions"]

            execution_path = ["cache_check" if state.get("is_cached") else "graph_start"]

            # ================================================================
            # NODE 1: Topic Check (Fast Model - Topic Validation)
            # ================================================================
            logger.info("[TOPIC_CHECK] Running Strands TopicChecker agent...")
            try:
                topic_response = await topic_agent.invoke_async(
                    context={"user_query": question},
                    max_tokens=100,
                )

                # Extract response text - handle various response formats
                response_text = ""
                if isinstance(topic_response, dict):
                    response_text = topic_response.get("content", "")
                    if isinstance(response_text, list):
                        response_text = str(response_text)
                elif hasattr(topic_response, "content"):
                    response_text = str(topic_response.content)
                else:
                    response_text = str(topic_response)

                # Parse validation result from response - look for YES/NO as per system prompt
                is_valid = "yes" in response_text.lower()
                topic_result = ValidationResult(
                    is_valid=is_valid,
                    reason="Topic validation passed" if is_valid else "Topic validation failed",
                    category=None,
                )
                state["topic_result"] = topic_result
                execution_path.append("topic_check")
                logger.info(f"[TOPIC_CHECK] Result: is_valid={topic_result.is_valid}")

            except Exception as topic_error:
                logger.warning(
                    f"[TOPIC_CHECK] Agent failed: {topic_error}, using fast keyword check"
                )
                is_in_scope = _is_question_in_scope(question, self.ollama_client, self.settings)
                state["topic_result"] = ValidationResult(
                    is_valid=is_in_scope,
                    reason="Fallback keyword-based check",
                    category=None,
                )

            # Check routing condition
            if not routing_funcs["check_topic_pass"](state):
                logger.info("[ROUTING] Topic check failed → Reject (out-of-scope)")
                # SAFEGUARD: Clear web search fallback flag for rejected queries (never use web search for out-of-scope)
                state["enable_web_search_fallback"] = False
                state = self.graph_config["nodes"]["reject_out_of_scope"](state)
                execution_path.append("reject_out_of_scope")
            else:
                # ================================================================
                # TOPIC PASSED → Check if time-sensitive (after topic validation)
                # ================================================================
                is_time_sensitive = self._is_time_sensitive_query(question)
                if is_time_sensitive:
                    logger.info(
                        f"[TIME_SENSITIVE_QUERY] Detected time-sensitive IN-SCOPE query: {question[:50]}..."
                    )
                    
                    # For time-sensitive queries, web search is REQUIRED - check availability first
                    if not self.web_search:
                        logger.warning("[TIME_SENSITIVE_QUERY] Web search unavailable - returning error message")
                        error_dict = _create_web_search_unavailable_message()
                        execution_path.append("time_sensitive_web_search_required")
                        return error_dict['text'], [error_dict]

                    # Test web search availability by attempting a search
                    try:
                        web_search_query = self._generate_web_search_query(question)
                        web_results, web_search_status = self.web_search.search(query=web_search_query, max_results=3)
                        
                        if web_search_status == 'api_unavailable':
                            logger.warning("[TIME_SENSITIVE_QUERY] Web search API unavailable - returning error message")
                            error_dict = _create_web_search_unavailable_message()
                            execution_path.append("time_sensitive_web_search_unavailable")
                            return error_dict['text'], [error_dict]
                        else:
                            # Web search available - proceed with time-sensitive web search
                            logger.info("[TIME_SENSITIVE_QUERY] Web search available - using web search for current info")
                            # Return tuple format as expected by method signature
                            answer, sources = self.answer_question_web_search_only(question, temperature, max_tokens)
                            return answer, sources
                            
                    except Exception as e:
                        logger.warning(f"[TIME_SENSITIVE_QUERY] Web search test failed: {e}")
                        error_dict = _create_web_search_unavailable_message()
                        execution_path.append("time_sensitive_web_search_error")
                        return error_dict['text'], [error_dict]
                # ================================================================
                # NODE 2: Security Check (Fast Model - Security Validation)
                # ================================================================
                logger.info("[SECURITY_CHECK] Running Strands SecurityChecker agent...")
                try:
                    security_response = await security_agent.invoke_async(
                        context={"user_query": question},
                        max_tokens=100,
                    )

                    # Extract response text - handle various response formats
                    response_text = ""
                    if isinstance(security_response, dict):
                        response_text = security_response.get("content", "")
                        if isinstance(response_text, list):
                            response_text = str(response_text)
                    elif hasattr(security_response, "content"):
                        response_text = str(security_response.content)
                    else:
                        response_text = str(security_response)

                    # Parse validation result from response
                    is_safe = (
                        "true" in response_text.lower()
                        or "safe" in response_text.lower()
                        or "yes" in response_text.lower()
                    )
                    state["security_result"] = ValidationResult(
                        is_valid=is_safe,
                        reason=(
                            "Security validation passed" if is_safe else "Security risk detected"
                        ),
                        category=None,
                    )
                    execution_path.append("security_check")
                    logger.info(f"[SECURITY_CHECK] Result: is_valid={is_safe}")

                except Exception as security_error:
                    logger.warning(
                        f"[SECURITY_CHECK] Agent failed: {security_error}, using fast pattern check"
                    )
                    is_attack = _is_security_attack(question, self.ollama_client, self.settings)
                    state["security_result"] = ValidationResult(
                        is_valid=not is_attack,
                        reason="Fallback pattern-based check",
                        category=None,
                    )

                # Check routing condition
                if not routing_funcs["check_security_pass"](state):
                    logger.info("[ROUTING] Security check failed → Reject (security risk)")
                    # SAFEGUARD: Clear web search fallback flag for rejected queries (never use web search for security violations)
                    state["enable_web_search_fallback"] = False
                    state = self.graph_config["nodes"]["reject_security_risk"](state)
                    execution_path.append("reject_security_risk")
                else:
                    # ================================================================
                    # NODE 3: RAG Worker (Powerful Model - Answer Generation)
                    # ================================================================
                    # CRITICAL: Use Python rag_worker for web search fallback OR time-sensitive queries
                    # (Strands agent doesn't support web search fallback logic)
                    if state.get("enable_web_search_fallback", False) or state.get("is_time_sensitive", False):
                        if state.get("is_time_sensitive", False):
                            logger.info(
                                "[RAG_WORKER] Using Python rag_worker for time-sensitive query "
                                "(requires web search support)"
                            )
                        else:
                            logger.info(
                                "[RAG_WORKER] Using Python rag_worker for web search fallback "
                                "(Strands agent doesn't support web search fallback)"
                            )
                        state = self.graph_config["nodes"]["rag_worker"](state)
                        execution_path.append("rag_worker_python")
                    else:
                        logger.info("[RAG_WORKER] Running Strands RAGWorker agent...")
                        try:
                            rag_context = (
                                f"Question: {question}\n"
                                f"Collections: {state.get('collections', ['milvus_docs'])}\n"
                                f"Top-k: {state.get('top_k', 5)}"
                            )

                            rag_response = await rag_agent.invoke_async(
                                context={"user_query": question, "knowledge": rag_context},
                                max_tokens=state.get("max_tokens", 512),
                            )

                            # Extract answer text - handle various response formats
                            answer_text = ""
                            if isinstance(rag_response, dict):
                                answer_text = rag_response.get("content", "")
                                if isinstance(answer_text, list):
                                    answer_text = str(answer_text)
                            elif hasattr(rag_response, "content"):
                                answer_text = str(rag_response.content)
                            else:
                                answer_text = str(rag_response)

                            rag_result = RAGResult(
                                answer=answer_text or "Unable to generate answer",
                                sources=cast(List[Dict[str, Any]], state.get("final_sources", [])),
                                confidence_score=0.85 if answer_text else 0.0,
                            )
                            state["rag_result"] = rag_result
                            execution_path.append("rag_worker")
                            logger.info("[RAG_WORKER] Answer generated successfully")

                        except Exception as rag_error:
                            logger.error(f"[RAG_WORKER] Agent failed: {rag_error}")
                            # Fallback to non-agent RAG execution
                            state = self.graph_config["nodes"]["rag_worker"](state)
                            execution_path.append("rag_worker_fallback")

                    # Format final result
                    state = self.graph_config["nodes"]["format_result"](state)
                    execution_path.append("format_result")

            total_time = time.time() - start_time
            state["execution_path"] = " → ".join(execution_path)

            logger.info(
                f"Graph execution completed in {total_time:.2f}s. "
                f"Path: {state['execution_path']} | "
                f"Confidence: {state.get('final_confidence', 0):.2%}"
            )

            # Store sources for streaming responses
            sources = state.get("final_sources", [])
            self._last_stream_sources = sources

            answer = state.get("final_answer", "")

            # Store response in cache ONLY for successful RAG responses (not rejections)
            # Skip caching for rejected queries to avoid unnecessary embedding calls
            final_confidence = state.get("final_confidence", 0)
            is_rejection = final_confidence == 0.0
            is_already_cached = state.get("is_cached", False)

            logger.info(
                f"Cache decision for '{question[:60]}...': "
                f"confidence={final_confidence}, is_rejection={is_rejection}, "
                f"is_already_cached={is_already_cached}, has_answer={bool(answer)}"
            )

            # DOUBLE-CHECK: Ensure we never cache rejection phrases
            rejection_phrases = [
                "can only help with questions about",
                "security concern",
                "detected a security",
                "out of scope",
            ]
            contains_rejection_phrase = any(
                phrase.lower() in answer.lower() for phrase in rejection_phrases
            )

            if (
                self.response_cache
                and answer
                and not is_already_cached
                and not is_rejection
                and not contains_rejection_phrase
            ):
                try:
                    logger.info(f"✓ Caching response for: {question[:60]}...")
                    question_embedding = self.ollama_client.embed_text(
                        question,
                        model=self.settings.ollama_embed_model,
                    )

                    # Check if this response includes web search sources
                    has_web_search = (
                        any(s.get("source_type") == "web_search" for s in sources)
                        if sources
                        else False
                    )

                    self.response_cache.store_response(
                        question=question,
                        question_embedding=question_embedding,
                        response=answer,
                        metadata={
                            "sources": sources,
                            "collection": collection_name or "unknown",
                            "response_time": round(total_time * 1000, 2),  # milliseconds
                            "confidence": final_confidence,
                            "execution_path": state.get("execution_path", "unknown"),
                            "has_web_search": has_web_search,  # Track if response came from web search
                        },
                    )
                    logger.debug(
                        f"Stored response in cache for question: {question[:60]} (has_web_search={has_web_search})"
                    )
                except Exception as cache_error:
                    logger.warning(f"Failed to cache response: {cache_error}")
            elif is_rejection or contains_rejection_phrase:
                logger.info(
                    f"✗ NOT caching rejection for: {question[:60]}... (is_rejection={is_rejection}, contains_phrase={contains_rejection_phrase})"
                )

            # DEBUG: Log final sources before returning
            final_answer: str = cast(str, state.get("final_answer", ""))
            final_sources: List[Dict] = cast(List[Dict], state.get("final_sources", []))
            logger.info(
                f"[FINAL_RETURN] Answer length: {len(final_answer)}, Sources count: {len(final_sources)}"
            )
            if final_sources:
                source_types = [s.get("source_type", "unknown") for s in final_sources]
                logger.info(f"[FINAL_RETURN] Source types: {source_types}")

            return (final_answer, final_sources)  # noqa: TRY300

        except Exception as e:
            logger.error(f"Graph execution failed: {e}", exc_info=True)
            self._last_stream_sources = []
            return ("An error occurred while processing your request.", [])

    def _is_time_sensitive_query(self, question: str) -> bool:
        """Detect if query is time-sensitive and should skip cache and use web search.

        Time-sensitive queries include:
        - Questions about latest/recent/current trends
        - Questions about 2024, 2025, specific years
        - Questions using temporal keywords like "new", "emerging", "upcoming"

        Args:
            question: User query

        Returns:
            True if query is time-sensitive, False otherwise
        """
        question_lower = question.lower()

        time_sensitive_keywords = [
            "latest",
            "recent",
            "newest",
            "current",
            "trends",
            "trending",
            "emerging",
            "new",
            "upcoming",
            "2024",
            "2025",
            "2026",
            "this year",
            "today",
            "this month",
            "latest news",
            "breaking",
            "just released",
            "recently launched",
        ]

        for keyword in time_sensitive_keywords:
            if keyword in question_lower:
                logger.debug(
                    f"[TIME_SENSITIVE] Query detected: '{keyword}' in '{question[:50]}...'"
                )
                return True

        return False

    def _should_trigger_web_search_fallback(self, kb_sources: List[Dict]) -> bool:
        """Check if KB results are weak enough to trigger web search fallback.

        This should only trigger when KB truly has no useful content, not just 
        when scores are mediocre. Users can manually trigger web search via button.

        Args:
            kb_sources: List of knowledge base sources with distance/relevance scores

        Returns:
            True if KB results are genuinely poor (very low scores AND few results)
        """
        if not kb_sources:
            logger.info("[WEB_SEARCH_FALLBACK] No KB sources found → Fallback: True")
            return True  # No KB results, definitely trigger web search

        # Calculate average relevance (distance is cosine similarity 0-1, higher = better)
        relevance_scores = [s.get("distance", 0) for s in kb_sources if "distance" in s]
        if not relevance_scores:
            logger.info("[WEB_SEARCH_FALLBACK] No relevance scores → Fallback: True")
            return True

        avg_relevance = sum(relevance_scores) / len(relevance_scores)
        max_relevance = max(relevance_scores)
        num_sources = len(kb_sources)
        
        # More conservative fallback: only trigger if BOTH conditions are met:
        # 1. Average relevance is very low (below threshold)
        # 2. Even the best result is poor (below higher threshold) OR very few results
        very_poor_avg = avg_relevance < self.settings.web_search_fallback_threshold
        very_poor_best = max_relevance < (self.settings.web_search_fallback_threshold + 0.1)  # +0.1 buffer
        very_few_results = num_sources < 2
        
        # Only fallback if average is poor AND (best result is also poor OR very few results)
        should_fallback = very_poor_avg and (very_poor_best or very_few_results)

        logger.info(
            f"[WEB_SEARCH_FALLBACK] KB analysis: {num_sources} sources, "
            f"avg: {avg_relevance:.3f}, max: {max_relevance:.3f} "
            f"(threshold: {self.settings.web_search_fallback_threshold}) → "
            f"Fallback: {should_fallback} (was too aggressive before)"
        )

        return should_fallback

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
        skip_cache_for_generic: bool = False,
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

        # Check if in degraded mode due to Milvus unavailability
        if self.initialization_error:
            logger.warning(f"[STREAM_DEGRADED_MODE] {self.initialization_error}")
            if "Milvus" not in self.initialization_error:
                # Unrecoverable error - return error message
                yield f"Error: {self.initialization_error}"
                return
            # For Milvus errors, continue with web search only if available

        try:
            # Use setting defaults if not provided
            if top_k is None:
                top_k = self.settings.default_top_k
            if collection_name is None:
                collection_name = self.settings.ollama_collection_name

            # NOTE: Time-sensitive check moved to happen AFTER topic validation
            # This ensures off-topic queries are rejected properly before checking time-sensitivity
            # Pre-declare variable for use throughout method
            is_time_sensitive = self._is_time_sensitive_query(question)

            # CRITICAL: Check competitor queries BEFORE cache - they need web search first
            is_competitor_query = _is_competitor_database_query(question)
            if is_competitor_query:
                logger.info(f"[COMPETITOR_QUERY] Detected competitor database query: {question[:50]}...")
                
                # For competitor queries, web search is REQUIRED - check availability first
                if not self.web_search:
                    logger.warning("[COMPETITOR_QUERY] Web search unavailable - returning error message")
                    error_msg = _create_web_search_unavailable_message('competitor')
                    self._last_stream_sources = [error_msg]
                    yield error_msg['text']
                    return

                # Test web search availability by attempting a search
                try:
                    web_search_query = self._generate_web_search_query(question)
                    web_results, web_search_status = self.web_search.search(query=web_search_query, max_results=3)
                    
                    if web_search_status == 'api_unavailable':
                        logger.warning("[COMPETITOR_QUERY] Web search API unavailable - returning error message")
                        error_msg = _create_web_search_unavailable_message('competitor')
                        self._last_stream_sources = [error_msg]
                        yield error_msg['text']
                        return
                except Exception as e:
                    logger.warning(f"[COMPETITOR_QUERY] Web search test failed: {e} - returning error message")
                    error_msg = _create_web_search_unavailable_message('competitor')
                    self._last_stream_sources = [error_msg]
                    yield error_msg['text']
                    return

                # Web search is available - continue with processing (skip cache)
                logger.info("[COMPETITOR_QUERY] Web search available - continuing with web search processing")

            # CHECK RESPONSE CACHE (but skip for time-sensitive queries and competitor queries)
            elif self.response_cache and not is_time_sensitive and not is_competitor_query:
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
                        answer = cached.get("response", "")
                        sources = cached.get("sources", [])

                        # Check if cached answer is empty - if so, trigger web search
                        if not answer.strip():
                            logger.info(
                                f"✓ Cache hit but answer is empty - triggering web search for: {question[:60]}"
                            )
                            # Clear sources so web search results replace cached sources
                            sources = []
                            answer = ""
                            # Continue to web search logic below (don't return)
                        else:
                            # Non-empty answer - return cached result
                            logger.info(
                                f"✓ Cache hit! Retrieved in {elapsed * 1000:.0f}ms (streaming)"
                            )
                            
                            # Mark sources as cached for proper UI badge detection
                            cached_sources = []
                            for source in sources:
                                cached_source = source.copy()
                                cached_source["source_type"] = "cached"  # Mark as cached for UI
                                cached_sources.append(cached_source)
                            
                            self._last_stream_sources = cached_sources

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

            # TIME-SENSITIVE CHECK (after scope validation passes)
            if is_time_sensitive:
                logger.info(
                    f"[TIME_SENSITIVE_QUERY] Detected time-sensitive IN-SCOPE query: {question[:50]}..."
                )
                
                # For time-sensitive queries, web search is REQUIRED - check availability first
                if not self.web_search:
                    logger.warning("[TIME_SENSITIVE_QUERY] Web search unavailable - returning error message")
                    error_msg = _create_web_search_unavailable_message('standard')
                    self._last_stream_sources = [error_msg]
                    yield error_msg['text']
                    return

                # Test web search availability by attempting a search
                try:
                    web_search_query = self._generate_web_search_query(question)
                    web_results, web_search_status = self.web_search.search(query=web_search_query, max_results=3)
                    
                    if web_search_status == 'api_unavailable':
                        logger.warning("[TIME_SENSITIVE_QUERY] Web search API unavailable - returning error message")
                        error_msg = _create_web_search_unavailable_message()
                        self._last_stream_sources = [error_msg]
                        yield error_msg['text']
                        return
                    else:
                        # Web search available - proceed with time-sensitive web search
                        logger.info("[TIME_SENSITIVE_QUERY] Web search available - using web search for current info")
                        async for chunk in self.stream_answer_web_search_only(question, temperature, max_tokens):
                            yield chunk
                        return
                        
                except Exception as e:
                    logger.warning(f"[TIME_SENSITIVE_QUERY] Web search test failed: {e}")
                    error_msg = _create_web_search_unavailable_message('standard')
                    self._last_stream_sources = [error_msg]
                    yield error_msg['text']
                    return
            # If not time-sensitive, continue with normal processing

            # Retrieve context
            context_chunks, sources = self.retrieve_context(
                collection_name=collection_name,
                query=question,
                top_k=top_k,
            )

            # Smart web search: trigger for supplements, low KB confidence, time-sensitive queries, OR competitor queries
            should_add_web_supplement = self.settings.enable_web_search_supplement
            should_add_web_fallback = (
                self.web_search and sources and self._should_trigger_web_search_fallback(sources)
            )
            should_add_time_sensitive = is_time_sensitive and self.web_search
            should_add_competitor_search = is_competitor_query and self.web_search  # Already checked availability above

            if self.web_search and (should_add_web_supplement or should_add_web_fallback or should_add_time_sensitive or should_add_competitor_search):
                try:
                    if should_add_competitor_search:
                        logger.info(
                            "[STREAM] Competitor database query → Triggering web search for external info..."
                        )
                    elif should_add_time_sensitive:
                        logger.info(
                            "[STREAM] Time-sensitive query → Triggering web search for latest info..."
                        )
                    elif should_add_web_fallback:
                        logger.info(
                            "[STREAM] KB confidence low → Triggering web search fallback..."
                        )
                    else:
                        logger.info("[STREAM] Adding web search supplementary sources...")

                    web_search_query = self._generate_web_search_query(question)
                    web_results, web_search_status = self.web_search.search(query=web_search_query, max_results=3)

                    if web_search_status == 'api_unavailable':
                        logger.warning("[STREAM] Web search features unavailable due to API quota/authentication issues")
                        # Add system message about web search being unavailable
                        system_message = _create_web_search_unavailable_message('standard')
                        
                        # For competitor queries or time-sensitive queries: return ONLY system message, no KB content
                        if should_add_competitor_search or should_add_time_sensitive:
                            if should_add_competitor_search:
                                logger.info("[STREAM] Competitor query with web search failure - returning only system message")
                                # Since 'competitor' and 'standard' now return identical messages, no need to recreate
                            else:
                                logger.info("[STREAM] Time-sensitive query with web search failure - returning only system message")
                            self._last_stream_sources = [system_message]
                            yield system_message['text']
                            return  # Don't generate any content
                        else:
                            # For non-time-sensitive, non-competitor queries: add system message and continue with KB
                            sources.append(system_message)
                    elif len(web_results) == 0:
                        logger.info("[STREAM] Web search returned no results")
                        
                        # For competitor queries or time-sensitive queries with no web results: return appropriate message
                        if should_add_competitor_search or should_add_time_sensitive:
                            if should_add_competitor_search:
                                logger.info("[STREAM] Competitor query with no web results - returning informative message")
                                guidance_message = _create_no_web_results_message('competitor')
                            else:
                                logger.info("[STREAM] Time-sensitive query with no web results - returning guidance message")
                                guidance_message = _create_no_web_results_message('standard')
                            self._last_stream_sources = [guidance_message]
                            yield guidance_message['text']
                            return  # Don't generate any content
                    else:
                        for web_result in web_results:
                            sources.append(
                                {
                                    "source_type": "web_search",
                                    "url": web_result.get("url", ""),
                                    "title": web_result.get("title", "Web Result"),
                                    "text": web_result.get("snippet", ""),
                                    "snippet": web_result.get("snippet", ""),
                                    "distance": 0.7,
                                    "metadata": {
                                        "source": "web",
                                        "title": web_result.get("title", ""),
                                    },
                                }
                            )

                    logger.info(f"[STREAM] Added {len(web_results)} web search sources")

                except Exception as e:
                    logger.warning(f"[STREAM] Web search failed (non-critical): {e}")
                    # For time-sensitive queries, if both KB and web search fail, 
                    # provide a helpful response instead of generic fallback
                    if is_time_sensitive and not context_chunks:
                        logger.info("[STREAM] Time-sensitive query failed, providing guidance...")
                        context_chunks = [
                            "I don't have access to real-time information about the latest trends in vector databases. "
                            "For the most current information, I'd recommend checking recent blog posts, news articles, "
                            "or official announcements from vector database companies like Milvus, Pinecone, Weaviate, and Qdrant. "
                            "However, I can help with general concepts about vector databases based on my knowledge."
                        ]
                        sources = [{
                            "source_type": "system_message", 
                            "text": "System guidance for time-sensitive queries",
                            "distance": 0.0
                        }]

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

            # Check if query is time-sensitive 
            is_time_sensitive = self._is_time_sensitive_query(question)
            if is_time_sensitive:
                logger.info(f"[STREAM_NO_CACHE] Time-sensitive query detected: {question[:50]}...")

            # CRITICAL: Check competitor queries BEFORE processing - they need web search first
            is_competitor_query = _is_competitor_database_query(question)
            if is_competitor_query:
                logger.info(f"[COMPETITOR_QUERY] Detected competitor database query in stream_answer_no_cache: {question[:50]}...")
                
                # For competitor queries, web search is REQUIRED - check availability first
                if not self.web_search:
                    logger.warning("[COMPETITOR_QUERY] Web search unavailable - returning error message")
                    error_msg = _create_web_search_unavailable_message('competitor')
                    self._last_stream_sources = [error_msg]
                    yield error_msg['text']
                    return

                # Test web search availability by attempting a search
                try:
                    web_search_query = self._generate_web_search_query(question)
                    web_results, web_search_status = self.web_search.search(query=web_search_query, max_results=3)
                    
                    if web_search_status == 'api_unavailable':
                        logger.warning("[COMPETITOR_QUERY] Web search API unavailable - returning error message")
                        error_msg = _create_web_search_unavailable_message('competitor')
                        self._last_stream_sources = [error_msg]
                        yield error_msg['text']
                        return
                except Exception as e:
                    logger.warning(f"[COMPETITOR_QUERY] Web search test failed: {e} - returning error message")
                    error_msg = _create_web_search_unavailable_message('competitor')
                    self._last_stream_sources = [error_msg]
                    yield error_msg['text']
                    return

                # Web search is available - continue with processing
                logger.info("[COMPETITOR_QUERY] Web search available - continuing with web search processing")

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

            # Smart web search: trigger for supplements, low KB confidence, time-sensitive queries, OR competitor queries
            should_add_web_supplement = self.settings.enable_web_search_supplement
            should_add_web_fallback = (
                self.web_search and sources and self._should_trigger_web_search_fallback(sources)
            )
            should_add_time_sensitive = is_time_sensitive and self.web_search
            should_add_competitor_search = is_competitor_query and self.web_search  # Already checked availability above

            if self.web_search and (should_add_web_supplement or should_add_web_fallback or should_add_time_sensitive or should_add_competitor_search):
                try:
                    if should_add_competitor_search:
                        logger.info(
                            "[STREAM_NO_CACHE] Competitor database query → Triggering web search for external info..."
                        )
                    elif should_add_time_sensitive:
                        logger.info(
                            "[STREAM_NO_CACHE] Time-sensitive query → Triggering web search for latest info..."
                        )
                    elif should_add_web_fallback:
                        logger.info(
                            "[STREAM_NO_CACHE] KB confidence low → Triggering web search fallback..."
                        )
                    else:
                        logger.info("[STREAM_NO_CACHE] Adding web search supplementary sources...")

                    web_search_query = self._generate_web_search_query(question)
                    web_results, web_search_status = self.web_search.search(query=web_search_query, max_results=3)

                    # Check if web search is unavailable due to API issues
                    if web_search_status == 'api_unavailable':
                        logger.warning("[STREAM_NO_CACHE] Web search features unavailable due to API quota/authentication issues")
                        # Add system message about web search being unavailable
                        sources.append(_create_web_search_unavailable_message('standard'))
                    else:
                        for web_result in web_results:
                            sources.append(
                                {
                                    "source_type": "web_search",
                                    "url": web_result.get("url", ""),
                                    "title": web_result.get("title", "Web Result"),
                                    "text": web_result.get("snippet", ""),
                                    "snippet": web_result.get("snippet", ""),
                                    "distance": 0.7,
                                    "metadata": {
                                        "source": "web",
                                        "title": web_result.get("title", ""),
                                    },
                                }
                            )

                    logger.info(f"[STREAM_NO_CACHE] Added {len(web_results)} web search sources")

                except Exception as e:
                    logger.warning(f"[STREAM_NO_CACHE] Web search failed (non-critical): {e}")
                    # If web search fails and we have no KB results for time-sensitive query,
                    # provide helpful guidance
                    if is_time_sensitive and not context_chunks:
                        logger.info("[STREAM_NO_CACHE] Time-sensitive query failed, providing guidance...")
                        context_chunks = [
                            "I don't have access to real-time information about the latest trends in vector databases. "
                            "For the most current information, I'd recommend checking recent blog posts, news articles, "
                            "or official announcements from vector database companies like Milvus, Pinecone, Weaviate, and Qdrant. "
                            "However, I can help with general concepts about vector databases based on my knowledge."
                        ]
                        sources = [{
                            "source_type": "system_message", 
                            "text": "System guidance for time-sensitive queries",
                            "distance": 0.0
                        }]
                    elif not context_chunks:
                        context_chunks = [
                            "I don't have access to real-time information, but I can help with general vector database concepts and Milvus documentation."
                        ]
                        sources = [{
                            "source_type": "system_message", 
                            "text": "System guidance for time-sensitive queries",
                            "distance": 0.0
                        }]

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
                if not self.web_search:
                    raise ValueError("Web search client is not available")

                web_search_query = self._generate_web_search_query(question)
                web_results, web_search_status = await asyncio.to_thread(self.web_search.search, web_search_query, 5)

                # Check if web search is unavailable due to API issues
                if web_search_status == 'api_unavailable':
                    logger.warning("[ASYNC_STREAM] Web search features unavailable due to API quota/authentication issues")
                    # Return error message for async streams - yield plain text like other streaming methods
                    stream_note_msg = _create_web_search_unavailable_message('stream_note')
                    yield f"\n\n{stream_note_msg['text']}\n\n"
                elif len(web_results) > 0:
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
        if not self.vector_db:
            logger.warning("[LIST_COLLECTIONS] Vector DB unavailable - returning empty list")
            return []

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

    async def answer_question_no_cache(
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
        return await self.answer_question(
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
