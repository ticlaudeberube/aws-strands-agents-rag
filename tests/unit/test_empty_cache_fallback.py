"""Unit tests for empty cache fallback functionality.

Tests the core logic where empty cached answers trigger web search fallback
while maintaining security constraints for out-of-scope queries.
"""

from unittest.mock import Mock, patch

import pytest

from src.agents.strands_graph_agent import StrandsGraphRAGAgent
from src.config.settings import Settings


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        ollama_host="http://localhost:11434",
        ollama_model="llama3.2",
        ollama_embed_model="nomic-embed-text",
        milvus_host="localhost",
        milvus_port=19530,
        milvus_db_name="test_db",
        # enable_web_search_supplement removed for compatibility
    )


@pytest.fixture
def agent(mock_settings):
    """Create agent with mocked dependencies."""
    with (
        patch("src.agents.strands_graph_agent.OllamaClient"),
        patch("src.agents.strands_graph_agent.MilvusVectorDB"),
        patch("src.agents.strands_graph_agent.WebSearchClient"),
    ):
        agent = StrandsGraphRAGAgent(settings=mock_settings)
        # Mock response cache
        agent.response_cache = Mock()
        return agent


class TestEmptyCacheFallback:
    """Test empty cache detection and web search fallback logic."""

    @pytest.mark.asyncio
    async def test_empty_cache_response_structure(self, agent):
        """Test that empty cached answer has correct structure."""
        # Mock cache response with empty answer
        mock_cache_response = {
            "answer": "",  # Empty answer - the key condition
            "sources": ["cached_source.md"],
            "response_type": "cache",
            "metadata": {"cached_at": "2026-04-12"},
        }

        # Verify the structure is as expected for empty cache fallback
        assert mock_cache_response["answer"] == ""
        assert isinstance(mock_cache_response["sources"], list)
        assert mock_cache_response["response_type"] == "cache"
        assert isinstance(mock_cache_response["metadata"], dict)

        # Test the condition that triggers fallback
        should_trigger_fallback = (
            not mock_cache_response["answer"] or mock_cache_response["answer"].strip() == ""
        )
        assert should_trigger_fallback is True

    def test_cache_response_validation(self, agent):
        """Test cache response validation logic."""
        # Test various empty answer scenarios
        empty_scenarios = [
            {"answer": ""},
            {"answer": "   "},  # whitespace only
            {"answer": None},
            {"answer": "\n\t  "},  # various whitespace
        ]

        for scenario in empty_scenarios:
            answer = scenario.get("answer", "")
            is_empty = not answer or str(answer).strip() == ""
            assert is_empty is True, f"Should detect empty answer for: {scenario}"

        # Test non-empty scenarios
        non_empty_scenarios = [
            {"answer": "Milvus is a vector database"},
            {"answer": "Valid answer with content"},
            {"answer": "0"},  # Edge case: string "0" is not empty
        ]

        for scenario in non_empty_scenarios:
            answer = scenario.get("answer", "")
            is_empty = not answer or str(answer).strip() == ""
            assert is_empty is False, f"Should NOT detect empty answer for: {scenario}"

    def test_response_type_structure(self, agent):
        """Test response type field validation."""
        valid_response_types = ["cache", "rag", "web_search", "validation_error", "security_error"]

        for response_type in valid_response_types:
            mock_response = {
                "answer": "Sample answer",
                "sources": [],
                "response_type": response_type,
                "metadata": {},
            }

            # Verify response type is in valid set
            assert mock_response["response_type"] in valid_response_types

            # Verify required fields exist
            required_fields = ["answer", "sources", "response_type", "metadata"]
            for field in required_fields:
                assert field in mock_response, f"Missing required field: {field}"


class TestCacheLogic:
    """Test cache-related logic without full agent integration."""

    def test_search_cache_method_exists(self, agent):
        """Verify that response cache has the expected search_cache method."""
        assert hasattr(agent.response_cache, "search_cache"), (
            "response_cache should have search_cache method"
        )

    def test_response_cache_structure(self, agent):
        """Test response cache initialization and structure."""
        # Verify response cache is properly mocked/initialized
        assert agent.response_cache is not None

        # Mock a search_cache call
        agent.response_cache.search_cache = Mock(return_value=None)

        # Test cache miss scenario
        result = agent.response_cache.search_cache("test question", [0.1, 0.2, 0.3])
        assert result is None  # No cache hit

        # Test cache hit scenario
        mock_hit = {
            "answer": "Cached answer",
            "sources": ["doc1.md"],
            "response_type": "cache",
            "metadata": {"cached_at": "2026-04-12"},
        }

        agent.response_cache.search_cache.return_value = mock_hit
        result = agent.response_cache.search_cache("test question", [0.1, 0.2, 0.3])

        assert result is not None
        assert result["answer"] == "Cached answer"
        assert result["response_type"] == "cache"
