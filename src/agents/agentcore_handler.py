"""AWS Lambda chat handler (Serverless Mode entry-point).

This is the serverless counterpart of the Local Mode FastAPI ``/v1/chat/completions``
endpoint. It is the entry-point for every chat request arriving through API
Gateway (proxy integration) and is referenced by Terraform as
``agentcore_handler.lambda_handler``.

Design reference: serverless-deployment design, section
"1b. Lambda Handler (agentcore_handler.py)", the "Response Schema (both modes)",
"CloudWatch Metric Dimensions", and "Error Handling → Lambda Handler" tables.

Responsibilities (Requirements 1.1, 1.3, 1.4, 1.5, 4.4, 6.6, 12.1, 12.2, 12.5):

- **10.1 Parsing & validation**: parse the API Gateway proxy ``body`` and extract
  ``question``, ``session_id``, optional ``force_web_search`` and ``top_k``.
  Return HTTP 400 *before invoking any agent node* for malformed JSON
  (``BAD_REQUEST``), a missing ``question`` (``MISSING_FIELD``), or ``top_k``
  outside the closed range [1, 50] (``INVALID_TOP_K``).
- **10.3 Session + graph**: load conversation history from DynamoDB
  (``query(session_id, ScanIndexForward=True, Limit=20)``), build the serverless
  graph via ``create_rag_graph`` and invoke its shared route, then persist the
  Q/A pair with ``ttl = floor(now) + 86400``. Degrade gracefully on DynamoDB
  read/write failures.
- **10.5 Error handling**: catch unhandled exceptions, log the full stack trace,
  emit the ``errors/total`` metric, and return HTTP 500 with
  ``{error_code, message}`` mapping the documented conditions.
- **10.7 Observability**: emit a structured JSON log (``request_id``,
  ``session_id``, ``tier_used``, ``latency_ms``, ``cache_hit``, ``error_code``
  when applicable, and ``cold_start=true`` on cold start) and custom CloudWatch
  metrics; wrap work in X-Ray subsegments where the SDK is available.

Import safety: all AWS-specific collaborators (DynamoDB client, CloudWatch
metrics, Bedrock/OpenSearch/Redis clients built by ``create_rag_graph``) use the
lazy-import pattern, so importing this module never requires ``boto3`` and does
not affect Local Mode (``api_server.py`` is unchanged).
"""

from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from typing import Any, Literal

from src.agents.strands_graph_agent import create_rag_graph
from src.config.settings import Settings, get_settings
from src.tools import cloudwatch_metrics as cw
from src.tools.dynamodb_client import (
    DynamoDBClient,
    SessionReadError,
    SessionWriteError,
)

logger = logging.getLogger(__name__)

# ``top_k`` is accepted in the closed range [1, 50] (Req 4.4, Property 15).
_TOP_K_MIN = 1
_TOP_K_MAX = 50

# Module-level cold-start flag. The first invocation in a warm Lambda execution
# context observes ``True``; every subsequent invocation observes ``False``
# (Req 12.5, Property 32).
_COLD_START = True

