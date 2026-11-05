"""Tests for the LOCAL_VECTOR_BACKEND selector (Phase 1 of OpenSearch migration).

The selector chooses the Local-Mode vector store. After the Milvus removal
OpenSearch is the only accepted engine; an invalid value fails fast at settings
load; serverless mode ignores the selector entirely.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def test_default_is_opensearch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Phase 2: OpenSearch is the default local vector backend. Clear any ambient
    # env override so we assert the code default, not the shell/.env value.
    monkeypatch.delenv("LOCAL_VECTOR_BACKEND", raising=False)
    assert Settings().local_vector_backend == "opensearch"


def test_milvus_value_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Milvus is no longer a selectable backend after the engine removal.
    monkeypatch.setenv("LOCAL_VECTOR_BACKEND", "milvus")
    with pytest.raises(ValidationError):
        Settings()


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
