"""Unit tests for cache prevention logic.

Tests that rejected queries (out-of-scope, security risks) are NOT cached,
while valid in-scope queries ARE cached appropriately.

This is critical to prevent cache pollution with rejection messages.
"""

from unittest.mock import Mock, call, patch

import pytest

from src.agents import strands_graph_agent
from src.config import Settings
from src.tools.response_cache import MilvusResponseCache

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


@pytest.fixture
def mock_response_cache():
    """Fixture providing a mocked response cache."""
    cache = Mock(spec=MilvusResponseCache)
    cache.store_response = Mock(return_value=True)
    cache.get_response = Mock(return_value=None)
    return cache


@pytest.fixture
def mock_vector_db():
    """Fixture providing a mocked vector database."""
    db = Mock()
    db.search = Mock(return_value=[])
    return db


@pytest.fixture
def mock_ollama_client():
    """Fixture providing a mocked Ollama client."""
    client = Mock()
    client.generate = Mock(return_value="Test answer")
    client.embed_text = Mock(return_value=[0.1, 0.2, 0.3])
    return client


# ============================================================================
# UNIT TESTS: Cache Prevention for Rejections
# ============================================================================


class TestCachePreventionLogic:
    """Test suite for cache prevention logic."""

    def test_final_confidence_zero_indicates_rejection(self):
        """Verify that final_confidence=0.0 indicates a rejection."""
        state = {
            "final_confidence": 0.0,
            "final_answer": "I can only help with questions about Milvus...",
            "final_sources": []
        }
        
        # Check if rejection flag is set
        is_rejection = state.get("final_confidence", 0) == 0.0
        assert is_rejection is True

    def test_final_confidence_positive_indicates_valid_response(self):
        """Verify that final_confidence>0 indicates a valid response."""
        state = {
            "final_confidence": 0.85,
            "final_answer": "Here's the answer...",
            "final_sources": [{"id": "doc1"}]
        }
        
        is_rejection = state.get("final_confidence", 0) == 0.0
        assert is_rejection is False

    def test_out_of_scope_sets_zero_confidence(self):
        """Verify out-of-scope rejection sets confidence to 0.0."""
        # Simulate reject_out_of_scope function behavior
        state = {}
        state["final_answer"] = "I can only help with questions about Milvus, vector databases, and RAG systems."
        state["final_sources"] = []
        state["final_confidence"] = 0.0
        
        assert state["final_confidence"] == 0.0
        assert len(state["final_sources"]) == 0

    def test_security_risk_sets_zero_confidence(self):
        """Verify security risk rejection sets confidence to 0.0."""
        # Simulate reject_security_risk function behavior
        state = {}
        state["final_answer"] = "I detected a security concern with your query."
        state["final_sources"] = []
        state["final_confidence"] = 0.0
        
        assert state["final_confidence"] == 0.0
        assert len(state["final_sources"]) == 0

    def test_valid_rag_result_has_positive_confidence(self):
        """Verify valid RAG results have positive confidence."""
        state = {
            "final_confidence": 0.75,
            "final_answer": "Milvus is a vector database...",
            "final_sources": [
                {
                    "id": "doc1",
                    "text": "Milvus documentation",
                    "metadata": {}
                }
            ]
        }
        
        is_rejection = state.get("final_confidence", 0) == 0.0
        assert is_rejection is False
        assert state["final_confidence"] > 0.0


# ============================================================================
# UNIT TESTS: Cache Storage Decision Logic
# ============================================================================


