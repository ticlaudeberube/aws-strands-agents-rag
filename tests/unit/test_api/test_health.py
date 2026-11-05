"""Unit tests for API health status and backend availability."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import api_server
from src.config.settings import Settings


def _mock_agent(opensearch_healthy: Mock) -> SimpleNamespace:
    """Build a minimal agent exposing the OpenSearch health probe."""
    return SimpleNamespace(opensearch_healthy=opensearch_healthy, vector_db=object())


def test_adopts_connected_mcp_agent_when_primary_agent_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later successful MCP connection restores the API's primary agent."""
    degraded_agent = _mock_agent(Mock(return_value=False))
    degraded_agent.vector_db = None
    connected_agent = _mock_agent(Mock(return_value=True))
    monkeypatch.setattr(api_server, "strands_agent", degraded_agent)
    monkeypatch.setattr(api_server, "mcp_server", SimpleNamespace(agent=connected_agent))

    api_server._adopt_connected_mcp_agent()

    assert api_server.strands_agent is connected_agent


def test_health_reports_warning_when_agent_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API remains reachable while reporting a missing vector database."""
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", None)

    data = api_server.health()

    assert data["status"] == "warning"
    assert data["vector_db_available"] is False
    assert "vector database is unavailable" in data["warning"]


def test_health_reports_warning_when_opensearch_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed OpenSearch probe is reported as degraded health."""
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(Mock(return_value=False)))

    data = api_server.health()

    assert data["status"] == "warning"
    assert data["vector_db_available"] is False
    assert "vector database is unavailable" in data["warning"]


def test_health_reports_ok_when_opensearch_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful OpenSearch probe preserves the normal healthy state."""
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(Mock(return_value=True)))

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
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(Mock(return_value=True)))

    data = api_server.health()

    assert data["web_search_enabled"] is False


def test_health_tracks_vector_db_availability_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated health checks reflect a vector DB going offline."""
    opensearch_healthy = Mock(side_effect=[True, False])
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(opensearch_healthy))

    available = api_server.health()
    unavailable = api_server.health()

    assert available["status"] == "ok"
    assert available["vector_db_available"] is True
    assert unavailable["status"] == "warning"
    assert unavailable["vector_db_available"] is False
    assert opensearch_healthy.call_count == 2


def test_detailed_health_warns_when_vector_db_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detailed health identifies vector DB failure as a degraded service."""
    agent = _mock_agent(Mock(return_value=False))
    agent.ollama_client = SimpleNamespace(
        is_available=Mock(return_value=True),
        get_available_models=Mock(return_value=[]),
    )

    async def get_agent() -> SimpleNamespace:
        return agent

    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "get_or_init_agent", get_agent)

    data = asyncio.run(api_server.health_detailed())

    assert data["status"] == "warning"
    assert data["services"]["vector_db"]["status"] == "unhealthy"
    agent.opensearch_healthy.assert_called()
