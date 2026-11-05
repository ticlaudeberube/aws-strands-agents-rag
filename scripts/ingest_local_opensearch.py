#!/usr/bin/env python
"""Offline ingestion into local OpenSearch using Ollama embeddings.

The Ollama analog of the Bedrock-based ``seed_knowledge_base`` in
``run_serverless_local.py``. Populates the local OpenSearch ``rag-kb`` index for
OpenSearch Local Mode (``DEPLOYMENT_MODE=local`` + ``LOCAL_VECTOR_BACKEND=opensearch``)
with **no AWS / Bedrock dependency**:

    1. build the local plain-HTTP OpenSearch client and ensure the indexes exist
       (768-dim HNSW cosine, created by ``OpenSearchClient.ensure_indexes``);
    2. read source documents (``.md`` / ``.txt`` under a directory, or a small
       built-in demo set);
    3. chunk each document (``src.indexing.chunking.chunk_text``, bound by
       ``settings.max_chunk_length``);
    4. embed each chunk with Ollama ``nomic-embed-text:v1.5`` (768-dim);
    5. index each chunk via ``OpenSearchClient.index_document`` with
       ``{id, text, metadata}`` matching what ``knn_search`` returns.

Prereqs: a local OpenSearch container (see docker-compose) and Ollama running
with the embedding model pulled.

Usage:
    .venv/bin/python scripts/ingest_local_opensearch.py                 # demo docs
    .venv/bin/python scripts/ingest_local_opensearch.py --docs ./data/docs
    .venv/bin/python scripts/ingest_local_opensearch.py --docs ./notes --glob '**/*.md'
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger("ingest_local_opensearch")

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
            "and Milvus both support HNSW with tunable m and ef_construction "
            "parameters for the speed/accuracy balance."
        ),
    },
]


def _load_documents(docs_dir: Path | None, pattern: str) -> list[dict[str, str]]:
    """Return ``[{title, text}]`` from a directory of text files, or demo docs."""
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


def ingest(docs: list[dict[str, str]], *, settings: object | None = None) -> int:
    """Chunk → Ollama-embed → index each document into local OpenSearch.

    Returns the number of chunks indexed. Separated from ``main`` so it is
    unit-testable with injected fakes.
    """
    from src.config.settings import get_settings
    from src.indexing.chunking import chunk_text
    from src.tools.ollama_client import OllamaClient
    from src.tools.opensearch_client import OpenSearchClient

    s = settings or get_settings()

    opensearch = OpenSearchClient.for_local(s)  # type: ignore[arg-type]
    opensearch.ensure_indexes()
    kb_index = s.opensearch_kb_index  # type: ignore[attr-defined]

    ollama = OllamaClient(
        host=s.ollama_host,  # type: ignore[attr-defined]
        timeout=s.ollama_timeout,  # type: ignore[attr-defined]
        pool_size=s.ollama_pool_size,  # type: ignore[attr-defined]
    )
    embed_model = s.ollama_embed_model  # type: ignore[attr-defined]
    max_tokens = s.max_chunk_length  # type: ignore[attr-defined]

    indexed = 0
    for doc in docs:
        title = doc.get("title", "")
        chunks = chunk_text(doc["text"], max_tokens=max_tokens)
        for ci, chunk in enumerate(chunks):
            vector = ollama.embed_text(chunk, model=embed_model)
            doc_id = f"{title or 'doc'}-{ci}"
            metadata = {
                "document_name": title,
                "source": doc.get("source", "local-ingest"),
                "chunk_index": ci,
            }
            opensearch.index_document(
                index=kb_index,
                doc_id=doc_id,
                vector=vector,
                text=chunk,
                metadata=metadata,
            )
            indexed += 1
    logger.info("Indexed %d chunk(s) into %s", indexed, kb_index)
    return indexed


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ingest docs into local OpenSearch (Ollama).")
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
    print(f"Ingested {count} chunk(s) into the local OpenSearch rag-kb index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
