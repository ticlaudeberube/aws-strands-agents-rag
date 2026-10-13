"""Unit tests for API health status and backend availability."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import api_server
import pytest
from src.config.settings import Settings


def _mock_agent(list_collections: Mock) -> SimpleNamespace:
    """Build a minimal agent exposing a vector database probe."""
    vector_db = SimpleNamespace(
        client=SimpleNamespace(list_collections=list_collections),
    )
    return SimpleNamespace(vector_db=vector_db)


def test_health_reports_warning_when_vector_db_client_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API remains reachable while reporting a missing vector database."""
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", None)

    data = asyncio.run(api_server.health())

    assert data["status"] == "warning"
    assert data["vector_db_available"] is False
    assert "vector database is unavailable" in data["warning"]


def test_health_reports_warning_when_vector_db_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed vector database probe is reported as degraded health."""
    list_collections = Mock(side_effect=ConnectionError("offline"))
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(list_collections))

    data = asyncio.run(api_server.health())

    assert data["status"] == "warning"
    assert data["vector_db_available"] is False
    assert "vector database is unavailable" in data["warning"]


def test_health_reports_ok_when_vector_db_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful vector database probe preserves the normal healthy state."""
    list_collections = Mock(return_value=[])
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(list_collections))

    data = asyncio.run(api_server.health())

    assert data["status"] == "ok"
    assert data["vector_db_available"] is True
    assert data["warning"] is None


def test_detailed_health_warns_when_vector_db_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detailed health identifies vector DB failure as a degraded service."""
    agent = _mock_agent(Mock(side_effect=ConnectionError("offline")))
    agent.ollama_client = SimpleNamespace(
        is_available=Mock(return_value=True),
        get_available_models=Mock(return_value=[]),
    )
    agent.embedding_cache = {}
    agent.search_cache = {}
    agent.answer_cache = {}
    agent.cache_size = 100

    async def get_agent() -> SimpleNamespace:
        return agent

    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "get_or_init_agent", get_agent)

    data = asyncio.run(api_server.health_detailed())

    assert data["status"] == "warning"
    assert data["services"]["vector_db"]["status"] == "unhealthy"
