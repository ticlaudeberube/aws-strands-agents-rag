"""Tests for the vendor-neutral vector-tuning settings.

The engine-agnostic HNSW/search tuning settings use the ``vectordb_*`` names
and ``VECTORDB_*`` env vars. The deprecated ``MILVUS_*`` aliases were removed in
Phase 2 of the OpenSearch migration. These tests verify:

- defaults are unchanged;
- the ``VECTORDB_*`` env var sets the field.

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


def test_old_milvus_env_is_no_longer_an_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    # The deprecated MILVUS_* aliases were removed; a stale MILVUS_SEARCH_EF must
    # NOT change the vectordb_search_ef field (it falls back to the default).
    monkeypatch.delenv("VECTORDB_SEARCH_EF", raising=False)
    monkeypatch.setenv("MILVUS_SEARCH_EF", "200")
    s = Settings()
    assert s.vectordb_search_ef == 64
