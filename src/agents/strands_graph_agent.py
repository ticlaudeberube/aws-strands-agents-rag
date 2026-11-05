"""Strands Graph-based RAG Agent factory with specialized nodes.

This module provides the dual-mode ``create_rag_graph`` factory and the
backend-agnostic building blocks for the three-node RAG architecture:
1. Topic Checker (fast model): Validates if query is in-scope
2. Security Checker (fast model): Detects security risks and attacks
3. RAG Worker (powerful model): Performs vector search and answer generation

Benefits:
- Early exit on out-of-scope or malicious queries (cost savings)
- Each node uses optimized model for its task
- Clean separation of concerns
- Parallel execution support for checkers

Architecture:
    Input → Topic Check → Security Check → RAG Worker → Output
              ↓ (fail)      ↓ (fail)
           Rejection    Rejection

The local-mode entrypoint used by the API/MCP server is
:class:`src.agents.local_opensearch_agent.LocalOpenSearchAgent`, which drives
answering through the shared ``create_rag_graph`` routing. The serverless mode
is wired by the Lambda handler through the same factory.
"""

import logging
import re
import time
from typing import Any

from pydantic import BaseModel, Field
from strands import Agent

from src.agents import prompts, rag_routing
from src.agents.node_config import NodeConfigManager
from src.agents.node_metrics import GraphMetrics, NodeMetrics
from src.config import Settings
from src.tools import (
    InMemoryCache,
    OllamaClient,
    WebSearchClient,
)

logger = logging.getLogger(__name__)

# Global metrics instance for tracking graph execution
graph_metrics = GraphMetrics()
node_config_manager = NodeConfigManager()


# ============================================================================
# STRUCTURED OUTPUT MODELS FOR ROUTING
# ============================================================================


class ValidationResult(BaseModel):
    """Structured output for topic and security validation."""

    is_valid: bool = Field(..., description="Whether the query passes validation")
    reason: str = Field(..., description="Explanation for the validation result")
    category: str | None = Field(
        None, description="Category of failure if invalid (security_risk, out_of_scope)"
    )


class RAGResult(BaseModel):
    """Structured output for RAG worker node."""

    answer: str = Field(..., description="Generated answer to the query")
    sources: list[dict] = Field(default_factory=list, description="Source documents used")
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score 0-1")


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


def _calculate_confidence_score(sources: list[dict], answer: str) -> float:
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
    ollama_client: OllamaClient | None = None,
    settings: Settings | None = None,
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
        "neon": ["neon"],
    }

    # Check for direct competitor mentions in questions asking for information
    info_requesting_patterns = [
        "what is",
        "tell me about",
        "tell me more about",
        "explain",
        "describe",
        "how does",
        "features of",
        "benefits of",
        "capabilities of",
        "pricing",
        "documentation",
        "getting started with",
        "about",
        # Additional patterns for more comprehensive detection
        "features",
        "capabilities",
        "advantages",
        "benefits",
        "pros",
        "cons",
        "performance",
        "scalability",
        "security",
        "api",
        "sdk",
        "tutorial",
        "guide",
        "setup",
        "install",
        "configure",
        "use",
        "work with",
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
        detected_competitor
        and has_info_request
        and "milvus" not in question_lower
        and "compare" not in question_lower
        and "vs" not in question_lower
    )

    # Additional check: Competitor + database/vector/search terms (even without info request patterns)
    tech_terms = [
        "database",
        "vector",
        "search",
        "index",
        "embedding",
        "similarity",
        "query",
        "storage",
    ]
    is_competitor_tech_query = (
        detected_competitor
        and any(tech_term in question_lower for tech_term in tech_terms)
        and "milvus" not in question_lower
        and "compare" not in question_lower
        and "vs" not in question_lower
    )

    if is_standalone_competitor_query or is_competitor_tech_query:
        query_type = "info-request" if is_standalone_competitor_query else "tech-specific"
        logger.info(
            f"[COMPETITOR_DETECTION] Detected competitor database query ({query_type}): {detected_competitor} (from: {question[:60]})"
        )
        return True

    return False


