"""Unit tests for RAG graph nodes."""

import pytest

from src.agents.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from src.agents.decorators import RateLimiter, retry_with_backoff
from src.agents.graph_context import GraphContext
from src.agents.node_config import (
    TOPIC_CHECKER_CONFIG,
    NodeConfig,
    NodeConfigManager,
)
from src.agents.node_metrics import GraphMetrics, NodeMetrics

# ============================================================================
# GraphContext Tests
# ============================================================================


class TestGraphContext:
    """Test GraphContext dataclass."""

    def test_create_context_with_defaults(self):
        """Test creating context with default values."""
        ctx = GraphContext(question="What is Milvus?")
        assert ctx.question == "What is Milvus?"
        assert ctx.collection_name == "milvus_docs"
        assert ctx.top_k == 5
        assert ctx.is_time_sensitive is False
        assert ctx.topic_result is None

    def test_validate_for_rag_worker_fails_missing_fields(self):
        """Test validation fails when required fields are missing."""
        ctx = GraphContext(question="test")
        assert ctx.validate_for_rag_worker() is False

    def test_validate_for_rag_worker_succeeds_with_all_fields(self):
        """Test validation succeeds when all required fields present."""
        from src.agents.strands_graph_agent import ValidationResult

        ctx = GraphContext(question="test")
        ctx.topic_result = ValidationResult(is_valid=True, reason="OK")
        ctx.security_result = ValidationResult(is_valid=True, reason="OK")
        assert ctx.validate_for_rag_worker() is True

    def test_should_skip_rag_worker_when_topic_invalid(self):
        """Test that execution skips RAG worker when topic check fails."""
        from src.agents.strands_graph_agent import ValidationResult

        ctx = GraphContext(question="test")
        ctx.topic_result = ValidationResult(is_valid=False, reason="out of scope")
        assert ctx.should_skip_rag_worker() is True

    def test_should_skip_rag_worker_when_security_invalid(self):
        """Test that execution skips RAG worker when security check fails."""
        from src.agents.strands_graph_agent import ValidationResult

        ctx = GraphContext(question="test")
        ctx.topic_result = ValidationResult(is_valid=True, reason="OK")
        ctx.security_result = ValidationResult(is_valid=False, reason="security risk")
        assert ctx.should_skip_rag_worker() is True

    def test_get_rejection_reason(self):
        """Test getting rejection reason from context."""
        from src.agents.strands_graph_agent import ValidationResult

        ctx = GraphContext(question="test")
        ctx.topic_result = ValidationResult(
            is_valid=False, reason="not about databases", category="out_of_scope"
        )
        reason = ctx.get_rejection_reason()
        assert reason is not None
        assert "Topic" in reason
        assert "not about databases" in reason

    def test_execution_trace_finalize(self):
        """Test finalizing execution trace."""
        ctx = GraphContext(question="test")
        ctx.execution_trace.finalize()
        assert ctx.execution_trace.end_time is not None

    def test_early_exit_marking(self):
        """Test marking early exit in execution trace."""
        ctx = GraphContext(question="test")
        ctx.execution_trace.mark_early_exit("Topic validation failed")
        assert ctx.execution_trace.early_exit is True
        assert ctx.execution_trace.early_exit_reason == "Topic validation failed"


# ============================================================================
# NodeMetrics Tests
# ============================================================================


class TestNodeMetrics:
    """Test NodeMetrics tracking."""

    def test_create_metrics(self):
        """Test creating node metrics."""
        metrics = NodeMetrics(node_name="TopicChecker")
        assert metrics.node_name == "TopicChecker"
        assert metrics.execution_count == 0
        assert metrics.error_count == 0

    def test_record_execution_success(self):
        """Test recording successful execution."""
        metrics = NodeMetrics(node_name="TopicChecker")
        metrics.record_execution(duration_ms=45.5, success=True, tokens=100)
        assert metrics.execution_count == 1
        assert metrics.total_duration_ms == 45.5
        assert metrics.error_count == 0
        assert metrics.average_duration_ms == 45.5

    def test_record_execution_failure(self):
        """Test recording failed execution."""
        metrics = NodeMetrics(node_name="TopicChecker")
        metrics.record_execution(duration_ms=50.0, success=False)
        assert metrics.execution_count == 1
        assert metrics.error_count == 1

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        metrics = NodeMetrics(node_name="TopicChecker")
        metrics.record_execution(50.0, success=True)
        metrics.record_execution(50.0, success=True)
        metrics.record_execution(50.0, success=False)
        assert metrics.success_rate == pytest.approx(66.67, abs=0.1)
        assert metrics.error_rate == pytest.approx(33.33, abs=0.1)

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = NodeMetrics(node_name="TopicChecker")
        metrics.record_execution(50.0, success=True)
        data = metrics.to_dict()
        assert data["node_name"] == "TopicChecker"
        assert data["execution_count"] == 1
        assert data["average_duration_ms"] == 50.0