# Error codes (design "Error Handling → Lambda Handler").
ERR_BAD_REQUEST = "BAD_REQUEST"
ERR_MISSING_FIELD = "MISSING_FIELD"
ERR_INVALID_TOP_K = "INVALID_TOP_K"
ERR_LLM = "LLM_ERROR"
ERR_INTERNAL = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Response envelope helpers (API Gateway proxy integration)
# ---------------------------------------------------------------------------
def _response(status_code: int, body: dict) -> dict:
    """Build an API Gateway proxy response with a JSON-serialised body."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _error(status_code: int, error_code: str, message: str) -> dict:
    """Build an error response matching the serverless error schema.

    The body always contains both ``error_code`` and ``message`` string fields
    (Property 3 / Req 1.5).
    """
    return _response(status_code, {"error_code": error_code, "message": message})


# ---------------------------------------------------------------------------
# 10.1 — Request parsing & validation
# ---------------------------------------------------------------------------
class _ValidationError(Exception):
    """Internal signal carrying a ready-to-return HTTP 400 error response."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def _parse_body(event: dict) -> dict:
    """Parse the API Gateway proxy ``body`` into a dict.

    Raises :class:`_ValidationError` (``BAD_REQUEST``) when the body is not
    valid JSON or is not a JSON object (design: malformed request JSON → 400).
    """
    raw = event.get("body") if isinstance(event, dict) else None

    # Already-decoded body (e.g. a test harness passing a dict) is accepted.
    if isinstance(raw, dict):
        return raw

    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        raise _ValidationError(ERR_BAD_REQUEST, "Request body is empty or missing.")

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise _ValidationError(ERR_BAD_REQUEST, f"Malformed request JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise _ValidationError(ERR_BAD_REQUEST, "Request body must be a JSON object.")
    return parsed


def _parse_request(event: dict) -> dict:
    """Parse + validate the request, returning the normalised fields.

    Performs *all* HTTP 400 validation before any agent node is invoked
    (Req 1.1, 4.4):

    - malformed JSON / non-object body → ``BAD_REQUEST``
    - missing or empty ``question`` → ``MISSING_FIELD``
    - ``top_k`` present but not an integer in [1, 50] → ``INVALID_TOP_K``

    Returns a dict with ``question`` (str), ``session_id`` (str),
    ``force_web_search`` (bool) and ``top_k`` (int). ``session_id`` defaults to a
    fresh UUID when absent; ``top_k`` defaults to ``settings.default_top_k``
    (clamped into range) when absent.
    """
    body = _parse_body(event)

    # question — required, non-empty after stripping (MISSING_FIELD).
    question = body.get("question")
    if question is None or not isinstance(question, str) or question.strip() == "":
        raise _ValidationError(ERR_MISSING_FIELD, "Field 'question' is required.")

    # session_id — optional; generate one when absent so persistence has a key.
    session_id = body.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        session_id = str(uuid.uuid4())

    # force_web_search — optional boolean, preserved verbatim (Property 1).
    force_web_search = bool(body.get("force_web_search", False))

    # top_k — optional; when present must be an int in [1, 50] (Property 15).
    top_k = _validate_top_k(body)

    return {
        "question": question,
        "session_id": session_id,
        "force_web_search": force_web_search,
        "top_k": top_k,
    }


def _validate_top_k(body: dict) -> int:
    """Validate ``top_k`` exhaustively over the integer domain (Req 4.4).

    When absent, a sensible default is used. When present it must be an integer
    (``bool`` is rejected — it is an ``int`` subclass but not a valid top_k) in
    the closed range [1, 50], otherwise ``INVALID_TOP_K`` is raised.
    """
    settings = get_settings()
    default_top_k = int(getattr(settings, "default_top_k", 10))
    default_top_k = max(_TOP_K_MIN, min(_TOP_K_MAX, default_top_k))

    if "top_k" not in body or body.get("top_k") is None:
        return default_top_k

    value = body["top_k"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise _ValidationError(
            ERR_INVALID_TOP_K,
            f"top_k must be an integer in [{_TOP_K_MIN}, {_TOP_K_MAX}].",
        )
    if value < _TOP_K_MIN or value > _TOP_K_MAX:
        raise _ValidationError(
            ERR_INVALID_TOP_K,
            f"top_k {value} is outside the allowed range [{_TOP_K_MIN}, {_TOP_K_MAX}].",
        )
    return int(value)


# ---------------------------------------------------------------------------
# 10.3 — Session load / persist + graph invocation
# ---------------------------------------------------------------------------
# Warm-context singletons: the graph and DynamoDB client are expensive to build
# (they construct the Bedrock/OpenSearch/Redis clients), so they are reused
# across warm invocations.
_GRAPH_CACHE: dict[str, Any] = {}
_DDB_CLIENT: DynamoDBClient | None = None


def _get_graph(settings: Settings) -> dict:
    """Build (once per warm context) and return the serverless RAG graph."""
    key = settings.deployment_mode
    graph = _GRAPH_CACHE.get(key)
    if graph is None:
        graph = create_rag_graph(settings)
        _GRAPH_CACHE[key] = graph
    return dict(graph)


def _get_ddb_client(settings: Settings) -> DynamoDBClient:
    """Build (once per warm context) and return the DynamoDB helper."""
    global _DDB_CLIENT
    if _DDB_CLIENT is None:
        _DDB_CLIENT = DynamoDBClient(settings)
    return _DDB_CLIENT


def _load_history(ddb: DynamoDBClient, session_id: str) -> list[dict]:
    """Load conversation history, degrading to empty on a read failure.

    Per the error-handling table: a DynamoDB session read failure logs a warning
    and proceeds with an empty history (processing continues, no 500).
    """
    try:
        return ddb.load_history(session_id)
    except SessionReadError:
        logger.warning(
            "Proceeding with empty history after DynamoDB read failure (session %s).",
            session_id,
        )
        return []


# ---------------------------------------------------------------------------
# X-Ray subsegment helper (optional, guarded)
# ---------------------------------------------------------------------------
class _xray_subsegment:
    """Context manager wrapping work in an X-Ray subsegment when available.

    X-Ray *active tracing* is enabled at the infrastructure level (Terraform
    observability module). This optional hook adds application subsegments when
    the ``aws_xray_sdk`` is installed, and is a no-op otherwise, so it never
    affects Local Mode or test environments.
    """

    def __init__(self, name: str):
        self._name = name
        self._recorder: Any = None

    def __enter__(self) -> "_xray_subsegment":
        try:
            from aws_xray_sdk.core import xray_recorder  # noqa: PLC0415

            self._recorder = xray_recorder
            self._recorder.begin_subsegment(self._name)
        except Exception:  # noqa: BLE001 - tracing is best-effort
            self._recorder = None
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        if self._recorder is not None:
            try:
                self._recorder.end_subsegment()
            except Exception:  # noqa: BLE001
                pass
        return False  # never suppress exceptions


# ---------------------------------------------------------------------------
# Lambda entry-point
# ---------------------------------------------------------------------------
def lambda_handler(event: dict, context: Any = None) -> dict:
    """AWS Lambda entry-point for the serverless RAG chat endpoint.

    Returns an API Gateway proxy response. Request validation errors return HTTP
    400; successful requests return HTTP 200 with the shared response schema;
    unhandled exceptions return HTTP 500 with ``{error_code, message}``.
    """
    global _COLD_START
    cold_start = _COLD_START
    _COLD_START = False

    start_time = time.time()
    settings = get_settings()
    metrics = cw.MetricsEmitter(settings)

    request_id = _extract_request_id(event, context)
    session_id = "unknown"
    tier_used = "none"
    cache_hit = False
    error_code: str | None = None

    try:
        # ---- 10.1: parse + validate BEFORE invoking any agent node --------
        try:
            request = _parse_request(event)
        except _ValidationError as ve:
            # 400s are an expected client-error outcome, not an unhandled error:
            # log at warning level and return the structured 400 envelope.
            error_code = ve.error_code
            logger.warning("Request validation failed [%s]: %s", ve.error_code, ve.message)
            return _error(400, ve.error_code, ve.message)

        session_id = request["session_id"]
        question = request["question"]
        top_k = request["top_k"]
        force_web_search = request["force_web_search"]

        # ---- 10.3: load session history (graceful degradation) -----------
        ddb = _get_ddb_client(settings)
        with _xray_subsegment("dynamodb_load_history"):
            _history = _load_history(ddb, session_id)
        logger.info("Loaded %d history turn(s) for session %s", len(_history), session_id)

        # ---- 10.3: build graph + invoke shared route ---------------------
        graph = _get_graph(settings)
        shared_route = graph.get("shared_route")
        if shared_route is None:  # pragma: no cover - defensive
            raise RuntimeError("Serverless graph is missing the shared_route entry.")

        try:
            with _xray_subsegment("rag_route"):
                routing_result = shared_route(
                    question,
                    top_k=top_k,
                    force_web_search=force_web_search,
                    metric_emitter=metrics.emit_named,
                )
        except Exception as exc:  # noqa: BLE001 - mapped to LLM_ERROR below
            # A failure inside generation/retrieval is reported as LLM_ERROR per
            # the error-handling table ("Bedrock model error → HTTP 500,
            # error_code: LLM_ERROR").
            error_code = ERR_LLM
            metrics.record_error()
            logger.error("RAG routing failed:\n%s", traceback.format_exc())
            return _error(500, ERR_LLM, f"LLM/RAG processing error: {exc}")

        tier_used = routing_result.tier_used
        cache_hit = routing_result.cache_hit

        # Record observability signals (Req 12.2).
        metrics.record_latency((time.time() - start_time) * 1000)
        metrics.record_cache_outcome(cache_hit)
        if tier_used == "websearch":
            metrics.record_websearch()

        # ---- 10.3: persist Q/A pair (graceful degradation on write) ------
        with _xray_subsegment("dynamodb_persist"):
            try:
                ddb.persist_turn(session_id, question, routing_result.answer)
            except SessionWriteError:
                # Write failure → log error, emit errors/total, still return the
                # answer (error-handling table).
                error_code = error_code or None
                metrics.record_error()
                logger.error(
                    "Session persistence failed for %s; returning answer anyway.",
                    session_id,
                )

        latency_ms = (time.time() - start_time) * 1000
        body = {
            "answer": routing_result.answer,
            "sources": routing_result.sources,
            "tier_used": tier_used,
            "session_id": session_id,
            "latency_ms": int(round(latency_ms)),
            "confidence_score": routing_result.confidence_score,
            "web_search_unavailable": routing_result.web_search_unavailable,
        }
        return _response(200, body)

    except Exception as exc:  # noqa: BLE001 - 10.5: catch-all unhandled error
        # Full stack trace + errors/total metric + structured HTTP 500
        # (Req 1.5, 6.6, Property 3).
        error_code = ERR_INTERNAL
        metrics.record_error()
        logger.error("Unhandled exception in lambda_handler:\n%s", traceback.format_exc())
        return _error(500, ERR_INTERNAL, f"Internal server error: {exc}")

    finally:
        # ---- 10.7: structured log + metric flush (always) ----------------
        latency_ms = (time.time() - start_time) * 1000
        try:
            cw.emit_structured_log(
                request_id=request_id,
                session_id=session_id,
                tier_used=tier_used,
                latency_ms=latency_ms,
                cache_hit=cache_hit,
                cold_start=cold_start,
                error_code=error_code,
            )
            metrics.flush()
        except Exception:  # noqa: BLE001 - observability must never break handling
            logger.debug("Observability emit failed:\n%s", traceback.format_exc())


def _extract_request_id(event: dict, context: Any) -> str:
    """Resolve the request id from the API Gateway event or Lambda context."""
    if isinstance(event, dict):
        rc = event.get("requestContext")
        if isinstance(rc, dict) and rc.get("requestId"):
            return str(rc["requestId"])
    aws_request_id = getattr(context, "aws_request_id", None)
    if aws_request_id:
        return str(aws_request_id)
    return str(uuid.uuid4())
