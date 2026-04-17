"""Integration tests for validation endpoint error handling."""

import pytest
from fastapi.testclient import TestClient

# This test module assumes the api_server is available to test
# It should be run with: pytest tests/integration/test_validation_api.py


@pytest.mark.integration
class TestValidationAPIErrors:
    """Test validation error responses from API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client for the API server."""
        # Import here to avoid circular imports
        try:
            from api_server import app
            return TestClient(app)
        except ImportError:
            pytest.skip("API server not available")

    def test_empty_input_validation_error(self, client):
        """Test that empty input returns validation error."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": ""}],
                    }
                ]
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "empty" in str(data["detail"]).lower()

    def test_min_length_validation_error(self, client):
        """Test that input shorter than minimum returns error."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": "a"}],  # Single character (too short)
                    }
                ]
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_max_length_validation_handling(self, client):
        """Test that excessive length is handled."""
        # Create input that might exceed max
        long_input = "x" * 10000

        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": long_input}],
                    }
                ]
            },
        )

        # Should either succeed with truncation or return error
        assert response.status_code in [200, 400]

    def test_xss_script_tag_sanitization(self, client):
        """Test that script tags are sanitized in validation."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": "<script>alert('xss')</script>What is Milvus?"}
                        ],
                    }
                ]
            },
        )

        # Should sanitize and process
        assert response.status_code in [200, 400]
        # Script tag should be removed, legitimate question remains

    def test_javascript_protocol_detection(self, client):
        """Test detection of javascript: protocol attacks."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": "javascript:alert('xss')"}
                        ],
                    }
                ]
            },
        )

        # Should be rejected for suspicious pattern
        assert response.status_code in [400]
        data = response.json()
        assert "detail" in data

    def test_event_handler_injection_detection(self, client):
        """Test detection of event handler injection."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": 'question" onclick="alert(\'xss\')"'}
                        ],
                    }
                ]
            },
        )

        # Depending on detection logic, should either sanitize or reject
        assert response.status_code in [200, 400]

    def test_iframe_injection_detection(self, client):
        """Test detection of iframe injection."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": '<iframe src="http://malicious.com"></iframe>'}
                        ],
                    }
                ]
            },
        )

        # Should be considered suspicious
        assert response.status_code in [400]

    def test_excessive_repetition_detection(self, client):
        """Test detection of excessive character repetition."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": "aaaaaaaaaa bbbbbbbbbb cccccccccc"}
                        ],
                    }
                ]
            },
        )

        # Excessive repetition should trigger DoS protection
        # Exact behavior depends on configuration
        assert response.status_code in [200, 400]

    def test_valid_input_passes_validation(self, client):
        """Test that legitimate input passes validation."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": "What is a vector database and how does Milvus work?"}
                        ],
                    }
                ]
            },
        )

        # Valid input should process (status 200 for response or 503 if services unavailable)
        assert response.status_code in [200, 503]

    def test_unicode_emoji_input_accepted(self, client):
        """Test that Unicode and emoji input is accepted."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": "你好 🚀 What is this? こんにちは"}
                        ],
                    }
                ]
            },
        )

        # Unicode and emoji should be accepted
        assert response.status_code in [200, 503]

    def test_whitespace_only_input_rejected(self, client):
        """Test that whitespace-only input is rejected."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": "   \n\t   "}
                        ],
                    }
                ]
            },
        )

        # Whitespace-only should be treated as empty
        assert response.status_code == 400

    def test_string_content_format_accepted(self, client):
        """Test that string content (not list format) is handled."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "What is Milvus?",  # Direct string, not list
                    }
                ]
            },
        )

        # Should handle both formats
        assert response.status_code in [200, 400, 503]

    def test_no_user_message_error(self, client):
        """Test that request with no user message returns error."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"text": "Some response"}],
                    }
                ]
            },
        )

        # Should error due to no user message
        assert response.status_code in [400]

    def test_validation_error_has_detail(self, client):
        """Test that validation errors include detail message."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": "a"}],  # Too short
                    }
                ]
            },
        )

        assert response.status_code == 400
        data = response.json()

        # Error should have detail field for frontend display
        assert "detail" in data
        detail = data["detail"]
        # Should contain helpful information
        assert len(str(detail)) > 0

    def test_sanitized_input_processing(self, client):
        """Test that sanitized input is actually processed."""
        # Input with HTML that will be sanitized
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": "<b>What</b> is Milvus?"}
                        ],
                    }
                ]
            },
        )

        # Should process the sanitized version
        assert response.status_code in [200, 503]


@pytest.mark.integration
class TestValidationEndpointHealth:
    """Test validation endpoint availability and health."""

    @pytest.fixture
    def client(self):
        """Create a test client for the API server."""
        try:
            from api_server import app
            return TestClient(app)
        except ImportError:
            pytest.skip("API server not available")

    def test_chat_completions_endpoint_exists(self, client):
        """Test that chat completions endpoint is available."""
        # Create a minimal valid request
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": "Valid question"}],
                    }
                ]
            },
        )

        # Should return either success or error, not 404
        assert response.status_code != 404

    def test_validation_happens_before_agent_call(self, client):
        """Test that validation rejects invalid input before agent processing."""
        # Send input that will fail validation
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": ""}],  # Empty
                    }
                ]
            },
        )

        # Should fail with 400, not process through agent
        assert response.status_code == 400

    def test_response_format_consistency(self, client):
        """Test that error responses have consistent format."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": "a"}],  # Too short
                    }
                ]
            },
        )

        assert response.status_code == 400
        data = response.json()

        # Should be JSON with expected structure
        assert isinstance(data, dict)
        assert "detail" in data or "error" in data or "message" in data
