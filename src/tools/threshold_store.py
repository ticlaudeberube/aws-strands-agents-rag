"""Runtime-tunable anti-hallucination thresholds backed by DynamoDB.

The Layer-3 anti-hallucination knobs (grounding/confidence thresholds, the
web-search fallback threshold, the semantic-cache threshold, and the
grounding-retry controls) default to the values in ``src/config/settings.py``.
Those are compile-time constants: changing one requires a redeploy.

This store adds the "change a row, no redeploy" capability from the production
hardening guidance: in **serverless mode**, when a thresholds table is
configured, the values are read **once at cold start** and each row overrides
the matching ``settings`` default for the life of the warm container. An
operator can retune grounding without shipping code; the change takes effect on
the next cold start (or a forced new deployment/version).

Design choices (match the existing ``DynamoDBClient``):

- **Fallback-first.** Any problem — table unset, ``boto3`` absent, table
  missing, scan error, malformed row — logs and falls back to the ``settings``
  value. The store is purely additive: with no table, behaviour is identical to
  today. Local mode never constructs it.
- **Read once, cache for the container.** A single ``scan`` (a handful of rows)
  on first use, cached thereafter, so there is no per-request DynamoDB call.
- **Lazy boto3.** ``boto3`` is imported on first use so importing this module
  (and the whole ``src.tools`` package) never requires the AWS SDK.

Table schema (one item per threshold)::

    { "name": "answer_grounding_threshold", "value": 0.45 }

``name`` is the partition key and matches the ``settings`` attribute name.
``value`` is a number (DynamoDB returns it as ``Decimal``) or a bool.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.config.settings import Settings

logger = logging.getLogger(__name__)

__all__ = ["ThresholdStore", "TUNABLE_THRESHOLDS"]

# The settings attributes an operator may override at runtime. Restricted to the
# Layer-3 anti-hallucination tuning knobs — deliberately NOT model IDs, table
# names, or other infra config, which must change through a deploy.
TUNABLE_THRESHOLDS: tuple[str, ...] = (
    "answer_grounding_threshold",
    "answer_confidence_threshold",
    "web_search_fallback_threshold",
    "response_cache_threshold",
    "grounding_retry_enabled",
    "grounding_retry_top_k_multiplier",
)


class ThresholdStore:
    """Resolve tunable thresholds, preferring DynamoDB overrides over settings.

    Args:
        settings: Application ``Settings`` (the fallback source and the table
            name via ``settings.dynamodb_thresholds_table``).
        resource: Optional pre-constructed ``boto3`` DynamoDB *resource*
            (tests / warm-start reuse). Bypasses lazy construction and the
            ``boto3`` import.
    """

    def __init__(self, settings: Settings, resource: Any | None = None) -> None:
        self._settings = settings
        self._table_name: str | None = getattr(settings, "dynamodb_thresholds_table", None)
        self._resource = resource
        self._overrides: dict[str, Any] | None = None  # None until first load

    # ------------------------------------------------------------------ #
    # boto3 resource (lazy)                                              #
    # ------------------------------------------------------------------ #
    @property
    def _ddb(self) -> Any:
        if self._resource is None:
            import boto3  # type: ignore[import-untyped]  # noqa: PLC0415  (lazy, serverless-only)

            region = getattr(self._settings, "aws_region", None) or "us-east-1"
            self._resource = boto3.resource("dynamodb", region_name=region)
        return self._resource

    # ------------------------------------------------------------------ #
    # Override loading (once, cached)                                    #
    # ------------------------------------------------------------------ #
    def _load_overrides(self) -> dict[str, Any]:
        """Scan the thresholds table once; return ``{name: value}`` overrides.

        Never raises: any failure yields an empty override map so callers fall
        back to ``settings``. Only recognised (``TUNABLE_THRESHOLDS``) names are
        kept, so a stray row cannot change unrelated behaviour.
        """
        if not self._table_name:
            return {}

        try:
            table = self._ddb.Table(self._table_name)
            items = table.scan(
                ProjectionExpression="#n, #v",
                ExpressionAttributeNames={"#n": "name", "#v": "value"},
            ).get("Items", [])
        except Exception as exc:  # noqa: BLE001 - any failure degrades to settings
            logger.warning(
                "Thresholds table read failed (%s); using settings.py defaults: %s",
                self._table_name,
                exc,
            )
            return {}

        overrides: dict[str, Any] = {}
        for item in items:
            name = item.get("name")
            if name not in TUNABLE_THRESHOLDS or "value" not in item:
                continue
            overrides[name] = self._coerce(name, item["value"])

        if overrides:
            logger.info(
                "Loaded %d threshold override(s) from %s: %s",
                len(overrides),
                self._table_name,
                sorted(overrides),
            )
        return overrides

    def _coerce(self, name: str, raw: Any) -> Any:
        """Coerce a DynamoDB value (often ``Decimal``) to the setting's type.

        Uses the current ``settings`` attribute's type as the target so a bool
        setting stays bool and an int setting stays int.
        """
        current = getattr(self._settings, name, None)
        try:
            if isinstance(current, bool):
                # bool must be checked before int (bool is a subclass of int).
                if isinstance(raw, str):
                    return raw.strip().lower() in ("1", "true", "yes", "on")
                return bool(raw)
            if isinstance(current, int):
                return int(raw)
            if isinstance(current, float):
                return float(raw)
        except (TypeError, ValueError) as exc:
            logger.warning("Ignoring malformed override for %s=%r: %s", name, raw, exc)
            return current
        return raw

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def get(self, name: str) -> Any:
        """Return the override for ``name`` if present, else the settings value.

        Lazily loads (and caches) the override map on first call.
        """
        if name not in TUNABLE_THRESHOLDS:
            # Not a tunable threshold → always the settings value.
            return getattr(self._settings, name)
        if self._overrides is None:
            self._overrides = self._load_overrides()
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._settings, name)

    def resolve_all(self) -> dict[str, Any]:
        """Return every tunable threshold resolved (override or settings)."""
        return {name: self.get(name) for name in TUNABLE_THRESHOLDS}
