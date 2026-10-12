"""Unit tests for InMemoryCache (task 1.3).

Verifies the Local Mode L1/L2/L3 behavior, including L2 TTL expiry honoring
``EMBEDDING_CACHE_TTL`` and faithful round-trips for all three layers.
"""

from __future__ import annotations

import pytest

from src.tools.in_memory_cache import InMemoryCache


# --------------------------------------------------------------------------- #
# Layer 2 - embedding cache (TTL-honoring)                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_embedding_round_trip():
    cache = InMemoryCache(ttl=3600)
    cache.set_embedding("emb:k1", [0.1, 0.2, 0.3])
    assert cache.get_embedding("emb:k1") == [0.1, 0.2, 0.3]


@pytest.mark.unit
def test_embedding_miss_returns_none():
    cache = InMemoryCache(ttl=3600)
    assert cache.get_embedding("missing") is None


@pytest.mark.unit
def test_embedding_ttl_expiry(monkeypatch):
    """An embedding older than the TTL is a miss and is evicted lazily."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr("src.tools.in_memory_cache.time.monotonic", lambda: fake_now["t"])

    cache = InMemoryCache(ttl=10)
    cache.set_embedding("emb:k1", [1.0, 2.0])

    # Within TTL -> hit
    fake_now["t"] = 1009.0
    assert cache.get_embedding("emb:k1") == [1.0, 2.0]

    # Past TTL -> miss + eviction
    fake_now["t"] = 1011.0
    assert cache.get_embedding("emb:k1") is None
    # Confirm eviction (internal state): subsequent access still a miss
    assert cache.get_embedding("emb:k1") is None


@pytest.mark.unit
def test_embedding_ttl_disabled_when_non_positive(monkeypatch):
    """TTL <= 0 disables L2 expiry (process-lifetime entries)."""
    fake_now = {"t": 0.0}
    monkeypatch.setattr("src.tools.in_memory_cache.time.monotonic", lambda: fake_now["t"])

    cache = InMemoryCache(ttl=0)
    cache.set_embedding("emb:k1", [5.0])

    fake_now["t"] = 10_000_000.0
    assert cache.get_embedding("emb:k1") == [5.0]


@pytest.mark.unit
def test_ttl_defaults_from_settings(monkeypatch):
    """When ttl is omitted, InMemoryCache reads settings.embedding_cache_ttl."""

    class _FakeSettings:
        embedding_cache_ttl = 1234

    monkeypatch.setattr("src.config.settings.get_settings", lambda: _FakeSettings())
    cache = InMemoryCache()
    assert cache.ttl == 1234.0


# --------------------------------------------------------------------------- #
# Layer 3 - search result cache                                               #
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_search_results_round_trip():
    cache = InMemoryCache(ttl=3600)
    results = [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}]
    cache.set_search_results("srch:k1", results)
    assert cache.get_search_results("srch:k1") == results


@pytest.mark.unit
def test_search_results_miss_returns_none():
    cache = InMemoryCache(ttl=3600)
    assert cache.get_search_results("missing") is None


# --------------------------------------------------------------------------- #
# Layer 1 - answer cache                                                       #
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_answer_round_trip():
    cache = InMemoryCache(ttl=3600)
    payload = {"answer": "A vector database.", "sources": []}
    cache.set_answer("ans:k1", payload)
    assert cache.get_answer("ans:k1") == payload


@pytest.mark.unit
def test_answer_miss_returns_none():
    cache = InMemoryCache(ttl=3600)
    assert cache.get_answer("missing") is None


# --------------------------------------------------------------------------- #
# Maintenance                                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_clear_empties_all_layers():
    cache = InMemoryCache(ttl=3600)
    cache.set_embedding("e", [0.1])
    cache.set_search_results("s", [{"id": 1}])
    cache.set_answer("a", {"answer": "x"})

    cache.clear()

    assert cache.get_embedding("e") is None
    assert cache.get_search_results("s") is None
    assert cache.get_answer("a") is None


@pytest.mark.unit
def test_ping_always_true():
    assert InMemoryCache(ttl=3600).ping() is True
