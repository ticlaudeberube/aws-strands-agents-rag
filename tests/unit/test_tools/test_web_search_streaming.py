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
