"""Unit tests for the anti-hallucination grounding gate in ``route_rag_query``.

These cover the behaviour added to make the shared router honest when neither
the knowledge base nor web search produced usable grounding: instead of asking
the LLM to generate an answer from weak/empty context (which invites
fabrication), the router returns :data:`NO_GROUNDING_ANSWER`.

The router is written purely against the backend *protocols*, so these tests
use lightweight in-memory fakes and never require Milvus/OpenSearch/Redis.
"""

from __future__ import annotations

from typing import Any

from src.agents import rag_routing
from src.agents.rag_routing import NO_GROUNDING_ANSWER, route_rag_query


class _FakeLLM:
    """Minimal LLMClient: records whether ``generate`` was ever called."""

    def __init__(self) -> None:
        self.generate_called = False

    def embed_text(self, _text: str) -> list[float]:
        return [0.0] * 8

    def generate(self, prompt: str, **_kwargs: Any) -> str:  # noqa: D401
        self.generate_called = True
        return "GENERATED ANSWER"


class _VectorStore:
    """VectorStore fake returning a fixed KB result set."""

    def __init__(self, results: list[dict]) -> None:
        self._results = results

    def knn_search(self, _index: str, _vector: list[float], _k: int) -> list[dict]:
        return list(self._results)


class _UnavailableWebSearch:
    """Web search that always reports itself unavailable (no usable results)."""

    def search(self, query: str, max_results: int = 3) -> tuple[list[dict], str]:
        return [], "api_unavailable"


class _WorkingWebSearch:
    """Web search that returns one usable, text-bearing result."""

    def search(self, query: str, max_results: int = 3) -> tuple[list[dict], str]:
        return (
            [{"title": "Pinecone", "url": "https://example.com", "snippet": "A vector DB."}],
            "success",
        )


def _route(llm: _FakeLLM, vector_store: _VectorStore, web_search: Any) -> rag_routing.RoutingResult:
    """Invoke the router with caches disabled so only KB/web tiers run."""
    return route_rag_query(
        "what is some obscure thing",
        llm=llm,
        vector_store=vector_store,
        cache=None,
        semantic_cache=None,
        web_search=web_search,
        kb_index="rag-kb",
        web_fallback_threshold=0.15,
    )


def test_low_relevance_and_web_unavailable_returns_honest_refusal() -> None:
    """KB below threshold + web unavailable + no usable sources → refusal, no LLM call."""
    # A single weak KB hit (relevance 0.05 < 0.15 threshold) with empty text.
    weak_kb = [{"id": "1", "text": "", "metadata": {}, "distance": 0.05}]
    llm = _FakeLLM()

    result = _route(llm, _VectorStore(weak_kb), _UnavailableWebSearch())

    assert result.answer == NO_GROUNDING_ANSWER
    assert result.web_search_unavailable is True
    assert llm.generate_called is False  # never asked to fabricate


def test_low_relevance_but_web_unavailable_with_usable_kb_text_still_generates() -> None:
    """If the weak KB hit still carries text, we have something to ground on → generate."""
    weak_but_text = [
        {"id": "1", "text": "Some partially relevant content.", "metadata": {}, "distance": 0.05}
    ]
    llm = _FakeLLM()

    result = _route(llm, _VectorStore(weak_but_text), _UnavailableWebSearch())

    assert result.answer == "GENERATED ANSWER"
    assert llm.generate_called is True


def test_low_relevance_with_working_web_search_generates_from_web() -> None:
    """Web search succeeding provides grounding → generate, not refuse."""
    weak_kb = [{"id": "1", "text": "", "metadata": {}, "distance": 0.05}]
    llm = _FakeLLM()

    result = _route(llm, _VectorStore(weak_kb), _WorkingWebSearch())

    assert result.answer == "GENERATED ANSWER"
    assert result.web_search_unavailable is False
    assert llm.generate_called is True


def test_strong_kb_relevance_bypasses_gate_and_generates() -> None:
    """Relevance above threshold never reaches the web-fallback refusal gate."""
    strong_kb = [
        {"id": "1", "text": "Milvus is a vector database.", "metadata": {}, "distance": 0.9}
    ]
    llm = _FakeLLM()

    result = _route(llm, _VectorStore(strong_kb), _UnavailableWebSearch())

    # Generation ran and the KB tier produced the answer. (The fixed fake answer
    # "GENERATED ANSWER" shares no content words with the source, so the
    # post-generation grounding check appends its caveat — expected here; the
    # grounding behaviour itself is covered by the dedicated tests below.)
    assert result.answer.startswith("GENERATED ANSWER")
    assert result.tier_used == "kb"
    assert result.answer != NO_GROUNDING_ANSWER
    assert llm.generate_called is True