def _create_web_search_unavailable_message(message_type: str = "standard") -> dict[str, str]:
    """Create standardized web search unavailable messages.

    Args:
        message_type: Type of message - 'standard'/'competitor' (same message), 'kb_fallback', or 'stream_note'

    Returns:
        Dictionary with 'text' and 'metadata' keys for system message
    """
    # DRY: Use the same message for all cases to maintain consistency
    standard_message = "Web search features are currently unavailable due to API quota or authentication issues. Please try again later."

    messages = {
        "standard": standard_message,
        "competitor": standard_message,  # Same message for consistency
        "kb_fallback": "Web search features are currently unavailable due to API quota or authentication issues. The following response is based only on our knowledge base.",
        "stream_note": "**Note:** Web search features are currently unavailable due to API quota or authentication issues. This response is based only on the knowledge base.",
    }

    # Use consistent metadata type for standard and competitor cases
    metadata_types = {
        "standard": "web_search_unavailable",
        "competitor": "web_search_unavailable",  # Same type for consistency
        "kb_fallback": "web_search_unavailable",
        "stream_note": "web_search_unavailable",
    }

    return {
        "text": messages[message_type],
        "metadata": f'{{"source": "system", "type": "{metadata_types[message_type]}"}}',
        "source_type": "system_message",
        "url": "",
    }


