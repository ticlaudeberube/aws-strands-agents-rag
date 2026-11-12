"""Tests that the anti-hallucination answer-quality metrics reach CloudWatch.

The shared router emits ``answer/low_grounding`` / ``answer/low_confidence`` via
the injected ``metric_emitter`` (``MetricsEmitter.emit_named``). These tests
verify the names stay in sync with ``rag_routing``, that the emitter registers
the correct unit, and that the full emit → flush path publishes them.
"""

from __future__ import annotations

from typing import Any

from src.agents import rag_routing
from src.tools import cloudwatch_metrics as cw


def test_metric_names_match_router() -> None:
    """The metric-name constants must match the router's (no drift)."""
    assert cw.ANSWER_LOW_GROUNDING == rag_routing.ANSWER_LOW_GROUNDING
    assert cw.ANSWER_LOW_CONFIDENCE == rag_routing.ANSWER_LOW_CONFIDENCE


def test_answer_metrics_have_count_unit() -> None:
    """Both answer-quality metrics publish as Count, not the None default."""
    assert cw._METRIC_UNITS[cw.ANSWER_LOW_GROUNDING] == "Count"
    assert cw._METRIC_UNITS[cw.ANSWER_LOW_CONFIDENCE] == "Count"


class _CaptureClient:
    """Fake CloudWatch client capturing put_metric_data calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def test_emit_named_then_flush_publishes_answer_metrics() -> None:
    """emit_named(answer/*) → flush() publishes both metrics with Count unit."""
    client = _CaptureClient()
    emitter = cw.MetricsEmitter(settings=None, client=client)

    # Simulate what the router does via metric_emitter.
    emitter.emit_named(rag_routing.ANSWER_LOW_GROUNDING)
    emitter.emit_named(rag_routing.ANSWER_LOW_CONFIDENCE)

    metrics = emitter.flush()

    published = {m["MetricName"]: m for m in metrics}
    assert rag_routing.ANSWER_LOW_GROUNDING in published
    assert rag_routing.ANSWER_LOW_CONFIDENCE in published
    assert published[rag_routing.ANSWER_LOW_GROUNDING]["Unit"] == "Count"
    assert published[rag_routing.ANSWER_LOW_CONFIDENCE]["Value"] == 1.0

    # And they were sent to CloudWatch via put_metric_data.
    assert len(client.calls) == 1
    sent_names = {m["MetricName"] for m in client.calls[0]["MetricData"]}
    assert rag_routing.ANSWER_LOW_GROUNDING in sent_names
    assert rag_routing.ANSWER_LOW_CONFIDENCE in sent_names


def test_router_low_grounding_flows_to_emitter_end_to_end() -> None:
    """Driving the real router with an ungrounded answer emits the metric."""
    client = _CaptureClient()
    emitter = cw.MetricsEmitter(settings=None, client=client)

    class _LLM:
        def embed_text(self, _t: str) -> list[float]:
            return [0.0] * 8

        def generate(self, prompt: str, **_k: Any) -> str:
            # Shares no content words with the KB source → low grounding.
            return "Pinecone bills forty dollars monthly for replica pods."

    class _VS:
        def knn_search(
            self,
            _i: str,
            _v: list[float],
            _k: int,
            filters: dict | None = None,
            query_text: str | None = None,
        ) -> list[dict]:
            return [{"id": "1", "text": "Milvus uses HNSW indexing.", "distance": 0.9}]

    rag_routing.route_rag_query(
        "how does Milvus index",
        llm=_LLM(),
        vector_store=_VS(),
        cache=None,
        semantic_cache=None,
        web_search=None,
        kb_index="rag-kb",
        metric_emitter=emitter.emit_named,
    )

    emitter.flush()
    sent_names = {m["MetricName"] for call in client.calls for m in call["MetricData"]}
    assert rag_routing.ANSWER_LOW_GROUNDING in sent_names
