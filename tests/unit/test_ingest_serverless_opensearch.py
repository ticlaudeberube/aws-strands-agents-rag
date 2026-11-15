"""Tests for the serverless Bedrock → OpenSearch Serverless ingestion script.

Verifies the endpoint guard, that chunks are embedded with the Bedrock client
(faked, 768-dim), and that they are indexed with the expected shape. No live AWS
or OpenSearch calls are made.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.ingest_serverless_opensearch import (
    EMBEDDING_PIPELINE,
    assert_serverless_endpoint,
    ingest,
)
from src.config.settings import Settings

SERVERLESS_ENDPOINT = "https://abc123.us-east-1.aoss.amazonaws.com"


class _FakeOpenSearch:
    def __init__(self) -> None:
        self.ensure_indexes_called = False
        self.indexed: list[dict[str, Any]] = []

    def ensure_indexes(self) -> None:
        self.ensure_indexes_called = True

    def index_document(
        self, index: str, doc_id: str, vector: list[float], text: str, metadata: dict
    ) -> None:
        self.indexed.append(
            {"index": index, "doc_id": doc_id, "vector": vector, "text": text, "metadata": metadata}
        )


class _FakeBedrock:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on

    def embed_text(
        self, text: str, model: str | None = None, timeout: int | None = None
    ) -> list[float]:
        self.calls.append(text)
        if self.fail_on is not None and self.fail_on in text:
            raise RuntimeError("throttled")
        return [0.0] * 768  # projected Titan output dimension


def _settings(endpoint: str | None = SERVERLESS_ENDPOINT) -> Settings:
    return Settings().model_copy(update={"opensearch_endpoint": endpoint})


def test_ingest_embeds_with_bedrock_and_indexes_with_expected_shape() -> None:
    fake_os = _FakeOpenSearch()
    fake_bedrock = _FakeBedrock()
    settings = _settings()

    count = ingest(
        [{"title": "doc-a", "text": "vector databases store embeddings for search"}],
        settings=settings,
        opensearch=fake_os,
        bedrock=fake_bedrock,
    )

    assert fake_os.ensure_indexes_called is True
    assert count == len(fake_os.indexed) >= 1
    assert len(fake_bedrock.calls) == count
    first = fake_os.indexed[0]
    assert first["index"] == settings.opensearch_kb_index  # rag-kb
    assert len(first["vector"]) == 768
    assert first["text"]
    assert first["metadata"]["document_name"] == "doc-a"
    assert first["metadata"]["embedding_pipeline"] == EMBEDDING_PIPELINE
    assert first["doc_id"].startswith("doc-a-")


def test_ingest_chunks_long_documents() -> None:
    fake_os = _FakeOpenSearch()
    long_text = " ".join(f"word{i}" for i in range(1200))

    ingest(
        [{"title": "long", "text": long_text}],
        settings=_settings(),
        opensearch=fake_os,
        bedrock=_FakeBedrock(),
    )

    assert len(fake_os.indexed) > 1
    chunk_indexes = [item["metadata"]["chunk_index"] for item in fake_os.indexed]
    assert chunk_indexes == list(range(len(fake_os.indexed)))


def test_ingest_stops_on_embedding_failure_and_names_the_chunk() -> None:
    fake_os = _FakeOpenSearch()

    with pytest.raises(RuntimeError, match="Embedding failed for chunk"):
        ingest(
            [{"title": "doc-b", "text": "first chunk ok, second chunk fails BOOM"}],
            settings=_settings(),
            opensearch=fake_os,
            bedrock=_FakeBedrock(fail_on="BOOM"),
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        None,
        "",
        "http://localhost:9200",
        "https://localhost:9200",
        "https://search-example.us-east-1.es.amazonaws.com",
        "https://abc123.us-east-1.aoss.amazonaws.com.evil.example",
    ],
)
def test_endpoint_guard_refuses_non_serverless_hosts(endpoint: str | None) -> None:
    fake_os = _FakeOpenSearch()
    fake_bedrock = _FakeBedrock()

    with pytest.raises(ValueError):
        ingest(
            [{"title": "doc-c", "text": "should never be embedded"}],
            settings=_settings(endpoint),
            opensearch=fake_os,
            bedrock=fake_bedrock,
        )

    assert fake_bedrock.calls == []
    assert fake_os.indexed == []


def test_assert_serverless_endpoint_returns_host() -> None:
    assert assert_serverless_endpoint(SERVERLESS_ENDPOINT + "/") == (
        "abc123.us-east-1.aoss.amazonaws.com"
    )
