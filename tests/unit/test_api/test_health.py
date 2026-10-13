"""Unit tests for API health status and backend availability."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import api_server
import pytest
from src.config.settings import Settings


def _mock_agent(list_collections: Mock) -> SimpleNamespace:
    """Build a minimal agent exposing a Milvus client probe."""
    vector_db = SimpleNamespace(
        client=SimpleNamespace(list_collections=list_collections),
    )
    return SimpleNamespace(vector_db=vector_db)


def test_health_reports_warning_when_milvus_client_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API remains reachable while reporting missing Milvus."""
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", None)

    data = asyncio.run(api_server.health())

    assert data["status"] == "warning"
    assert data["milvus_available"] is False
    assert "Milvus is unavailable" in data["warning"]


def test_health_reports_warning_when_milvus_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed live Milvus probe is reported as degraded health."""
    list_collections = Mock(side_effect=ConnectionError("offline"))
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(list_collections))

    data = asyncio.run(api_server.health())

    assert data["status"] == "warning"
    assert data["milvus_available"] is False
    assert "Milvus is unavailable" in data["warning"]


def test_health_reports_ok_when_milvus_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful Milvus probe preserves the normal healthy state."""
    list_collections = Mock(return_value=[])
    monkeypatch.setattr(api_server, "settings", Settings())
    monkeypatch.setattr(api_server, "strands_agent", _mock_agent(list_collections))

    data = asyncio.run(api_server.health())

    assert data["status"] == "ok"
    assert data["milvus_available"] is True
    assert data["warning"] is None