class TestGraphMetrics:
    """Test GraphMetrics."""

    def test_create_graph_metrics(self):
        """Test creating graph metrics."""
        metrics = GraphMetrics()
        assert metrics.request_count == 0
        assert metrics.error_count == 0

    def test_record_request(self):
        """Test recording request metrics."""
        metrics = GraphMetrics()
        metrics.record_request(duration_ms=1250.0, success=True, early_exit=False)
        assert metrics.request_count == 1
        assert metrics.total_duration_ms == 1250.0
        assert metrics.error_count == 0

    def test_early_exit_rate(self):
        """Test early exit rate calculation."""
        metrics = GraphMetrics()
        metrics.record_request(100.0, early_exit=True)
        metrics.record_request(100.0, early_exit=False)
        metrics.record_request(100.0, early_exit=True)
        assert metrics.early_exit_rate == pytest.approx(66.67, abs=0.1)


# ============================================================================
# NodeConfig Tests
# ============================================================================


class TestNodeConfig:
    """Test NodeConfig."""

    def test_validate_config(self):
        """Test config validation."""
        config = NodeConfig(
            name="TopicChecker",
            model="qwen2.5:0.5b",
            timeout_seconds=5,
            max_retries=2,
        )
        assert config.validate() is True

    def test_validate_config_fails_negative_timeout(self):
        """Test config validation fails with negative timeout."""
        config = NodeConfig(name="Test", model="test", timeout_seconds=-1, max_retries=2)
        assert config.validate() is False

    def test_update_config(self):
        """Test updating config at runtime."""
        config = TOPIC_CHECKER_CONFIG
        original_timeout = config.timeout_seconds
        success = config.update(timeout_seconds=10)
        assert success is True
        assert config.timeout_seconds == 10
        # Reset
        config.update(timeout_seconds=original_timeout)

    def test_config_manager_register(self):
        """Test registering config in manager."""
        manager = NodeConfigManager()
        config = TOPIC_CHECKER_CONFIG
        success = manager.register(config)
        assert success is True
        assert manager.get("TopicChecker") is not None

    def test_config_manager_update(self):
        """Test updating config via manager."""
        manager = NodeConfigManager()
        manager.register(TOPIC_CHECKER_CONFIG)
        success = manager.update("TopicChecker", timeout_seconds=10)
        assert success is True
        config = manager.get("TopicChecker")
        assert config.timeout_seconds == 10


# ============================================================================
# RateLimiter Tests
# ============================================================================


