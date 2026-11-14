"""Tests for the LocalOpenSearchAgent facade (Phase 1 of the migration).

The facade is the local-mode agent that delegates answering to the graph's
``shared_route``. These tests verify delegation and
the degraded-mode behavior when the local OpenSearch container is unreachable,
using injected fakes (no live OpenSearch/Ollama).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.agents.guardrails import ANCHORS, ScopeGate
from src.config.settings import Settings


def _settings() -> Settings:
    s = Settings()
    s.deployment_mode = "local"
    s.local_vector_backend = "opensearch"
    return s


class _FakeRoutingResult:
    def __init__(self) -> None:
        self.answer = "OpenSearch-backed answer"
        self.sources = [{"text": "ctx", "distance": 0.9}]
        self.cache_hit = False
        self.tier_used = "kb"


def _scope_stub() -> ScopeGate:
    """Gate where only anchor descriptions are in scope (deterministic, no model)."""
    return ScopeGate(
        embed=lambda text: [1.0, 0.0] if text in ANCHORS else [0.0, 1.0],
        threshold=0.5,
    )


def _fake_graph(route_calls: list[dict]) -> dict:
    def shared_route(question: str, **kwargs: Any) -> _FakeRoutingResult:
        route_calls.append({"question": question, **kwargs})
        return _FakeRoutingResult()

    return {
        "shared_route": shared_route,
        "backends": {"web_search": None},
        "scope_gate": _scope_stub(),
    }


@pytest.mark.asyncio
async def test_answer_question_delegates_to_shared_route() -> None:
    route_calls: list[dict] = []
    with (
        patch("src.tools.opensearch_client.OpenSearchClient.for_local") as mock_for_local,
        patch(
            "src.agents.strands_graph_agent.create_rag_graph", return_value=_fake_graph(route_calls)
        ),
    ):
        mock_for_local.return_value.ensure_indexes.return_value = None
        from src.agents.local_opensearch_agent import LocalOpenSearchAgent

        agent = LocalOpenSearchAgent(_settings())
        out = await agent.answer_question(question="what is HNSW?", top_k=7)

    assert out == {
        "answer": "OpenSearch-backed answer",
        "sources": [{"text": "ctx", "distance": 0.9}],
    }
    assert agent.initialization_error is None
    assert route_calls == [
        {"question": "what is HNSW?", "top_k": 7, "temperature": None, "max_tokens": None}
    ]


@pytest.mark.asyncio
async def test_stream_answer_yields_answer_and_sets_sources() -> None:
    route_calls: list[dict] = []
    with (
        patch("src.tools.opensearch_client.OpenSearchClient.for_local") as mock_for_local,
        patch(
            "src.agents.strands_graph_agent.create_rag_graph", return_value=_fake_graph(route_calls)
        ),
    ):
        mock_for_local.return_value.ensure_indexes.return_value = None
        from src.agents.local_opensearch_agent import LocalOpenSearchAgent

        agent = LocalOpenSearchAgent(_settings())
        chunks = [c async for c in agent.stream_answer(question="q")]

    assert chunks == ["OpenSearch-backed answer"]
    assert agent._last_stream_sources == [{"text": "ctx", "distance": 0.9}]


@pytest.mark.asyncio
async def test_force_web_rejects_out_of_scope_before_search_or_routing() -> None:
    route_calls: list[dict] = []
    with (
        patch("src.tools.opensearch_client.OpenSearchClient.for_local") as mock_for_local,
        patch(
            "src.agents.strands_graph_agent.create_rag_graph", return_value=_fake_graph(route_calls)
        ),
    ):
        mock_for_local.return_value.ensure_indexes.return_value = None
        from src.agents.local_opensearch_agent import LocalOpenSearchAgent

        agent = LocalOpenSearchAgent(_settings())
        chunks = [
            chunk
            async for chunk in agent.stream_answer_web_search_only(
                question="Who is the US president?"
            )
        ]

    assert chunks == [
        "I can help with questions about vector databases, vector search, embeddings, and RAG."
    ]
    assert route_calls == []


def test_degraded_mode_when_opensearch_unavailable() -> None:
    route_calls: list[dict] = []
    with (
        patch(
            "src.tools.opensearch_client.OpenSearchClient.for_local",
            side_effect=RuntimeError("conn refused"),
        ),
        patch(
            "src.agents.strands_graph_agent.create_rag_graph", return_value=_fake_graph(route_calls)
        ),
    ):
        from src.agents.local_opensearch_agent import LocalOpenSearchAgent

        agent = LocalOpenSearchAgent(_settings())

    assert agent.initialization_error is not None
    assert "OpenSearch connection failed" in agent.initialization_error
    assert agent.opensearch_healthy() is False
    assert agent.vector_db is None
