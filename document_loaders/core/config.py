"""Configuration management for Milvus operations."""

import os
from dataclasses import dataclass


@dataclass
class MilvusConfig:
    uri: str = "http://localhost:19530"
    token: str = "root:Milvus"
    db_name: str = "default"


@dataclass
class EmbeddingConfig:
    provider: str = "huggingface"
    hf_model: str | None = None
    ollama_model: str | None = None


def get_milvus_config() -> MilvusConfig:
    return MilvusConfig(
        uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
        token=os.getenv("MILVUS_TOKEN", "root:Milvus"),
        db_name=os.getenv("MILVUS_DB_NAME", "default"),
    )


def get_embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig(
        provider=os.getenv("EMBEDDING_PROVIDER", "huggingface"),
        hf_model=os.getenv("HF_EMBEDDING_MODEL"),
        ollama_model=os.getenv("OLLAMA_EMBEDDING_MODEL"),
    )
