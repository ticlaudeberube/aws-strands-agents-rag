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
    """Captures search bodies and returns fixed or explicitly queued hit sets."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.last_index: str | None = None
        self.last_body: dict[str, Any] | None = None
        self.search_bodies: list[dict[str, Any]] = []
        self.responses = list(responses or [])

    def search(self, index: str, body: dict) -> dict:
        self.last_index = index
        self.last_body = body
        self.search_bodies.append(body)
        if self.responses:
            return self.responses.pop(0)
        result: dict[str, Any] = {
            "hits": {
                "hits": [
                    {"_id": "a", "_score": 0.9, "_source": {"text": "alpha", "metadata": {}}},
                    {"_id": "b", "_score": 0.7, "_source": {"text": "beta", "metadata": {}}},
                ]
            }
        }
        return result


def _client(
    search_ef: int = 64,
    *,
    hybrid: bool = False,
    bm25_weight: float = 0.5,
    vector_weight: float = 1.0,
    fake: _FakeClient | None = None,
) -> tuple[OpenSearchClient, _FakeClient]:
    settings = Settings()
    settings.deployment_mode = "serverless"
    settings.vectordb_search_ef = search_ef
    settings.hybrid_search_enabled = hybrid
    settings.hybrid_search_bm25_weight = bm25_weight
    settings.hybrid_search_vector_weight = vector_weight
    fake = fake or _FakeClient()
    return OpenSearchClient(settings=settings, client=fake), fake


def _knn_clause(body: dict[str, Any] | None) -> dict[str, Any]:
    assert body is not None
    query = body["query"]
    # Hybrid bodies nest the kNN clause inside a bool/should; pure-vector bodies
    # expose it directly. Return the kNN "vector" clause either way.
    if "bool" in query:
        for clause in query["bool"]["should"]:
            if "knn" in clause:
                return dict(clause["knn"]["vector"])
        raise AssertionError("no knn clause in hybrid bool query")
    return dict(query["knn"]["vector"])


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


# --------------------------------------------------------------------------- #
# Hybrid search (BM25 + vector)
# --------------------------------------------------------------------------- #


def test_hybrid_disabled_is_pure_vector_even_with_query_text() -> None:
    # Flag off: query_text is ignored and the body stays pure vector k-NN.
    client, fake = _client(hybrid=False)
    client.knn_search("rag-kb", [0.0] * 8, k=5, query_text="vector database HNSW")
    assert fake.last_body is not None
    assert "bool" not in fake.last_body["query"]
    assert "knn" in fake.last_body["query"]


def test_hybrid_enabled_without_query_text_is_pure_vector() -> None:
    # Hybrid needs BOTH the flag and a non-empty query_text; no text -> vector.
    client, fake = _client(hybrid=True)
    client.knn_search("rag-kb", [0.0] * 8, k=5)
    assert fake.last_body is not None
    assert "bool" not in fake.last_body["query"]


def test_hybrid_enabled_blank_query_text_is_pure_vector() -> None:
    client, fake = _client(hybrid=True)
    client.knn_search("rag-kb", [0.0] * 8, k=5, query_text="   ")
    assert fake.last_body is not None
    assert "bool" not in fake.last_body["query"]


def test_hybrid_runs_separate_vector_and_lexical_searches() -> None:
    client, fake = _client(hybrid=True)
    client.knn_search("rag-kb", [0.0] * 8, k=5, query_text="what is HNSW")
    assert len(fake.search_bodies) == 2
    assert "knn" in fake.search_bodies[0]["query"]
    assert fake.search_bodies[1]["query"]["match"]["text"]["query"] == "what is HNSW"


def test_hybrid_fuses_by_configured_weights_and_preserves_vector_distance() -> None:
    vector_response = {
        "hits": {
            "hits": [
                {"_id": "vector", "_score": 0.82, "_source": {"text": "vector result"}},
                {"_id": "shared", "_score": 0.71, "_source": {"text": "shared result"}},
            ]
        }
    }
    lexical_response = {
        "hits": {
            "hits": [
                {"_id": "shared", "_score": 9.0, "_source": {"text": "shared result"}},
                {"_id": "lexical", "_score": 15.0, "_source": {"text": "lexical result"}},
            ]
        }
    }
    fake = _FakeClient([vector_response, lexical_response])
    client, _ = _client(
        hybrid=True,
        bm25_weight=0.3,
        vector_weight=1.5,
        fake=fake,
    )
    results = client.knn_search("rag-kb", [0.0] * 8, k=5, query_text="HNSW")

    assert [result["id"] for result in results] == ["shared", "vector", "lexical"]
    assert results[0]["distance"] == 0.71
    assert results[1]["distance"] == 0.82
    assert results[2]["distance"] is None
    assert results[0]["rrf_score"] > results[1]["rrf_score"] > results[2]["rrf_score"]


def test_hybrid_filters_both_vector_and_lexical_searches() -> None:
    client, fake = _client(hybrid=True)
    flt = {"term": {"metadata.tenant_id": "tenant-a"}}
    # The filter must scope both retrieval paths to the same permitted documents.
    client.knn_search("rag-kb", [0.0] * 8, k=5, filters=flt, query_text="HNSW")
    vector_query = fake.search_bodies[-2]["query"]["knn"]["vector"]
    lexical_query = fake.search_bodies[-1]["query"]["bool"]
    assert vector_query["filter"] == flt
    assert lexical_query["filter"] == flt


def test_hybrid_keeps_ef_search_and_metadata_filter_on_vector_clause() -> None:
    # The recall knob and metadata filter are retained in vector queries.
    client, fake = _client(hybrid=True, search_ef=100)
    flt = {"term": {"metadata.source": "official"}}
    client.knn_search("rag-kb", [0.0] * 8, k=5, query_text="HNSW", filters=flt)
    knn_vec = fake.search_bodies[-2]["query"]["knn"]["vector"]
    assert knn_vec["method_parameters"]["ef_search"] == 100
    assert knn_vec["filter"] == flt


def test_hybrid_search_is_disabled_for_semantic_cache_index() -> None:
    client, fake = _client(hybrid=True)
    client.knn_search("rag-cache", [0.0] * 8, k=5, query_text="HNSW")
    assert len(fake.search_bodies) == 1
    assert "knn" in fake.last_body["query"]
