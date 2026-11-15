"""Tests for the configurable follow-up join depth (FOLLOWUP_USER_TURNS)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.agents import rag_routing, strands_graph_agent
from src.agents.history import condense_question
from src.agents.rag_routing import route_rag_query
from src.agents.strands_graph_agent import create_rag_graph
from src.config.settings import Settings
from src.tools.opensearch_client import OpenSearchClient

STRONG_KB_HIT = [{"id": "1", "text": "Milvus facts.", "metadata": {}, "distance": 0.9}]


def _history(user_questions: int) -> list[dict[str, str]]:
    """Alternate user and assistant turns, with ``user_questions`` user turns."""
    turns: list[dict[str, str]] = []
    for index in range(user_questions):
        turns.append({"role": "user", "content": f"question {index}"})
        turns.append({"role": "assistant", "content": f"answer {index}"})
    return turns


class _LLM:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.embedded.append(text)
        return [0.1] * 8

    def generate(self, prompt: str, **_kwargs: Any) -> str:
        return "answer"


class _VectorStore:
    def knn_search(self, *_args: Any, **_kwargs: Any) -> list[dict]:
        return list(STRONG_KB_HIT)


def _embedded_for(history: list[dict[str, str]], join_turns: int | None) -> str:
    llm = _LLM()
    kwargs: dict[str, Any] = {}
    if join_turns is not None:
        kwargs["join_turns"] = join_turns
    route_rag_query(
        "final question",
        llm=llm,
        vector_store=_VectorStore(),
        cache=None,
        semantic_cache=None,
        kb_index="rag-kb",
        history=history,
        **kwargs,
    )
    return llm.embedded[0]


# ---- Settings -----------------------------------------------------------


def test_default_join_depth_is_three() -> None:
    # Check the field default, not Settings(): the local .env may override it.
    assert Settings.model_fields["followup_user_turns"].default == 3


def test_env_var_sets_join_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOLLOWUP_USER_TURNS", "10")

    assert Settings().followup_user_turns == 10


@pytest.mark.parametrize("value", ["0", "21"])
def test_join_depth_is_bounded(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("FOLLOWUP_USER_TURNS", value)

    with pytest.raises(ValidationError):
        Settings()


# ---- Router -------------------------------------------------------------


def test_router_defaults_to_three_user_questions() -> None:
    text = _embedded_for(_history(5), join_turns=None)

    assert text == "question 2 question 3 question 4 final question"


def test_router_joins_ten_user_questions_when_configured() -> None:
    text = _embedded_for(_history(12), join_turns=10)

    expected = " ".join([f"question {index}" for index in range(2, 12)] + ["final question"])
    assert text == expected


def test_router_join_depth_one_uses_only_last_question() -> None:
    text = _embedded_for(_history(5), join_turns=1)

    assert text == "question 4 final question"


# ---- Condenser fallback -------------------------------------------------


def test_condenser_fallback_uses_configured_depth() -> None:
    def failing(_prompt: str) -> str:
        raise RuntimeError("model unavailable")

    text = condense_question("final question", _history(5), failing, fallback_turns=4)

    assert text == "question 1 question 2 question 3 question 4 final question"


# ---- Graph wiring -------------------------------------------------------


class _FakeOSTransport:
    def search(self, index: str, body: dict) -> dict:
        return {"hits": {"hits": []}}

    class _Indices:
        def exists(self, index: str) -> bool:
            return True

        def create(self, index: str, body: dict) -> None:
            return None

    indices = _Indices()


def test_graph_passes_configured_join_depth_to_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOLLOWUP_USER_TURNS", "7")
    settings = Settings()
    settings.deployment_mode = "local"
    settings.local_vector_backend = "opensearch"

    class _Ollama:
        def embed_text(self, _text: str, model: str | None = None) -> list[float]:
            return [0.0] * 8

        def generate(self, prompt: str, **_kwargs: Any) -> str:
            return "answer"

    graph = create_rag_graph(
        settings,
        ollama_client=_Ollama(),  # type: ignore[arg-type]
        opensearch_client=OpenSearchClient(settings=settings, client=_FakeOSTransport()),
    )

    with (
        patch.object(strands_graph_agent, "CONDENSE_FOLLOWUPS", False),
        patch.object(rag_routing, "route_rag_query", return_value=object()) as route,
    ):
        graph["shared_route"]("final question", history=_history(2))

    assert route.call_args.kwargs["join_turns"] == 7
