"""Tests for history handling in the serverless-local agent shim.

The shim backs the same chat endpoints as the local facade. Turns sent with a
request take precedence. The DynamoDB session is read only when a request
carries no turns.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.serverless_api_server import ServerlessAgentShim

SESSION_ROWS = [{"question": "Stored question", "answer": "Stored answer"}]
REQUEST_HISTORY = [{"role": "user", "content": "Request question"}]


class _FakeDDB:
    def __init__(self) -> None:
        self.load_calls: list[str] = []

    def load_history(self, session_id: str) -> list[dict]:
        self.load_calls.append(session_id)
        return list(SESSION_ROWS)

    def persist_turn(self, session_id: str, question: str, answer: str) -> None:
        return None


class _Result:
    answer = "ok"
    sources: list[dict] = []
    tier_used = "kb"
    cache_hit = False


def _shim_with(ddb: _FakeDDB) -> tuple[ServerlessAgentShim, list[dict[str, Any]]]:
    routed: list[dict[str, Any]] = []

    def shared_route(question: str, **kwargs: Any) -> _Result:
        routed.append({"question": question, **kwargs})
        return _Result()

    shim = object.__new__(ServerlessAgentShim)
    shim._ddb = ddb  # type: ignore[assignment]  # test double for DynamoDBClient
    shim._shared_route = shared_route
    shim._last_stream_tier = "kb"
    shim._last_stream_sources = []
    return shim, routed


@pytest.mark.asyncio
async def test_request_history_takes_precedence_over_session() -> None:
    ddb = _FakeDDB()
    shim, routed = _shim_with(ddb)

    await shim.answer_question(question="What can I do with it?", history=REQUEST_HISTORY)

    assert ddb.load_calls == []
    assert routed[0]["history"] == REQUEST_HISTORY


@pytest.mark.asyncio
async def test_session_history_is_read_when_request_has_no_turns() -> None:
    ddb = _FakeDDB()
    shim, routed = _shim_with(ddb)

    await shim.answer_question(question="What is HNSW?", session_id="session-1")

    assert ddb.load_calls == ["session-1"]
    assert routed[0]["history"] == SESSION_ROWS


@pytest.mark.asyncio
async def test_stream_answer_forwards_request_history() -> None:
    ddb = _FakeDDB()
    shim, routed = _shim_with(ddb)

    _ = [chunk async for chunk in shim.stream_answer(question="q", history=REQUEST_HISTORY)]

    assert ddb.load_calls == []
    assert routed[0]["history"] == REQUEST_HISTORY
