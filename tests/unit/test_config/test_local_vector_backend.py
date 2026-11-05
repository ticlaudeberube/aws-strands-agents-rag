"""Tests for the LOCAL_VECTOR_BACKEND selector (Phase 1 of OpenSearch migration).

The selector chooses the Local-Mode vector store (milvus | opensearch) without
changing deployment_mode. Default is milvus so current behavior is unchanged;
an invalid value fails fast at settings load; serverless mode ignores it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def test_default_is_milvus() -> None:
    assert Settings().local_vector_backend == "milvus"


def test_opensearch_value_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_VECTOR_BACKEND", "opensearch")
    assert Settings().local_vector_backend == "opensearch"


def test_invalid_value_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_VECTOR_BACKEND", "pinecone")
    with pytest.raises(ValidationError):
        Settings()


def test_local_opensearch_connection_defaults() -> None:
    s = Settings()
    assert s.opensearch_local_host == "localhost"
    assert s.opensearch_local_port == 9200


def test_serverless_ignores_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    # The selector is only consulted in the local branch of create_rag_graph;
    # here we assert it loads independently of deployment_mode (serverless does
    # not reject or require it).
    monkeypatch.setenv("DEPLOYMENT_MODE", "serverless")
    monkeypatch.setenv("LOCAL_VECTOR_BACKEND", "opensearch")
    s = Settings()
    assert s.deployment_mode == "serverless"
    assert s.local_vector_backend == "opensearch"  # loaded, simply unused by serverless
