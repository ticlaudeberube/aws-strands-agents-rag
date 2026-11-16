"""Local settings for document loader scripts.

This module reads configuration from `.env` (when present) and environment
variables so loader scripts do not depend on `src.config.settings`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class LoaderSettings:
    ollama_host: str
    ollama_model: str
    ollama_embed_model: str
    ollama_timeout: int
    ollama_pool_size: int
    opensearch_local_host: str
    opensearch_local_port: int
    opensearch_kb_index: str
    opensearch_cache_index: str
    response_cache_collection_name: str
    response_cache_threshold: float
    response_cache_embedding_dim: int
    response_cache_source: str
    agent_cache_size: int
    embedding_cache_ttl: int
    web_search_timeout: int
    embedding_dim: int
    max_chunk_length: int
    embedding_batch_size: int


@lru_cache(maxsize=1)
def get_loader_settings() -> LoaderSettings:
    _load_env()
    return LoaderSettings(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:1b"),
        ollama_embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:v1.5"),
        ollama_timeout=_get_int("OLLAMA_TIMEOUT", 30),
        ollama_pool_size=_get_int("OLLAMA_POOL_SIZE", 5),
        opensearch_local_host=os.getenv("OPENSEARCH_LOCAL_HOST", "localhost"),
        opensearch_local_port=_get_int("OPENSEARCH_LOCAL_PORT", 9200),
        opensearch_kb_index=os.getenv("OPENSEARCH_KB_INDEX", "rag-kb"),
        opensearch_cache_index=os.getenv("OPENSEARCH_CACHE_INDEX", "rag-cache"),
        response_cache_collection_name=os.getenv(
            "RESPONSE_CACHE_COLLECTION_NAME", "response_cache"
        ),
        response_cache_threshold=float(os.getenv("RESPONSE_CACHE_THRESHOLD", "0.99")),
        response_cache_embedding_dim=_get_int("RESPONSE_CACHE_EMBEDDING_DIM", 768),
        response_cache_source=os.getenv("RESPONSE_CACHE_SOURCE", "data/responses.json"),
        agent_cache_size=_get_int("AGENT_CACHE_SIZE", 500),
        embedding_cache_ttl=_get_int("EMBEDDING_CACHE_TTL", 3600),
        web_search_timeout=_get_int("WEB_SEARCH_TIMEOUT", 10),
        embedding_dim=_get_int("EMBEDDING_DIM", 768),
        max_chunk_length=_get_int("MAX_CHUNK_LENGTH", 250),
        embedding_batch_size=_get_int("EMBEDDING_BATCH_SIZE", 32),
    )
