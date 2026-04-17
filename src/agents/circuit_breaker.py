"""Circuit breaker pattern for external service resilience."""

import logging
import time
from enum import Enum
from typing import Any, TypeVar
from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """States for circuit breaker."""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Failing, reject calls
    HALF_OPEN = "HALF_OPEN"  # Testing if service recovered


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""

    pass


class CircuitBreaker:
    """Circuit breaker for protecting calls to external services."""

    def __init__(
        self,
        name: str = "CircuitBreaker",
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            name: Name of the circuit breaker
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes in HALF_OPEN before closing
            timeout_seconds: Time before transitioning from OPEN to HALF_OPEN
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting calls)."""
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self.state == CircuitState.HALF_OPEN

    def _transition_to_open(self) -> None:
        """Transition circuit to OPEN state."""
        self.state = CircuitState.OPEN
        self.last_failure_time = time.time()
        logger.warning(f"[CIRCUIT_BREAKER] {self.name} opened after {self.failure_count} failures")

    def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state."""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        logger.info(f"[CIRCUIT_BREAKER] {self.name} transitioned to HALF_OPEN")

    def _transition_to_closed(self) -> None:
        """Transition circuit to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info(f"[CIRCUIT_BREAKER] {self.name} closed")

    def _check_timeout(self) -> None:
        """Check if timeout has elapsed for OPEN state."""
        if (
            self.is_open
            and self.last_failure_time
            and (time.time() - self.last_failure_time) >= self.timeout_seconds
        ):
            self._transition_to_half_open()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        self._check_timeout()

        if self.is_open:
            raise CircuitBreakerOpen(f"Circuit breaker {self.name} is open. Service unavailable.")

        try:
            result = func(*args, **kwargs)

            if self.is_half_open:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self._transition_to_closed()
                    logger.info(
                        f"[CIRCUIT_BREAKER] {self.name} recovered after "
                        f"{self.success_count} successful calls"
                    )
            elif self.is_closed:
                # Reset failure count on success
                if self.failure_count > 0:
                    self.failure_count = 0

            return result

        except Exception as e:
            self.failure_count += 1
            logger.warning(
                f"[CIRCUIT_BREAKER] {self.name} failure {self.failure_count}/{self.failure_threshold}: {str(e)[:100]}"
            )

            if self.is_half_open or self.failure_count >= self.failure_threshold:
                self._transition_to_open()

            raise

    def reset(self) -> None:
        """Reset circuit breaker to CLOSED state."""
        self._transition_to_closed()
        logger.info(f"[CIRCUIT_BREAKER] {self.name} manually reset")

    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
        }


class MilvusCircuitBreaker(CircuitBreaker):
    """Circuit breaker specialized for Milvus database operations."""

    def __init__(self) -> None:
        """Initialize Milvus-specific circuit breaker."""
        super().__init__(
            name="Milvus",
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=30.0,
        )


class WebSearchCircuitBreaker(CircuitBreaker):
    """Circuit breaker specialized for web search API operations."""

    def __init__(self) -> None:
        """Initialize web search-specific circuit breaker."""
        super().__init__(
            name="WebSearch",
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=60.0,
        )
