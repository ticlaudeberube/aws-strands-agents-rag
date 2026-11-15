"""Tests that the LocalOpenSearchAgent facade forwards conversation history.

Each answer method must pass ``history`` to the shared route, and the web-only
path must pass it to the scope gate. Existing delegation tests in
``test_local_opensearch_agent.py`` cover calls without history.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.config.settings import Settings

HISTORY = [
    {"role": "user", "content": "What is a vector database?"},
    {"role": "assistant", "content": "A store for embeddings."},
]
FOLLOW_UP = "What can I do with it?"


class _FakeRoutingResult:
    def __init__(self) -> None:
        self.answer = "answer"
        self.sources = [{"text": "ctx", "distance": 0.9}]
        self.cache_hit = False
        self.tier_used = "kb"


class _RecordingScopeGate:
    """Scope gate that accepts everything and records its calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    def allows(
        self,
        question: str,
        query_vector: Any = None,
        history: Any = None,
    ) -> bool:
        self.calls.append((question, query_vector, history))
        return True


def _settings() -> Settings:
    s = Settings()
    s.deployment_mode = "local"
    s.local_vector_backend = "opensearch"
    return s


def _graph(route_calls: list[dict], gate: _RecordingScopeGate) -> dict:
    def shared_route(question: str, **kwargs: Any) -> _FakeRoutingResult:
        route_calls.append({"question": question, **kwargs})
        return _FakeRoutingResult()

    # A non-None web backend lets the web-only path reach the shared route.
    return {
        "shared_route": shared_route,
        "backends": {"web_search": object()},
        "scope_gate": gate,
    }


def _agent(route_calls: list[dict], gate: _RecordingScopeGate) -> Any:
    with (
        patch("src.tools.opensearch_client.OpenSearchClient.for_local") as mock_for_local,
        patch(
            "src.agents.strands_graph_agent.create_rag_graph",
            return_value=_graph(route_calls, gate),
        ),
    ):
        mock_for_local.return_value.ensure_indexes.return_value = None
        from src.agents.local_opensearch_agent import LocalOpenSearchAgent

        return LocalOpenSearchAgent(_settings())


@pytest.mark.asyncio
async def test_answer_question_forwards_history() -> None:
    route_calls: list[dict] = []
    agent = _agent(route_calls, _RecordingScopeGate())

    await agent.answer_question(question=FOLLOW_UP, history=HISTORY)

    assert route_calls[-1]["history"] == HISTORY


@pytest.mark.asyncio
async def test_answer_question_no_cache_forwards_history() -> None:
    route_calls: list[dict] = []
    agent = _agent(route_calls, _RecordingScopeGate())

    await agent.answer_question_no_cache(question=FOLLOW_UP, history=HISTORY)

    assert route_calls[-1]["history"] == HISTORY


@pytest.mark.asyncio
async def test_stream_answer_forwards_history() -> None:
    route_calls: list[dict] = []
    agent = _agent(route_calls, _RecordingScopeGate())

    _ = [chunk async for chunk in agent.stream_answer(question=FOLLOW_UP, history=HISTORY)]

    assert route_calls[-1]["history"] == HISTORY


@pytest.mark.asyncio
async def test_stream_answer_no_cache_forwards_history() -> None:
    route_calls: list[dict] = []
    agent = _agent(route_calls, _RecordingScopeGate())

    _ = [chunk async for chunk in agent.stream_answer_no_cache(question=FOLLOW_UP, history=HISTORY)]

    assert route_calls[-1]["history"] == HISTORY


@pytest.mark.asyncio
async def test_web_only_stream_forwards_history_to_scope_gate_and_route() -> None:
    route_calls: list[dict] = []
    gate = _RecordingScopeGate()
    agent = _agent(route_calls, gate)

    _ = [
        chunk
        async for chunk in agent.stream_answer_web_search_only(question=FOLLOW_UP, history=HISTORY)
    ]

    assert gate.calls == [(FOLLOW_UP, None, HISTORY)]
    assert route_calls[-1]["history"] == HISTORY
    assert route_calls[-1]["force_web_search"] is True


def test_web_only_sync_forwards_history_to_scope_gate_and_route() -> None:
    route_calls: list[dict] = []
    gate = _RecordingScopeGate()
    agent = _agent(route_calls, gate)

    agent.answer_question_web_search_only(FOLLOW_UP, history=HISTORY)

    assert gate.calls == [(FOLLOW_UP, None, HISTORY)]
    assert route_calls[-1]["history"] == HISTORY


@pytest.mark.asyncio
async def test_answer_question_without_history_sends_no_history_key() -> None:
    route_calls: list[dict] = []
    agent = _agent(route_calls, _RecordingScopeGate())

    await agent.answer_question(question="What is HNSW?")

    assert "history" not in route_calls[-1]
