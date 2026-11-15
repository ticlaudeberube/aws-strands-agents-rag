"""Tests that the chat endpoints pass prior conversation turns to the agent.

The agent is replaced with a recording fake, so no Ollama or OpenSearch is
needed. The current (final) user message must not appear in the history.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import api_server

COMPLETIONS = "/v1/chat/completions"
STREAM = "/v1/chat/completions/stream"


def _message(role: str, text: str) -> dict[str, Any]:
    return {"role": role, "content": [{"text": text}]}


TWO_TURN_MESSAGES = [
    _message("user", "What is a vector database?"),
    _message("assistant", "A database for embeddings."),
    _message("user", "What can I do with it?"),
]
EXPECTED_HISTORY = [
    {"role": "user", "content": "What is a vector database?"},
    {"role": "assistant", "content": "A database for embeddings."},
]


class _RecordingAgent:
    """Stand-in for LocalOpenSearchAgent that records each answer call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.initialization_error: str | None = None
        self._last_stream_sources: list[dict[str, Any]] = []
        self._last_stream_tier = "kb"

    async def answer_question(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("answer_question", kwargs))
        return {"answer": "ok", "sources": []}

    async def answer_question_no_cache(self, **kwargs: Any) -> tuple[str, list[dict]]:
        self.calls.append(("answer_question_no_cache", kwargs))
        return "ok", []

    async def stream_answer(self, **kwargs: Any):  # noqa: ANN201
        self.calls.append(("stream_answer", kwargs))
        yield "ok"

    async def stream_answer_no_cache(self, **kwargs: Any):  # noqa: ANN201
        self.calls.append(("stream_answer_no_cache", kwargs))
        yield "ok"

    async def stream_answer_web_search_only(self, **kwargs: Any):  # noqa: ANN201
        self.calls.append(("stream_answer_web_search_only", kwargs))
        yield "ok"

    def last_history(self) -> Any:
        return self.calls[-1][1]["history"]


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> _RecordingAgent:
    recording = _RecordingAgent()
    monkeypatch.setattr(api_server, "strands_agent", recording)
    monkeypatch.setattr(api_server, "initialization_error", None)
    return recording


@pytest.fixture
def client() -> TestClient:
    # No ``with`` block: the lifespan (Ollama/OpenSearch startup) is not run.
    return TestClient(api_server.app)


def test_completions_sends_prior_turns_without_current_message(
    agent: _RecordingAgent, client: TestClient
) -> None:
    response = client.post(COMPLETIONS, json={"messages": TWO_TURN_MESSAGES})

    assert response.status_code == 200
    assert agent.calls[-1][0] == "answer_question"
    assert agent.last_history() == EXPECTED_HISTORY


def test_completions_single_turn_sends_empty_history(
    agent: _RecordingAgent, client: TestClient
) -> None:
    response = client.post(COMPLETIONS, json={"messages": [_message("user", "What is HNSW?")]})

    assert response.status_code == 200
    assert agent.last_history() == []


def test_completions_bypass_cache_sends_history(agent: _RecordingAgent, client: TestClient) -> None:
    response = client.post(f"{COMPLETIONS}?bypass_cache=true", json={"messages": TWO_TURN_MESSAGES})

    assert response.status_code == 200
    assert agent.calls[-1][0] == "answer_question_no_cache"
    assert agent.last_history() == EXPECTED_HISTORY


def test_completions_force_web_search_sends_history(
    agent: _RecordingAgent, client: TestClient
) -> None:
    response = client.post(
        COMPLETIONS,
        json={"messages": TWO_TURN_MESSAGES, "force_web_search": True},
    )

    assert response.status_code == 200
    assert agent.calls[-1][0] == "stream_answer_web_search_only"
    assert agent.last_history() == EXPECTED_HISTORY


def test_completions_stream_flag_sends_prior_turns(
    agent: _RecordingAgent, client: TestClient
) -> None:
    # The React UI streams through /v1/chat/completions with "stream": true.
    response = client.post(COMPLETIONS, json={"messages": TWO_TURN_MESSAGES, "stream": True})

    assert response.status_code == 200
    assert agent.calls[-1][0] == "stream_answer"
    assert agent.last_history() == EXPECTED_HISTORY


def test_completions_stream_flag_bypass_cache_sends_prior_turns(
    agent: _RecordingAgent, client: TestClient
) -> None:
    response = client.post(
        f"{COMPLETIONS}?bypass_cache=true",
        json={"messages": TWO_TURN_MESSAGES, "stream": True},
    )

    assert response.status_code == 200
    assert agent.calls[-1][0] == "stream_answer_no_cache"
    assert agent.last_history() == EXPECTED_HISTORY


def test_stream_endpoint_sends_prior_turns(agent: _RecordingAgent, client: TestClient) -> None:
    response = client.post(STREAM, json={"messages": TWO_TURN_MESSAGES})

    assert response.status_code == 200
    assert agent.calls[-1][0] == "stream_answer"
    assert agent.last_history() == EXPECTED_HISTORY


def test_stream_endpoint_force_web_search_sends_prior_turns(
    agent: _RecordingAgent, client: TestClient
) -> None:
    response = client.post(STREAM, json={"messages": TWO_TURN_MESSAGES, "force_web_search": True})

    assert response.status_code == 200
    assert agent.calls[-1][0] == "stream_answer_web_search_only"
    assert agent.last_history() == EXPECTED_HISTORY
