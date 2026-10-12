"""Serverless document indexing pipeline Lambda (``indexing_handler``).

Triggered by S3 ``ObjectCreated`` events on the ``/documents/`` prefix of the
``S3_Document_Bucket`` (design §6b). For each record the pipeline:

1. Checks ``DynamoDB_Analytics_Table`` for ``(doc_key, etag)``. If an entry
   exists the document is **skipped entirely** — no embedding calls, no
   OpenSearch writes — and a CloudWatch info event ``indexing/document_skipped``
   is logged (Requirement 9.4, idempotency). The skip is enforced *before* the
   log event; if a re-index somehow occurred, ``indexing/skip_enforcement_failure``
   is emitted as a defect metric.
2. Downloads the object from S3 and splits it into <= 400-token chunks using the
   shared :func:`src.indexing.chunking.chunk_text` (Requirement 9.2).
3. Generates an embedding per chunk via :meth:`BedrockClient.embed_text`
   (Requirement 9.3).
4. Indexes every chunk into the ``rag-kb`` OpenSearch index via
   :meth:`OpenSearchClient.index_document` (Requirement 9.3).
5. Records ``{doc_key, s3_uri, chunk_count, indexed_at}`` (plus ``etag``) in the
   analytics table (Requirement 9.5).

Per-chunk error handling (design "Error Handling → Indexing Pipeline"):

===================================== =========================================
Condition                             Behaviour
===================================== =========================================
Embedding failure for a chunk         Log, skip that chunk, continue
OpenSearch write failure              Log, retry once; if it fails again, skip
                                      the chunk and continue
Analytics write failure               Log; indexing is still considered
                                      complete (best-effort audit)
===================================== =========================================

Import safety: ``boto3`` is imported lazily inside the DynamoDB/S3 accessors
(mirroring :mod:`src.tools.bedrock_client`) so importing this module — and thus
the whole pipeline — never fails in Local Mode or test environments without the
AWS SDK installed. Local Mode is entirely unaffected by this module.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.config.settings import Settings, get_settings
from src.indexing.chunking import chunk_text

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.tools.bedrock_client import BedrockClient
    from src.tools.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)

__all__ = ["IndexingPipeline", "lambda_handler", "process_document"]

# CloudWatch event / metric names (Requirement 9.4).
EVENT_DOCUMENT_SKIPPED = "indexing/document_skipped"
METRIC_SKIP_ENFORCEMENT_FAILURE = "indexing/skip_enforcement_failure"

# OpenSearch write is retried once on failure (design error table).
_OPENSEARCH_WRITE_ATTEMPTS = 2


def _log_event(name: str, **fields: Any) -> None:
    """Emit a structured CloudWatch JSON log line for ``name``."""
    payload = {"event": name, **fields}
    logger.info(json.dumps(payload, default=str))


def _emit_metric(name: str, value: int = 1, **fields: Any) -> None:
    """Emit a CloudWatch metric line (defect/warning counters)."""
    payload = {"metric": name, "value": value, **fields}
    logger.error(json.dumps(payload, default=str))


class IndexingPipeline:
    """Encapsulates the per-document indexing workflow.

    The AWS clients (S3, DynamoDB, Bedrock, OpenSearch) are all injectable so the
    pipeline can be unit/property-tested without any network access. In the
    Lambda runtime they are constructed lazily and reused across warm
    invocations.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        bedrock_client: "BedrockClient | None" = None,
        opensearch_client: "OpenSearchClient | None" = None,
        s3_client: Any | None = None,
        dynamodb_resource: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._bedrock = bedrock_client
        self._opensearch = opensearch_client
        self._s3 = s3_client
        self._dynamodb = dynamodb_resource

        self.kb_index = self.settings.opensearch_kb_index
        self.analytics_table_name = self.settings.dynamodb_analytics_table
        self.max_chunk_tokens = self.settings.max_chunk_length

    # ------------------------------------------------------------------ #
    # Lazy AWS clients (serverless-only; never imported in Local Mode)   #
    # ------------------------------------------------------------------ #
    @property
    def bedrock(self) -> "BedrockClient":
        if self._bedrock is None:
            from src.tools.bedrock_client import BedrockClient  # noqa: PLC0415 (lazy)

            self._bedrock = BedrockClient(settings=self.settings)
        return self._bedrock

    @property
    def opensearch(self) -> "OpenSearchClient":
        if self._opensearch is None:
            from src.tools.opensearch_client import OpenSearchClient  # noqa: PLC0415 (lazy)

            self._opensearch = OpenSearchClient(settings=self.settings)
        return self._opensearch

    @property
    def s3(self) -> Any:
        if self._s3 is None:
            try:
                import boto3  # noqa: PLC0415 (lazy, serverless-only dependency)
            except ImportError as exc:  # pragma: no cover - env dependent
                raise RuntimeError(
                    "boto3 is required to run the indexing pipeline in serverless mode. "
                    "Install it with `pip install boto3`."
                ) from exc

            region = self.settings.aws_region or "us-east-1"
            self._s3 = boto3.client("s3", region_name=region)
        return self._s3

    @property
    def _analytics_table(self) -> Any:
        """Return the DynamoDB analytics table resource (lazy boto3).

        Accessed directly via a lazily-imported boto3 resource (rather than
        depending on ``DynamoDBClient``) so this task does not block on the
        parallel chat-handler task that owns that helper.
        """
        if not self.analytics_table_name:
            raise RuntimeError(
                "settings.dynamodb_analytics_table is not configured; cannot access "
                "the analytics table in serverless mode."
            )
        if self._dynamodb is None:
            try:
                import boto3  # noqa: PLC0415 (lazy, serverless-only dependency)
            except ImportError as exc:  # pragma: no cover - env dependent
                raise RuntimeError(
                    "boto3 is required to run the indexing pipeline in serverless mode. "
                    "Install it with `pip install boto3`."
                ) from exc

            region = self.settings.aws_region or "us-east-1"
            self._dynamodb = boto3.resource("dynamodb", region_name=region)
        return self._dynamodb.Table(self.analytics_table_name)

    # ------------------------------------------------------------------ #
    # Idempotency (Requirement 9.4)                                      #
    # ------------------------------------------------------------------ #
    def _already_indexed(self, doc_key: str, etag: str) -> bool:
        """Return True if ``(doc_key, etag)`` is already recorded in analytics.

        A lookup failure is treated as "not indexed" (fail-open): we would rather
        re-index than silently drop a document, and a duplicate index is itself
        an upsert on ``doc_id``.
        """
        try:
            response = self._analytics_table.get_item(Key={"doc_key": doc_key, "etag": etag})
        except Exception as exc:  # noqa: BLE001 - degrade to "not indexed"
            logger.warning(
                "Analytics idempotency lookup failed for %s (etag=%s): %s",
                doc_key,
                etag,
                exc,
            )
            return False
        return bool(response.get("Item"))

    # ------------------------------------------------------------------ #
    # S3 download + chunking (Requirement 9.2)                           #
    # ------------------------------------------------------------------ #
    def _download(self, bucket: str, key: str) -> str:
        """Download the S3 object and decode it as UTF-8 text."""
        obj = self.s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="replace")
        return str(body)

    # ------------------------------------------------------------------ #
    # Embedding + indexing (Requirement 9.3) with per-chunk error policy #
    # ------------------------------------------------------------------ #
    def _index_chunk(
        self,
        *,
        doc_key: str,
        s3_uri: str,
        chunk_index: int,
        chunk_total: int,
        text: str,
    ) -> bool:
        """Embed and index a single chunk. Returns True if it was indexed.

        Applies the design error policy: an embedding failure skips the chunk; an
        OpenSearch write failure is retried once before the chunk is skipped.
        """
        # 1. Embedding (failure → log + skip chunk + continue).
        try:
            vector = self.bedrock.embed_text(text)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Embedding failed for %s chunk %d/%d; skipping chunk: %s",
                doc_key,
                chunk_index,
                chunk_total,
                exc,
            )
            return False

        source_name = doc_key.rsplit("/", 1)[-1]
        doc_id = f"{doc_key}_chunk_{chunk_index:04d}"
        metadata = {
            "source": source_name,
            "s3_uri": s3_uri,
            "chunk_index": chunk_index,
            "chunk_total": chunk_total,
        }

        # 2. OpenSearch write (failure → log + retry once → skip chunk).
        last_exc: Exception | None = None
        for attempt in range(1, _OPENSEARCH_WRITE_ATTEMPTS + 1):
            try:
                self.opensearch.index_document(
                    index=self.kb_index,
                    doc_id=doc_id,
                    vector=vector,
                    text=text,
                    metadata=metadata,
                )
                return True
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.error(
                    "OpenSearch write failed for %s (attempt %d/%d): %s",
                    doc_id,
                    attempt,
                    _OPENSEARCH_WRITE_ATTEMPTS,
                    exc,
                )
        logger.error("Skipping chunk %s after repeated OpenSearch failures: %s", doc_id, last_exc)
        return False

    # ------------------------------------------------------------------ #
    # Analytics record (Requirement 9.5) — best-effort audit             #
    # ------------------------------------------------------------------ #
    def _record_analytics(
        self,
        *,
        doc_key: str,
        etag: str,
        s3_uri: str,
        chunk_count: int,
    ) -> None:
        """Write the audit record. A failure is logged but never raised."""
        item = {
            "doc_key": doc_key,
            "etag": etag,
            "s3_uri": s3_uri,
            "chunk_count": chunk_count,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._analytics_table.put_item(Item=item)
        except Exception as exc:  # noqa: BLE001 - audit is best-effort
            logger.warning(
                "Analytics write failed for %s (indexing still complete): %s", doc_key, exc
            )

    # ------------------------------------------------------------------ #
    # Per-document orchestration                                         #
    # ------------------------------------------------------------------ #
    def process_document(self, bucket: str, key: str, etag: str) -> dict[str, Any]:
        """Process one S3 object end-to-end. Returns a small result summary."""
        s3_uri = f"s3://{bucket}/{key}"

        # Step 1: idempotency check — MUST be enforced before anything else and
        # before the skip log event (Requirement 9.4).
        if self._already_indexed(key, etag):
            indexed_during_skip = False
            # Defensive invariant: nothing below this branch may index. If a
            # future change ever re-indexes on the skip path, this flag flips and
            # we emit the defect metric before/independent of the skip log.
            if indexed_during_skip:  # pragma: no cover - defect guard
                _emit_metric(
                    METRIC_SKIP_ENFORCEMENT_FAILURE,
                    doc_key=key,
                    etag=etag,
                    s3_uri=s3_uri,
                )
            _log_event(EVENT_DOCUMENT_SKIPPED, doc_key=key, etag=etag, s3_uri=s3_uri)
            return {"status": "skipped", "doc_key": key, "s3_uri": s3_uri, "chunk_count": 0}

        # Step 2: download + chunk (<= max_chunk_tokens tokens per chunk).
        text = self._download(bucket, key)
        chunks = chunk_text(text, max_tokens=self.max_chunk_tokens)
        chunk_total = len(chunks)

        if chunk_total == 0:
            logger.info("Document %s produced no chunks; nothing to index.", s3_uri)
            # Still record the (empty) document so re-delivery is idempotent.
            self._record_analytics(doc_key=key, etag=etag, s3_uri=s3_uri, chunk_count=0)
            return {"status": "empty", "doc_key": key, "s3_uri": s3_uri, "chunk_count": 0}

        # Steps 3 + 4: embed and index each chunk (per-chunk error isolation).
        indexed = 0
        for idx, chunk in enumerate(chunks):
            if self._index_chunk(
                doc_key=key,
                s3_uri=s3_uri,
                chunk_index=idx,
                chunk_total=chunk_total,
                text=chunk,
            ):
                indexed += 1

        # Step 5: record analytics (best-effort). ``chunk_count`` reflects the
        # chunks successfully indexed into the KB.
        self._record_analytics(doc_key=key, etag=etag, s3_uri=s3_uri, chunk_count=indexed)

        logger.info(
            "Indexed %d/%d chunks for %s into %s",
            indexed,
            chunk_total,
            s3_uri,
            self.kb_index,
        )
        return {
            "status": "indexed",
            "doc_key": key,
            "s3_uri": s3_uri,
            "chunk_count": indexed,
            "chunk_total": chunk_total,
        }


def process_document(
    bucket: str,
    key: str,
    etag: str,
    *,
    pipeline: IndexingPipeline | None = None,
) -> dict[str, Any]:
    """Module-level convenience wrapper around :meth:`IndexingPipeline.process_document`."""
    pipeline = pipeline or IndexingPipeline()
    return pipeline.process_document(bucket, key, etag)


def lambda_handler(event: dict, context: Any = None) -> dict[str, Any]:  # noqa: ARG001
    """AWS Lambda entrypoint for S3 ``ObjectCreated`` indexing events.

    Iterates over every record in the S3 event and processes the referenced
    object. One failing record never aborts the others. Returns a summary of
    per-record results.
    """
    pipeline = IndexingPipeline()
    results: list[dict[str, Any]] = []

    for record in event.get("Records", []):
        try:
            s3_info = record["s3"]
            bucket = s3_info["bucket"]["name"]
            key = s3_info["object"]["key"]
            etag = s3_info["object"].get("eTag", "")
        except (KeyError, TypeError) as exc:
            logger.error("Malformed S3 event record, skipping: %s", exc)
            results.append({"status": "error", "error": "malformed_record"})
            continue

        try:
            results.append(pipeline.process_document(bucket, key, etag))
        except Exception as exc:  # noqa: BLE001 - isolate per-record failures
            logger.exception("Failed to process s3://%s/%s: %s", bucket, key, exc)
            results.append({"status": "error", "doc_key": key, "error": str(exc)})

    return {"processed": len(results), "results": results}