def test_has_usable_grounding_detects_text_and_snippet() -> None:
    """The grounding helper treats any non-empty text/snippet as usable."""
    assert rag_routing._has_usable_grounding([{"text": "hello"}]) is True
    assert rag_routing._has_usable_grounding([{"snippet": "hi"}]) is True
    assert rag_routing._has_usable_grounding([{"text": "", "snippet": ""}]) is False
    assert rag_routing._has_usable_grounding([]) is False
    assert rag_routing._has_usable_grounding(["not a dict"]) is False  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Post-generation grounding check (item 3)
# ---------------------------------------------------------------------------


class _EchoLLM:
    """LLMClient whose ``generate`` returns a fixed, caller-controlled answer."""

    def __init__(self, answer: str) -> None:
        self._answer = answer

    def embed_text(self, _text: str) -> list[float]:
        return [0.0] * 8

    def generate(self, prompt: str, **_kwargs: Any) -> str:
        return self._answer


def _route_with_answer(
    answer: str, kb_sources: list[dict], grounding_threshold: float = 0.35
) -> rag_routing.RoutingResult:
    """Route with strong KB relevance so the KB-generation path runs."""
    return route_rag_query(
        "tell me about vector indexing",
        llm=_EchoLLM(answer),
        vector_store=_VectorStore(kb_sources),
        cache=None,
        semantic_cache=None,
        web_search=None,
        kb_index="rag-kb",
        grounding_threshold=grounding_threshold,
    )


def test_compute_grounding_score_full_support() -> None:
    """Every answer content word present in sources → score 1.0."""
    sources = [{"text": "Milvus supports HNSW and IVF indexing for vector search."}]
    score = rag_routing.compute_grounding_score(
        "Milvus supports HNSW indexing for vector search", sources
    )
    assert score == 1.0


def test_compute_grounding_score_no_support() -> None:
    """Answer content words absent from sources → low score."""
    sources = [{"text": "Milvus supports HNSW indexing."}]
    score = rag_routing.compute_grounding_score(
        "Pinecone offers serverless pods priced per hour quarterly", sources
    )
    assert score < 0.35


def test_compute_grounding_score_empty_answer_is_fully_grounded() -> None:
    """No content words to verify → treated as grounded (1.0), not a false alarm."""
    assert rag_routing.compute_grounding_score("the and of to", [{"text": "anything"}]) == 1.0


def test_compute_grounding_score_no_sources_is_zero() -> None:
    """Content-bearing answer with no source text → 0.0."""
    assert rag_routing.compute_grounding_score("Milvus indexing", []) == 0.0


def test_grounded_answer_passes_without_caveat() -> None:
    """A well-supported KB answer is returned unchanged with a high score."""
    kb_sources = [
        {
            "id": "1",
            "text": "Milvus supports HNSW and IVF indexing for fast vector search.",
            "metadata": {},
            "distance": 0.9,
        }
    ]
    answer = "Milvus supports HNSW indexing for fast vector search."

    result = _route_with_answer(answer, kb_sources)

    assert result.answer == answer  # no caveat appended
    assert rag_routing.LOW_GROUNDING_CAVEAT not in result.answer
    assert result.grounding_score >= 0.35
    assert rag_routing.ANSWER_LOW_GROUNDING not in result.metrics


def test_ungrounded_answer_gets_caveat_and_metric() -> None:
    """A KB answer unsupported by sources keeps the text but is flagged."""
    kb_sources = [
        {
            "id": "1",
            "text": "Milvus supports HNSW and IVF indexing for vector search.",
            "metadata": {},
            "distance": 0.9,
        }
    ]
    # Fabricated answer sharing almost no content words with the source.
    answer = "Pinecone charges forty dollars monthly for serverless replica pods."

    result = _route_with_answer(answer, kb_sources)

    assert result.answer.startswith(answer)
    assert rag_routing.LOW_GROUNDING_CAVEAT in result.answer
    assert rag_routing.ANSWER_LOW_GROUNDING in result.metrics
    assert result.grounding_score < 0.35
    # Confidence is pulled down to reflect the weak grounding.
    assert result.confidence_score <= result.grounding_score


