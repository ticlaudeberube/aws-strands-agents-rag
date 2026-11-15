"""Serverless handler tests for DynamoDB-backed follow-up history.

The handler's DynamoDB client, graph, metrics, and log emitter are replaced
with fakes. The follow-up test runs the real ``route_rag_query`` against fake
LLM, vector, and cache backends.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.agents import agentcore_handler as handler
from src.agents.rag_routing import route_rag_query
from src.tools.dynamodb_client import SessionReadError

PRIOR_QUESTION = "What is a vector database?"
FOLLOW_UP = "What can I do with it?"
JOINED_TEXT = f"{PRIOR_QUESTION} {FOLLOW_UP}"
SESSION_ROWS = [{"question": PRIOR_QUESTION, "answer": "A database that stores embeddings."}]
STRONG_KB_HIT = [
    {
        "id": "1",
        "text": "Vector databases index embeddings for similarity search.",
        "metadata": {},
        "distance": 0.9,
    }
]


class _FakeDDB:
    """DynamoDB helper fake with configurable history and recorded writes."""

    def __init__(self, rows: list[dict] | None = None, read_error: bool = False) -> None:
        self._rows = rows or []
        self._read_error = read_error
        self.persisted: list[tuple[str, str, str]] = []

    def load_history(self, session_id: str) -> list[dict]:
        if self._read_error:
            raise SessionReadError("simulated read failure")
        return list(self._rows)

    def persist_turn(self, session_id: str, question: str, answer: str) -> None:
        self.persisted.append((session_id, question, answer))


class _RecordingLLM:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.embedded.append(text)
        return [0.1] * 8

    def generate(self, prompt: str, **_kwargs: Any) -> str:
        return "A vector database supports similarity search."


class _RecordingVectorStore:
    def __init__(self) -> None:
        self.query_texts: list[str | None] = []

    def knn_search(
        self,
        _index: str,
        _vector: list[float],
        _k: int,
        filters: dict | None = None,
        query_text: str | None = None,
    ) -> list[dict]:
        self.query_texts.append(query_text)
        return list(STRONG_KB_HIT)


class _RecordingCache:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_embedding(self, key: str) -> None:
        self.calls.append(f"get_embedding:{key}")
        return None

    def set_embedding(self, key: str, _vector: list[float]) -> None:
        self.calls.append(f"set_embedding:{key}")

    def get_search_results(self, key: str) -> None:
        self.calls.append(f"get_search_results:{key}")
        return None

    def set_search_results(self, key: str, _results: list[dict]) -> None:
        self.calls.append(f"set_search_results:{key}")


class _RecordingSemanticCache:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search_semantic_cache(self, question: str, query_vector: list[float], threshold: float):
        self.calls.append("search")
        return None

    def store_semantic_cache(self, **_kwargs: Any) -> None:
        self.calls.append("store")


class _HandlerResult:
    """Plain routing result with the fields the handler serializes."""

    answer = "ok"
    sources: list[dict] = []
    tier_used = "kb"
    cache_hit = False
    confidence_score = 0.9
    grounding_score = 0.9
    web_search_unavailable = False


def _event(question: str) -> dict[str, Any]:
    return {"body": json.dumps({"question": question, "session_id": "session-1"})}


@pytest.fixture
def emitters() -> Any:
    """Silence CloudWatch emission for every handler test."""
    with (
        patch.object(handler.cw, "MetricsEmitter", MagicMock()),
        patch.object(handler.cw, "emit_structured_log", MagicMock()),
    ):
        yield


def _invoke(
    question: str,
    ddb: _FakeDDB,
    shared_route: Any,
) -> dict[str, Any]:
    with (
        patch.object(handler, "_get_ddb_client", return_value=ddb),
        patch.object(handler, "_get_graph", return_value={"shared_route": shared_route}),
    ):
        response = handler.lambda_handler(_event(question), None)
    assert response["statusCode"] == 200
    body: dict[str, Any] = json.loads(response["body"])
    return body


def test_handler_passes_dynamodb_history_to_shared_route(emitters: None) -> None:
    calls: list[dict[str, Any]] = []

    def shared_route(question: str, **kwargs: Any) -> Any:
        calls.append({"question": question, **kwargs})
        return _HandlerResult()

    _invoke(FOLLOW_UP, _FakeDDB(rows=SESSION_ROWS), shared_route)

    assert calls[0]["history"] == SESSION_ROWS


def test_handler_follow_up_embeds_joined_text_and_skips_cache(emitters: None) -> None:
    llm = _RecordingLLM()
    vector_store = _RecordingVectorStore()
    cache = _RecordingCache()
    semantic_cache = _RecordingSemanticCache()

    def shared_route(question: str, **kwargs: Any) -> Any:
        return route_rag_query(
            question,
            llm=llm,
            vector_store=vector_store,
            cache=cache,
            semantic_cache=semantic_cache,
            kb_index="rag-kb",
            **kwargs,
        )

    body = _invoke(FOLLOW_UP, _FakeDDB(rows=SESSION_ROWS), shared_route)

    assert llm.embedded[0] == JOINED_TEXT
    assert all(text == JOINED_TEXT for text in vector_store.query_texts)
    assert cache.calls == []
    assert semantic_cache.calls == []
    assert body["answer"]


def test_handler_degrades_to_empty_history_on_read_failure(emitters: None) -> None:
    calls: list[dict[str, Any]] = []

    def shared_route(question: str, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return _HandlerResult()

    body = _invoke(FOLLOW_UP, _FakeDDB(read_error=True), shared_route)

    assert calls[0]["history"] == []
    assert body["answer"] == "ok"