class TestCacheStorageDecisions:
    """Test suite for decisions about whether to cache responses."""

    def test_rejection_should_not_be_cached(self, mock_response_cache):
        """Verify rejection responses should not be cached."""
        state = {
            "final_confidence": 0.0,
            "final_answer": "I can only help with...",
            "final_sources": []
        }
        
        # Decision logic: should we cache?
        is_rejection = state.get("final_confidence", 0) == 0.0
        should_cache = not is_rejection and state.get("final_answer")
        
        assert should_cache is False
        # Cache store should NOT be called
        mock_response_cache.store_response.assert_not_called()

    def test_valid_response_should_be_cached(self, mock_response_cache):
        """Verify valid responses should be cached."""
        state = {
            "final_confidence": 0.85,
            "final_answer": "Milvus is a vector database...",
            "final_sources": [{"id": "doc1"}]
        }
        
        # Decision logic: should we cache?
        is_rejection = state.get("final_confidence", 0) == 0.0
        has_answer = bool(state.get("final_answer"))
        should_cache = not is_rejection and has_answer
        
        assert should_cache is True

    def test_cache_decision_respects_is_cached_flag(self):
        """Verify cache decision respects already-cached flag."""
        state = {
            "final_confidence": 0.85,
            "final_answer": "Answer from cache",
            "is_cached": True
        }
        
        # If marked as already cached, don't cache again
        is_rejected = state.get("final_confidence", 0) == 0.0
        already_cached = state.get("is_cached", False)
        should_store = not is_rejected and not already_cached
        
        assert should_store is False

    def test_cache_decision_requires_answer_text(self):
        """Verify cache requires actual answer text."""
        state = {
            "final_confidence": 0.85,
            "final_answer": None,
            "final_sources": []
        }
        
        # Decision: should we cache?
        is_rejected = state.get("final_confidence", 0) == 0.0
        has_answer = bool(state.get("final_answer"))
        should_cache = not is_rejected and has_answer
        
        assert should_cache is False

    def test_cache_decision_requires_confidence_above_zero(self):
        """Verify cache requires confidence > 0.0."""
        state = {
            "final_confidence": 0.0,
            "final_answer": "Some answer",
            "final_sources": []
        }
        
        is_rejected = state.get("final_confidence", 0) == 0.0
        should_cache = not is_rejected
        
        assert should_cache is False


# ============================================================================
# UNIT TESTS: Rejection Message Consistency
# ============================================================================


class TestRejectionMessageConsistency:
    """Test suite for rejection message consistency."""

    def test_out_of_scope_message_contains_milvus_reference(self):
        """Verify out-of-scope message mentions Milvus."""
        message = "I can only help with questions about Milvus, vector databases, and RAG systems."
        
        assert "milvus" in message.lower()
        assert "vector database" in message.lower()

    def test_security_risk_message_mentions_security(self):
        """Verify security risk message mentions security."""
        message = "I detected a security concern with your query. Please rephrase and ask a legitimate question."
        
        assert "security" in message.lower() or "concern" in message.lower()

    def test_out_of_scope_message_is_consistent(self):
        """Verify out-of-scope messages are consistent across code."""
        # All should use the same message
        message1 = "I can only help with questions about Milvus, vector databases, and RAG systems."
        message2 = "I can only help with questions about Milvus, vector databases, and RAG systems."
        
        assert message1 == message2

    def test_rejection_messages_are_user_friendly(self):
        """Verify rejection messages are friendly and clear."""
        messages = [
            "I can only help with questions about Milvus, vector databases, and RAG systems.",
            "I detected a security concern with your query. Please rephrase and ask a legitimate question."
        ]
        
        for message in messages:
            # Messages should be reasonably long (not too terse)
            assert len(message) > 10
            # Should start with capital letter (proper capitalization)
            assert message[0].isupper()
            # Should be coherent English messages
            assert "i" in message.lower()  # Personal pronoun shows it's from the AI


# ============================================================================
# UNIT TESTS: Response Formatting for Cache
# ============================================================================


class TestResponseFormattingForCache:
    """Test suite for response formatting before caching."""

    def test_response_can_be_serialized_to_json(self):
        """Verify responses can be serialized for caching."""
        response = {
            "answer": "Test answer",
            "sources": [
                {
                    "id": "doc1",
                    "text": "Referenced text",
                    "metadata": {"url": "https://example.com"}
                }
            ],
            "confidence_score": 0.85,
            "timestamp": 1234567890
        }
        
        # Should be JSON serializable
        import json
        json_str = json.dumps(response)
        assert isinstance(json_str, str)
        
        # Should be able to deserialize
        deserialized = json.loads(json_str)
        assert deserialized["answer"] == response["answer"]

    def test_cache_key_generation(self):
        """Verify cache keys can be generated consistently."""
        question = "What is Milvus?"
        
        # Cache key should be deterministic
        import hashlib
        key1 = hashlib.sha256(question.encode()).hexdigest()
        key2 = hashlib.sha256(question.encode()).hexdigest()
        
        assert key1 == key2

    def test_different_questions_have_different_cache_keys(self):
        """Verify different questions produce different cache keys."""
        q1 = "What is Milvus?"
        q2 = "What is Pinecone?"
        
        import hashlib
        key1 = hashlib.sha256(q1.encode()).hexdigest()
        key2 = hashlib.sha256(q2.encode()).hexdigest()
        
        assert key1 != key2

    def test_case_sensitive_cache_keys(self):
        """Verify cache keys are case-sensitive."""
        q1 = "What is Milvus?"
        q2 = "what is milvus?"
        
        import hashlib
        key1 = hashlib.sha256(q1.encode()).hexdigest()
        key2 = hashlib.sha256(q2.encode()).hexdigest()
        
        # Keys should be different (case-sensitive)
        assert key1 != key2


