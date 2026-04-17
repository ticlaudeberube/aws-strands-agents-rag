"""Configuration settings for the application."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Default collection name for knowledge base RAG search (Option A: Semantic Cache Only)
    # Data: 6,878 document chunks from embeddings.json
    ollama_collection_name: str = Field(
        default="milvus_rag_collection",
        validation_alias="OLLAMA_COLLECTION_NAME",
        description="Collection name for knowledge base RAG search (contains embeddings.json).",
    )
    # Maximum number of tokens for LLM responses
    max_tokens: int = Field(
        default=2000,
        validation_alias="MAX_TOKENS",
        description="Maximum number of tokens for LLM responses.",
    )
    # Response cache similarity threshold (for cache hits)
    response_cache_threshold: float = Field(
        default=0.92,
        validation_alias="RESPONSE_CACHE_THRESHOLD",
        description="Minimum cosine similarity for cache hit (0-1).",
    )

    # Response cache stats limit (number of entries to return in stats)
    response_cache_stats_limit: int = Field(
        default=100,
        validation_alias="RESPONSE_CACHE_STATS_LIMIT",
        description="Number of cache entries to return in stats.",
    )

    # Collection name for response cache
    response_cache_collection_name: str = Field(
        default="response_cache",
        validation_alias="RESPONSE_CACHE_COLLECTION_NAME",
        description="Collection name for cached Q&A pairs.",
    )

    # Embedding dimension for response cache (must match embedding model)
    response_cache_embedding_dim: int = Field(
        default=768,
        validation_alias="RESPONSE_CACHE_EMBEDDING_DIM",
        description="Embedding dimension for response cache (must match embedding model).",
    )

    # Ollama Configuration
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5")
    ollama_timeout: int = 30  # Request timeout in seconds
    ollama_pool_size: int = 5  # Connection pool size
    ollama_temperature: float = 0.1  # LLM temperature for generation
    ollama_max_tokens: int = 2000  # Maximum tokens for LLM generation

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
    milvus_hnsw_m: int = int(
        os.getenv("MILVUS_HNSW_M", "30")
    )  # Maximum connections for each element in HNSW
    milvus_hnsw_ef_construction: int = int(
        os.getenv("MILVUS_HNSW_EF_CONSTRUCTION", "200")
    )  # Dynamic list size for HNSW construction
    milvus_ivf_nlist: int = int(os.getenv("MILVUS_IVF_NLIST", "128"))  # IVF_FLAT nlist parameter

    # Deployment Mode
    use_agentcore: bool = Field(
        default=False,
        validation_alias="USE_AGENTCORE",
        description="Set to True to use AgentCore (serverless/cloud) mode; False for local Strands agent.",
    )

    # AgentCore Distributed Cache/Session Analytics (for Lambda/Bedrock)
    redis_cache_enabled: bool = Field(
        default=False,
        validation_alias="REDIS_CACHE_ENABLED",
        description="Enable Redis distributed cache for AgentCore.",
    )
    redis_host: str | None = Field(
        default=None, validation_alias="REDIS_HOST", description="Redis host for distributed cache."
    )
    redis_port: int | None = Field(
        default=6379, validation_alias="REDIS_PORT", description="Redis port for distributed cache."
    )
    redis_db: int | None = Field(
        default=0, validation_alias="REDIS_DB", description="Redis DB index for distributed cache."
    )
    embedding_cache_ttl_hours: int = Field(
        default=1,
        validation_alias="EMBEDDING_CACHE_TTL_HOURS",
        description="TTL for embedding cache in hours.",
    )
    search_cache_ttl_hours: int = Field(
        default=24,
        validation_alias="SEARCH_CACHE_TTL_HOURS",
        description="TTL for search cache in hours.",
    )
    use_dynamodb_cache: bool = Field(
        default=False,
        validation_alias="USE_DYNAMODB_CACHE",
        description="Enable DynamoDB for distributed cache (alternative to Redis).",
    )
    dynamodb_cache_table: str | None = Field(
        default=None,
        validation_alias="DYNAMODB_CACHE_TABLE",
        description="DynamoDB table name for distributed cache.",
    )
    agentcore_session_table: str | None = Field(
        default=None,
        validation_alias="AGENTCORE_SESSION_TABLE",
        description="DynamoDB table for AgentCore session analytics.",
    )
    enable_question_analytics: bool = Field(
        default=False,
        validation_alias="ENABLE_QUESTION_ANALYTICS",
        description="Enable question analytics for AgentCore sessions.",
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
    enable_web_search_supplement: bool = Field(
        default=False,
        validation_alias="ENABLE_WEB_SEARCH_SUPPLEMENT",
    )  # Add web search results as supplementary sources to KB results (off by default)
    web_search_fallback_threshold: float = Field(
        default=0.15,  # Much more restrictive - only fallback when KB truly has no good content
        validation_alias="WEB_SEARCH_FALLBACK_THRESHOLD",
    )  # Minimum average KB relevance score (0-1) before triggering web search fallback (default: 0.15, was 0.5)
    tavily_api_key: str | None = Field(
        default=None,
        validation_alias="TAVILY_API_KEY",
    )  # Tavily API key for web search (reads TAVILY_API_KEY from .env)

    # AWS Configuration (optional)
    aws_region: str | None = "us-west-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
