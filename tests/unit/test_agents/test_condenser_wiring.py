"""Wiring tests: the graph's shared route passes a per-mode condenser to the router.

Local mode condenses with ``settings.ollama_model`` (``OLLAMA_MODEL``) through Ollama. Serverless mode
condenses with ``amazon.nova-lite-v1:0`` through Bedrock. The router is
patched, so no live model or service is called.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.agents import rag_routing, strands_graph_agent
from src.agents.strands_graph_agent import (
    CONDENSE_MAX_TOKENS,
    CONDENSE_MODEL_SERVERLESS,
    CONDENSE_TEMPERATURE,
    create_rag_graph,
)
from src.config.settings import Settings
from src.tools.in_memory_cache import InMemoryCache
from src.tools.opensearch_client import OpenSearchClient

HISTORY = [
    {"role": "user", "content": "What is Milvus?"},
    {"role": "assistant", "content": "A vector database."},
]


class _RecordingLLM:
    """Stands in for the Ollama and Bedrock clients; records generate calls."""

    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []

    def embed_text(self, _text: str, model: str | None = None) -> list[float]:
        return [0.0] * 8

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        self.generate_calls.append(
            {"prompt": prompt, "model": model, "temperature": temperature, "max_tokens": max_tokens}
        )
        return "Standalone question: Do you recommend Milvus for my project?"


class _FakeOSTransport:
    def search(self, index: str, body: dict) -> dict:
        return {"hits": {"hits": []}}

    class _Indices:
        def exists(self, index: str) -> bool:
            return True

        def create(self, index: str, body: dict) -> None:
            return None

    indices = _Indices()


def _opensearch() -> OpenSearchClient:
    return OpenSearchClient(settings=Settings(), client=_FakeOSTransport())


def _condenser_for(graph: dict[str, Any], llm: _RecordingLLM) -> Any:
    """Run the graph's shared route with condensing enabled; return the condenser."""
    with (
        patch.object(strands_graph_agent, "CONDENSE_FOLLOWUPS", True),
        patch.object(rag_routing, "route_rag_query", return_value=object()) as route,
    ):
        graph["shared_route"]("Do you recommend it for my project?", history=HISTORY)
    condenser = route.call_args.kwargs["condenser"]
    assert callable(condenser)
    return condenser


def test_condenser_is_not_passed_by_default() -> None:
    settings = Settings()
    settings.deployment_mode = "local"
    settings.local_vector_backend = "opensearch"
    llm = _RecordingLLM()
    graph = create_rag_graph(
        settings,
        ollama_client=llm,  # type: ignore[arg-type]
        opensearch_client=_opensearch(),
    )

    with patch.object(rag_routing, "route_rag_query", return_value=object()) as route:
        graph["shared_route"]("Do you recommend it for my project?", history=HISTORY)

    assert route.call_args.kwargs["condenser"] is None
    assert llm.generate_calls == []


def test_local_mode_condenses_with_llama_model() -> None:
    settings = Settings()
    settings.deployment_mode = "local"
    settings.local_vector_backend = "opensearch"
    llm = _RecordingLLM()
    graph = create_rag_graph(
        settings,
        ollama_client=llm,  # type: ignore[arg-type]
        opensearch_client=_opensearch(),
    )

    condenser = _condenser_for(graph, llm)
    rewrite = condenser("the prompt")

    assert rewrite == "Standalone question: Do you recommend Milvus for my project?"
    call = llm.generate_calls[-1]
    assert call["model"] == Settings().ollama_model
    assert call["temperature"] == CONDENSE_TEMPERATURE
    assert call["max_tokens"] == CONDENSE_MAX_TOKENS


def test_serverless_mode_condenses_with_nova_lite() -> None:
    settings = Settings()
    settings.deployment_mode = "serverless"
    llm = _RecordingLLM()
    graph = create_rag_graph(
        settings,
        bedrock_client=llm,
        opensearch_client=_opensearch(),
        redis_cache=InMemoryCache(),
    )

    condenser = _condenser_for(graph, llm)
    condenser("the prompt")

    assert llm.generate_calls[-1]["model"] == CONDENSE_MODEL_SERVERLESS == "amazon.nova-lite-v1:0"
