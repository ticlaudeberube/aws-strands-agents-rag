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


def test_adopts_connected_mcp_agent_when_primary_agent_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later successful MCP connection restores the API's primary agent."""
    degraded_agent = _mock_agent(Mock())
    degraded_agent.vector_db = None
    connected_agent = _mock_agent(Mock())
    monkeypatch.setattr(api_server, "strands_agent", degraded_agent)
    monkeypatch.setattr(api_server, "mcp_server", SimpleNamespace(agent=connected_agent))

    api_server._adopt_connected_mcp_agent()

    assert api_server.strands_agent is connected_agent


def test_health_reports_warning_when_vector_db_client_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API remains reachable while reporting a missing vector database."""
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", None)

    data = api_server.health()

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

    data = api_server.health()

    assert data["status"] == "warning"
    assert data["vector_db_available"] is False
    assert "vector database is unavailable" in data["warning"]
    list_collections.assert_called_once_with(
        db_name=Settings().milvus_db_name,
        timeout=api_server.VECTOR_DB_HEALTH_CHECK_TIMEOUT_SECONDS,
    )


def test_health_reports_ok_when_vector_db_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful vector database probe preserves the normal healthy state."""
    list_collections = Mock(return_value=[])
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(list_collections))

    data = api_server.health()

    assert data["status"] == "ok"
    assert data["vector_db_available"] is True
    assert data["warning"] is None


def test_health_disables_web_search_when_feature_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured key alone does not enable web search."""
    configured_settings = Settings().model_copy(
        update={
            "enable_web_search_supplement": False,
            "tavily_api_key": "configured",
        }
    )
    monkeypatch.setattr(api_server, "settings", configured_settings)
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(Mock(return_value=[])))

    data = api_server.health()

    assert data["web_search_enabled"] is False


def test_health_tracks_vector_db_availability_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated health checks reflect a vector DB going offline."""
    list_collections = Mock(side_effect=[[], ConnectionError("offline")])
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(list_collections))

    available = api_server.health()
    unavailable = api_server.health()

    assert available["status"] == "ok"
    assert available["vector_db_available"] is True
    assert unavailable["status"] == "warning"
    assert unavailable["vector_db_available"] is False
    assert list_collections.call_count == 2
    assert all(
        call.kwargs
        == {
            "db_name": Settings().milvus_db_name,
            "timeout": api_server.VECTOR_DB_HEALTH_CHECK_TIMEOUT_SECONDS,
        }
        for call in list_collections.call_args_list
    )


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
    agent.vector_db.client.list_collections.assert_called_once_with(
        db_name=Settings().milvus_db_name,
        timeout=api_server.VECTOR_DB_HEALTH_CHECK_TIMEOUT_SECONDS,
    )