# ---------------------------------------------------------------------------
# Temporal keyword matching — word boundaries (finding M1)
# ---------------------------------------------------------------------------


def test_temporal_keyword_is_word_boundary_not_substring() -> None:
    """'new' matches a standalone word but NOT inside 'renew'/'newcomer'."""
    # True positives: whole-word temporal terms.
    assert rag_routing.is_time_sensitive_query("what's new in Milvus") is True
    assert rag_routing.is_time_sensitive_query("the newest HNSW params") is True
    assert rag_routing.is_time_sensitive_query("latest release notes") is True

    # False positives eliminated: 'new' embedded in a non-temporal word.
    assert rag_routing.is_time_sensitive_query("how do I renew my index?") is False
    assert rag_routing.is_time_sensitive_query("a newcomer to vector search") is False

    # Non-temporal query stays non-temporal.
    assert rag_routing.is_time_sensitive_query("tell me about Milvus") is False


# ---------------------------------------------------------------------------
# Answer quality: grounding + confidence caveats (finding H2)
# ---------------------------------------------------------------------------

_QUALITY_SOURCES = [
    {"text": "Milvus supports HNSW and IVF indexing for fast vector search.", "distance": 0.9}
]


def test_quality_grounded_high_confidence_no_caveat() -> None:
    """A supported, confident answer is returned unchanged."""
    answer = "Milvus supports HNSW indexing for fast vector search."
    out, conf, ground, metric = rag_routing.evaluate_answer_quality(answer, _QUALITY_SOURCES, 0.8)
    assert out == answer
    assert metric is None
    assert conf == 0.8
    assert ground >= 0.35


def test_quality_ungrounded_gets_only_grounding_caveat() -> None:
    """Low grounding wins over low confidence; only the grounding caveat fires."""
    answer = "Pinecone charges forty dollars monthly for serverless replica pods."
    out, conf, _ground, metric = rag_routing.evaluate_answer_quality(
        answer,
        _QUALITY_SOURCES,
        0.2,  # confidence also low
    )
    assert metric == rag_routing.ANSWER_LOW_GROUNDING
    assert rag_routing.LOW_GROUNDING_CAVEAT in out
    assert rag_routing.LOW_CONFIDENCE_CAVEAT not in out  # mutually exclusive


def test_quality_grounded_low_confidence_gets_only_confidence_caveat() -> None:
    """When grounding passes but confidence is low, only the confidence caveat fires."""
    answer = "Milvus supports HNSW indexing for fast vector search."
    out, _conf, _ground, metric = rag_routing.evaluate_answer_quality(answer, _QUALITY_SOURCES, 0.3)
    assert metric == rag_routing.ANSWER_LOW_CONFIDENCE
    assert rag_routing.LOW_CONFIDENCE_CAVEAT in out
    assert rag_routing.LOW_GROUNDING_CAVEAT not in out  # mutually exclusive


def test_quality_empty_answer_untouched() -> None:
    """Empty answers (system-message paths) are never annotated."""
    out, conf, ground, metric = rag_routing.evaluate_answer_quality("", _QUALITY_SOURCES, 0.1)
    assert out == ""
    assert metric is None
    assert ground == 1.0


def test_quality_confidence_threshold_is_configurable() -> None:
    """A lower threshold suppresses the confidence caveat for the same answer."""
    answer = "Milvus supports HNSW indexing for fast vector search."
    # confidence 0.4 is below the 0.45 default but above a 0.3 custom threshold.
    _, _, _, metric_default = rag_routing.evaluate_answer_quality(answer, _QUALITY_SOURCES, 0.4)
    _, _, _, metric_custom = rag_routing.evaluate_answer_quality(
        answer, _QUALITY_SOURCES, 0.4, confidence_threshold=0.3
    )
    assert metric_default == rag_routing.ANSWER_LOW_CONFIDENCE
    assert metric_custom is None


# ---------------------------------------------------------------------------
# Soft-steer: one widened-retrieval retry on weak grounding (item 2)
# ---------------------------------------------------------------------------


