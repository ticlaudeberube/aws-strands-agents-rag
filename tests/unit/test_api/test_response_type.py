"""Tests for API response-type metadata."""

import pytest

import api_server
from scripts.serverless_api_server import ServerlessAgentShim


def test_forced_web_search_is_labeled_web_without_results() -> None:
    assert api_server._determine_response_type([], force_web_search=True) == ("web_search", False)


def test_scope_rejection_is_not_labeled_as_a_kb_answer() -> None:
    assert api_server._determine_response_type([], tier_used="topic") == ("out_of_scope", False)
    assert api_server._determine_response_type([], force_web_search=True, tier_used="topic") == (
        "out_of_scope",
        False,
    )


def test_response_type_still_uses_sources_for_normal_answers() -> None:
    assert api_server._determine_response_type([{"source_type": "web_search"}]) == (
        "web_search",
        False,
    )
    assert api_server._determine_response_type([{"source_type": "cached"}]) == ("cached", True)
    assert api_server._determine_response_type([]) == ("rag", False)


@pytest.mark.asyncio
async def test_unavailable_forced_web_search_explains_configuration_check() -> None:
    class _UnavailableSearch:
        def search(self, **_kwargs):
            return [], "api_unavailable"

    shim = object.__new__(ServerlessAgentShim)
    shim.web_search = _UnavailableSearch()
    shim._last_stream_sources = []

    messages = [message async for message in shim.stream_answer_web_search_only("What is HNSW?")]

    assert "Tavily API key and quota" in messages[0]
    assert shim._last_stream_tier == "websearch"


@pytest.mark.asyncio
async def test_serverless_force_web_rejects_out_of_scope_before_search() -> None:
    class _SearchMustNotRun:
        def search(self, **_kwargs):
            raise AssertionError("out-of-scope requests must not invoke web search")

    shim = object.__new__(ServerlessAgentShim)
    shim.web_search = _SearchMustNotRun()
    shim._last_stream_sources = []

    messages = [
        message async for message in shim.stream_answer_web_search_only("Who is the US president?")
    ]

    assert messages == [
        "I can help with questions about vector databases, vector search, embeddings, and RAG."
    ]
    assert shim._last_stream_tier == "topic"
