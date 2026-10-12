"""Shared, backend-agnostic RAGWorker routing (Cache → KB → Web Search).

This module is the **single, mode-independent** implementation of the three-tier
answer-routing pipeline described in the serverless-deployment design
("Request Flow" sections and design §5). It is written purely against the shared
backend *protocols* defined in :mod:`src.tools.interfaces`:

- :class:`~src.tools.interfaces.LLMClient`      — ``embed_text`` / ``generate``
- :class:`~src.tools.interfaces.VectorStore`    — ``knn_search``
- :class:`~src.tools.interfaces.CacheBackend`   — ``get/set_embedding`` / ``get/set_search_results``
- :class:`~src.tools.interfaces.SemanticCache`  — ``search_semantic_cache`` / ``store_semantic_cache``

Because it never references a concrete client, the same routing function serves
both deployment modes. In Serverless Mode it is wired into the graph by
``create_rag_graph`` (task 8.1) and invoked by the Lambda handler (task 10). In
Local Mode the long-running ``StrandsGraphRAGAgent.answer_question`` path is
left untouched (byte-for-byte equivalent to its historical behaviour), so this
module introduces no regression there; it is a shared capability the serverless
branch consumes.

Routing contract (Requirements 2.1–2.6, 3.6, 3.7)
-------------------------------------------------
Given a question that has already passed ``TopicChecker`` and
``SecurityChecker``, :func:`route_rag_query` decides the answer tier:

1. **force_web_search** (Req 2.6): bypass cache *and* KB, go straight to web
   search.
2. **Temporal-keyword bypass** (Req 2.3): queries containing temporal keywords
   ("latest", "recent", "2024", "today", "trending", …) skip the cache and do a
   fresh KB vector search.
3. **Cache check** (Req 2.1, 2.2): for non-temporal queries, check the Layer 2
   embedding cache, then the Layer 4 semantic cache. A semantic hit with
   similarity ≥ 0.92 **and non-empty answer** short-circuits and is returned
   without calling the LLM (Req 2.2). An entry that exists but has an **empty
   answer** triggers web search (Req 2.5).
4. **KB search** (Req 2.1): embed (cache-aware) and run a top-k vector search.
5. **Web-search fallback** (Req 2.4): when the average KB relevance is below
   0.15, invoke web search and return web-sourced results.
6. **Generation**: otherwise generate the answer from KB context via the LLM and
   populate the Layer 2/3/4 caches for subsequent hits.

Graceful degradation (Req 3.6, 3.7)
------------------------------------
If the Layer 2/3 cache backend (Redis) is unavailable the pipeline proceeds
without it and records ``cache/redis_unavailable``. If the Layer 4 semantic
cache (OpenSearch ``rag-cache``) is unreachable the pipeline skips Layer 4 and
proceeds directly to KB search, recording ``cache/opensearch_unavailable``.
Emitted metric names are collected on :class:`RoutingResult.metrics` so the
Lambda handler can forward them to CloudWatch; a caller-supplied
``metric_emitter`` callback is also invoked for live emission.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "RoutingResult",
    "route_rag_query",
    "is_time_sensitive_query",
    "average_relevance",
    "TEMPORAL_KEYWORDS",
    "CACHE_REDIS_UNAVAILABLE",
    "CACHE_OPENSEARCH_UNAVAILABLE",
]

# CloudWatch warning metric names (Requirements 3.6, 3.7).
CACHE_REDIS_UNAVAILABLE = "cache/redis_unavailable"
CACHE_OPENSEARCH_UNAVAILABLE = "cache/opensearch_unavailable"

# Default semantic-cache similarity threshold (Req 2.2) and web-search fallback
# threshold (Req 2.4). Callers normally pass the configured values from
# ``Settings``; these are the documented defaults.
DEFAULT_SEMANTIC_THRESHOLD = 0.92
DEFAULT_WEB_FALLBACK_THRESHOLD = 0.15
DEFAULT_TOP_K = 10

# Temporal keywords that force a cache bypass (Req 2.3). Mirrors the local
# ``StrandsGraphRAGAgent._is_time_sensitive_query`` keyword set so both modes
# classify time-sensitivity identically.
TEMPORAL_KEYWORDS: tuple[str, ...] = (
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
)


def is_time_sensitive_query(question: str) -> bool:
    """Return ``True`` when ``question`` contains a temporal keyword (Req 2.3).

    Case-insensitive substring match against :data:`TEMPORAL_KEYWORDS`, matching
    the Local Mode classifier so cache-bypass behaviour is identical in both
    modes.
    """
    lowered = question.lower()
    for keyword in TEMPORAL_KEYWORDS:
        if keyword in lowered:
            logger.debug("[ROUTING] Temporal keyword '%s' → cache bypass", keyword)
            return True
    return False


def average_relevance(sources: list[dict]) -> float:
    """Compute the average cosine-similarity relevance of KB ``sources``.

    Each source carries its similarity under the ``distance`` key (cosine
    similarity, higher = more relevant), matching both ``OpenSearchClient`` and
    the local Milvus result shape. Returns ``0.0`` when there are no scored
    sources so an empty/unscored result set triggers the web-search fallback.
    """
    scores = [float(s["distance"]) for s in sources if isinstance(s.get("distance"), (int, float))]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


@dataclass
class RoutingResult:
    """Outcome of :func:`route_rag_query`.

    Attributes:
        answer: The generated or cached answer text.
        sources: Source documents backing the answer (KB and/or web).
        tier_used: Which tier produced the answer — ``"cache"``, ``"kb"`` or
            ``"websearch"`` (matches the ``tier_used`` observability field).
        cache_hit: ``True`` when the answer came from the semantic cache.
        web_search_unavailable: ``True`` when a web search was attempted but
            returned no usable results (Req 10.3).
        confidence_score: Heuristic confidence (semantic-cache similarity or KB
            average relevance).
        metrics: Ordered list of CloudWatch warning-metric names emitted during
            routing (e.g. ``cache/redis_unavailable``), for the handler to
            forward.
    """

    answer: str
    sources: list[dict] = field(default_factory=list)
    tier_used: str = "kb"
    cache_hit: bool = False
    web_search_unavailable: bool = False
    confidence_score: float = 0.0
    metrics: list[str] = field(default_factory=list)


def _emit(
    metric: str,
    result: RoutingResult,
    metric_emitter: Callable[[str], None] | None,
) -> None:
    """Record a warning metric on the result and forward it to the emitter."""
    result.metrics.append(metric)
    logger.warning("[ROUTING] Emitting warning metric: %s", metric)
    if metric_emitter is not None:
        try:
            metric_emitter(metric)
        except Exception as exc:  # noqa: BLE001 - metric emission must never break routing
            logger.warning("[ROUTING] metric_emitter failed for %s: %s", metric, exc)


def _cache_available(cache: Any) -> bool:
    """Return whether the Layer 2/3 cache backend is usable (Req 3.6).

    A backend exposing ``redis_available`` (the ``RedisCache`` soft
    circuit-breaker) is considered available only when that flag is truthy;
    otherwise the mere presence of a backend means it is available (the local
    ``InMemoryCache`` is always available).
    """
    if cache is None:
        return False
    return bool(getattr(cache, "redis_available", True))


def _run_web_search(
    question: str,
    web_search: Any,
    kb_sources: list[dict],
    max_results: int = 3,
) -> tuple[list[dict], bool]:
    """Run a web search and normalise results to the shared source schema.

    Returns ``(web_sources, unavailable)``. ``unavailable`` is ``True`` when no
    usable web results were produced (API unavailable, timeout, or empty), per
    Requirement 10.3. Each returned source includes a non-empty ``url`` and a
    ``source_type`` of ``"web_search"`` to match the response schema (Req 10.5).
    """
    if web_search is None:
        return [], True

    try:
        results, status = web_search.search(query=question, max_results=max_results)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully (Req 10.3)
        logger.warning("[ROUTING] Web search failed: %s", exc)
        return [], True

    if status != "success" or not results:
        logger.info("[ROUTING] Web search produced no usable results (status=%s)", status)
        return [], True

    web_sources: list[dict] = []
    for item in results:
        web_sources.append(
            {
                "source_type": "web_search",
                "url": item.get("url", ""),
                "title": item.get("title", "Web Result"),
                "text": item.get("snippet", ""),
                "snippet": item.get("snippet", ""),
                "distance": 0.7,
                "metadata": {"source": "web", "title": item.get("title", "")},
            }
        )
    return web_sources, False


def _build_web_result(
    question: str,
    web_search: Any,
    kb_sources: list[dict],
    confidence: float,
) -> RoutingResult:
    """Produce a web-sourced :class:`RoutingResult`, degrading to KB on failure."""
    web_sources, unavailable = _run_web_search(question, web_search, kb_sources)
    if unavailable:
        # Req 10.3: return the best available KB answer with the unavailable flag.
        return RoutingResult(
            answer="",
            sources=kb_sources,
            tier_used="websearch",
            cache_hit=False,
            web_search_unavailable=True,
            confidence_score=confidence,
        )
    return RoutingResult(
        answer="",
        sources=web_sources,
        tier_used="websearch",
        cache_hit=False,
        web_search_unavailable=False,
        confidence_score=0.7,
    )


def route_rag_query(
    question: str,
    *,
    llm: Any,
    vector_store: Any,
    cache: Any,
    semantic_cache: Any,
    web_search: Any = None,
    kb_index: str,
    top_k: int = DEFAULT_TOP_K,
    force_web_search: bool = False,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
    web_fallback_threshold: float = DEFAULT_WEB_FALLBACK_THRESHOLD,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    metric_emitter: Callable[[str], None] | None = None,
) -> RoutingResult:
    """Route a (validated) query through Cache → KB → Web Search.

    This is the shared, backend-agnostic RAGWorker routing. It operates purely
    through the injected backend protocol clients, so it is identical in both
    deployment modes. ``TopicChecker``/``SecurityChecker`` run *before* this
    function; a rejected query never reaches here.

    Args:
        question: The user query (already in-scope and safe).
        llm: :class:`LLMClient` (``embed_text``/``generate``).
        vector_store: :class:`VectorStore` (``knn_search``).
        cache: :class:`CacheBackend` Layer 2/3 (may be unavailable → Req 3.6).
        semantic_cache: :class:`SemanticCache` Layer 4 (may be unavailable → Req 3.7).
        web_search: Optional web-search client (``search(query, max_results)``).
        kb_index: KB index/collection name for ``knn_search`` (e.g. ``rag-kb``).
        top_k: Vector-search top-k (validated by the handler to be 1–50).
        force_web_search: When ``True``, bypass cache + KB (Req 2.6).
        semantic_threshold: Layer 4 cache-hit similarity threshold (Req 2.2).
        web_fallback_threshold: KB relevance below which web search runs (Req 2.4).
        temperature: LLM sampling temperature for generation.
        max_tokens: Optional max-token cap for generation.
        metric_emitter: Optional callback invoked with each warning-metric name.

    Returns:
        A :class:`RoutingResult` describing the chosen tier and the answer.
    """
    result_metrics: RoutingResult = RoutingResult(answer="")  # scratch for early metrics

    # ---- Tier 0: force_web_search bypasses cache AND KB (Req 2.6) ----------
    if force_web_search:
        logger.info("[ROUTING] force_web_search=True → bypassing cache and KB")
        web_result = _build_web_result(question, web_search, kb_sources=[], confidence=0.0)
        web_result.metrics = result_metrics.metrics
        # Generate from whatever sources the web search produced (empty when the
        # search was unavailable; the unavailable flag is already set).
        web_result.answer = _generate_from_sources(
            llm, question, web_result.sources, temperature, max_tokens
        )
        return web_result

    is_temporal = is_time_sensitive_query(question)

    # ---- Compute (cache-aware) query embedding ----------------------------
    query_vector, redis_up = _get_query_embedding(question, llm, cache, bypass_cache=is_temporal)
    if cache is not None and not redis_up:
        _emit(CACHE_REDIS_UNAVAILABLE, result_metrics, metric_emitter)

    # ---- Tier 1: cache check for non-temporal queries (Req 2.1, 2.2, 2.5) --
    if not is_temporal:
        cache_result = _check_semantic_cache(
            question,
            query_vector,
            semantic_cache,
            semantic_threshold,
            result_metrics,
            metric_emitter,
        )
        if cache_result is not None:
            cached_entry, opensearch_up = cache_result
            if cached_entry is not None:
                answer = (cached_entry.get("response") or "").strip()
                if answer:
                    # Req 2.2: cache hit ≥ threshold with non-empty answer →
                    # return WITHOUT calling the LLM.
                    logger.info("[ROUTING] Semantic cache hit → returning cached answer")
                    return RoutingResult(
                        answer=answer,
                        sources=cached_entry.get("sources", []),
                        tier_used="cache",
                        cache_hit=True,
                        confidence_score=float(cached_entry.get("similarity", semantic_threshold)),
                        metrics=result_metrics.metrics,
                    )
                # Req 2.5: entry exists but empty answer → web search.
                logger.info("[ROUTING] Cached entry has empty answer → web search (Req 2.5)")
                web_result = _build_web_result(question, web_search, kb_sources=[], confidence=0.0)
                web_result.metrics = result_metrics.metrics
                web_result.answer = _generate_from_sources(
                    llm, question, web_result.sources, temperature, max_tokens
                )
                return web_result

    # ---- Tier 2: KB vector search (Req 2.1, 4.2) --------------------------
    kb_sources = _kb_search(
        question,
        query_vector,
        vector_store,
        cache,
        kb_index,
        top_k,
        is_temporal,
        result_metrics,
        metric_emitter,
    )
    relevance = average_relevance(kb_sources)
    logger.info(
        "[ROUTING] KB search: %d sources, avg relevance=%.3f (fallback threshold=%.3f)",
        len(kb_sources),
        relevance,
        web_fallback_threshold,
    )

    # ---- Tier 3: web-search fallback on low KB relevance (Req 2.4) --------
    if relevance < web_fallback_threshold:
        logger.info("[ROUTING] KB relevance below threshold → web search fallback (Req 2.4)")
        web_result = _build_web_result(question, web_search, kb_sources, confidence=relevance)
        web_result.metrics = result_metrics.metrics
        web_result.answer = _generate_from_sources(
            llm, question, web_result.sources or kb_sources, temperature, max_tokens
        )
        return web_result

    # ---- Generation from KB context, then populate caches -----------------
    answer = _generate_from_sources(llm, question, kb_sources, temperature, max_tokens)

    _populate_caches(
        question,
        query_vector,
        kb_sources,
        answer,
        cache,
        semantic_cache,
        top_k,
        result_metrics,
        metric_emitter,
    )

    return RoutingResult(
        answer=answer,
        sources=kb_sources,
        tier_used="kb",
        cache_hit=False,
        confidence_score=relevance,
        metrics=result_metrics.metrics,
    )


# ---------------------------------------------------------------------------
# Internal helpers (each operates only through the shared protocols)
# ---------------------------------------------------------------------------


def _get_query_embedding(
    question: str,
    llm: Any,
    cache: Any,
    bypass_cache: bool,
) -> tuple[list[float], bool]:
    """Return ``(embedding, redis_available)`` using the L2 cache when possible.

    Checks the Layer 2 embedding cache first (Req 3.4) unless ``bypass_cache``
    (temporal query). On a miss, embeds via the LLM and stores to L2. If the
    cache backend errors / is unavailable, ``redis_available`` is ``False`` so
    the caller can emit ``cache/redis_unavailable`` (Req 3.6).
    """
    redis_available = _cache_available(cache)
    cache_key = _embedding_cache_key(cache, question)

    if not bypass_cache and redis_available and cache_key is not None:
        try:
            cached = cache.get_embedding(cache_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ROUTING] L2 get_embedding failed: %s", exc)
            cached = None
            redis_available = False
        if cached:
            logger.debug("[ROUTING] L2 embedding cache hit")
            return [float(x) for x in cached], _cache_available(cache)

    vector = [float(x) for x in llm.embed_text(question)]

    if not bypass_cache and redis_available and cache_key is not None:
        try:
            cache.set_embedding(cache_key, vector)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ROUTING] L2 set_embedding failed: %s", exc)
            redis_available = False

    return vector, _cache_available(cache) and redis_available


def _check_semantic_cache(
    question: str,
    query_vector: list[float],
    semantic_cache: Any,
    threshold: float,
    result: RoutingResult,
    metric_emitter: Callable[[str], None] | None,
) -> tuple[dict | None, bool] | None:
    """Query the Layer 4 semantic cache, degrading gracefully (Req 3.7).

    Returns:
        - ``(entry, True)`` where ``entry`` is the best cache entry (or ``None``
          on a clean miss) when the cache was reachable, or
        - ``None`` when the semantic cache is unavailable/unreachable, after
          emitting ``cache/opensearch_unavailable``.
    """
    if semantic_cache is None:
        return (None, True)

    try:
        entry = _call_search_semantic_cache(semantic_cache, question, query_vector, threshold)
    except Exception as exc:  # noqa: BLE001 - Req 3.7 graceful degradation
        logger.warning("[ROUTING] Layer 4 semantic cache unavailable: %s", exc)
        _emit(CACHE_OPENSEARCH_UNAVAILABLE, result, metric_emitter)
        return None

    return (entry, True)


def _call_search_semantic_cache(
    semantic_cache: Any,
    question: str,
    query_vector: list[float],
    threshold: float,
) -> dict | None:
    """Call ``search_semantic_cache`` tolerating both protocol signatures.

    The ``SemanticCache`` protocol (and ``SemanticCacheAdapter``) expose
    ``search_semantic_cache(question, query_vector, threshold)`` while the
    serverless ``OpenSearchClient`` exposes
    ``search_semantic_cache(query_vector, threshold)`` (no ``question``). This
    helper adapts to whichever signature the injected client provides so the
    shared routing works unchanged in both modes.
    """
    result: dict | None
    try:
        result = semantic_cache.search_semantic_cache(
            question=question, query_vector=query_vector, threshold=threshold
        )
    except TypeError:
        # Serverless OpenSearchClient signature: (query_vector, threshold).
        result = semantic_cache.search_semantic_cache(query_vector, threshold)
    return result


def _kb_search(
    question: str,
    query_vector: list[float],
    vector_store: Any,
    cache: Any,
    kb_index: str,
    top_k: int,
    bypass_cache: bool,
    result: RoutingResult,
    metric_emitter: Callable[[str], None] | None,
) -> list[dict]:
    """Run the KB vector search with L3 result caching (Req 2.1, 3.5, 4.2).

    For non-temporal queries the Layer 3 search-result cache is consulted first
    and populated on a miss. The vector search itself returns sources ranked by
    cosine similarity (``distance`` key). On any vector-store failure an empty
    list is returned so the caller falls back to web search.
    """
    search_key = _search_cache_key(cache, question, top_k)

    if not bypass_cache and _cache_available(cache) and search_key is not None:
        try:
            cached = cache.get_search_results(search_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ROUTING] L3 get_search_results failed: %s", exc)
            cached = None
            if cache is not None:
                _emit(CACHE_REDIS_UNAVAILABLE, result, metric_emitter)
        if cached:
            logger.debug("[ROUTING] L3 search-result cache hit")
            return list(cached)

    try:
        sources = vector_store.knn_search(kb_index, query_vector, top_k)
    except Exception as exc:  # noqa: BLE001 - degrade to web fallback
        logger.warning("[ROUTING] KB vector search failed: %s", exc)
        return []

    sources = list(sources or [])

    if not bypass_cache and _cache_available(cache) and search_key is not None and sources:
        try:
            cache.set_search_results(search_key, sources)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ROUTING] L3 set_search_results failed: %s", exc)

    return sources


def _populate_caches(
    question: str,
    query_vector: list[float],
    kb_sources: list[dict],
    answer: str,
    cache: Any,
    semantic_cache: Any,
    top_k: int,
    result: RoutingResult,
    metric_emitter: Callable[[str], None] | None,
) -> None:
    """Store the fresh answer in the Layer 4 semantic cache (best-effort)."""
    if not answer or semantic_cache is None:
        return
    try:
        semantic_cache.store_semantic_cache(
            question=question,
            query_vector=query_vector,
            answer=answer,
            sources=kb_sources,
        )
    except Exception as exc:  # noqa: BLE001 - never fail the request on cache write
        logger.warning("[ROUTING] Layer 4 store_semantic_cache failed: %s", exc)


def _generate_from_sources(
    llm: Any,
    question: str,
    sources: list[dict],
    temperature: float,
    max_tokens: int | None,
) -> str:
    """Generate an answer from retrieved ``sources`` via the LLM (Req 5.6).

    Uses the LLM client's own prompt formatting when available
    (``BedrockClient.format_rag_prompt``), otherwise falls back to the shared
    prompt template, so the retrieved context is always included in the prompt.
    """
    prompt = _format_prompt(llm, question, sources)
    try:
        return str(llm.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens))
    except TypeError:
        # Protocol-minimal LLMs may not accept max_tokens=None kwargs.
        return str(llm.generate(prompt))


def _format_prompt(llm: Any, question: str, sources: list[dict]) -> str:
    """Build the RAG prompt, preferring the LLM client's own formatter."""
    formatter = getattr(llm, "format_rag_prompt", None)
    if callable(formatter):
        return str(formatter(question, sources))

    # Fallback: shared prompt template (same structure as Local Mode).
    from src.agents import prompts

    context_parts = []
    for i, source in enumerate(sources, 1):
        text = source.get("text") or source.get("snippet") or ""
        metadata = source.get("metadata") or {}
        title = metadata.get("title") or source.get("title") or ""
        context_parts.append(f"[{i}] {title}\n{text}" if title else f"[{i}] {text}")
    context = "\n\n".join(context_parts)

    system_instructions = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
        formatting_rules=prompts.FORMATTING_RULES
    )
    return prompts.format_rag_prompt(
        system_instructions=system_instructions,
        question=question,
        context=context,
    )


def _embedding_cache_key(cache: Any, question: str) -> str | None:
    """Build the L2 cache key, using the backend's hasher when available."""
    if cache is None:
        return None
    key_fn = getattr(cache, "embedding_key", None)
    if callable(key_fn):
        return str(key_fn(question))
    return f"emb:{question.strip().lower()}"


def _search_cache_key(cache: Any, question: str, top_k: int) -> str | None:
    """Build the L3 cache key, using the backend's hasher when available."""
    if cache is None:
        return None
    key_fn = getattr(cache, "search_results_key", None)
    if callable(key_fn):
        return str(key_fn(question, top_k))
    return f"srch:{question.strip().lower()}:{top_k}"
