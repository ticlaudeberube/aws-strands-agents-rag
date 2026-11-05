"""Tests for the local client builders used by OpenSearch Local Mode.

`OpenSearchClient.for_local` and `RedisCache.for_local` construct plain-HTTP /
plain-TCP clients pointed at local containers, injecting them so the cloud
(TLS/SigV4) transports are bypassed. Constructing a client does not open a
connection, so these assert on the resulting transport configuration without a
live server, and confirm the cloud path is untouched when `for_local` is not
used.
"""

from __future__ import annotations

import pytest

from src.config.settings import Settings
from src.tools.opensearch_client import OpenSearchClient
from src.tools.redis_cache import RedisCache


def test_opensearch_for_local_builds_plain_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSEARCH_LOCAL_HOST", "localhost")
    monkeypatch.setenv("OPENSEARCH_LOCAL_PORT", "9201")
    client = OpenSearchClient.for_local(Settings())

    # The injected opensearch-py transport targets the local host/port over HTTP.
    hosts = client.client.transport.hosts
    assert hosts[0]["host"] == "localhost"
    assert hosts[0]["port"] == 9201
    # Index names and dims come through from settings as usual.
    assert client.kb_index == "rag-kb"
    assert client.vector_dim == 768


def test_opensearch_cloud_path_untouched_without_for_local() -> None:
    # A plain Settings() in serverless shape with no endpoint should still try
    # the cloud builder (which raises a clear ValueError), proving for_local did
    # not alter the default constructor behaviour.
    settings = Settings()
    settings.opensearch_endpoint = None
    with pytest.raises(ValueError, match="opensearch_endpoint"):
        OpenSearchClient(settings=settings)


def test_redis_for_local_builds_non_tls_client(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("redis", reason="redis-py (serverless extra) not installed")
    monkeypatch.setenv("REDIS_ENDPOINT", "localhost:6380")
    cache = RedisCache.for_local(Settings())

    kwargs = cache.client.get_connection_kwargs()
    assert kwargs["host"] == "localhost"
    assert kwargs["port"] == 6380
    # Non-TLS: a plain redis.Redis uses a non-SSL connection class. The ssl flag
    # is not set to True (local container has no TLS).
    assert kwargs.get("ssl", False) is False
    assert cache.redis_available is True


def test_redis_for_local_defaults_endpoint() -> None:
    pytest.importorskip("redis", reason="redis-py (serverless extra) not installed")
    cache = RedisCache.for_local(Settings())
    kwargs = cache.client.get_connection_kwargs()
    assert kwargs["host"] == "localhost"
    assert kwargs["port"] == 6379
