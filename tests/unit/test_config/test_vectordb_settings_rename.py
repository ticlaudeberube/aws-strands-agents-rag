"""Tests for the vendor-neutral vector-tuning settings rename.

Phase 1 of the OpenSearch migration renames the engine-agnostic HNSW/search
tuning settings from ``milvus_*`` to ``vectordb_*`` while still accepting the
old ``MILVUS_*`` env vars as deprecated aliases. These tests verify:

- defaults are unchanged;
- the new ``VECTORDB_*`` env var sets the field;
- the old ``MILVUS_*`` env var still sets the field (deprecated alias);
- ``VECTORDB_*`` wins when both are set.

Env vars are set via monkeypatch and a fresh ``Settings()`` is constructed each
time (pydantic-settings reads the environment at instantiation).
"""

from __future__ import annotations

import pytest

from src.config.settings import Settings


def test_defaults_unchanged() -> None:
    s = Settings()
    assert s.vectordb_index_type == "HNSW"
    assert s.vectordb_metric_type == "COSINE"
    assert s.vectordb_hnsw_m == 30
    assert s.vectordb_hnsw_ef_construction == 200
    assert s.vectordb_ivf_nlist == 128
    assert s.vectordb_search_ef == 64


def test_new_vectordb_env_sets_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTORDB_SEARCH_EF", "128")
    monkeypatch.setenv("VECTORDB_HNSW_M", "48")
    s = Settings()
    assert s.vectordb_search_ef == 128
    assert s.vectordb_hnsw_m == 48


def test_old_milvus_env_still_works_as_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deprecated alias path: a pre-migration .env with MILVUS_* must still apply.
    monkeypatch.delenv("VECTORDB_SEARCH_EF", raising=False)
    monkeypatch.setenv("MILVUS_SEARCH_EF", "200")
    s = Settings()
    assert s.vectordb_search_ef == 200


def test_new_name_wins_when_both_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTORDB_SEARCH_EF", "256")
    monkeypatch.setenv("MILVUS_SEARCH_EF", "32")
    s = Settings()
    assert s.vectordb_search_ef == 256