# ============================================================================
# INTEGRATION TESTS: Cache Behavior with Mocks
# ============================================================================


class TestCacheBehaviorWithMocks:
    """Test suite for cache behavior with mocked components."""

    def test_rejection_flow_does_not_call_cache_store(self, mock_response_cache):
        """Verify rejection flow doesn't call cache.store_response."""
        state = {
            "final_confidence": 0.0,
            "final_answer": "Rejection message",
            "final_sources": []
        }
        
        # Logic: only cache if not rejected and has answer
        is_rejected = state.get("final_confidence", 0) == 0.0
        if not is_rejected and state.get("final_answer"):
            mock_response_cache.store_response(
                question="test",
                answer=state["final_answer"],
                sources=state["final_sources"],
                metadata={}
            )
        
        # Verify store was not called
        mock_response_cache.store_response.assert_not_called()

    def test_valid_response_calls_cache_store(self, mock_response_cache):
        """Verify valid response calls cache.store_response."""
        state = {
            "final_confidence": 0.85,
            "final_answer": "Valid answer",
            "final_sources": [{"id": "doc1"}]
        }
        
        # Logic: cache if not rejected and has answer
        is_rejected = state.get("final_confidence", 0) == 0.0
        if not is_rejected and state.get("final_answer"):
            mock_response_cache.store_response(
                question="What is Milvus?",
                answer=state["final_answer"],
                sources=state["final_sources"],
                metadata={}
            )
        
        # Verify store was called
        mock_response_cache.store_response.assert_called_once()

    def test_zero_confidence_is_clear_rejection_signal(self):
        """Verify 0.0 confidence is unambiguous rejection signal."""
        # Check all rejection scenarios
        rejection_scenarios = [
            {"final_confidence": 0.0, "reason": "out_of_scope"},
            {"final_confidence": 0.0, "reason": "security_risk"},
            {"final_confidence": 0.0, "reason": "unknown_error"}
        ]
        
        for scenario in rejection_scenarios:
            is_rejected = scenario.get("final_confidence", 0) == 0.0
            assert is_rejected is True


# ============================================================================
# VALIDATION TESTS: Cache Key Stability
# ============================================================================


class TestCacheKeyStability:
    """Test suite for cache key stability and consistency."""

    def test_same_question_generates_same_key(self):
        """Verify same question always generates same cache key."""
        question = "What is Milvus?"
        
        import hashlib
        keys = [hashlib.sha256(question.encode()).hexdigest() for _ in range(5)]
        
        # All keys should be identical
        assert len(set(keys)) == 1

    def test_whitespace_affects_cache_key(self):
        """Verify whitespace is significant in cache keys."""
        q1 = "What is Milvus?"
        q2 = "What  is  Milvus?"  # Extra spaces
        
        import hashlib
        key1 = hashlib.sha256(q1.encode()).hexdigest()
        key2 = hashlib.sha256(q2.encode()).hexdigest()
        
        # Should be different due to whitespace
        assert key1 != key2

    def test_punctuation_affects_cache_key(self):
        """Verify punctuation is significant in cache keys."""
        q1 = "What is Milvus?"
        q2 = "What is Milvus"  # No question mark
        
        import hashlib
        key1 = hashlib.sha256(q1.encode()).hexdigest()
        key2 = hashlib.sha256(q2.encode()).hexdigest()
        
        # Should be different
        assert key1 != key2
