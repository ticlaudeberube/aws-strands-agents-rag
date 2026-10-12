"""Configuration settings for the application."""

import os
from typing import Any, Literal

from pydantic import Field, model_validator
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
    # Single source of truth for selecting backends. "local" wires Ollama +
    # Milvus + FastAPI; "serverless" wires Bedrock + OpenSearch + Lambda.
    deployment_mode: Literal["local", "serverless"] = Field(
        default="local",
        validation_alias="DEPLOYMENT_MODE",
        description=(
            'Deployment mode: "local" (Ollama + Milvus + FastAPI) or '
            '"serverless" (Bedrock + OpenSearch + Lambda).'
        ),
    )
    # Backward-compatible boolean. Retained so existing code reading
    # `settings.use_agentcore` keeps working. It is derived from
    # `deployment_mode` (use_agentcore == (deployment_mode == "serverless")).
    # If only the legacy USE_AGENTCORE env var is set (and DEPLOYMENT_MODE is
    # not), its value seeds deployment_mode so old configs still select the
    # serverless/AgentCore path.
    use_agentcore: bool = Field(
        default=False,
        validation_alias="USE_AGENTCORE",
        description="Derived from deployment_mode; True in serverless/AgentCore mode, False locally.",
    )

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        """Interpret a raw config value as a boolean the way pydantic does."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "t", "y"}
        return bool(value)

    @model_validator(mode="before")
    @classmethod
    def _promote_legacy_use_agentcore(cls, data: Any) -> Any:
        """Backward-compatibility bridge for the legacy ``USE_AGENTCORE`` flag.

        ``deployment_mode`` is the single source of truth. If an existing
        config supplies only the legacy ``USE_AGENTCORE`` flag (and does not
        set ``DEPLOYMENT_MODE``), promote the mode to ``"serverless"`` so old
        configurations keep selecting the serverless/AgentCore path.

        This runs in ``before`` mode so the decision is based on what the
        config *sources* actually provided (env vars, ``.env`` file, init
        kwargs) rather than on resolved defaults. The raw input ``data`` dict
        is keyed by the alias/field names that were supplied by a source;
        fields that fall back to their default are absent from it, which makes
        it the reliable signal that ``model_fields_set`` and ``os.getenv``
        cannot provide (the latter does not see ``.env`` file values).
        """
        if not isinstance(data, dict):
            return data

        def _provided(*keys: str) -> bool:
            return any(k in data for k in keys)

        def _get(*keys: str) -> Any:
            for k in keys:
                if k in data:
                    return data[k]
            return None

        deployment_mode_provided = _provided("deployment_mode", "DEPLOYMENT_MODE")
        use_agentcore_provided = _provided("use_agentcore", "USE_AGENTCORE")

        if not deployment_mode_provided and use_agentcore_provided:
            if cls._coerce_bool(_get("use_agentcore", "USE_AGENTCORE")):
                # Write using the field's validation alias so the value is
                # accepted (the field only permits the DEPLOYMENT_MODE alias).
                data["DEPLOYMENT_MODE"] = "serverless"

        return data

    @model_validator(mode="after")
    def _sync_use_agentcore(self) -> "Settings":
        """Re-derive ``use_agentcore`` from the authoritative deployment_mode.

        ``use_agentcore == (deployment_mode == "serverless")`` always holds, so
        existing code reading ``settings.use_agentcore`` keeps working and the
        two settings can never disagree.
        """
        object.__setattr__(self, "use_agentcore", self.deployment_mode == "serverless")
        return self

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

    # ------------------------------------------------------------------
    # Serverless Mode Configuration (deployment_mode == "serverless")
    # ------------------------------------------------------------------
    # All serverless fields have safe defaults so that importing/instantiating
    # Settings in local mode never requires any AWS configuration.

    # Bedrock (LLM inference + embeddings)
    bedrock_inference_model_id: str = Field(
        default="anthropic.claude-3-haiku-20240307-v1:0",
        validation_alias="BEDROCK_INFERENCE_MODEL_ID",
        description="Default Bedrock model ID used for answer generation.",
    )
    bedrock_embedding_model_id: str = Field(
        default="amazon.titan-embed-text-v1",
        validation_alias="BEDROCK_EMBEDDING_MODEL_ID",
        description="Bedrock model ID used for query/document embeddings (1536-dim).",
    )
    bedrock_model_override: str | None = Field(
        default=None,
        validation_alias="BEDROCK_MODEL_OVERRIDE",
        description="Optional Bedrock model ID that overrides the default inference model.",
    )
    bedrock_embedding_dim: int = Field(
        default=1536,
        validation_alias="BEDROCK_EMBEDDING_DIM",
        description="Raw embedding dimension returned by the Bedrock embedding model.",
    )
    bedrock_pca_target_dim: int = Field(
        default=768,
        validation_alias="BEDROCK_PCA_TARGET_DIM",
        description=(
            "Target embedding dimension after PCA reduction, matching the OpenSearch "
            "768-dim k-NN index (and the local nomic-embed-text:v1.5 dimension)."
        ),
    )
    bedrock_pca_matrix_uri: str | None = Field(
        default=None,
        validation_alias="BEDROCK_PCA_MATRIX_URI",
        description=(
            "Location of the pre-computed PCA projection matrix "
            "(e.g. s3://bucket/key.npy or a local .npy path). When unset, a "
            "deterministic built-in projection derived from the matrix dimensions is used."
        ),
    )

    # OpenSearch Serverless (vector store + Layer 4 semantic cache)
    opensearch_endpoint: str | None = Field(
        default=None,
        validation_alias="OPENSEARCH_ENDPOINT",
        description="OpenSearch Serverless collection endpoint (HTTPS, VPC).",
    )
    opensearch_kb_index: str = Field(
        default="rag-kb",
        validation_alias="OPENSEARCH_KB_INDEX",
        description="OpenSearch index name for the knowledge base documents.",
    )
    opensearch_cache_index: str = Field(
        default="rag-cache",
        validation_alias="OPENSEARCH_CACHE_INDEX",
        description="OpenSearch index name for the Layer 4 semantic response cache.",
    )

    # ElastiCache Redis (Layer 2 embedding cache / Layer 3 search result cache)
    redis_endpoint: str | None = Field(
        default=None,
        validation_alias="REDIS_ENDPOINT",
        description="ElastiCache Redis endpoint (TLS) for distributed cache in serverless mode.",
    )
    redis_embedding_ttl: int = Field(
        default=3600,
        validation_alias="REDIS_EMBEDDING_TTL",
        description="TTL in seconds for Layer 2 embedding cache entries (default 1 hour).",
    )
    redis_search_ttl: int = Field(
        default=86400,
        validation_alias="REDIS_SEARCH_TTL",
        description="TTL in seconds for Layer 3 search result cache entries (default 24 hours).",
    )

    # Document indexing pipeline (shared chunking bound)
    max_chunk_length: int = Field(
        default=400,
        validation_alias="MAX_CHUNK_LENGTH",
        description=(
            "Maximum number of tokens per document chunk, shared by the local "
            "document loaders and the serverless indexing pipeline (Requirement 9.2)."
        ),
    )

    # DynamoDB (session history + indexing analytics)
    dynamodb_session_table: str | None = Field(
        default=None,
        validation_alias="DYNAMODB_SESSION_TABLE",
        description="DynamoDB table storing conversation history (TTL 24h).",
    )
    dynamodb_analytics_table: str | None = Field(
        default=None,
        validation_alias="DYNAMODB_ANALYTICS_TABLE",
        description="DynamoDB table storing per-query/indexing analytics.",
    )

    # Secrets Manager (secret identifiers resolved at Lambda cold start)
    secrets_tavily_api_key: str | None = Field(
        default=None,
        validation_alias="SECRETS_TAVILY_API_KEY",
        description="Secrets Manager secret name/ARN holding the Tavily API key.",
    )
    secrets_redis_credentials: str | None = Field(
        default=None,
        validation_alias="SECRETS_REDIS_CREDENTIALS",
        description="Secrets Manager secret name/ARN holding Redis credentials.",
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

    # Input Validation Configuration
    min_message_length: int = Field(
        default=2,
        validation_alias="MIN_MESSAGE_LENGTH",
        description="Minimum message length in characters (configurable)",
    )
    max_message_length: int = Field(
        default=5000,
        validation_alias="MAX_MESSAGE_LENGTH",
        description="Maximum message length in characters (API DoS protection)",
    )
    enable_html_sanitization: bool = Field(
        default=True,
        validation_alias="ENABLE_HTML_SANITIZATION",
        description="Enable HTML sanitization using bleach library",
    )
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
