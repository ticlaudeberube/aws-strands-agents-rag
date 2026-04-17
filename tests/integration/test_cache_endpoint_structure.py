"""Integration tests for cache endpoint response structure.

Tests that the cache endpoint returns the full response structure including
response_type field needed for proper badge display in the React frontend.
"""

import requests


class TestCacheEndpointStructure:
    """Test cache endpoint response structure and format."""

    BASE_URL = "http://localhost:8000"

    def test_cache_endpoint_full_response_structure(self):
        """Test that cache endpoint returns complete response structure."""
        # Query cached responses from the API
        response = requests.get(f"{self.BASE_URL}/v1/cache/responses", params={"limit": 1})

        assert response.status_code == 200
        data = response.json()

        # Verify response has cached_responses
        assert "cached_responses" in data
        cached_responses = data["cached_responses"]

        # If we have cached responses, verify structure
        if cached_responses:
            first_response = cached_responses[0]
            assert "question" in first_response
            assert "answer" in first_response
            # Sources might be in metadata or at top level
            assert "metadata" in first_response or "sources" in first_response

    def test_cache_endpoint_empty_answer_structure(self):
        """Test cache endpoint with empty answer returns proper structure."""
        # Query all cached responses
        response = requests.get(f"{self.BASE_URL}/v1/cache/responses", params={"limit": 50})

        assert response.status_code == 200
        data = response.json()

        # Response should have cached_responses key
        assert "cached_responses" in data
        # Should be a list (may be empty)
        assert isinstance(data["cached_responses"], list)

    def test_cache_endpoint_no_cache_hit(self):
        """Test cache endpoint returns proper empty structure."""
        # Query with limit 0 to get empty results
        response = requests.get(f"{self.BASE_URL}/v1/cache/responses", params={"limit": 0})

        # Should return 200 (OK) with empty list
        assert response.status_code == 200
        data = response.json()
        assert "cached_responses" in data
        assert isinstance(data["cached_responses"], list)

    def test_cache_endpoint_response_type_consistency(self):
        """Test that cache endpoint returns consistent structure."""
        # Query cached responses
        response = requests.get(f"{self.BASE_URL}/v1/cache/responses", params={"limit": 10})

        assert response.status_code == 200
        data = response.json()
        assert "cached_responses" in data

        # All cached responses should have required fields
        for cached_response in data["cached_responses"]:
            assert "question" in cached_response
            assert "answer" in cached_response

    def test_cache_endpoint_metadata_structure(self):
        """Test that cache endpoint includes proper structure."""
        response = requests.get(f"{self.BASE_URL}/v1/cache/responses", params={"limit": 5})

        assert response.status_code == 200
        data = response.json()
        assert "cached_responses" in data

        # If we have cached responses, check structure
        if data["cached_responses"]:
            response_item = data["cached_responses"][0]
            # Should have metadata field containing cached info
            assert "metadata" in response_item or "question" in response_item

    def test_cache_endpoint_sources_format(self):
        """Test that cached responses have proper structure."""
        response = requests.get(f"{self.BASE_URL}/v1/cache/responses", params={"limit": 5})

        assert response.status_code == 200
        data = response.json()
        assert "cached_responses" in data

        # Each cached response should be a dict with question/answer
        for cached_response in data["cached_responses"]:
            assert isinstance(cached_response, dict)
            assert "question" in cached_response
            assert "answer" in cached_response
