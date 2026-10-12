"""Process-local in-memory cache for Local Mode (L1/L2/L3).

This is the Local Mode equivalent of the serverless ``RedisCache``. It
reproduces the conceptual 4-layer cache's hot layers using plain Python dicts
held for the lifetime of the process:

===== =============================== ==================================
Layer Purpose                         Lifetime
===== =============================== ==================================
L1    Hot answer cache                Process lifetime
L2    Query embedding cache           Process lifetime, TTL ``EMBEDDING_CACHE_TTL``
L3    Search result cache             Process lifetime
===== =============================== ==================================

L1 and L3 live for the lifetime of the process (fast, zero-dependency, reset on
restart). L2 honors ``settings.embedding_cache_ttl`` (``EMBEDDING_CACHE_TTL``,
default 3600 seconds): embeddings older than the TTL are treated as a miss and
evicted lazily on access. Layer 4 (the persistent semantic response cache) is
served separately by ``MilvusResponseCache`` in Local Mode, not by this class.

This class conforms to the :class:`~src.tools.interfaces.CacheBackend` protocol
(``get/set_embedding``, ``get/set_search_results``) and adds L1 answer-cache
helpers (``get_answer`` / ``set_answer``) so the ``create_rag_graph`` factory
can wire it in as the Local Mode hot cache.
"""

from __future__ import annotations

import time

__all__ = ["InMemoryCache"]

# Sentinel default so callers can distinguish "no TTL override" from ttl=0.
_UNSET = object()


class InMemoryCache:
    """In-memory L1/L2/L3 cache backing Local Mode.

    Args:
        ttl: TTL in seconds for L2 (embedding) entries. When omitted, the TTL
            is read from ``settings.embedding_cache_ttl`` (``EMBEDDING_CACHE_TTL``,
            default 3600s). A TTL ``<= 0`` disables L2 expiry (entries live for
            the process lifetime, like L1/L3).
    """

    def __init__(self, ttl: int | float | None | object = _UNSET):
        if ttl is _UNSET:
            # Lazy import to avoid import cycles and to pick up env/config at
            # construction time, matching how the local clients read settings.
            from src.config.settings import get_settings

            ttl = get_settings().embedding_cache_ttl

        self.ttl: float = float(ttl)  # type: ignore[arg-type]

        # L1: hot answer cache -> {cache_key: answer_payload}
        self._answer_cache: dict[str, dict] = {}
        # L2: query embedding cache -> {cache_key: (vector, stored_at_monotonic)}
        self._embedding_cache: dict[str, tuple[list[float], float]] = {}
        # L3: search result cache -> {cache_key: results}
        self._search_cache: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------ #
    # Layer 2 - embedding cache (CacheBackend protocol, TTL-honoring)    #
    # ------------------------------------------------------------------ #
    def get_embedding(self, cache_key: str) -> list[float] | None:
        """Return the cached embedding for ``cache_key``, or ``None`` on miss.

        Entries older than the configured TTL are treated as a miss and evicted
        lazily. A non-positive TTL disables expiry.
        """
        entry = self._embedding_cache.get(cache_key)
        if entry is None:
            return None

        vector, stored_at = entry
        if self.ttl > 0 and (time.monotonic() - stored_at) > self.ttl:
            # Expired: evict and report a miss.
            self._embedding_cache.pop(cache_key, None)
            return None
        return vector

    def set_embedding(self, cache_key: str, vector: list[float]) -> None:
        """Store an embedding vector in L2 with the current timestamp."""
        self._embedding_cache[cache_key] = (list(vector), time.monotonic())

    # ------------------------------------------------------------------ #
    # Layer 3 - search result cache (CacheBackend protocol)             #
    # ------------------------------------------------------------------ #
    def get_search_results(self, cache_key: str) -> list[dict] | None:
        """Return cached L3 search results for ``cache_key``, or ``None``."""
        return self._search_cache.get(cache_key)

    def set_search_results(self, cache_key: str, results: list[dict]) -> None:
        """Store L3 search results for ``cache_key``."""
        self._search_cache[cache_key] = list(results)

    # ------------------------------------------------------------------ #
    # Layer 1 - hot answer cache (local extension, used by the factory) #
    # ------------------------------------------------------------------ #
    def get_answer(self, cache_key: str) -> dict | None:
        """Return the cached L1 answer payload for ``cache_key``, or ``None``."""
        return self._answer_cache.get(cache_key)

    def set_answer(self, cache_key: str, answer: dict) -> None:
        """Store an L1 answer payload for ``cache_key``."""
        self._answer_cache[cache_key] = answer

    # ------------------------------------------------------------------ #
    # Maintenance helpers                                                #
    # ------------------------------------------------------------------ #
    def clear(self) -> None:
        """Clear all layers (L1/L2/L3). Primarily useful for tests."""
        self._answer_cache.clear()
        self._embedding_cache.clear()
        self._search_cache.clear()

    def ping(self) -> bool:
        """Health check. Always ``True`` for a process-local cache.

        Present so the in-memory cache is a drop-in for the serverless
        ``RedisCache`` (which uses ``ping()`` for its circuit breaker).
        """
        return True