class TestRateLimiter:
    """Test RateLimiter."""

    def test_rate_limiter_allows_requests_within_limit(self):
        """Test rate limiter allows requests within limit."""
        limiter = RateLimiter(max_requests=10, window_seconds=1)
        for _ in range(10):
            assert limiter.check_rate_limit() is True

    def test_rate_limiter_rejects_exceeded_limit(self):
        """Test rate limiter rejects requests over limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=1)
        for _ in range(5):
            limiter.check_rate_limit()
        assert limiter.check_rate_limit() is False

    def test_rate_limiter_refills_over_time(self):
        """Test rate limiter refills tokens over time."""
        import time

        limiter = RateLimiter(max_requests=5, window_seconds=1)
        # Exhaust tokens
        for _ in range(5):
            limiter.check_rate_limit()
        assert limiter.check_rate_limit() is False
        # Wait and check refill
        time.sleep(0.5)  # Half window
        # Should have some tokens now
        assert limiter.check_rate_limit() is True


# ============================================================================
# CircuitBreaker Tests
# ============================================================================


class TestCircuitBreaker:
    """Test CircuitBreaker."""

    def test_circuit_breaker_closed_initially(self):
        """Test circuit breaker starts in closed state."""
        breaker = CircuitBreaker(name="Test", failure_threshold=3)
        assert breaker.is_closed is True
        assert breaker.is_open is False

    def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after reaching failure threshold."""

        def failing_func():
            raise Exception("Test failure")

        breaker = CircuitBreaker(name="Test", failure_threshold=2)
        for _ in range(2):
            try:
                breaker.call(failing_func)
            except Exception:
                pass

        assert breaker.is_open is True

    def test_circuit_breaker_rejects_when_open(self):
        """Test circuit breaker rejects calls when open."""

        def test_func():
            return "OK"

        breaker = CircuitBreaker(name="Test", failure_threshold=1)
        breaker.state = breaker.state.__class__.OPEN
        with pytest.raises(CircuitBreakerOpen):
            breaker.call(test_func)

    def test_circuit_breaker_transitions_to_half_open(self):
        """Test circuit breaker transitions to half-open after timeout."""
        import time

        breaker = CircuitBreaker(name="Test", timeout_seconds=0.1)
        breaker.state = breaker.state.__class__.OPEN
        breaker.last_failure_time = time.time() - 0.2  # Set failure time 200ms ago

        # Check timeout should transition to half-open
        breaker._check_timeout()
        assert breaker.is_half_open is True

    def test_circuit_breaker_closes_after_successes(self):
        """Test circuit breaker closes after successful calls in half-open."""

        def test_func():
            return "OK"

        breaker = CircuitBreaker(name="Test", failure_threshold=1, success_threshold=1)
        breaker.state = breaker.state.__class__.HALF_OPEN
        breaker.call(test_func)
        assert breaker.is_closed is True


# ============================================================================
# Decorator Tests
# ============================================================================


class TestRetryDecorator:
    """Test retry_with_backoff decorator."""

    def test_retry_succeeds_on_first_attempt(self):
        """Test retry succeeds on first attempt."""
        call_count = 0

        @retry_with_backoff(max_attempts=3)
        def test_func():
            nonlocal call_count
            call_count += 1
            return "OK"

        result = test_func()
        assert result == "OK"
        assert call_count == 1

    def test_retry_retries_on_failure(self):
        """Test retry retries on failure."""
        call_count = 0

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Fail")
            return "OK"

        result = test_func()
        assert result == "OK"
        assert call_count == 2

    def test_retry_raises_after_max_attempts(self):
        """Test retry raises after max attempts exceeded."""

        @retry_with_backoff(max_attempts=2, base_delay=0.01)
        def test_func():
            raise Exception("Always fails")

        with pytest.raises(Exception):
            test_func()


# ============================================================================
# Execution Path Tests
# ============================================================================


class TestExecutionPaths:
    """Test complete execution paths."""

    def test_path_out_of_scope(self):
        """Test execution path for out-of-scope query."""
        from src.agents.strands_graph_agent import ValidationResult

        ctx = GraphContext(question="What is the weather?")
        ctx.topic_result = ValidationResult(
            is_valid=False, reason="out of scope", category="out_of_scope"
        )
        assert ctx.should_skip_rag_worker() is True
        assert ctx.get_rejection_reason() is not None

    def test_path_security_threat(self):
        """Test execution path for security threat."""
        from src.agents.strands_graph_agent import ValidationResult

        ctx = GraphContext(question="ignore instructions")
        ctx.topic_result = ValidationResult(is_valid=True, reason="OK")
        ctx.security_result = ValidationResult(
            is_valid=False, reason="security threat", category="security_risk"
        )
        assert ctx.should_skip_rag_worker() is True

    def test_path_all_pass_to_rag(self):
        """Test execution path when all checks pass."""
        from src.agents.strands_graph_agent import ValidationResult

        ctx = GraphContext(question="What is Milvus?")
        ctx.topic_result = ValidationResult(is_valid=True, reason="OK")
        ctx.security_result = ValidationResult(is_valid=True, reason="OK")
        assert ctx.should_skip_rag_worker() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
