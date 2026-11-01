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
    """Relevance above threshold never reaches the web-fallback gate."""
    strong_kb = [
        {"id": "1", "text": "Milvus is a vector database.", "metadata": {}, "distance": 0.9}
    ]
    llm = _FakeLLM()

    result = _route(llm, _VectorStore(strong_kb), _UnavailableWebSearch())

    assert result.answer == "GENERATED ANSWER"
    assert result.tier_used == "kb"
    assert llm.generate_called is True


def test_has_usable_grounding_detects_text_and_snippet() -> None:
    """The grounding helper treats any non-empty text/snippet as usable."""
    assert rag_routing._has_usable_grounding([{"text": "hello"}]) is True
    assert rag_routing._has_usable_grounding([{"snippet": "hi"}]) is True
    assert rag_routing._has_usable_grounding([{"text": "", "snippet": ""}]) is False
    assert rag_routing._has_usable_grounding([]) is False
    assert rag_routing._has_usable_grounding(["not a dict"]) is False  # type: ignore[list-item]
