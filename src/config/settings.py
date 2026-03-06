"""Configuration settings for the application."""

import os
from pydantic import Field
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
    milvus_index_type: str = os.getenv(
        "MILVUS_INDEX_TYPE", "HNSW"
    )  # Index type (HNSW, IVF_FLAT, FLAT)
    milvus_metric_type: str = os.getenv(
        "MILVUS_METRIC_TYPE", "COSINE"
    )  # Similarity metric (COSINE, L2, IP)
    # HNSW Index Parameters
    milvus_hnsw_m: int = int(
        os.getenv("MILVUS_HNSW_M", "30")
    )  # Maximum connections for each element in HNSW
    milvus_hnsw_ef_construction: int = int(
        os.getenv("MILVUS_HNSW_EF_CONSTRUCTION", "200")
    )  # Dynamic list size for HNSW construction
    milvus_ivf_nlist: int = int(
        os.getenv("MILVUS_IVF_NLIST", "128")
    )  # Number of clusters for IVF_FLAT index
    milvus_search_ef: int = int(
        os.getenv("MILVUS_SEARCH_EF", "64")
    )  # HNSW search parameter (speed/accuracy tradeoff)

    # Collection Configuration
    ollama_collection_name: str = "milvus_rag_collection"
    response_cache_collection_name: str = Field(
        default="response_cache",
        validation_alias="RESPONSE_CACHE_COLLECTION_NAME",
    )

    # Embedding and chunk processing
    max_chunk_length: int = 250  # Reduced from 400 for faster context processing (30-40% speedup)
    embedding_dim: int = Field(
        default=768,
        validation_alias="EMBEDDING_DIM",
    )
    response_cache_embedding_dim: int = Field(
        default=768,
        validation_alias="RESPONSE_CACHE_EMBEDDING_DIM",
    )

    # Performance Settings
    ollama_num_threads: int = 6
    tokenizers_parallelism: bool = False
    pytorch_mps_high_watermark_ratio: float = 0.0

    # LLM Generation Optimization
    max_tokens: int = 256  # Limit output length for faster generation (256 tokens ≈ 1-2s vs 3-4s)
    ollama_temperature: float = 0.7  # Temperature for response generation
    ollama_max_tokens: int = 256  # Max tokens for response generation

    # Caching Configuration
    agent_cache_size: int = 500  # LRU cache size for embeddings, searches, and answers
    embedding_batch_size: int = 32  # Batch size for bulk embedding operations
    response_cache_threshold: float = Field(
        default=0.99,
        validation_alias="RESPONSE_CACHE_THRESHOLD",
    )
    response_cache_stats_limit: int = Field(
        default=10000,
        validation_alias="RESPONSE_CACHE_STATS_LIMIT",
    )

    # Retrieval Tuning (Phase 3B)
    default_top_k: int = int(
        os.getenv("DEFAULT_TOP_K", "10")
    )  # Default number of context chunks for retrieval
    search_comparison_top_k: int = int(
        os.getenv("SEARCH_COMPARISON_TOP_K", "2")
    )  # Top-k for product comparison searches (optimized for speed)
    embedding_cache_ttl: int = int(
        os.getenv("EMBEDDING_CACHE_TTL", "3600")
    )  # Time-to-live for cached embeddings in seconds (3600 = 1 hour)

    # Application Configuration
    log_level: str = "INFO"
    batch_size: int = 10
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    api_port: int = 8000  # API server port (reads API_PORT from .env, defaults to 8000)
    enable_cache_warmup: bool = False  # Enable/disable response cache warmup on startup (reads ENABLE_CACHE_WARMUP from .env)
    web_search_timeout: int = 10  # Web search request timeout in seconds

    # AWS Configuration (optional)
    aws_region: Optional[str] = "us-west-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