class _TopKAwareVectorStore:
    """VectorStore returning weak results at the base top_k and a strong,
    well-grounded result once top_k is widened — simulating the supporting chunk
    sitting just outside the original retrieval window."""

    STRONG_TEXT = "Milvus supports HNSW and IVF indexing for fast vector search."

    def __init__(self, base_top_k: int) -> None:
        self._base_top_k = base_top_k
        self.calls: list[int] = []

    def knn_search(self, _index: str, _vector: list[float], k: int) -> list[dict]:
        self.calls.append(k)
        if k <= self._base_top_k:
            # Weak but text-bearing: relevance passes the web-fallback gate, but
            # the content won't ground the strong answer.
            return [{"id": "w", "text": "Unrelated filler about postage rates.", "distance": 0.9}]
        return [{"id": "s", "text": self.STRONG_TEXT, "distance": 0.95}]


class _SourceAwareLLM:
    """LLM whose answer echoes its retrieved source text, so grounding reflects
    which retrieval attempt produced the context."""

    def __init__(self) -> None:
        self.generate_calls = 0

    def embed_text(self, _text: str) -> list[float]:
        return [0.0] * 8

    def generate(self, prompt: str, **_kwargs: Any) -> str:
        self.generate_calls += 1
        # The source text is embedded in the RAG prompt; echo the strong answer
        # when the strong chunk is present, otherwise a non-grounded answer.
        if "HNSW and IVF indexing" in prompt:
            return "Milvus supports HNSW and IVF indexing for fast vector search."
        return "Pinecone charges monthly for serverless replica pods."


def _route_retry(
    vector_store: Any,
    llm: Any,
    *,
    enabled: bool = True,
    multiplier: int = 2,
    top_k: int = rag_routing.DEFAULT_TOP_K,
) -> rag_routing.RoutingResult:
    return route_rag_query(
        "tell me about milvus indexing",
        llm=llm,
        vector_store=vector_store,
        cache=None,
        semantic_cache=None,
        web_search=None,
        kb_index="rag-kb",
        top_k=top_k,
        grounding_retry_enabled=enabled,
        grounding_retry_top_k_multiplier=multiplier,
    )


def test_grounding_retry_recovers_with_widened_top_k() -> None:
    """Weak first attempt + strong retry → retry answer kept, no caveat, metric emitted."""
    store = _TopKAwareVectorStore(base_top_k=rag_routing.DEFAULT_TOP_K)
    llm = _SourceAwareLLM()

    result = _route_retry(store, llm)

    # Searched twice: base top_k, then widened.
    assert store.calls == [rag_routing.DEFAULT_TOP_K, rag_routing.DEFAULT_TOP_K * 2]
    assert llm.generate_calls == 2
    # The recovered answer is well grounded → no caveat.
    assert rag_routing.LOW_GROUNDING_CAVEAT not in result.answer
    assert result.grounding_score >= 0.35
    assert rag_routing.ANSWER_GROUNDING_RETRY in result.metrics


def test_grounding_retry_disabled_skips_second_search() -> None:
    """With the retry off, a single search runs and the caveat is applied."""
    store = _TopKAwareVectorStore(base_top_k=rag_routing.DEFAULT_TOP_K)
    llm = _SourceAwareLLM()

    result = _route_retry(store, llm, enabled=False)

    assert store.calls == [rag_routing.DEFAULT_TOP_K]  # no retry
    assert llm.generate_calls == 1
    assert rag_routing.LOW_GROUNDING_CAVEAT in result.answer
    assert rag_routing.ANSWER_GROUNDING_RETRY not in result.metrics


def test_grounding_retry_top_k_capped_at_max() -> None:
    """The widened top_k never exceeds MAX_TOP_K even with a large multiplier."""
    # base below max, but base*multiplier would exceed it.
    store = _TopKAwareVectorStore(base_top_k=30)
    llm = _SourceAwareLLM()

    result = _route_retry(store, llm, multiplier=10, top_k=30)

    assert store.calls == [30, rag_routing.MAX_TOP_K]  # capped, not 300
    assert rag_routing.ANSWER_GROUNDING_RETRY in result.metrics
    assert result is not None


def test_grounding_retry_not_attempted_at_max_top_k() -> None:
    """When top_k is already at MAX_TOP_K there is no room to widen → no retry."""
    store = _TopKAwareVectorStore(base_top_k=rag_routing.MAX_TOP_K)
    llm = _SourceAwareLLM()

    result = _route_retry(store, llm, top_k=rag_routing.MAX_TOP_K)

    assert store.calls == [rag_routing.MAX_TOP_K]  # single search
    assert rag_routing.ANSWER_GROUNDING_RETRY not in result.metrics
    assert rag_routing.LOW_GROUNDING_CAVEAT in result.answer
