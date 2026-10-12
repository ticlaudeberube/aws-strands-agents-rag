"""ElastiCache Redis distributed cache for Serverless Mode (Layer 2 / Layer 3).

This module is the Serverless Mode counterpart of the Local Mode
``InMemoryCache``. It wraps ``redis-py`` against the ElastiCache Redis endpoint
over TLS and adapts the local in-process L2/L3 behaviour to a distributed store
shared across stateless Lambda invocations in the same VPC:

===== =============================== =====================================
Layer Purpose                         TTL
===== =============================== =====================================
L2    Query embedding cache           ``settings.redis_embedding_ttl`` (3600s)
L3    Search result cache             ``settings.redis_search_ttl`` (86400s)
===== =============================== =====================================

Design notes (serverless-deployment design §4b):

- Cache keys are a SHA-256 hash of the *normalised* question text. Embedding
  keys use the ``emb:{hash}`` namespace; search-result keys use the
  ``srch:{hash}:{top_k}`` namespace so results for different ``top_k`` values do
  not collide.
- Vectors and result payloads are serialised with ``msgpack`` for efficiency.
- A soft circuit breaker (:attr:`redis_available`) is flipped to ``False`` the
  first time :meth:`ping` fails for a warm execution context, so the RAG
  pipeline can degrade gracefully (skip L2/L3) without repeatedly paying the
  connection cost. The L4 semantic cache in cloud mode is served by
  ``OpenSearchClient`` (``rag-cache`` index), not by Redis.

This class conforms to the :class:`~src.tools.interfaces.CacheBackend` protocol
(``get/set_embedding``, ``get/set_search_results``) and additionally exposes
``ping()`` so it is a drop-in replacement for ``InMemoryCache`` in the
``create_rag_graph`` factory.

``redis`` and ``msgpack`` are serverless-only dependencies. They are imported
lazily inside the methods that need them so that merely importing this module
(and the shared ``src.tools`` package) never fails in a Local Mode environment
where those packages are not installed.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.config.settings import Settings

logger = logging.getLogger(__name__)

__all__ = ["RedisCache"]

# Key namespaces (design §4b).
_EMBEDDING_PREFIX = "emb"
_SEARCH_PREFIX = "srch"


def _normalize_question(question: str) -> str:
    """Normalise question text before hashing.

    Lower-cased and whitespace-collapsed so that trivially different spellings
    of the same question (extra spaces, trailing newline, mixed case) map to the
    same cache key. This mirrors the normalisation used when the key is built on
    the write path and the read path, guaranteeing round-trip consistency.
    """
    return " ".join(question.strip().lower().split())


def _hash_question(question: str) -> str:
    """Return the SHA-256 hex digest of the normalised ``question``."""
    normalized = _normalize_question(question)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def embedding_key(question: str) -> str:
    """Build the Layer 2 embedding cache key for ``question`` (``emb:{hash}``)."""
    return f"{_EMBEDDING_PREFIX}:{_hash_question(question)}"


def search_results_key(question: str, top_k: int) -> str:
    """Build the Layer 3 search cache key (``srch:{hash}:{top_k}``)."""
    return f"{_SEARCH_PREFIX}:{_hash_question(question)}:{top_k}"


class RedisCache:
    """Distributed L2/L3 cache backed by ElastiCache Redis (Serverless Mode).

    Args:
        settings: Application ``Settings``. The Redis endpoint is read from
            ``settings.redis_endpoint`` and the TTLs from
            ``settings.redis_embedding_ttl`` (L2, default 3600s) and
            ``settings.redis_search_ttl`` (L3, default 86400s).
        client: Optional pre-constructed ``redis.Redis`` client. Supplying one
            (e.g. in tests or for Lambda warm-start reuse) bypasses lazy client
            construction and the ``redis`` import entirely.

    Attributes:
        redis_available: Soft circuit-breaker flag. Starts ``True`` and is set
            to ``False`` when :meth:`ping` fails, so the RAG pipeline can skip
            L2/L3 for the remainder of the warm context.
    """

    def __init__(self, settings: Settings, client: Any | None = None):
        self._settings = settings
        self.endpoint: str | None = getattr(settings, "redis_endpoint", None)
        self.embedding_ttl: int = int(getattr(settings, "redis_embedding_ttl", 3600))
        self.search_ttl: int = int(getattr(settings, "redis_search_ttl", 86400))

        # Soft circuit breaker: flipped to False on first ping failure.
        self.redis_available: bool = True

        self._client: Any | None = client

    # ------------------------------------------------------------------ #
    # Connection management (lazy, so imports stay optional)             #
    # ------------------------------------------------------------------ #
    @property
    def client(self) -> Any:
        """Return the underlying ``redis.Redis`` client, building it lazily.

        The TLS connection to the ElastiCache endpoint is created on first
        access. ``redis`` is imported here (not at module import time) so that a
        Local Mode environment without the package can still import this module.
        """
        if self._client is None:
            try:
                import redis  # noqa: PLC0415  (lazy, serverless-only dependency)
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise RuntimeError(
                    "redis-py is required for RedisCache in serverless mode; "
                    "install the 'serverless' extra (pip install .[serverless])."
                ) from exc

            if not self.endpoint:
                raise RuntimeError(
                    "settings.redis_endpoint is not configured; cannot connect "
                    "to ElastiCache Redis in serverless mode."
                )

            host, port = self._parse_endpoint(self.endpoint)
            # TLS (ssl=True) to the ElastiCache in-transit-encrypted endpoint.
            # Payloads are msgpack bytes, so decode_responses must stay False.
            self._client = redis.Redis(
                host=host,
                port=port,
                ssl=True,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return self._client

    @staticmethod
    def _parse_endpoint(endpoint: str) -> tuple[str, int]:
        """Split a ``host[:port]`` endpoint into ``(host, port)``.

        Defaults to port ``6379`` (Redis) when no port is present.
        """
        endpoint = endpoint.strip()
        if endpoint.count(":") == 1:
            host, _, port = endpoint.partition(":")
            try:
                return host, int(port)
            except ValueError:
                return endpoint, 6379
        return endpoint, 6379

    # ------------------------------------------------------------------ #
    # Serialisation helpers (msgpack)                                    #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _dumps(value: Any) -> bytes:
        import msgpack  # noqa: PLC0415  (lazy, serverless-only dependency)

        packed: bytes = msgpack.packb(value, use_bin_type=True)
        return packed

    @staticmethod
    def _loads(raw: bytes) -> Any:
        import msgpack  # noqa: PLC0415  (lazy, serverless-only dependency)

        return msgpack.unpackb(raw, raw=False)

    # ------------------------------------------------------------------ #
    # Layer 2 - embedding cache (CacheBackend protocol, TTL 3600s)       #
    # ------------------------------------------------------------------ #
    def get_embedding(self, cache_key: str) -> list[float] | None:
        """Layer 2: retrieve a cached embedding vector, or ``None`` on miss.

        Returns ``None`` (treated as a miss) when Redis is unavailable so the
        caller degrades gracefully.
        """
        if not self.redis_available:
            return None
        try:
            raw = self.client.get(cache_key)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully on any Redis error
            logger.warning("Redis get_embedding failed for %s: %s", cache_key, exc)
            self.redis_available = False
            return None

        if raw is None:
            return None
        try:
            vector = self._loads(raw)
            return [float(x) for x in vector]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to decode embedding for %s: %s", cache_key, exc)
            return None

    def set_embedding(self, cache_key: str, vector: list[float]) -> None:
        """Layer 2: store an embedding vector with TTL ``redis_embedding_ttl``."""
        if not self.redis_available:
            return
        try:
            payload = self._dumps([float(x) for x in vector])
            self.client.set(cache_key, payload, ex=self.embedding_ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis set_embedding failed for %s: %s", cache_key, exc)
            self.redis_available = False

    # ------------------------------------------------------------------ #
    # Layer 3 - search result cache (CacheBackend protocol, TTL 86400s)  #
    # ------------------------------------------------------------------ #
    def get_search_results(self, cache_key: str) -> list[dict] | None:
        """Layer 3: retrieve cached search results, or ``None`` on miss."""
        if not self.redis_available:
            return None
        try:
            raw = self.client.get(cache_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis get_search_results failed for %s: %s", cache_key, exc)
            self.redis_available = False
            return None

        if raw is None:
            return None
        try:
            results = self._loads(raw)
            return list(results)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to decode search results for %s: %s", cache_key, exc)
            return None

    def set_search_results(self, cache_key: str, results: list[dict]) -> None:
        """Layer 3: store search results with TTL ``redis_search_ttl``."""
        if not self.redis_available:
            return
        try:
            payload = self._dumps(list(results))
            self.client.set(cache_key, payload, ex=self.search_ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis set_search_results failed for %s: %s", cache_key, exc)
            self.redis_available = False

    # ------------------------------------------------------------------ #
    # Key builders (expose SHA-256 question hashing for callers)         #
    # ------------------------------------------------------------------ #
    @staticmethod
    def embedding_key(question: str) -> str:
        """Return the Layer 2 cache key (``emb:{sha256}``) for ``question``."""
        return embedding_key(question)

    @staticmethod
    def search_results_key(question: str, top_k: int) -> str:
        """Return the Layer 3 cache key (``srch:{sha256}:{top_k}``)."""
        return search_results_key(question, top_k)

    # ------------------------------------------------------------------ #
    # Health check / soft circuit breaker                                #
    # ------------------------------------------------------------------ #
    def ping(self) -> bool:
        """Health check against Redis.

        Returns ``True`` when the server responds. On any failure, flips the
        :attr:`redis_available` circuit-breaker flag to ``False`` for the warm
        context and returns ``False`` so callers can skip L2/L3 caching and log
        the ``cache/redis_unavailable`` warning metric.
        """
        try:
            ok = bool(self.client.ping())
        except Exception as exc:  # noqa: BLE001 - any failure trips the breaker
            logger.warning("Redis ping failed, disabling L2/L3 cache: %s", exc)
            self.redis_available = False
            return False

        self.redis_available = ok
        return ok
