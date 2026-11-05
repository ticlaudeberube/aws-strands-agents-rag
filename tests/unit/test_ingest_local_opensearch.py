"""Tests for the offline Ollama → OpenSearch ingestion script.

Verifies the ingest path chunks documents, embeds each chunk with Ollama
(faked, 768-dim), and calls OpenSearchClient.index_document with the expected
{id, text, metadata} shape — all without live Ollama/OpenSearch.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.config.settings import Settings
from scripts.ingest_local_opensearch import ingest


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


class _FakeOllama:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def embed_text(self, text: str, model: str | None = None) -> list[float]:
        return [0.0] * 768  # nomic-embed-text:v1.5 dimension


def test_ingest_embeds_and_indexes_with_expected_shape() -> None:
    fake_os = _FakeOpenSearch()
    settings = Settings()

    with (
        patch(
            "src.tools.opensearch_client.OpenSearchClient.for_local",
            return_value=fake_os,
        ),
        patch("src.tools.ollama_client.OllamaClient", _FakeOllama),
    ):
        count = ingest(
            [{"title": "doc-a", "text": "vector databases store embeddings for search"}],
            settings=settings,
        )

    assert fake_os.ensure_indexes_called is True
    assert count == len(fake_os.indexed) >= 1
    first = fake_os.indexed[0]
    assert first["index"] == settings.opensearch_kb_index  # rag-kb
    assert len(first["vector"]) == 768
    assert first["text"]
    assert first["metadata"]["document_name"] == "doc-a"
    assert "chunk_index" in first["metadata"]
    assert first["doc_id"].startswith("doc-a-")


def test_ingest_chunks_long_documents() -> None:
    fake_os = _FakeOpenSearch()
    settings = Settings()
    # Build text longer than max_chunk_length tokens so chunk_text splits it.
    long_text = " ".join(f"word{i}" for i in range(settings.max_chunk_length * 2 + 10))

    with (
        patch(
            "src.tools.opensearch_client.OpenSearchClient.for_local",
            return_value=fake_os,
        ),
        patch("src.tools.ollama_client.OllamaClient", _FakeOllama),
    ):
        count = ingest([{"title": "big", "text": long_text}], settings=settings)

    assert count >= 2  # multiple chunks
    # chunk indices are sequential starting at 0
    indices = [item["metadata"]["chunk_index"] for item in fake_os.indexed]
    assert indices == list(range(len(indices)))
