#!/usr/bin/env python3
"""Test that web search streaming works correctly with force_web_search=true."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.strands_graph_agent import StrandsGraphRAGAgent
from src.config.settings import get_settings


@pytest.mark.asyncio
async def test_web_search_streaming():
    """Test the streaming web search path."""
    settings = get_settings()

    async def _mock_stream(*args, **kwargs):
        for chunk in ["Milvus ", "is ", "a ", "vector ", "database."]:
            yield chunk

    with (
        patch("src.agents.strands_graph_agent.MilvusVectorDB"),
        patch("src.agents.strands_graph_agent.OllamaClient"),
        patch("src.agents.strands_graph_agent.MilvusResponseCache"),
        patch("src.agents.strands_graph_agent.WebSearchClient"),
    ):
        agent = StrandsGraphRAGAgent(settings=settings)

    agent.stream_answer_web_search_only = _mock_stream  # type: ignore[method-assign]
    agent._last_stream_sources = []  # type: ignore[attr-defined]

    full_response = ""
    async for chunk in agent.stream_answer_web_search_only(
        question="What is Milvus?",
        temperature=0.1,
        max_tokens=500,
    ):
        full_response += chunk

    assert isinstance(full_response, str)
    assert len(full_response) > 0


@pytest.mark.asyncio
async def test_forced_web_search_reports_when_disabled_without_generating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forced web-only query should not generate an answer without search results."""
    settings = get_settings()

    with (
        patch("src.agents.strands_graph_agent.MilvusVectorDB"),
        patch("src.agents.strands_graph_agent.OllamaClient"),
        patch("src.agents.strands_graph_agent.MilvusResponseCache"),
        patch("src.agents.strands_graph_agent.WebSearchClient"),
    ):
        agent = StrandsGraphRAGAgent(settings=settings)

    agent.web_search = None
    monkeypatch.setattr(
        agent,
        "_generate_web_search_query",
        lambda question: pytest.fail("A disabled web search must not build a query"),
    )

    chunks = [
        chunk
        async for chunk in agent.stream_answer_web_search_only(
            question="What is the latest vector DB release?"
        )
    ]

    assert chunks == [
        "Web search is disabled. Enable it in server settings to use web-only search."
    ]
    assert agent._last_stream_sources[0]["metadata"] == (
        '{"source": "system", "type": "web_search_disabled"}'
    )
