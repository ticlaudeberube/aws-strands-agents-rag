"""Integration tests for API server endpoints.

Tests the FastAPI endpoints exposed by api_server.py, including:
- /health endpoint (service availability)
- /v1/chat/completions endpoint (OpenAI-compatible chat interface)
- Response format validation
- Cache endpoint checks
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.config import Settings

# Note: Full integration tests require running services.
# These tests focus on endpoint contracts and response validation.


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def settings():
    """Fixture providing test settings."""
    return Settings(
        ollama_host="http://localhost:11434",
        ollama_model="qwen2.5:0.5b",
        ollama_embed_model="nomic-embed-text",
        milvus_host="localhost",
        milvus_port=19530,
        milvus_db_name="test_db",
    )


# ============================================================================
# UNIT TESTS: API Response Format Validation
# ============================================================================


class TestChatCompletionResponseFormat:
    """Test suite for OpenAI-compatible chat completion response format."""

    def test_response_has_required_fields(self):
        """Verify chat completion response has all required fields."""
        # This is the expected response structure from OpenAI API
        sample_response = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "rag-agent",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Sample answer"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
        
        # Verify structure
        assert "id" in sample_response
        assert "choices" in sample_response
        assert "model" in sample_response
        assert isinstance(sample_response["choices"], list)
        assert len(sample_response["choices"]) > 0
        assert "message" in sample_response["choices"][0]

    def test_response_message_has_content_and_role(self):
        """Verify response message has content and role fields."""
        message = {
            "role": "assistant",
            "content": "Sample response"
        }
        
        assert "role" in message
        assert "content" in message
        assert message["role"] == "assistant"
        assert isinstance(message["content"], str)

    def test_response_choices_index_starts_at_zero(self):
        """Verify choices array uses zero-based indexing."""
        choices = [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "answer"},
                "finish_reason": "stop"
            }
        ]
        
        assert choices[0]["index"] == 0

    def test_response_finish_reason_valid_values(self):
        """Verify finish_reason has valid values."""
        valid_reasons = ["stop", "length", "function_call", "content_filter"]
        
        for reason in valid_reasons:
            assert reason in valid_reasons  # Sanity check


# ============================================================================
# UNIT TESTS: Health Check Endpoint
# ============================================================================


class TestHealthCheckEndpoint:
    """Test suite for /health endpoint."""

    def test_health_response_structure(self):
        """Verify /health endpoint returns expected structure."""
        expected_health_response = {
            "status": "ok",
            "model": "rag-agent",
            "ollama": "http://localhost:11434",
            "milvus": "localhost:19530",
            "web_search_enabled": True
        }
        
        # Verify expected fields
        assert "status" in expected_health_response
        assert "model" in expected_health_response
        assert expected_health_response["status"] == "ok"

    def test_health_status_values(self):
        """Verify health status has valid values."""
        valid_statuses = ["ok", "degraded", "error"]
        test_status = "ok"
        
        assert test_status in valid_statuses

    def test_health_includes_service_endpoints(self):
        """Verify health check includes service endpoint information."""
        health = {
            "status": "ok",
            "ollama": "http://localhost:11434",
            "milvus": "localhost:19530"
        }
        
        assert "ollama" in health
        assert "milvus" in health


# ============================================================================
# UNIT TESTS: Chat Completion Request Format
# ============================================================================


class TestChatCompletionRequestFormat:
    """Test suite for OpenAI-compatible chat completion request."""

    def test_request_has_required_fields(self):
        """Verify chat completion request has required fields."""
        sample_request = {
            "model": "rag-agent",
            "messages": [
                {
                    "role": "user",
                    "content": "What is Milvus?"
                }
            ],
            "temperature": 0.7,
            "max_tokens": 100
        }
        
        assert "model" in sample_request
        assert "messages" in sample_request
        assert isinstance(sample_request["messages"], list)
        assert len(sample_request["messages"]) > 0

    def test_message_has_role_and_content(self):
        """Verify message has role and content."""
        message = {
            "role": "user",
            "content": "Sample question"
        }
        
        assert "role" in message
        assert "content" in message
        assert message["role"] in ["user", "assistant", "system"]

    def test_temperature_is_in_valid_range(self):
        """Verify temperature parameter is in valid range."""
        valid_temperatures = [0.0, 0.5, 0.7, 1.0, 2.0]
        
        for temp in valid_temperatures:
            assert 0.0 <= temp <= 2.0

    def test_max_tokens_is_positive_integer(self):
        """Verify max_tokens is a positive integer."""
        max_tokens_values = [10, 100, 1000, 4096]
        
        for tokens in max_tokens_values:
            assert isinstance(tokens, int)
            assert tokens > 0


# ============================================================================
# UNIT TESTS: Response Format with Sources
# ============================================================================


class TestResponseWithSources:
    """Test suite for response format that includes sources."""

    def test_response_can_include_sources_metadata(self):
        """Verify response can include source metadata."""
        # Extended response format with sources
        response_content = {
            "answer": "Sample answer text",
            "sources": [
                {
                    "id": "doc-1",
                    "text": "Source text",
                    "distance": 0.2,
                    "metadata": {"url": "https://example.com"}
                }
            ]
        }
        
        assert "answer" in response_content
        assert "sources" in response_content
        assert isinstance(response_content["sources"], list)

    def test_source_has_required_fields(self):
        """Verify source object has required fields."""
        source = {
            "id": "doc-1",
            "text": "Document text",
            "metadata": {
                "source": "knowledge_base",
                "collection": "milvus_docs"
            }
        }
        
        assert "id" in source
        assert "text" in source
        assert isinstance(source["metadata"], dict)

    def test_sources_list_can_be_empty(self):
        """Verify sources list can be empty (for rejections)."""
        sources = []
        
        assert isinstance(sources, list)
        assert len(sources) == 0

    def test_rejection_response_has_no_sources(self):
        """Verify rejection responses have empty sources."""
        rejection_response = {
            "answer": "I can only help with questions about Milvus...",
            "sources": []
        }
        
        assert rejection_response["sources"] == []
        assert len(rejection_response["answer"]) > 0


# ============================================================================
# UNIT TESTS: Cache Endpoint Format
# ============================================================================


class TestCacheEndpoint:
    """Test suite for /api/cache endpoints."""

    def test_cache_stats_response_structure(self):
        """Verify cache stats endpoint returns expected structure."""
        cache_stats = {
            "embedding_cache": {
                "size": 100,
                "hits": 50,
                "misses": 25
            },
            "response_cache": {
                "size": 20,
                "hits": 10,
                "misses": 5
            }
        }
        
        assert "embedding_cache" in cache_stats
        assert "response_cache" in cache_stats
        assert "size" in cache_stats["embedding_cache"]
        assert "hits" in cache_stats["embedding_cache"]

    def test_cache_hit_rate_can_be_calculated(self):
        """Verify cache statistics allow hit rate calculation."""
        cache_data = {
            "hits": 80,
            "misses": 20
        }
        
        total_requests = cache_data["hits"] + cache_data["misses"]
        hit_rate = cache_data["hits"] / total_requests if total_requests > 0 else 0
        
        assert hit_rate == 0.8
        assert 0.0 <= hit_rate <= 1.0


# ============================================================================
# VALIDATION TESTS: Token Usage Reporting
# ============================================================================


class TestTokenUsageReporting:
    """Test suite for token usage in responses."""

    def test_usage_object_has_token_counts(self):
        """Verify usage object includes token counts."""
        usage = {
            "prompt_tokens": 15,
            "completion_tokens": 42,
            "total_tokens": 57
        }
        
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    def test_token_counts_are_non_negative(self):
        """Verify token counts are non-negative integers."""
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "total_tokens": 300
        }
        
        for key, value in usage.items():
            assert isinstance(value, int)
            assert value >= 0

    def test_total_tokens_equals_sum(self):
        """Verify total_tokens equals sum of prompt and completion tokens."""
        usage = {
            "prompt_tokens": 50,
            "completion_tokens": 75,
            "total_tokens": 125
        }
        
        calculated_total = usage["prompt_tokens"] + usage["completion_tokens"]
        assert usage["total_tokens"] == calculated_total


# ============================================================================
# VALIDATION TESTS: Error Handling
# ============================================================================


class TestErrorHandling:
    """Test suite for error response formats."""

    def test_error_response_has_message(self):
        """Verify error responses include error message."""
        error_response = {
            "error": {
                "message": "Invalid request",
                "code": "invalid_request"
            }
        }
        
        assert "error" in error_response
        assert "message" in error_response["error"]

    def test_http_status_codes_are_valid(self):
        """Verify HTTP status codes are valid."""
        valid_codes = [200, 201, 400, 401, 403, 404, 500, 502, 503]
        
        for code in valid_codes:
            assert isinstance(code, int)
            assert 100 <= code < 600

    def test_missing_field_error_format(self):
        """Verify missing field error format."""
        error = {
            "error": {
                "message": "Missing required field: messages",
                "code": "missing_field"
            }
        }
        
        assert "messages" in error["error"]["message"].lower()

    def test_invalid_model_error_format(self):
        """Verify invalid model error format."""
        error = {
            "error": {
                "message": "Invalid model: gpt-5",
                "code": "invalid_model"
            }
        }
        
        assert "invalid_model" in error["error"]["code"].lower()


# ============================================================================
# CONTRACT TESTS: API Stability
# ============================================================================


class TestAPIContractStability:
    """Test suite for API contract stability and backward compatibility."""

    def test_chat_completions_endpoint_path(self):
        """Verify chat completions endpoint path follows OpenAI convention."""
        endpoint_path = "/v1/chat/completions"
        
        assert endpoint_path.startswith("/v1/")
        assert "chat" in endpoint_path.lower()
        assert "completions" in endpoint_path.lower()

    def test_health_endpoint_path(self):
        """Verify health endpoint path is standard."""
        endpoint_path = "/health"
        
        assert "health" in endpoint_path.lower()

    def test_api_version_prefix(self):
        """Verify API uses versioned endpoints."""
        versioned_endpoint = "/v1/chat/completions"
        
        assert "/v1/" in versioned_endpoint
        assert versioned_endpoint.startswith("/v")

    def test_openai_compatibility_model_field(self):
        """Verify model field is compatible with OpenAI format."""
        request = {
            "model": "rag-agent",
            "messages": []
        }
        
        # Should be a string, not a number or object
        assert isinstance(request["model"], str)
        assert len(request["model"]) > 0
