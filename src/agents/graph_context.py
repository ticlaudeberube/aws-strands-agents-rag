"""Structured context and execution tracing for RAG graph."""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NodeTiming:
    """Execution timing information for a single node."""

    node_name: str
    start_time: float
    end_time: float
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str = ""
    success: bool = True
    error_message: str | None = None

    @property
    def duration_ms(self) -> float:
        """Total execution time in milliseconds."""
        return (self.end_time - self.start_time) * 1000


@dataclass
class ExecutionTrace:
    """Complete execution trace for a graph run."""

    timings: dict[str, NodeTiming] = field(default_factory=dict)
    decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    early_exit: bool = False
    early_exit_reason: str | None = None

    def record_node_timing(self, node_timing: NodeTiming) -> None:
        """Record timing for a node execution."""
        self.timings[node_timing.node_name] = node_timing
        logger.debug(
            f"[TIMING] {node_timing.node_name}: {node_timing.duration_ms:.1f}ms, "
            f"success={node_timing.success}"
        )

    def record_decision(self, node_name: str, decision_data: dict[str, Any]) -> None:
        """Record decision-making data for a node."""
        self.decisions[node_name] = decision_data
        logger.debug(f"[DECISION] {node_name}: {decision_data}")

    def mark_early_exit(self, reason: str) -> None:
        """Mark that execution exited early."""
        self.early_exit = True
        self.early_exit_reason = reason
        logger.info(f"[EARLY_EXIT] {reason}")

    def finalize(self) -> None:
        """Finalize the trace and log summary."""
        self.end_time = time.time()
        total_duration = (self.end_time - self.start_time) * 1000

        logger.info(
            f"[EXECUTION_TRACE] Total: {total_duration:.1f}ms, "
            f"early_exit={self.early_exit}, nodes={len(self.timings)}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert trace to dictionary for API responses."""
        return {
            "total_duration_ms": (self.end_time or time.time() - self.start_time) * 1000,
            "early_exit": self.early_exit,
            "early_exit_reason": self.early_exit_reason,
            "nodes": {
                name: {
                    "duration_ms": timing.duration_ms,
                    "success": timing.success,
                    "error": timing.error_message,
                    "tokens": {"input": timing.input_tokens, "output": timing.output_tokens},
                }
                for name, timing in self.timings.items()
            },
            "decisions": self.decisions,
        }


@dataclass
class GraphContext:
    """Typed context passed through the RAG graph execution."""

    # Input query
    question: str

    # Knowledge base configuration
    collection_name: str = "milvus_docs"
    collections: list[str] = field(default_factory=lambda: ["milvus_docs"])
    top_k: int = 5

    # Execution flags
    is_time_sensitive: bool = False
    enable_web_search_fallback: bool = False

    # Execution state
    execution_trace: ExecutionTrace = field(default_factory=ExecutionTrace)

    # Node results (populated during execution)
    topic_result: Any | None = None
    security_result: Any | None = None
    retrieval_result: dict[str, Any] | None = None
    final_answer: str | None = None
    final_sources: list[dict[str, Any]] | None = None
    confidence_score: float | None = None

    # Additional data
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate_for_rag_worker(self) -> bool:
        """Validate context has required fields for RAG worker."""
        required_fields = ["question", "collection_name", "topic_result", "security_result"]
        missing = [f for f in required_fields if getattr(self, f, None) is None]
        if missing:
            logger.error(f"Context missing required fields: {missing}")
            return False
        return True

    def should_skip_rag_worker(self) -> bool:
        """Check if execution should skip RAG worker (early exit)."""
        if self.topic_result and not getattr(self.topic_result, "is_valid", True):
            return True
        if self.security_result and not getattr(self.security_result, "is_valid", True):
            return True
        return False

    def get_rejection_reason(self) -> str | None:
        """Get the reason for early rejection, if applicable."""
        if self.topic_result and not getattr(self.topic_result, "is_valid", True):
            return f"Topic rejected: {getattr(self.topic_result, 'reason', 'unknown')}"
        if self.security_result and not getattr(self.security_result, "is_valid", True):
            return f"Security rejected: {getattr(self.security_result, 'reason', 'unknown')}"
        return None

    def finalize_execution(self) -> None:
        """Finalize execution and prepare for response."""
        self.execution_trace.finalize()
        if self.should_skip_rag_worker():
            reason = self.get_rejection_reason() or "Unknown"
            self.execution_trace.mark_early_exit(reason)

    def to_response_dict(self) -> dict[str, Any]:
        """Convert context to API response format."""
        return {
            "answer": self.final_answer or "",
            "sources": self.final_sources or [],
            "confidence_score": self.confidence_score or 0.0,
            "execution_trace": self.execution_trace.to_dict(),
        }
