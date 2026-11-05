#!/usr/bin/env python3
"""Retrieve and print all entries from the response cache index in OpenSearch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from document_loaders.core.tools import OpenSearchVectorDB
from document_loaders.local_settings import get_loader_settings

settings = get_loader_settings()
vector_db = OpenSearchVectorDB(
    host=settings.opensearch_local_host,
    port=settings.opensearch_local_port,
)

cache_index = settings.opensearch_cache_index

print(f"Querying all entries from index: {cache_index}")

try:
    if not vector_db.client.indices.exists(index=cache_index):
        print(f"Index '{cache_index}' does not exist.")
        sys.exit(0)

    response = vector_db.client.search(
        index=cache_index,
        body={"size": 100, "query": {"match_all": {}}},
        _source=["question", "answer", "sources"],
    )
    hits = response.get("hits", {}).get("hits", [])
    print(f"Found {len(hits)} entries in {cache_index}:")
    for i, hit in enumerate(hits):
        print(f"Entry {i + 1}: id={hit.get('_id')} source={hit.get('_source')}")
except Exception as e:
    print(f"Error querying OpenSearch: {e}")