def _create_web_search_disabled_message() -> dict[str, str]:
    """Create a system message for web search disabled by configuration."""
    return {
        "text": "Web search is disabled. Enable it in server settings to use web-only search.",
        "metadata": '{"source": "system", "type": "web_search_disabled"}',
        "source_type": "system_message",
        "url": "",
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

    # Word-boundary matching against the whole question. This correctly handles
    # multi-word keywords ("vector database") AND avoids substring false
    # positives that the previous ``keyword in word`` check produced — e.g.
    # "rag" matching "storage", "annoy" matching the verb "annoy", or "mysql"
    # pulling an otherwise off-topic question in-scope.
    score = 0
    matched: list[str] = []
    for keyword, weight in in_scope_keywords.items():
        if re.search(rf"\b{re.escape(keyword)}\b", question_lower):
            score += weight
            matched.append(keyword)

    # Any keyword match means in-scope.
    if score > 0:
        logger.debug(f"[SCOPE_CHECK] Keyword match (score={score}, matched={matched}): in-scope")
        return True

    # Fast reject: No keywords at all = definitely out of scope
    # This avoids expensive LLM calls for clearly out-of-scope queries
    logger.debug("[SCOPE_CHECK] No keyword match (score=0): out-of-scope (fast reject)")
    return False


# ============================================================================
# GRAPH AGENT FACTORY
# ============================================================================


def _build_serverless_backends(
    settings: Settings,
    bedrock_client: Any | None = None,
    opensearch_client: Any | None = None,
    redis_cache: Any | None = None,
) -> tuple[Any, Any, Any, Any]:
    """Resolve the serverless-mode backend set (Bedrock + OpenSearch + Redis).

    Returns ``(llm, vector_store, cache, semantic_cache)`` where the Layer 4
    semantic cache is served by the OpenSearch ``rag-cache`` index (the same
    client as the vector store, via its ``search_semantic_cache`` /
    ``store_semantic_cache`` methods).

    Backend selection by mode (serverless):

    - ``llm``           -> :class:`~src.tools.bedrock_client.BedrockClient`
      (``claude-3-haiku`` generation, ``titan-embed-text-v1`` embeddings with
      1536->768 PCA).
    - ``vector_store``  -> :class:`~src.tools.opensearch_client.OpenSearchClient`
      (``rag-kb`` k-NN index).
    - ``cache``         -> :class:`~src.tools.redis_cache.RedisCache`
      (ElastiCache Layer 2/3).
    - ``semantic_cache``-> the same ``OpenSearchClient`` (``rag-cache`` index,
      Layer 4).

    Injection-first construction
    ----------------------------
    Pre-built instances (passed by the Lambda handler or tests) are always used
    as-is. Only when an instance is **not** injected is a default constructed
    from ``settings``. ``BedrockClient`` and ``RedisCache`` defer their AWS
    client/connection creation until first use (``boto3`` / ``redis`` are
    imported lazily), so constructing them never requires the serverless SDKs to
    be installed. ``OpenSearchClient`` eagerly builds its ``opensearch-py``
    client on construction; if the dependency is absent (or the endpoint is not
    configured) a clear :class:`RuntimeError` is raised naming the missing piece
    and pointing at the inject-a-client remedy, rather than an opaque import
    error.
    """
    from src.tools.bedrock_client import BedrockClient
    from src.tools.opensearch_client import OpenSearchClient
    from src.tools.redis_cache import RedisCache

    # Bedrock + Redis defer their SDK import / connection to first use, so a
    # default instance can always be constructed without boto3/redis present.
    llm = bedrock_client if bedrock_client is not None else BedrockClient(settings)
    cache = redis_cache if redis_cache is not None else RedisCache(settings)

    # OpenSearch is the one client that eagerly builds its transport on
    # construction. Prefer the injected instance; otherwise construct a default
    # and translate a missing-dependency / unconfigured-endpoint failure into a
    # clear, actionable error.
    if opensearch_client is not None:
        vector_store = opensearch_client
    else:
        try:
            vector_store = OpenSearchClient(settings)
        except (ImportError, ValueError) as exc:
            raise RuntimeError(
                "Could not construct a default OpenSearchClient for serverless "
                "mode. Install the serverless extra (opensearch-py) and set "
                "OPENSEARCH_ENDPOINT, or pass a pre-built opensearch_client to "
                f"create_rag_graph(). (Original error: {exc})"
            ) from exc

    # Serverless L4 semantic cache is the OpenSearch rag-cache index, served by
    # the same OpenSearch client (search_semantic_cache / store_semantic_cache).
    semantic_cache = vector_store

    logger.info("Serverless backends resolved: Bedrock + OpenSearch + Redis")
    return llm, vector_store, cache, semantic_cache


def create_rag_graph(
    settings: Settings,
    fast_model_id: str | None = None,
    rag_model_id: str | None = None,
    # --- Dual-mode backend injection points -------------------------------
    # Local Mode backends
    ollama_client: OllamaClient | None = None,
    # Serverless Mode backends (accepted as pre-built instances so the module
    # imports and local mode works without the serverless client modules being
    # present).
    bedrock_client: Any | None = None,
    opensearch_client: Any | None = None,
    redis_cache: Any | None = None,
):
    """Create the dual-mode Strands Graph-based RAG Agent.

    This is the single wiring point for both deployment modes. It reads
    ``settings.deployment_mode`` **once** at construction time and injects the
    mode-appropriate backend clients into the shared routing. ``TopicChecker``
    and ``SecurityChecker`` are backend-agnostic (pure in-process
    keyword/pattern matching) and behave identically in both modes.

    Backend wiring by mode:

    - ``deployment_mode == "local"`` (default): ``OllamaClient`` +
      ``OpenSearchClient`` (local container, serving both KB retrieval and the
      Layer 4 semantic cache) + ``InMemoryCache`` (or local ``RedisCache`` when
      ``REDIS_CACHE_ENABLED`` is set).
    - ``deployment_mode == "serverless"``: ``BedrockClient`` +
      ``OpenSearchClient`` + ``RedisCache`` (OpenSearch ``rag-cache`` index as
      the L4 semantic cache).

    Args:
        settings: Application configuration (``settings.deployment_mode`` selects
            the backend set).
        fast_model_id: Model ID for topic/security checker agents
            (default: ``settings.ollama_model``). Local-mode only.
        rag_model_id: Model ID for the RAG worker agent
            (default: ``settings.ollama_model``). Local-mode only.
        ollama_client: Optional pre-initialized Ollama client (local mode).
            Created from settings when ``None``.
        bedrock_client: Optional pre-initialized Bedrock client (serverless mode).
        opensearch_client: Optional pre-initialized OpenSearch client
            (both modes).
        redis_cache: Optional pre-initialized Redis cache (serverless mode).

    Returns:
        A graph configuration dict containing the Strands agents, nodes, and
        routing functions.
    """

    # Read the deployment mode ONCE at construction. The node logic never
    # re-checks the mode per request.
    deployment_mode = settings.deployment_mode

    # The backend handles consumed by the shared routing. These are populated
    # per mode below. ``cache`` conforms to the CacheBackend protocol and
    # ``semantic_cache`` to the SemanticCache protocol so ``shared_route`` can
    # consume them through the shared interfaces regardless of mode.
    cache: Any
    semantic_cache: Any

    if deployment_mode == "serverless":
        llm, vector_store, cache, semantic_cache = _build_serverless_backends(
            settings,
            bedrock_client=bedrock_client,
            opensearch_client=opensearch_client,
            redis_cache=redis_cache,
        )
        # Bind the serverless clients to the shared closure names so
        # ``shared_route`` resolves consistently across modes.
        ollama_runtime = llm
        vector_db = vector_store
    else:  # "local"
        # Local Mode: Ollama + local OpenSearch (KB + L4 semantic cache) +
        # InMemoryCache (or local Redis). Prefer injected instances (tests /
        # reuse); otherwise construct from settings.
        ollama_runtime = ollama_client or OllamaClient(
            host=settings.ollama_host,
            timeout=settings.ollama_timeout,
            pool_size=settings.ollama_pool_size,
        )

        # Offline OpenSearch Local Mode: Ollama embeddings (768-dim) against a
        # local, plain-HTTP OpenSearch container. The SAME OpenSearchClient
        # serves KB retrieval (VectorStore) and the Layer 4 semantic cache
        # (SemanticCache), mirroring the serverless wiring. Imported lazily so
        # the module does not require opensearch-py at import time.
        from src.tools.opensearch_client import OpenSearchClient  # noqa: PLC0415

        os_client = opensearch_client or OpenSearchClient.for_local(settings)
        vector_db = os_client
        semantic_cache = os_client
        local_kb_index = settings.opensearch_kb_index

        # L2/L3 cache: InMemory by default (zero-setup), or a plain-TCP local
        # Redis for full prod-parity when REDIS_CACHE_ENABLED is set.
        if settings.redis_cache_enabled:
            from src.tools.redis_cache import RedisCache  # noqa: PLC0415

            cache = redis_cache or RedisCache.for_local(settings)
        else:
            cache = InMemoryCache(ttl=settings.embedding_cache_ttl)

    # Bind the resolved LLM client to the name the shared routing closures use.
    # In local mode this is the real Ollama client; the serverless branch binds
    # the Bedrock client to the same name.
    ollama_client = ollama_runtime

    # Use provided model IDs or fall back to settings
    fast_model = fast_model_id or settings.ollama_model
    rag_model = rag_model_id or settings.ollama_model

    logger.info(
        f"Creating RAG Graph (mode={deployment_mode}) with models: "
        f"fast={fast_model}, rag={rag_model}"
    )

    # Initialize web search client (only if enabled)
    web_search = None
    if settings.enable_web_search_supplement:
        web_search = WebSearchClient(timeout=settings.web_search_timeout)
        logger.info("Web search supplementary sources enabled")

    # NODE 1: Topic Checker
    def topic_check_node(state: dict) -> dict:
        """Check if query is in scope (about databases, RAG, vector search, etc.)."""
        question = state.get("question", "")
        logger.info(f"[TOPIC_CHECK] Processing: {question[:50]}...")

        # Record node execution start
        start_time = time.time()
        node_metrics = NodeMetrics(node_name="topic_check")

        is_in_scope = _is_question_in_scope(question, ollama_client, settings)

        result = ValidationResult(
            is_valid=is_in_scope,
            reason=(
                "Query is about vector databases/RAG" if is_in_scope else "Query is out of scope"
            ),
            category=None if is_in_scope else "out_of_scope",
        )

        state["topic_result"] = result

        # Record metrics
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        node_metrics.record_execution(duration_ms, success=is_in_scope)
        graph_metrics.node_metrics["topic_check"] = node_metrics

        logger.info(f"[TOPIC_CHECK] Result: is_valid={result.is_valid}")

        return state

    # NODE 2: Security Checker
    def security_check_node(state: dict) -> dict:
        """Check for security attacks and malicious input using LLM classification."""
        question = state.get("question", "")
        logger.info(f"[SECURITY_CHECK] Processing: {question[:50]}...")

        # Record node execution start
        start_time = time.time()
        node_metrics = NodeMetrics(node_name="security_check")

        # Use LLM-based classification with pattern matching fallback
        is_attack = _is_security_attack(question, ollama_client, settings)

        result = ValidationResult(
            is_valid=not is_attack,
            reason="Query is safe" if not is_attack else "Query contains security risk",
            category=None if not is_attack else "security_risk",
        )

        state["security_result"] = result

        # Record metrics
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        node_metrics.record_execution(duration_ms, success=not is_attack)
        graph_metrics.node_metrics["security_check"] = node_metrics

        logger.info(f"[SECURITY_CHECK] Result: is_valid={result.is_valid}")

        return state

    # NODE 4: Failure Handlers
    def reject_out_of_scope(state: dict) -> dict:
        """Handle out-of-scope queries."""
        state["final_answer"] = (
            "I can help with questions about vector databases, vector search, embeddings, and RAG."
        )
        state["final_sources"] = []
        state["final_confidence"] = 0.0
        logger.info("[REJECTION] Out-of-scope query")
        return state

    def reject_security_risk(state: dict) -> dict:
        """Handle security risks."""
        state["final_answer"] = (
            "I detected a security concern with your query. "
            "Please rephrase and ask a legitimate question."
        )
        state["final_sources"] = []
        state["final_confidence"] = 0.0
        logger.info("[REJECTION] Query was a security risk")
        return state

    def format_rag_result(state: dict) -> dict:
        """Format RAG worker result as final output."""
        rag_result = state.get("rag_result")
        if rag_result:
            state["final_answer"] = rag_result.answer
            state["final_sources"] = rag_result.sources
            state["final_confidence"] = rag_result.confidence_score
        return state

    # Routing conditions
    def check_topic_pass(state: dict) -> bool:
        """Route: if topic check passed, continue to security check."""
        result = state.get("topic_result")
        return result.is_valid if result else False

    def check_security_pass(state: dict) -> bool:
        """Route: if security check passed, continue to RAG worker."""
        result = state.get("security_result")
        return result.is_valid if result else False

    # Build the graph with real Strands agent instances and routing functions
    # Actual execution uses agent.invoke() calls with conditional routing

    graph_config: dict[str, Any] = {
        "nodes": {
            "topic_check": topic_check_node,
            "security_check": security_check_node,
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
            # Security Check → Rejection (if failed). Validated queries are
            # answered by the shared Cache → KB → Web routing (``shared_route``),
            # not an in-graph worker node.
            ("security_check", "reject_security_risk", lambda s: not check_security_pass(s)),
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

    # ========================================================================
    # RETURN CONFIG WITH REAL STRANDS AGENTS
    # ========================================================================

    # ========================================================================
    # SHARED RAGWORKER ROUTING (Cache → KB → Web Search)
    # ========================================================================
    # The shared, backend-agnostic routing (``route_rag_query``) honours the
    # three-tier decisions identically in both modes: 0.92 semantic threshold,
    # temporal-keyword cache bypass, 0.15 web-search fallback, force_web_search,
    # empty-answer fallback, and graceful degradation on Redis/OpenSearch
    # unavailability (Requirements 2.1-2.6, 3.6, 3.7). It is bound here to the
    # mode-appropriate backends and the configured thresholds so the Lambda
    # handler (serverless) can invoke it after TopicChecker/SecurityChecker pass
    # without re-reading settings or re-constructing clients.
    #
    # Both modes use the OpenSearch KB index (``settings.opensearch_kb_index``,
    # default ``rag-kb``). Local Mode answers are driven by
    # ``LocalOpenSearchAgent`` through this same ``shared_route``.
    if deployment_mode == "serverless":
        kb_index = settings.opensearch_kb_index
    else:
        # Local Mode: the OpenSearch KB index bound as local_kb_index above.
        kb_index = local_kb_index

    # Resolve the runtime-tunable Layer-3 thresholds ONCE at graph-build time
    # (= Lambda cold start, since the graph is a warm-context singleton). In
    # serverless mode with a thresholds table configured, DynamoDB rows override
    # the settings defaults so operators can retune without a redeploy; any
    # failure (or local mode, or no table) falls back to settings.py. See
    # src/tools/threshold_store.py and docs/ANTI_HALLUCINATION.md.
    if deployment_mode == "serverless" and getattr(settings, "dynamodb_thresholds_table", None):
        from src.tools.threshold_store import ThresholdStore  # noqa: PLC0415 (serverless-only)

        _thresholds = ThresholdStore(settings).resolve_all()
    else:
        _thresholds = {
            "answer_grounding_threshold": settings.answer_grounding_threshold,
            "answer_confidence_threshold": settings.answer_confidence_threshold,
            "web_search_fallback_threshold": settings.web_search_fallback_threshold,
            "response_cache_threshold": settings.response_cache_threshold,
            "grounding_retry_enabled": settings.grounding_retry_enabled,
            "grounding_retry_top_k_multiplier": settings.grounding_retry_top_k_multiplier,
        }

    def shared_route(
        question: str,
        top_k: int = rag_routing.DEFAULT_TOP_K,
        force_web_search: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metric_emitter: Any | None = None,
        history: list[dict] | None = None,
    ) -> rag_routing.RoutingResult:
        """Route a validated query through the shared Cache → KB → Web pipeline.

        Thin binding over :func:`src.agents.rag_routing.route_rag_query` that
        injects the mode-appropriate backends and configured thresholds.
        ``history`` (optional prior turns) is forwarded so generation has
        multi-turn conversational context.
        """
        return rag_routing.route_rag_query(
            question,
            llm=ollama_client,
            vector_store=vector_db,
            cache=cache,
            semantic_cache=semantic_cache,
            web_search=web_search,
            kb_index=kb_index,
            top_k=top_k,
            force_web_search=force_web_search,
            semantic_threshold=_thresholds["response_cache_threshold"],
            web_fallback_threshold=_thresholds["web_search_fallback_threshold"],
            grounding_threshold=_thresholds["answer_grounding_threshold"],
            confidence_threshold=_thresholds["answer_confidence_threshold"],
            grounding_retry_enabled=_thresholds["grounding_retry_enabled"],
            grounding_retry_top_k_multiplier=_thresholds["grounding_retry_top_k_multiplier"],
            temperature=(temperature if temperature is not None else settings.ollama_temperature),
            max_tokens=max_tokens,
            metric_emitter=metric_emitter,
            history=history,
        )

    graph_config = {
        "strands_agents": {
            "topic_agent": topic_agent,
            "security_agent": security_agent,
        },
        "nodes": {
            "topic_check": topic_check_node,
            "security_check": security_check_node,
            "reject_out_of_scope": reject_out_of_scope,
            "reject_security_risk": reject_security_risk,
            "format_result": format_rag_result,
        },
        "routing_functions": {
            "check_topic_pass": check_topic_pass,
            "check_security_pass": check_security_pass,
        },
        # Dual-mode wiring metadata. The mode is read once above; these injected
        # backend handles are exposed so the shared routing (task 8.1) and the
        # Lambda handler can consume them through the shared interfaces without
        # re-reading settings.deployment_mode or re-constructing clients.
        "deployment_mode": deployment_mode,
        "backends": {
            "llm": ollama_client,
            "vector_store": vector_db,
            "cache": cache,
            "semantic_cache": semantic_cache,
            "web_search": web_search,
        },
        "kb_index": kb_index,
        # Shared, backend-agnostic RAGWorker routing honouring the three-tier
        # decisions (Requirements 2.1-2.6, 3.6, 3.7). Invoked by the serverless
        # Lambda handler after the TopicChecker/SecurityChecker nodes pass.
        "shared_route": shared_route,
    }

    logger.info(
        f"✓ RAG Graph created (mode={deployment_mode}): TopicChecker → "
        "SecurityChecker → shared Cache→KB→Web routing"
    )

    return graph_config
