"""Decorators for resilience and performance control in RAG graph."""

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Optional, TypeVar, cast

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 0.1,
    exponential: bool = True,
    max_delay: Optional[float] = None,
) -> Callable[[F], F]:
    """Decorator for retrying functions with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        exponential: Use exponential backoff (True) or linear (False)
        max_delay: Maximum delay between retries (None for unlimited)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"[RETRY] {func.__name__} succeeded on attempt {attempt + 1}")
                    return result
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2**attempt if exponential else attempt + 1)
                        if max_delay:
                            delay = min(delay, max_delay)
                        logger.warning(
                            f"[RETRY] {func.__name__} failed (attempt {attempt + 1}/{max_attempts}), "
                            f"retrying in {delay:.2f}s: {str(e)[:100]}"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[RETRY] {func.__name__} failed after {max_attempts} attempts: {str(e)}"
                        )

            raise last_exception

        return cast(F, wrapper)

    return decorator


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 0.1,
    exponential: bool = True,
    max_delay: Optional[float] = None,
) -> Callable[[F], F]:
    """Async version of retry_with_backoff decorator.

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        exponential: Use exponential backoff (True) or linear (False)
        max_delay: Maximum delay between retries (None for unlimited)

    Returns:
        Decorated async function with retry logic
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"[RETRY] {func.__name__} succeeded on attempt {attempt + 1}")
                    return result
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2**attempt if exponential else attempt + 1)
                        if max_delay:
                            delay = min(delay, max_delay)
                        logger.warning(
                            f"[RETRY] {func.__name__} failed (attempt {attempt + 1}/{max_attempts}), "
                            f"retrying in {delay:.2f}s: {str(e)[:100]}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"[RETRY] {func.__name__} failed after {max_attempts} attempts: {str(e)}"
                        )

            raise last_exception

        return cast(F, wrapper)

    return decorator


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.tokens: float = float(max_requests)
        self.last_update = time.time()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        tokens_to_add = (elapsed / self.window_seconds) * self.max_requests
        self.tokens = min(self.max_requests, self.tokens + tokens_to_add)
        self.last_update = now

    def check_rate_limit(self, cost: int = 1) -> bool:
        """Check if request is within rate limit.

        Args:
            cost: Token cost of this request

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def wait_for_allowance(self, cost: int = 1) -> float:
        """Wait until request is allowed.

        Args:
            cost: Token cost of this request

        Returns:
            Time waited in seconds
        """
        start = time.time()
        while not self.check_rate_limit(cost):
            time.sleep(0.01)  # Small sleep to avoid busy waiting
        return time.time() - start


def rate_limit(max_requests: int = 100, window_seconds: int = 60) -> Callable[[F], F]:
    """Decorator for rate limiting function calls.

    Args:
        max_requests: Maximum requests allowed in the window
        window_seconds: Time window in seconds

    Returns:
        Decorated function with rate limiting
    """
    limiter = RateLimiter(max_requests, window_seconds)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not limiter.check_rate_limit():
                logger.warning(f"[RATE_LIMIT] {func.__name__} rate limit exceeded, waiting...")
                limiter.wait_for_allowance()
            return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def sanitize_input(max_length: int = 5000) -> Callable[[F], F]:
    """Decorator for sanitizing string inputs.

    Args:
        max_length: Maximum input length

    Returns:
        Decorated function with input sanitization
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Sanitize first positional argument if it's a string
            if args and isinstance(args[0], str):
                sanitized = args[0].strip()[:max_length]
                args = (sanitized,) + args[1:]

            # Sanitize 'question' kwarg if present
            if "question" in kwargs and isinstance(kwargs["question"], str):
                kwargs["question"] = kwargs["question"].strip()[:max_length]

            return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator
