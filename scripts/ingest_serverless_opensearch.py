#!/usr/bin/env python
"""Offline ingestion into OpenSearch Serverless using Bedrock Titan embeddings.

The serverless counterpart of ``scripts/ingest_local_opensearch.py``. It runs the
same embedding path as the indexing Lambda, so the vectors it writes live in the
serverless embedding space:

    Titan ``amazon.titan-embed-text-v1`` (1536-dim) -> fixed 1536->768 projection
    (``BedrockClient.embed_text``), the same code the query path uses.

This script never writes to a local OpenSearch container and never embeds with
Ollama. The endpoint guard refuses any ``OPENSEARCH_ENDPOINT`` that is not an
OpenSearch Serverless (``aoss``) host, so local vectors cannot reach the
serverless index through this path.

Steps:
    1. build the SigV4-signed serverless client (``OpenSearchClient``) and ensure
       the indexes exist (768-dim HNSW cosine);
    2. read source documents (``.md`` / ``.txt`` under a directory, or a small
       built-in demo set);
    3. chunk each document (``src.indexing.chunking.chunk_text``, bound by
       ``settings.max_chunk_length``);
    4. embed each chunk with ``BedrockClient.embed_text``;
    5. index each chunk into ``settings.opensearch_kb_index``.

Failure policy: an embedding or write error stops the run and names the chunk.
A bulk loader that skips chunks silently leaves gaps in the knowledge base.

Prereqs: AWS credentials with ``bedrock:InvokeModel`` and the ``aoss`` data
access policy for the caller's IAM principal. Set ``OPENSEARCH_ENDPOINT`` to the
collection endpoint. Leave ``BEDROCK_PCA_MATRIX_URI`` unset so the built-in
projection is used, the same as the Lambda.

Usage:
    .venv/bin/python scripts/ingest_serverless_opensearch.py                 # demo docs
    .venv/bin/python scripts/ingest_serverless_opensearch.py --docs ./data/docs
    .venv/bin/python scripts/ingest_serverless_opensearch.py --docs ./notes --glob '**/*.md'
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger("ingest_serverless_opensearch")

# Identifies the embedding pipeline in each chunk's metadata, so a stored chunk
# can always be traced back to the space that produced it.
EMBEDDING_PIPELINE = "titan-1536-projected-768"

# Hostname suffix of every OpenSearch Serverless collection endpoint.
_AOSS_HOST_SUFFIX = ".aoss.amazonaws.com"

# A tiny built-in corpus so the script works end-to-end with no doc directory.
_DEMO_DOCS: list[dict[str, str]] = [
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
            "Serverless supports HNSW with tunable m and ef_construction "
            "parameters for the speed/accuracy balance."
        ),
    },
]


def assert_serverless_endpoint(endpoint: str | None) -> str:
    """Return the host of a serverless collection endpoint or raise.

    Refuses an unset endpoint, a plain-HTTP endpoint, and any host that is not an
    ``*.aoss.amazonaws.com`` collection. This is the guard that keeps the script
    from writing to the local OpenSearch container.
    """
    if not endpoint:
        raise ValueError(
            "OPENSEARCH_ENDPOINT is not set; it must be a serverless collection endpoint."
        )
    if not endpoint.startswith("https://"):
        raise ValueError(f"OPENSEARCH_ENDPOINT must use https:// for serverless: {endpoint!r}")
    host = endpoint[len("https://") :].rstrip("/")
    if not host.endswith(_AOSS_HOST_SUFFIX):
        raise ValueError(
            f"OPENSEARCH_ENDPOINT host {host!r} is not an OpenSearch Serverless "
            f"collection (expected a *{_AOSS_HOST_SUFFIX} host). Refusing to write."
        )
    return host


def _load_documents(docs_dir: Path | None, pattern: str) -> list[dict[str, str]]:
    """Return ``[{title, text, source}]`` from a directory of text files, or demo docs."""
    if docs_dir is None:
        logger.info("No --docs directory given; using the built-in demo corpus.")
        return list(_DEMO_DOCS)
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"--docs path is not a directory: {docs_dir}")
    docs: list[dict[str, str]] = []
    for path in sorted(docs_dir.glob(pattern)):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if text:
            docs.append({"title": path.stem, "text": text, "source": str(path)})
    logger.info("Loaded %d document(s) from %s", len(docs), docs_dir)
    return docs


def ingest(
    docs: list[dict[str, str]],
    *,
    settings: Any | None = None,
    opensearch: Any | None = None,
    bedrock: Any | None = None,
) -> int:
    """Chunk, embed with Titan plus projection, and index each document.

    ``opensearch`` and ``bedrock`` are injectable for tests. When omitted, the
    serverless ``OpenSearchClient`` and ``BedrockClient`` are built from
    ``settings``. Returns the number of chunks indexed.
    """
    from src.config.settings import get_settings
    from src.indexing.chunking import chunk_text

    s = settings or get_settings()
    assert_serverless_endpoint(s.opensearch_endpoint)

    if opensearch is None:
        from src.tools.opensearch_client import OpenSearchClient

        opensearch = OpenSearchClient(settings=s)
    if bedrock is None:
        from src.tools.bedrock_client import BedrockClient

        bedrock = BedrockClient(settings=s)

    opensearch.ensure_indexes()
    kb_index = s.opensearch_kb_index
    max_tokens = s.max_chunk_length

    indexed = 0
    for doc in docs:
        title = doc.get("title", "")
        chunks = chunk_text(doc["text"], max_tokens=max_tokens)
        for ci, chunk in enumerate(chunks):
            doc_id = f"{title or 'doc'}-{ci}"
            try:
                vector = bedrock.embed_text(chunk)
            except Exception as exc:
                raise RuntimeError(
                    f"Embedding failed for chunk {doc_id} (len={len(chunk)}): {exc}"
                ) from exc
            metadata = {
                "document_name": title,
                "source": doc.get("source", "serverless-ingest"),
                "chunk_index": ci,
                "embedding_pipeline": EMBEDDING_PIPELINE,
            }
            try:
                opensearch.index_document(
                    index=kb_index,
                    doc_id=doc_id,
                    vector=vector,
                    text=chunk,
                    metadata=metadata,
                )
            except Exception as exc:
                raise RuntimeError(f"Indexing failed for chunk {doc_id}: {exc}") from exc
            indexed += 1

    logger.info("Indexed %d chunk(s) into %s", indexed, kb_index)
    return indexed


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Ingest docs into OpenSearch Serverless (Bedrock Titan embeddings)."
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=None,
        help="Directory of .md/.txt documents to ingest (default: built-in demo corpus).",
    )
    parser.add_argument(
        "--glob",
        default="**/*.md",
        help="Glob for files under --docs (default: '**/*.md').",
    )
    args = parser.parse_args(argv)

    try:
        docs = _load_documents(args.docs, args.glob)
        if not docs:
            print("No documents to ingest.", file=sys.stderr)
            return 1
        count = ingest(docs)
    except Exception as exc:  # noqa: BLE001 - surface a clear CLI error
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 2

    print(f"Ingested {count} chunk(s) into the serverless OpenSearch rag-kb index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
