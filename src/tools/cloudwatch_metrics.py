"""Structured JSON logging + custom CloudWatch metrics helper (Serverless Mode).

Backs the Lambda chat handler's observability responsibilities (design
"CloudWatch Metric Dimensions" + Requirements 12.1, 12.2, 12.5):

- :func:`emit_structured_log` writes a single-line JSON log entry containing the
  required fields (``request_id``, ``session_id``, ``tier_used``, ``latency_ms``,
  ``cache_hit``, optional ``error_code``, and ``cold_start=true`` on cold start).
- :class:`MetricsEmitter` publishes the custom metrics in the
  ``StrandsRAG/{Stage}`` namespace (``cache/hit_rate``, ``cache/miss_rate``,
  ``rag/latency_p50``, ``rag/latency_p99``, ``websearch/invocation_count``,
  ``errors/total``, plus the degradation counters emitted by the shared router).

Metrics are published two ways and the emitter degrades gracefully:

1. If a ``boto3`` CloudWatch client is available, ``put_metric_data`` is used.
2. Otherwise (and always, as a durable backstop) the metric is written as an
   Embedded Metric Format (EMF) JSON log line, which CloudWatch extracts into
   metrics automatically. EMF needs no AWS SDK, so it works in any environment.

Import safety: ``boto3`` is imported lazily so importing this module — and the
whole ``src.tools`` package — never fails in Local Mode or test environments.
A metric-publish failure is logged and swallowed; observability must never
break request handling.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.config.settings import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "MetricsEmitter",
    "emit_structured_log",
    "metric_namespace",
    # Metric name constants (design "CloudWatch Metric Dimensions").
    "CACHE_HIT_RATE",
    "CACHE_MISS_RATE",
    "RAG_LATENCY_P50",
    "RAG_LATENCY_P99",
    "WEBSEARCH_INVOCATION_COUNT",
    "ERRORS_TOTAL",
]

# ---- Metric names (design "CloudWatch Metric Dimensions") ----------------- #
CACHE_HIT_RATE = "cache/hit_rate"
CACHE_MISS_RATE = "cache/miss_rate"
RAG_LATENCY_P50 = "rag/latency_p50"
RAG_LATENCY_P99 = "rag/latency_p99"
WEBSEARCH_INVOCATION_COUNT = "websearch/invocation_count"
ERRORS_TOTAL = "errors/total"

# Units keyed by metric name so EMF + put_metric_data agree.
_METRIC_UNITS = {
    CACHE_HIT_RATE: "Percent",
    CACHE_MISS_RATE: "Percent",
    RAG_LATENCY_P50: "Milliseconds",
    RAG_LATENCY_P99: "Milliseconds",
    WEBSEARCH_INVOCATION_COUNT: "Count",
    ERRORS_TOTAL: "Count",
    "cache/redis_unavailable": "Count",
    "cache/opensearch_unavailable": "Count",
}


def metric_namespace(settings: Settings | None = None) -> str:
    """Return the CloudWatch namespace ``StrandsRAG/{Stage}``.

    The stage is taken from the ``STAGE`` env var (set by the Terraform compute
    module per environment) and falls back to the deployment mode so the
    namespace is always well-formed.
    """
    stage = os.getenv("STAGE") or os.getenv("STRANDS_RAG_STAGE")
    if not stage and settings is not None:
        stage = getattr(settings, "deployment_mode", None)
    return f"StrandsRAG/{stage or 'dev'}"


def emit_structured_log(
    *,
    request_id: str,
    session_id: str,
    tier_used: str,
    latency_ms: float,
    cache_hit: bool,
    cold_start: bool = False,
    error_code: str | None = None,
    extra: dict | None = None,
    logger_: logging.Logger | None = None,
) -> dict:
    """Emit a structured JSON log entry and return the entry dict.

    Guarantees the required observability fields are present and non-null
    (Property 32 / Req 12.1, 12.5): ``request_id``, ``session_id``,
    ``tier_used``, ``latency_ms``, ``cache_hit``. ``error_code`` is included
    only when applicable; ``cold_start=true`` is included only on cold start.
    """
    entry: dict[str, Any] = {
        "request_id": request_id,
        "session_id": session_id,
        "tier_used": tier_used,
        "latency_ms": int(round(latency_ms)),
        "cache_hit": bool(cache_hit),
    }
    if cold_start:
        entry["cold_start"] = True
    if error_code is not None:
        entry["error_code"] = error_code
    if extra:
        entry.update(extra)

    (logger_ or logger).info(json.dumps(entry))
    return entry


class MetricsEmitter:
    """Publishes custom CloudWatch metrics for a single Lambda invocation.

    Metrics are buffered and flushed together — latency observations feed both
    the p50 and p99 metrics, and cache hits/misses are converted into the
    combined hit/miss rate (design "CloudWatch Metric Dimensions"). Each metric
    is emitted both via ``put_metric_data`` (when a CloudWatch client is
    available) and as an EMF log line (always), so a metric is never lost even
    without the AWS SDK.

    Args:
        settings: Application ``Settings`` (used for the namespace / region).
        client: Optional pre-constructed ``boto3`` CloudWatch client. When
            omitted, the client is created lazily and, if ``boto3`` is absent,
            metrics fall back to EMF-only.
    """

    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self._settings = settings
        self._client = client
        self._client_attempted = client is not None
        self.namespace = metric_namespace(settings)

        # Buffered observations.
        self._latencies_ms: list[float] = []
        self._cache_hits = 0
        self._cache_misses = 0
        self._websearch_invocations = 0
        self._errors = 0
        # name -> (value, unit) for ad-hoc counters (degradation metrics, etc.)
        self._counters: dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # boto3 client (lazy, optional)                                      #
    # ------------------------------------------------------------------ #
    @property
    def client(self) -> Any | None:
        """Return a CloudWatch client, or ``None`` when boto3 is unavailable."""
        if self._client is None and not self._client_attempted:
            self._client_attempted = True
            try:
                import boto3  # type: ignore[import-untyped]  # noqa: PLC0415  (lazy, serverless-only)

                region = getattr(self._settings, "aws_region", None) or "us-east-1"
                self._client = boto3.client("cloudwatch", region_name=region)
            except Exception as exc:  # noqa: BLE001 - EMF fallback is always available
                logger.debug("CloudWatch client unavailable; using EMF logs only: %s", exc)
                self._client = None
        return self._client

    # ------------------------------------------------------------------ #
    # Observation recording                                              #
    # ------------------------------------------------------------------ #
    def record_latency(self, latency_ms: float) -> None:
        """Record an end-to-end latency observation (feeds p50 + p99)."""
        self._latencies_ms.append(float(latency_ms))

    def record_cache_outcome(self, hit: bool) -> None:
        """Record a cache hit (``True``) or miss (``False``)."""
        if hit:
            self._cache_hits += 1
        else:
            self._cache_misses += 1

    def record_websearch(self) -> None:
        """Record a Tavily web-search invocation."""
        self._websearch_invocations += 1

    def record_error(self) -> None:
        """Record an unhandled error (feeds ``errors/total``)."""
        self._errors += 1

    def increment(self, name: str, value: float = 1.0) -> None:
        """Increment an ad-hoc counter metric by ``name`` (e.g. degradation)."""
        self._counters[name] = self._counters.get(name, 0.0) + value

    def emit_named(self, name: str) -> None:
        """Callback-friendly single-metric emit (used as ``metric_emitter``).

        The shared router calls this with warning-metric names such as
        ``cache/redis_unavailable`` / ``cache/opensearch_unavailable``.
        """
        self.increment(name, 1.0)

    # ------------------------------------------------------------------ #
    # Flush                                                              #
    # ------------------------------------------------------------------ #
    def flush(self) -> list[dict]:
        """Compute derived metrics and publish them. Returns the metric list."""
        metrics = self._build_metric_data()
        if not metrics:
            return metrics
        self._publish_put_metric_data(metrics)
        self._publish_emf(metrics)
        return metrics

    def _build_metric_data(self) -> list[dict]:
        metrics: list[dict] = []

        # Cache hit / miss rate (percent of this invocation's lookups).
        total_lookups = self._cache_hits + self._cache_misses
        if total_lookups > 0:
            hit_rate = 100.0 * self._cache_hits / total_lookups
            metrics.append(self._metric(CACHE_HIT_RATE, hit_rate))
            metrics.append(self._metric(CACHE_MISS_RATE, 100.0 - hit_rate))

        # Latency p50 / p99 from this invocation's observations.
        if self._latencies_ms:
            metrics.append(self._metric(RAG_LATENCY_P50, _percentile(self._latencies_ms, 50)))
            metrics.append(self._metric(RAG_LATENCY_P99, _percentile(self._latencies_ms, 99)))

        if self._websearch_invocations:
            metrics.append(
                self._metric(WEBSEARCH_INVOCATION_COUNT, float(self._websearch_invocations))
            )

        if self._errors:
            metrics.append(self._metric(ERRORS_TOTAL, float(self._errors)))

        for name, value in self._counters.items():
            metrics.append(self._metric(name, value))

        return metrics

    @staticmethod
    def _metric(name: str, value: float) -> dict:
        return {
            "MetricName": name,
            "Value": float(value),
            "Unit": _METRIC_UNITS.get(name, "None"),
        }

    def _publish_put_metric_data(self, metrics: list[dict]) -> None:
        client = self.client
        if client is None:
            return
        try:
            client.put_metric_data(Namespace=self.namespace, MetricData=metrics)
        except Exception as exc:  # noqa: BLE001 - never break on observability
            logger.warning("put_metric_data failed (falling back to EMF logs): %s", exc)

    def _publish_emf(self, metrics: list[dict]) -> None:
        """Write an Embedded Metric Format log line so metrics survive without boto3."""
        try:
            definitions = [{"Name": m["MetricName"], "Unit": m["Unit"]} for m in metrics]
            emf: dict[str, Any] = {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": self.namespace,
                            "Dimensions": [],
                            "Metrics": definitions,
                        }
                    ],
                },
            }
            for m in metrics:
                emf[m["MetricName"]] = m["Value"]
            logger.info(json.dumps(emf))
        except Exception as exc:  # noqa: BLE001
            logger.debug("EMF metric emit failed: %s", exc)


def _percentile(values: list[float], pct: float) -> float:
    """Return the ``pct`` percentile of ``values`` (nearest-rank, no deps)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0, min(len(ordered) - 1, int(math.ceil(pct / 100.0 * len(ordered))) - 1))
    return ordered[rank]
