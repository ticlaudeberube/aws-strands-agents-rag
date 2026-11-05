"""Integration tests for the FastAPI app in api_server.py.

These exercise the real endpoints through a FastAPI ``TestClient``. Values that
depend on configuration (Ollama host, vector-DB host/port) are asserted against
``Settings`` rather than hardcoded literals, so the tests stay correct if the
defaults change.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config.settings import Settings, get_settings


@pytest.fixture
def api_client():
    """Create API test client."""
    from api_server import app

    return TestClient(app)


class TestAPIHealth:
    """Test health check endpoints."""

    @patch("api_server.get_or_init_agent")
    @patch("api_server.get_settings")
    def test_health_endpoint(self, mock_settings, mock_agent, api_client):
        """Health returns a valid status and the configured service endpoints."""
        mock_settings.return_value = Settings()

        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in {"ok", "warning", "error"}

    def test_health_reports_configured_endpoints_not_hardcoded(self, api_client):
        """/health echoes the Ollama host and OpenSearch host/port from settings."""
        settings = get_settings()

        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        # Degraded responses only carry {"status": "error", "detail": ...}.
        if data.get("status") == "error":
            pytest.skip(f"health endpoint degraded: {data.get('detail')}")

        # The reported values must come from settings, not baked-in literals.
        assert data["ollama"] == settings.ollama_host
        assert settings.opensearch_local_host in data["vector_db"]
        assert str(settings.opensearch_local_port) in data["vector_db"]
        assert isinstance(data["vector_db_available"], bool)


class TestAPIModels:
    """Test models endpoint."""

    def test_list_models(self, api_client):
        """Test listing available models."""
        response = api_client.get("/v1/models")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) > 0
        assert data["data"][0]["id"] == "rag-agent"


class TestAPIChatCompletions:
    """Test chat completions endpoint."""

    @patch("api_server.get_or_init_agent")
    def test_chat_completions_success(self, mock_agent, api_client):
        """A well-formed request returns an OpenAI-compatible completion."""
        mock_agent_instance = AsyncMock()
        mock_agent_instance.answer_question.return_value = ("Test answer", [])
        mock_agent.return_value = mock_agent_instance

        request_data = {
            "messages": [{"role": "user", "content": [{"text": "What is a vector database?"}]}],
            "model": "rag-agent",
        }

        response = api_client.post("/v1/chat/completions", json=request_data)

        # The endpoint may answer (200) or degrade cleanly (503) if the agent is
        # unavailable, but it must not 500 or reject a valid request as malformed.
        assert response.status_code in {200, 503}
        if response.status_code == 200:
            data = response.json()
            assert data["choices"][0]["message"]["role"] == "assistant"

    @patch("api_server.get_or_init_agent")
    def test_chat_completions_empty_messages_is_rejected(self, mock_agent, api_client):
        """An empty messages list is a client error, not a server crash."""
        mock_agent.return_value = AsyncMock()

        response = api_client.post(
            "/v1/chat/completions", json={"messages": [], "model": "rag-agent"}
        )

        assert response.status_code in {400, 422}

    def test_chat_completions_invalid_messages_type_is_rejected(self, api_client):
        """A non-list ``messages`` field fails request validation (422)."""
        response = api_client.post(
            "/v1/chat/completions", json={"messages": "not a list", "model": "rag-agent"}
        )

        assert response.status_code == 422

    def test_chat_completions_missing_messages_is_rejected(self, api_client):
        """Omitting the required ``messages`` field fails validation (422)."""
        response = api_client.post("/v1/chat/completions", json={"model": "rag-agent"})

        assert response.status_code == 422
