"""Unit tests for the DynamoDB-backed runtime threshold store.

Verify the "change a row, no redeploy" override path: a configured thresholds
table overrides the matching ``settings`` defaults, every failure mode falls
back to ``settings``, values are coerced to the setting's type, and the table is
read at most once (cold-start cache).

A lightweight fake DynamoDB *resource* is injected so no boto3/network is used.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.config.settings import Settings
from src.tools.threshold_store import TUNABLE_THRESHOLDS, ThresholdStore


class _FakeTable:
    def __init__(self, items: list[dict], scan_calls: list[int]) -> None:
        self._items = items
        self._scan_calls = scan_calls
        self.raise_on_scan = False

    def scan(self, **_kwargs: Any) -> dict:
        self._scan_calls.append(1)
        if self.raise_on_scan:
            raise RuntimeError("boom")
        return {"Items": list(self._items)}


class _FakeResource:
    def __init__(self, items: list[dict]) -> None:
        self.scan_calls: list[int] = []
        self._table = _FakeTable(items, self.scan_calls)

    def Table(self, _name: str) -> _FakeTable:  # noqa: N802 (boto3 API name)
        return self._table


def _settings(*, thresholds_table: str | None = "StrandsRAG-Thresholds") -> Settings:
    # Settings uses validation_alias (env var names) and forbids extra kwargs,
    # so set attributes after construction rather than via the constructor.
    settings = Settings()
    settings.deployment_mode = "serverless"
    settings.dynamodb_thresholds_table = thresholds_table
    return settings


def test_override_replaces_settings_value() -> None:
    res = _FakeResource([{"name": "answer_grounding_threshold", "value": Decimal("0.6")}])
    store = ThresholdStore(_settings(), resource=res)
    assert store.get("answer_grounding_threshold") == 0.6


def test_missing_override_falls_back_to_settings() -> None:
    res = _FakeResource([])  # empty table
    settings = _settings()
    store = ThresholdStore(settings, resource=res)
    assert store.get("answer_confidence_threshold") == settings.answer_confidence_threshold


def test_no_table_configured_uses_settings_without_scanning() -> None:
    res = _FakeResource([{"name": "answer_grounding_threshold", "value": Decimal("0.9")}])
    settings = _settings(thresholds_table=None)
    store = ThresholdStore(settings, resource=res)
    assert store.get("answer_grounding_threshold") == settings.answer_grounding_threshold
    assert res.scan_calls == []  # never scanned


def test_scan_failure_falls_back_to_settings() -> None:
    res = _FakeResource([])
    res._table.raise_on_scan = True
    settings = _settings()
    store = ThresholdStore(settings, resource=res)
    assert store.get("answer_grounding_threshold") == settings.answer_grounding_threshold


def test_unknown_rows_are_ignored() -> None:
    res = _FakeResource(
        [
            {"name": "bedrock_inference_model_id", "value": "evil-model"},  # not tunable
            {"name": "answer_grounding_threshold", "value": Decimal("0.5")},
        ]
    )
    store = ThresholdStore(_settings(), resource=res)
    assert store.get("answer_grounding_threshold") == 0.5
    # A non-tunable name always resolves to settings, never the stray row.
    assert store.get("bedrock_inference_model_id") == _settings().bedrock_inference_model_id


def test_bool_coercion_for_grounding_retry_enabled() -> None:
    res = _FakeResource([{"name": "grounding_retry_enabled", "value": False}])
    store = ThresholdStore(_settings(), resource=res)
    assert store.get("grounding_retry_enabled") is False


def test_bool_coercion_from_string() -> None:
    res = _FakeResource([{"name": "grounding_retry_enabled", "value": "false"}])
    store = ThresholdStore(_settings(), resource=res)
    assert store.get("grounding_retry_enabled") is False


def test_int_coercion_for_multiplier() -> None:
    res = _FakeResource([{"name": "grounding_retry_top_k_multiplier", "value": Decimal("3")}])
    store = ThresholdStore(_settings(), resource=res)
    value = store.get("grounding_retry_top_k_multiplier")
    assert value == 3
    assert isinstance(value, int)


def test_table_scanned_at_most_once() -> None:
    res = _FakeResource([{"name": "answer_grounding_threshold", "value": Decimal("0.5")}])
    store = ThresholdStore(_settings(), resource=res)
    store.get("answer_grounding_threshold")
    store.get("answer_confidence_threshold")
    store.resolve_all()
    assert res.scan_calls == [1]  # single scan, cached thereafter


def test_resolve_all_returns_every_tunable() -> None:
    res = _FakeResource([{"name": "answer_grounding_threshold", "value": Decimal("0.5")}])
    store = ThresholdStore(_settings(), resource=res)
    resolved = store.resolve_all()
    assert set(resolved) == set(TUNABLE_THRESHOLDS)
    assert resolved["answer_grounding_threshold"] == 0.5
