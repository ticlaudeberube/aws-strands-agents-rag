"""DynamoDB session + analytics table helper (Serverless Mode).

This module backs the Lambda chat handler (``agentcore_handler``) with the two
DynamoDB tables described in the serverless-deployment design:

===================== =================================================
Table                 Purpose
===================== =================================================
``session_table``     Per-session conversation history (TTL 24h).
``analytics_table``   Per-query / indexing analytics (best-effort audit).
===================== =================================================

Design references:

- "1b. Lambda Handler" — load history keyed on ``session_id`` before invoking
  the graph; persist the Q/A pair with ``ttl = now + 86400`` afterwards.
- "Error Handling → Lambda Handler" — a session *read* failure degrades to an
  empty history (processing continues); a session *write* failure is logged,
  emits the ``errors/total`` metric and still returns the answer. Neither
  propagates a 500 to the caller.

Import safety: ``boto3`` is imported lazily (mirroring ``bedrock_client`` /
``redis_cache``) so merely importing this module — and therefore the whole
``src.tools`` package — never fails in Local Mode or test environments where
the AWS SDK is not installed. The ``dynamodb`` resource is constructed lazily
on first use.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.config.settings import Settings

logger = logging.getLogger(__name__)

__all__ = ["DynamoDBClient", "SessionReadError", "SessionWriteError"]

# Conversation history is loaded oldest-first, capped to the most recent turns.
_HISTORY_LIMIT = 20
# Session rows live for 24 hours (design: ``ttl = now + 86400``).
_SESSION_TTL_SECONDS = 86400


class SessionReadError(RuntimeError):
    """Raised internally when a session history read fails irrecoverably."""


class SessionWriteError(RuntimeError):
    """Raised internally when a session persistence write fails."""


class DynamoDBClient:
    """Thin DynamoDB helper for the session and analytics tables.

    Args:
        settings: Application ``Settings``. The table names are read from
            ``settings.dynamodb_session_table`` and
            ``settings.dynamodb_analytics_table`` and the region from
            ``settings.aws_region``.
        resource: Optional pre-constructed ``boto3`` DynamoDB *resource*.
            Supplying one (e.g. in tests, or for Lambda warm-start reuse)
            bypasses lazy construction and the ``boto3`` import entirely.
    """

    def __init__(self, settings: Settings, resource: Any | None = None):
        self._settings = settings
        self.session_table_name: str | None = getattr(settings, "dynamodb_session_table", None)
        self.analytics_table_name: str | None = getattr(settings, "dynamodb_analytics_table", None)
        self._resource = resource

    # ------------------------------------------------------------------ #
    # boto3 resource (lazy)                                              #
    # ------------------------------------------------------------------ #
    @property
    def resource(self) -> Any:
        """Return the DynamoDB ``boto3`` resource, creating it on first use.

        ``boto3`` is imported here (not at module import time) so importing
        this module never fails in Local Mode where boto3 may be absent.
        """
        if self._resource is None:
            try:
                import boto3  # type: ignore[import-untyped]  # noqa: PLC0415  (lazy, serverless-only)
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise RuntimeError(
                    "boto3 is required to use DynamoDBClient in serverless mode. "
                    "Install it with `pip install boto3`."
                ) from exc

            region = getattr(self._settings, "aws_region", None) or "us-east-1"
            self._resource = boto3.resource("dynamodb", region_name=region)
        return self._resource

    def _session_table(self) -> Any:
        if not self.session_table_name:
            raise RuntimeError(
                "settings.dynamodb_session_table is not configured; cannot access "
                "the session table in serverless mode."
            )
        return self.resource.Table(self.session_table_name)

    def _analytics_table(self) -> Any:
        if not self.analytics_table_name:
            raise RuntimeError(
                "settings.dynamodb_analytics_table is not configured; cannot access "
                "the analytics table in serverless mode."
            )
        return self.resource.Table(self.analytics_table_name)

    # ------------------------------------------------------------------ #
    # Session history (read / persist)                                   #
    # ------------------------------------------------------------------ #
    def load_history(self, session_id: str, limit: int = _HISTORY_LIMIT) -> list[dict]:
        """Load conversation history for ``session_id`` (oldest-first).

        Queries the session table with ``ScanIndexForward=True`` (ascending sort
        key) and ``Limit`` so the most recent turns are returned in chronological
        order. On any read failure this raises :class:`SessionReadError`; the
        handler catches it and degrades gracefully to an empty history (per the
        error-handling table).
        """
        try:
            from boto3.dynamodb.conditions import (
                Key,  # type: ignore[import-untyped]  # noqa: PLC0415
            )

            table = self._session_table()
            response = table.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=True,
                Limit=limit,
            )
            items = response.get("Items", [])
            return list(items)
        except Exception as exc:  # noqa: BLE001 - any read failure degrades gracefully
            logger.warning("DynamoDB session read failed for session %s: %s", session_id, exc)
            raise SessionReadError(str(exc)) from exc

    def persist_turn(
        self,
        session_id: str,
        question: str,
        answer: str,
        *,
        now: float | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Persist a Q/A pair to the session table with a 24h TTL.

        The ``ttl`` attribute is ``floor(now) + 86400`` (design "Session
        persistence always writes with correct TTL"). ``question`` and
        ``answer`` are stored verbatim. Returns the TTL value written.

        On any write failure this raises :class:`SessionWriteError`; the handler
        logs it, emits the ``errors/total`` metric and still returns the answer.
        """
        invocation_time = time.time() if now is None else now
        ttl = int(math.floor(invocation_time)) + _SESSION_TTL_SECONDS
        timestamp_ms = int(invocation_time * 1000)

        item: dict[str, Any] = {
            "session_id": session_id,
            # Sort key: millisecond timestamp keeps turns ordered and unique.
            "timestamp": timestamp_ms,
            "question": question,
            "answer": answer,
            "ttl": ttl,
        }
        if metadata:
            item["metadata"] = metadata

        try:
            table = self._session_table()
            table.put_item(Item=item)
            return ttl
        except Exception as exc:  # noqa: BLE001
            logger.error("DynamoDB session write failed for session %s: %s", session_id, exc)
            raise SessionWriteError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Analytics (best-effort audit)                                      #
    # ------------------------------------------------------------------ #
    def record_analytics(self, record: dict) -> None:
        """Best-effort write of an analytics record. Never raises.

        Analytics are an audit aid, so a failure here is logged and swallowed
        rather than affecting the request outcome.
        """
        try:
            item = dict(record)
            item.setdefault("record_id", str(uuid.uuid4()))
            self._analytics_table().put_item(Item=item)
        except Exception as exc:  # noqa: BLE001 - audit is best-effort
            logger.warning("DynamoDB analytics write failed: %s", exc)
