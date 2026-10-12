"""Unit tests for the serverless indexing pipeline (task 12.1).

Covers the shared chunker's ≤400-token guarantee and the ``IndexingPipeline``
orchestration (idempotency skip, happy-path embed/index/record, and the
per-chunk error-isolation policy). All AWS backends are replaced by in-process
fakes so these tests need no boto3, OpenSearch, Bedrock, or AWS config.

Requirements: 9.2, 9.3, 9.4, 9.5.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.indexing.chunking import chunk_text, count_tokens
from src.indexing.indexing_handler import (
    EVENT_DOCUMENT_SKIPPED,
    IndexingPipeline,
    lambda_handler,
)


# --------------------------------------------------------------------------- #
# In-process fakes (no AWS / boto3)                                           #
# --------------------------------------------------------------------------- #
class FakeBedrock:
    def __init__(self, fail_on: set[str] | None = None):
        self.fail_on = fail_on or set()
        self.calls: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        if text in self.fail_on:
            raise RuntimeError("embedding boom")
        return [float(len(text))] * 4


class FakeOpenSearch:
    def __init__(self, fail_doc_ids: dict[str, int] | None = None):
        # doc_id -> number of leading attempts that should raise
        self.fail_doc_ids = fail_doc_ids or {}
        self.indexed: list[dict[str, Any]] = []
        self._attempts: dict[str, int] = {}

    def index_document(self, *, index, doc_id, vector, text, metadata) -> None:
        self._attempts[doc_id] = self._attempts.get(doc_id, 0) + 1
        if self._attempts[doc_id] <= self.fail_doc_ids.get(doc_id, 0):
            raise RuntimeError("opensearch boom")
        self.indexed.append({"index": index, "doc_id": doc_id, "text": text, "metadata": metadata})


class FakeTable:
    def __init__(self, existing: dict[tuple[str, str], dict] | None = None):
        self.items: dict[tuple[str, str], dict] = dict(existing or {})
        self.puts: list[dict] = []

    def get_item(self, Key):  # noqa: N803 - boto3 kwarg name
        item = self.items.get((Key["doc_key"], Key["etag"]))
        return {"Item": item} if item is not None else {}

    def put_item(self, Item):  # noqa: N803 - boto3 kwarg name
        self.puts.append(Item)
        self.items[(Item["doc_key"], Item["etag"])] = Item


class FakeDynamoResource:
    """Stands in for a boto3 DynamoDB resource; ``.Table(name)`` -> FakeTable."""

    def __init__(self, table: "FakeTable"):
        self._table = table

    def Table(self, name):  # noqa: N802 - boto3 resource method name
        return self._table


class FakeS3:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3 kwarg names
        return {"Body": SimpleNamespace(read=lambda: self._body)}


def _settings():
    return SimpleNamespace(
        opensearch_kb_index="rag-kb",
        dynamodb_analytics_table="analytics",
        max_chunk_length=400,
        aws_region="us-east-1",
    )


def _pipeline(*, body="", bedrock=None, opensearch=None, table=None):
    table = table or FakeTable()
    return IndexingPipeline(
        settings=_settings(),
        bedrock_client=bedrock or FakeBedrock(),
        opensearch_client=opensearch or FakeOpenSearch(),
        s3_client=FakeS3(body),
        dynamodb_resource=FakeDynamoResource(table),
    )


# --------------------------------------------------------------------------- #
# Chunking bound (Requirement 9.2)                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n_words", [0, 1, 399, 400, 401, 1000, 2500])
def test_chunk_text_never_exceeds_bound(n_words):
    text = " ".join(f"w{i}" for i in range(n_words))
    chunks = chunk_text(text, max_tokens=400)
    assert all(count_tokens(c) <= 400 for c in chunks)
    assert sum(count_tokens(c) for c in chunks) == n_words


def test_chunk_text_hard_splits_single_huge_token():
    chunks = chunk_text("x" * 5000, max_tokens=400)
    assert chunks and all(count_tokens(c) <= 400 for c in chunks)


# --------------------------------------------------------------------------- #
# Idempotency skip (Requirement 9.4)                                          #
# --------------------------------------------------------------------------- #
def test_already_indexed_document_is_skipped(caplog):
    table = FakeTable(existing={("documents/a.txt", "etag1"): {"doc_key": "documents/a.txt"}})
    bedrock = FakeBedrock()
    os_client = FakeOpenSearch()
    p = _pipeline(body="hello world", bedrock=bedrock, opensearch=os_client, table=table)

    with caplog.at_level("INFO"):
        result = p.process_document("bucket", "documents/a.txt", "etag1")

    assert result["status"] == "skipped"
    # No embedding calls and no OpenSearch writes on the skip path.
    assert bedrock.calls == []
    assert os_client.indexed == []
    assert EVENT_DOCUMENT_SKIPPED in caplog.text


# --------------------------------------------------------------------------- #
# Happy path: embed + index + record (Requirements 9.3, 9.5)                  #
# --------------------------------------------------------------------------- #
def test_happy_path_indexes_all_chunks_and_records_analytics():
    body = " ".join(f"token{i}" for i in range(850))  # 3 chunks @ 400
    table = FakeTable()
    os_client = FakeOpenSearch()
    p = _pipeline(body=body, opensearch=os_client, table=table)

    result = p.process_document("bucket", "documents/a.txt", "etag1")

    assert result["status"] == "indexed"
    assert result["chunk_count"] == 3
    assert len(os_client.indexed) == 3
    assert all(d["index"] == "rag-kb" for d in os_client.indexed)
    # Analytics record contains all required fields (Req 9.5).
    assert len(table.puts) == 1
    rec = table.puts[0]
    assert rec["doc_key"] == "documents/a.txt"
    assert rec["s3_uri"] == "s3://bucket/documents/a.txt"
    assert rec["chunk_count"] == 3
    assert rec["indexed_at"].endswith("+00:00") or rec["indexed_at"].endswith("Z")


# --------------------------------------------------------------------------- #
# Per-chunk error isolation (design error table)                             #
# --------------------------------------------------------------------------- #
def test_embedding_failure_skips_only_that_chunk():
    body = " ".join(f"t{i}" for i in range(800))  # 2 chunks
    chunks = chunk_text(body, max_tokens=400)
    bedrock = FakeBedrock(fail_on={chunks[0]})
    os_client = FakeOpenSearch()
    p = _pipeline(body=body, bedrock=bedrock, opensearch=os_client)

    result = p.process_document("bucket", "documents/a.txt", "etag1")

    assert result["chunk_total"] == 2
    assert result["chunk_count"] == 1  # one chunk skipped, one indexed
    assert len(os_client.indexed) == 1


def test_opensearch_retry_once_then_succeeds():
    body = " ".join(f"t{i}" for i in range(10))  # 1 chunk
    os_client = FakeOpenSearch(fail_doc_ids={"documents/a.txt_chunk_0000": 1})
    p = _pipeline(body=body, opensearch=os_client)

    result = p.process_document("bucket", "documents/a.txt", "etag1")

    assert result["chunk_count"] == 1  # succeeded on the retry
    assert len(os_client.indexed) == 1


def test_opensearch_double_failure_skips_chunk():
    body = " ".join(f"t{i}" for i in range(10))  # 1 chunk
    os_client = FakeOpenSearch(fail_doc_ids={"documents/a.txt_chunk_0000": 2})
    p = _pipeline(body=body, opensearch=os_client)

    result = p.process_document("bucket", "documents/a.txt", "etag1")

    assert result["chunk_count"] == 0  # retried once, still failed, skipped
    assert os_client.indexed == []


# --------------------------------------------------------------------------- #
# lambda_handler record iteration                                            #
# --------------------------------------------------------------------------- #
def test_lambda_handler_malformed_record_does_not_abort_others():
    event = {"Records": [{"not_s3": True}]}
    out = lambda_handler(event, None)
    assert out["processed"] == 1
    assert out["results"][0]["status"] == "error"
