"""Configuration settings for the application."""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env variables
    )

    # Ollama Configuration
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5")
    ollama_timeout: int = 30  # Request timeout in seconds
    ollama_pool_size: int = 5  # Connection pool size

    # Milvus Configuration
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_db_name: str = "knowledge_base"
    loader_milvus_db_name: str = "knowledge_base"
    milvus_user: str = "root"
    milvus_password: str = "Milvus"
    milvus_timeout: int = 30  # Request timeout in seconds
    milvus_pool_size: int = 10  # Connection pool size

    # Collection Configuration
    ollama_collection_name: str = "milvus_rag_collection"

    # Embedding and chunk processing
    max_chunk_length: int = 250  # Reduced from 400 for faster context processing (30-40% speedup)
    embedding_dim: int = 768

    # Performance Settings
    ollama_num_threads: int = 6
    tokenizers_parallelism: bool = False
    pytorch_mps_high_watermark_ratio: float = 0.0

    # LLM Generation Optimization
    max_tokens: int = 256  # Limit output length for faster generation (256 tokens ≈ 1-2s vs 3-4s)

    # Caching Configuration
    agent_cache_size: int = 500  # LRU cache size for embeddings, searches, and answers
    embedding_batch_size: int = 32  # Batch size for bulk embedding operations

    # Application Configuration
    log_level: str = "INFO"
    batch_size: int = 10
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    api_port: int = 8000  # API server port (reads API_PORT from .env, defaults to 8000)
    enable_cache_warmup: bool = False  # Enable/disable response cache warmup on startup (reads ENABLE_CACHE_WARMUP from .env)

    # AWS Configuration (optional)
    aws_region: Optional[str] = "us-west-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
