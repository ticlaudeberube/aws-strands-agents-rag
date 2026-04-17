"""Node-level metrics and monitoring for RAG graph execution."""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NodeMetrics:
    """Track execution metrics for a single node."""

    node_name: str
    execution_count: int = 0
    total_duration_ms: float = 0.0
    error_count: int = 0
    total_tokens: int = 0

    @property
    def average_duration_ms(self) -> float:
        """Average execution duration in milliseconds."""
        if self.execution_count == 0:
            return 0.0
        return self.total_duration_ms / self.execution_count

    @property
    def success_rate(self) -> float:
        """Success rate as percentage (0-100)."""
        if self.execution_count == 0:
            return 100.0
        return ((self.execution_count - self.error_count) / self.execution_count) * 100

    @property
    def error_rate(self) -> float:
        """Error rate as percentage (0-100)."""
        return 100.0 - self.success_rate

    def record_execution(self, duration_ms: float, success: bool = True, tokens: int = 0) -> None:
        """Record a node execution."""
        self.execution_count += 1
        self.total_duration_ms += duration_ms
        self.total_tokens += tokens
        if not success:
            self.error_count += 1

        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            f"[{self.node_name.upper()}] execution_time={duration_ms:.1f}ms, "
            f"success={success}, tokens={tokens}",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for API responses."""
        return {
            "node_name": self.node_name,
            "execution_count": self.execution_count,
            "average_duration_ms": round(self.average_duration_ms, 2),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "success_rate": round(self.success_rate, 2),
            "error_rate": round(self.error_rate, 2),
            "error_count": self.error_count,
            "total_tokens": self.total_tokens,
        }

    def reset(self) -> None:
        """Reset metrics."""
        self.execution_count = 0
        self.total_duration_ms = 0.0
        self.error_count = 0
        self.total_tokens = 0


@dataclass
class GraphMetrics:
    """Aggregate metrics for the entire RAG graph."""

    start_time: float = field(default_factory=time.time)
    request_count: int = 0
    total_duration_ms: float = 0.0
    error_count: int = 0
    early_exit_count: int = 0
    node_metrics: dict[str, NodeMetrics] = field(default_factory=dict)

    @property
    def average_request_duration_ms(self) -> float:
        """Average request duration."""
        if self.request_count == 0:
            return 0.0
        return self.total_duration_ms / self.request_count

    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.request_count == 0:
            return 100.0
        return ((self.request_count - self.error_count) / self.request_count) * 100

    @property
    def early_exit_rate(self) -> float:
        """Percentage of requests that exited early."""
        if self.request_count == 0:
            return 0.0
        return (self.early_exit_count / self.request_count) * 100

    def get_or_create_node_metrics(self, node_name: str) -> NodeMetrics:
        """Get or create metrics for a node."""
        if node_name not in self.node_metrics:
            self.node_metrics[node_name] = NodeMetrics(node_name=node_name)
        return self.node_metrics[node_name]

    def record_request(
        self, duration_ms: float, success: bool = True, early_exit: bool = False
    ) -> None:
        """Record a request execution."""
        self.request_count += 1
        self.total_duration_ms += duration_ms
        if not success:
            self.error_count += 1
        if early_exit:
            self.early_exit_count += 1

        logger.info(
            f"[GRAPH_METRICS] request={self.request_count}, "
            f"duration={duration_ms:.1f}ms, success={success}, early_exit={early_exit}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for API responses."""
        return {
            "requests_total": self.request_count,
            "average_latency_ms": round(self.average_request_duration_ms, 2),
            "total_latency_ms": round(self.total_duration_ms, 2),
            "success_rate": round(self.success_rate, 2),
            "error_count": self.error_count,
            "early_exit_rate": round(self.early_exit_rate, 2),
            "uptime_seconds": time.time() - self.start_time,
            "nodes": {name: metrics.to_dict() for name, metrics in self.node_metrics.items()},
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.start_time = time.time()
        self.request_count = 0
        self.total_duration_ms = 0.0
        self.error_count = 0
        self.early_exit_count = 0
        for metrics in self.node_metrics.values():
            metrics.reset()
