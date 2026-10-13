#!/usr/bin/env python
"""Invoke the REAL serverless Lambda handler locally, end-to-end.

Unlike scripts/run_serverless_local.py (which calls shared_route directly) and
scripts/serverless_api_server.py (the GUI shim), this harness exercises the
actual production entry point — ``agentcore_handler.lambda_handler`` — with its
full behavior: request parsing/validation, DynamoDB session history load +
persist, the serverless shared route, the serverless response envelope, and
observability. The only substitution is pointing the backends at the local
Docker containers (OpenSearch/Redis/DynamoDB) + real Bedrock, by pre-seeding the
handler's module-level warm caches.

This validates that the production handler (not just the shared pipeline) works,
including DynamoDB session persistence and multi-turn history.

Run:
    .venv/bin/python scripts/run_lambda_handler_local.py "your question"

Prereqs: docker/serverless-local/docker-compose.yml up (incl. dynamodb);
AWS creds for Bedrock in us-east-1; .env.serverless-local present.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env.serverless-local", override=True)
except Exception:  # noqa: BLE001
    pass

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("run_lambda_handler_local")

from scripts.run_serverless_local import (  # noqa: E402
    build_local_dynamodb_client,
    build_local_opensearch_client,
    build_local_redis_cache,
    seed_knowledge_base,
)


def _api_gateway_event(question: str, session_id: str) -> dict:
    """Build an API Gateway v2 proxy event like the deployed POST /chat sends."""
    return {
        "version": "2.0",
        "routeKey": "POST /chat",
        "requestContext": {"requestId": f"local-{session_id}", "http": {"method": "POST"}},
        "body": json.dumps({"question": question, "session_id": session_id, "top_k": 5}),
        "isBase64Encoded": False,
    }


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else "What is a vector database?"
    session_id = sys.argv[2] if len(sys.argv) > 2 else "local-handler-session"

    import api_server  # noqa: F401 - ensure src importable side effects are fine
    from src.agents import agentcore_handler as h
    from src.agents.strands_graph_agent import create_rag_graph
    from src.config.settings import get_settings
    from src.tools.bedrock_client import BedrockClient

    settings = get_settings()
    if settings.deployment_mode != "serverless":
        logger.error("DEPLOYMENT_MODE must be 'serverless' (got %r).", settings.deployment_mode)
        return 2

    # Build the injected local backends.
    bedrock = BedrockClient(settings)
    opensearch = build_local_opensearch_client()
    redis_cache = build_local_redis_cache(settings)
    ddb = build_local_dynamodb_client(settings)
    if ddb is None:
        logger.error("DYNAMODB_LOCAL_ENDPOINT not set; cannot test session persistence.")
        return 2

    opensearch.ensure_indexes()
    seed_knowledge_base(opensearch, bedrock, settings.opensearch_kb_index)

    # Pre-seed the handler's warm caches so lambda_handler uses the local
    # backends instead of constructing real-AWS clients.
    graph = create_rag_graph(
        settings,
        bedrock_client=bedrock,
        opensearch_client=opensearch,
        redis_cache=redis_cache,
    )
    h._GRAPH_CACHE[settings.deployment_mode] = graph  # noqa: SLF001 - intentional injection
    h._DDB_CLIENT = ddb  # noqa: SLF001

    # --- Turn 1 ---------------------------------------------------------
    print("\n" + "=" * 72)
    print(f"TURN 1 — session={session_id!r}")
    print("=" * 72)
    resp1 = h.lambda_handler(_api_gateway_event(question, session_id))
    print("statusCode:", resp1["statusCode"])
    body1 = json.loads(resp1["body"])
    print(json.dumps(body1, indent=2)[:1200])

    # --- Verify the turn was persisted to DynamoDB ----------------------
    history = ddb.load_history(session_id)
    print("\n" + "-" * 72)
    print(f"DynamoDB session history now has {len(history)} turn(s):")
    for turn in history:
        print(f"  - Q: {turn.get('question')!r}  ttl={turn.get('ttl')}")
    print("-" * 72)

    # --- Turn 2 (same session) to show history accumulates --------------
    print("\n" + "=" * 72)
    print("TURN 2 — same session (second question)")
    print("=" * 72)
    resp2 = h.lambda_handler(_api_gateway_event("How does HNSW indexing help?", session_id))
    print("statusCode:", resp2["statusCode"])
    history2 = ddb.load_history(session_id)
    print(f"DynamoDB session history now has {len(history2)} turn(s)")

    # --- Validation (negative path): a bad request returns a 400 --------
    print("\n" + "=" * 72)
    print("VALIDATION — missing 'question' should be HTTP 400")
    print("=" * 72)
    bad_event = {"body": json.dumps({"session_id": session_id}), "isBase64Encoded": False}
    bad = h.lambda_handler(bad_event)
    print("statusCode:", bad["statusCode"], "body:", bad["body"])

    ok = (
        resp1["statusCode"] == 200
        and resp2["statusCode"] == 200
        and len(history2) >= 2
        and bad["statusCode"] == 400
    )
    print("\nRESULT:", "✅ PASS" if ok else "❌ FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
