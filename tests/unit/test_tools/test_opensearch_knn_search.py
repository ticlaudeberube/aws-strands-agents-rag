"""Unit tests for OpenSearch k-NN search query construction.

Cover the vector-filtering configuration improvements:
- the HNSW search-time recall knob (`ef_search`) is sent on every k-NN query
  and is clamped to at least `k`;
- an optional metadata `filters` clause is passed through into the k-NN query
  when provided, and omitted otherwise (unchanged pure-vector behaviour).

A fake OpenSearch client captures the request body, so no network or the
`opensearch-py` dependency is required.
"""

from __future__ import annotations

from typing import Any

from src.config.settings import Settings
from src.tools.opensearch_client import OpenSearchClient


class _FakeClient:
    """Captures the last search body and returns a fixed, ordered hit set."""

    def __init__(self) -> None:
        self.last_index: str | None = None
        self.last_body: dict[str, Any] | None = None

    def search(self, index: str, body: dict) -> dict:
        self.last_index = index
        self.last_body = body
        result: dict[str, Any] = {
            "hits": {
                "hits": [
                    {"_id": "a", "_score": 0.9, "_source": {"text": "alpha", "metadata": {}}},
                    {"_id": "b", "_score": 0.7, "_source": {"text": "beta", "metadata": {}}},
                ]
            }
        }
        return result


def _client(search_ef: int = 64) -> tuple[OpenSearchClient, _FakeClient]:
    settings = Settings()
    settings.deployment_mode = "serverless"
    settings.vectordb_search_ef = search_ef
    fake = _FakeClient()
    return OpenSearchClient(settings=settings, client=fake), fake


def _knn_clause(body: dict[str, Any] | None) -> dict[str, Any]:
    assert body is not None
    clause: dict[str, Any] = body["query"]["knn"]["vector"]
    return clause


def test_knn_search_sends_ef_search_recall_knob() -> None:
    client, fake = _client(search_ef=100)
    client.knn_search("rag-kb", [0.0] * 8, k=10)
    clause = _knn_clause(fake.last_body)
    assert clause["method_parameters"]["ef_search"] == 100


def test_ef_search_is_clamped_to_at_least_k() -> None:
    # ef_search must be >= k to return k candidates.
    client, fake = _client(search_ef=5)
    client.knn_search("rag-kb", [0.0] * 8, k=20)
    assert _knn_clause(fake.last_body)["method_parameters"]["ef_search"] == 20


def test_knn_search_without_filter_is_pure_vector() -> None:
    client, fake = _client()
    client.knn_search("rag-kb", [0.0] * 8, k=5)
    # No filter clause when none requested (unchanged behaviour).
    assert "filter" not in _knn_clause(fake.last_body)


def test_knn_search_passes_through_metadata_filter() -> None:
    client, fake = _client()
    flt = {"term": {"metadata.source": "official"}}
    client.knn_search("rag-kb", [0.0] * 8, k=5, filters=flt)
    assert _knn_clause(fake.last_body)["filter"] == flt


def test_knn_search_returns_results_sorted_by_score_desc() -> None:
    client, _ = _client()
    results = client.knn_search("rag-kb", [0.0] * 8, k=5)
    scores = [r["distance"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0]["id"] == "a"
