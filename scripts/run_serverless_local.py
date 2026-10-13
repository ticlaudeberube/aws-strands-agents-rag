#!/usr/bin/env python
"""Run the SERVERLESS-MODE RAG pipeline locally (Option A).

Exercises the exact serverless code path — ``create_rag_graph`` with the
Bedrock + OpenSearch + Redis backends and the shared ``shared_route`` the Lambda
handler uses — but against **local** OpenSearch/Redis Docker containers and
**real** Bedrock. Nothing is deployed to AWS beyond live Bedrock inference.

Why a standalone runner (not api_server.py)?
    The production ``OpenSearchClient`` assumes OpenSearch Serverless (TLS +
    SigV4 ``aoss`` auth on port 443) and ``RedisCache`` assumes an in-transit
    encrypted ElastiCache endpoint (``ssl=True``). Neither can point at a plain
    local container through settings alone. ``create_rag_graph`` accepts
    pre-built backend instances, so this runner injects locally-configured
    clients WITHOUT modifying any ``src/`` production code.

Prereqs:
    1. docker/serverless-local/docker-compose.yml up (OpenSearch + Redis).
    2. AWS creds for account 996428372683 in us-east-1 (Bedrock access).
    3. .env.serverless-local present (loaded automatically).

Usage:
    .venv/bin/python scripts/run_serverless_local.py "your question here"
    .venv/bin/python scripts/run_serverless_local.py          # uses a default Q
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.tools.dynamodb_client import DynamoDBClient

# Ensure the repo root is importable when launched directly as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load .env.serverless-local before importing settings so DEPLOYMENT_MODE etc.
# are in the environment when get_settings() reads them.
try:
    from dotenv import load_dotenv

    _ENV_FILE = _REPO_ROOT / ".env.serverless-local"
    load_dotenv(_ENV_FILE, override=True)
except Exception:  # noqa: BLE001 - dotenv is best-effort
    pass

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("run_serverless_local")


def build_local_opensearch_client():
    """Build an opensearch-py client pointed at the local container.

    Plain HTTP, no auth, no SigV4 — matches the compose service that runs with
    the security plugin disabled. This is injected into create_rag_graph so the
    production OpenSearchClient's cloud transport assumptions are bypassed.
    """
    from opensearchpy import OpenSearch

    host = os.environ.get("OPENSEARCH_LOCAL_HOST", "localhost")
    port = int(os.environ.get("OPENSEARCH_LOCAL_PORT", "9200"))

    raw_client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=None,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )

    # Wrap the raw transport in the production OpenSearchClient by injecting the
    # client, so index names, k-NN query shapes, and the semantic-cache methods
    # are exactly the serverless ones.
    from src.tools.opensearch_client import OpenSearchClient

    return OpenSearchClient(client=raw_client)


def build_local_redis_cache(settings):
    """Build a RedisCache backed by a plain (non-TLS) local redis client."""
    import redis

    from src.tools.redis_cache import RedisCache

    endpoint = os.environ.get("REDIS_ENDPOINT", "localhost:6379")
    host, _, port = endpoint.partition(":")
    raw = redis.Redis(
        host=host or "localhost",
        port=int(port or "6379"),
        ssl=False,  # local container has no TLS (prod ElastiCache does)
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    return RedisCache(settings, client=raw)


def build_local_dynamodb_client(settings) -> DynamoDBClient | None:
    """Build a DynamoDBClient pointed at the local DynamoDB container.

    Injects a boto3 DynamoDB *resource* configured with the local endpoint, so
    the production DynamoDBClient (which otherwise targets real AWS DynamoDB) is
    used verbatim against DynamoDB Local. Ensures the session + analytics tables
    exist. Returns None if the local endpoint is not configured.
    """
    import boto3

    from src.tools.dynamodb_client import DynamoDBClient

    endpoint = os.environ.get("DYNAMODB_LOCAL_ENDPOINT")
    if not endpoint:
        return None

    region = getattr(settings, "aws_region", None) or "us-east-1"
    # DynamoDB Local ignores credentials but boto3 still requires some to be set.
    resource = boto3.resource(
        "dynamodb",
        region_name=region,
        endpoint_url=endpoint,
        aws_access_key_id="local",
        aws_secret_access_key="local",
    )
    _ensure_dynamodb_tables(resource, settings)
    return DynamoDBClient(settings, resource=resource)


def _ensure_dynamodb_tables(resource, settings) -> None:
    """Create the session + analytics tables in DynamoDB Local if absent.

    Session table key schema mirrors what DynamoDBClient.persist_turn writes:
    partition key ``session_id`` (S) + sort key ``timestamp`` (N). The analytics
    table uses ``record_id`` (S) as its partition key.
    """
    existing = set(resource.meta.client.list_tables().get("TableNames", []))

    session_table = getattr(settings, "dynamodb_session_table", None)
    analytics_table = getattr(settings, "dynamodb_analytics_table", None)

    if session_table and session_table not in existing:
        resource.create_table(
            TableName=session_table,
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "N"},
            ],
            BillingMode="PAY_PER_REQUEST",
        ).wait_until_exists()
        logger.info("Created local DynamoDB session table: %s", session_table)

    if analytics_table and analytics_table not in existing:
        resource.create_table(
            TableName=analytics_table,
            KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        ).wait_until_exists()
        logger.info("Created local DynamoDB analytics table: %s", analytics_table)


_SEED_DOCS = [
    {
        "title": "What is a vector database",
        "text": (
            "A vector database stores high-dimensional embedding vectors and "
            "supports approximate nearest-neighbor (ANN) search. It is the core "
            "retrieval component of a Retrieval-Augmented Generation (RAG) system, "
            "letting an application find the documents most semantically similar "
            "to a query embedding."
        ),
    },
    {
        "title": "HNSW indexing",
        "text": (
            "HNSW (Hierarchical Navigable Small World) is a graph-based ANN index "
            "that trades a small amount of recall for very fast search. OpenSearch "
            "and Milvus both support HNSW with tunable m and ef_construction "
            "parameters for the speed/accuracy balance."
        ),
    },
]


def seed_knowledge_base(opensearch_client, bedrock_client, kb_index: str) -> int:
    """Index a couple of KB documents so retrieval returns real context.

    Embeds each doc with Bedrock Titan (via the migrated client) and indexes it
    into the local OpenSearch rag-kb index. Returns the number of docs indexed.
    """
    count = 0
    for i, doc in enumerate(_SEED_DOCS):
        vector = bedrock_client.embed_text(doc["text"])
        opensearch_client.index_document(
            index=kb_index,
            doc_id=f"seed-{i}",
            vector=vector,
            text=doc["text"],
            metadata={"title": doc["title"]},
        )
        count += 1
    return count


def main() -> int:
    question = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What is a vector database and how does HNSW indexing help RAG?"
    )

    from src.agents.strands_graph_agent import create_rag_graph
    from src.config.settings import get_settings
    from src.tools.bedrock_client import BedrockClient

    settings = get_settings()
    if settings.deployment_mode != "serverless":
        logger.error(
            "DEPLOYMENT_MODE is %r, expected 'serverless'. Did .env.serverless-local load?",
            settings.deployment_mode,
        )
        return 2

    logger.info("Deployment mode: %s", settings.deployment_mode)
    logger.info("Bedrock model override: %s", settings.bedrock_model_override)
    logger.info("AWS region: %s", settings.aws_region)

    # Build injected backends: real Bedrock, local OpenSearch, local Redis.
    bedrock = BedrockClient(settings)
    opensearch = build_local_opensearch_client()
    redis_cache = build_local_redis_cache(settings)

    # Ensure the rag-kb / rag-cache indexes exist, then seed the KB.
    opensearch.ensure_indexes()
    seeded = seed_knowledge_base(opensearch, bedrock, settings.opensearch_kb_index)
    logger.info("Seeded %d KB document(s) into %s", seeded, settings.opensearch_kb_index)

    # Build the serverless graph with the injected backends — the SAME factory
    # and shared_route the Lambda handler uses.
    graph = create_rag_graph(
        settings,
        bedrock_client=bedrock,
        opensearch_client=opensearch,
        redis_cache=redis_cache,
    )
    shared_route = graph["shared_route"]

    print("\n" + "=" * 72)
    print(f"QUESTION: {question}")
    print("=" * 72)

    result = shared_route(question, top_k=5)

    print("\nANSWER:\n")
    print(result.answer)
    print("\n" + "-" * 72)
    print(f"tier_used        : {result.tier_used}")
    print(f"cache_hit        : {result.cache_hit}")
    print(f"confidence_score : {result.confidence_score}")
    print(f"sources          : {len(result.sources)} document(s)")
    print("-" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
