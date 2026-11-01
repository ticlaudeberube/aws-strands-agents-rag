"""Tests for the local-path anti-hallucination parity (finding H1).

The local answer-generation tool (``create_answer_generation_tool`` in
``strands_graph_agent``) must apply the same code-level grounding protections as
the shared router: an honest refusal when there are no usable sources, and a
low-grounding caveat when a generated answer is poorly supported. These tests
drive the tool directly with a fake Ollama client, so no Milvus/Ollama server
is required.
"""

from __future__ import annotations

from typing import Any

from src.agents import rag_routing
from src.agents.strands_graph_agent import create_answer_generation_tool
from src.config.settings import Settings


class _FakeOllama:
    """Ollama stand-in returning a fixed answer; records whether it was called."""

    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.generate_called = False

    def generate(self, prompt: str, **_kwargs: Any) -> str:
        self.generate_called = True
        return self._answer

    def embed_text(self, _text: str, **_kwargs: Any) -> list[float]:
        return [0.0] * 8


def _settings() -> Settings:
    return Settings(
        ollama_host="http://localhost:11434",
        milvus_host="localhost",
        milvus_port=19530,
    )


def test_no_usable_sources_returns_honest_refusal_without_generating() -> None:
    """Empty / text-less sources → NO_GROUNDING_ANSWER, LLM never called."""
    ollama = _FakeOllama("some fabricated answer")
    generate = create_answer_generation_tool(ollama, _settings())

    result = generate(
        question="what is some obscure thing",
        context="No documents found.",
        sources=[],
    )

    assert result.answer == rag_routing.NO_GROUNDING_ANSWER
    assert result.confidence_score == 0.0
    assert ollama.generate_called is False


def test_grounded_answer_passes_without_caveat() -> None:
    """A well-supported answer is returned unchanged, no caveat."""
    sources = [
        {"text": "Milvus supports HNSW and IVF indexing for fast vector search.", "distance": 0.9}
    ]
    ollama = _FakeOllama("Milvus supports HNSW indexing for fast vector search.")
    generate = create_answer_generation_tool(ollama, _settings())

    result = generate(
        question="how does Milvus index vectors",
        context="Milvus supports HNSW and IVF indexing for fast vector search.",
        sources=sources,
    )

    assert rag_routing.LOW_GROUNDING_CAVEAT not in result.answer
    assert ollama.generate_called is True


def test_ungrounded_answer_gets_caveat_and_lowered_confidence() -> None:
    """An answer unsupported by sources keeps its text but is flagged."""
    sources = [
        {"text": "Milvus supports HNSW and IVF indexing for vector search.", "distance": 0.9}
    ]
    # Answer shares almost no content words with the source text.
    ollama = _FakeOllama("Pinecone charges forty dollars monthly for serverless replica pods.")
    generate = create_answer_generation_tool(ollama, _settings())

    result = generate(
        question="how does Milvus index vectors",
        context="Milvus supports HNSW and IVF indexing for vector search.",
        sources=sources,
    )

    assert rag_routing.LOW_GROUNDING_CAVEAT in result.answer
    assert result.answer.startswith("Pinecone charges forty dollars")
    assert ollama.generate_called is True
