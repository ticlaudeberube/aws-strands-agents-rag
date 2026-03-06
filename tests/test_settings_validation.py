#!/usr/bin/env python3
"""Comprehensive test script to validate all environment variables and settings."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import get_settings


def test_settings():
    """Test all settings loaded from environment variables."""
    print("=" * 80)
    print("SETTINGS VALIDATION TEST")
    print("=" * 80)

    try:
        settings = get_settings()

        # Group settings by category
        sections = {
            "Ollama Configuration": [
                "ollama_host",
                "ollama_model",
                "ollama_embed_model",
                "ollama_timeout",
                "ollama_pool_size",
                "ollama_num_threads",
            ],
            "Milvus Configuration": [
                "milvus_host",
                "milvus_port",
                "milvus_db_name",
                "loader_milvus_db_name",
                "milvus_user",
                "milvus_password",
                "milvus_timeout",
                "milvus_pool_size",
                "milvus_index_type",
                "milvus_metric_type",
                "milvus_hnsw_m",
                "milvus_hnsw_ef_construction",
                "milvus_ivf_nlist",
                "milvus_search_ef",
            ],
            "Collection Configuration": [
                "ollama_collection_name",
                "response_cache_collection_name",
            ],
            "Embedding Configuration": [
                "max_chunk_length",
                "embedding_dim",
                "response_cache_embedding_dim",
            ],
            "Performance Settings": [
                "tokenizers_parallelism",
                "pytorch_mps_high_watermark_ratio",
                "max_tokens",
            ],
            "Cache Configuration": [
                "agent_cache_size",
                "embedding_batch_size",
                "response_cache_threshold",
                "response_cache_stats_limit",
            ],
            "Retrieval Tuning": [
                "default_top_k",
                "search_comparison_top_k",
                "embedding_cache_ttl",
            ],
            "Application Configuration": [
                "log_level",
                "batch_size",
                "user_agent",
                "api_port",
                "enable_cache_warmup",
                "web_search_timeout",
            ],
            "AWS Configuration": [
                "aws_region",
                "aws_access_key_id",
                "aws_secret_access_key",
            ],
        }

        all_valid = True

        for section, fields in sections.items():
            print(f"\n[{section}]")
            print("-" * 80)
            for field in fields:
                try:
                    value = getattr(settings, field)
                    # Mask sensitive values
                    if field in ["milvus_password", "aws_secret_access_key", "tavily_api_key"]:
                        display_value = "***" if value else "NOT SET"
                    elif isinstance(value, bool):
                        display_value = value
                    elif isinstance(value, (int, float)):
                        display_value = value
                    elif value is None:
                        display_value = "None (Optional)"
                    else:
                        # Truncate long strings
                        display_value = str(value)[:60] + ("..." if len(str(value)) > 60 else "")

                    status = "✓ OK"
                    if field == "enable_cache_warmup":
                        print(f"  {field:.<50} {display_value:<20} {status}")
                    else:
                        print(f"  {field:.<50} {display_value:<20} {status}")
                except AttributeError as e:
                    print(f"  {field:.<50} MISSING {f'({str(e)})':<20} ✗ ERROR")
                    all_valid = False

        print("\n" + "=" * 80)
        print("CRITICAL SETTINGS VALIDATION")
        print("=" * 80)

        # Validate critical settings
        critical_checks = [
            ("Milvus connectivity", lambda: settings.milvus_host and settings.milvus_port > 0),
            (
                "Ollama connectivity",
                lambda: (
                    settings.ollama_host
                    and "localhost" in settings.ollama_host
                    or "127.0.0.1" in settings.ollama_host
                ),
            ),
            (
                "Embedding dimension",
                lambda: settings.embedding_dim == settings.response_cache_embedding_dim,
            ),
            ("Cache threshold valid", lambda: 0 <= settings.response_cache_threshold <= 1),
            ("Cache stats limit valid", lambda: settings.response_cache_stats_limit > 0),
            ("Response cache threshold", lambda: settings.response_cache_threshold >= 0.8),
            ("API port valid", lambda: settings.api_port > 0 and settings.api_port < 65536),
            ("Search EF valid", lambda: settings.milvus_search_ef > 0),
            (
                "Collection names set",
                lambda: settings.ollama_collection_name and settings.response_cache_collection_name,
            ),
        ]

        for check_name, check_func in critical_checks:
            try:
                result = check_func()
                status = "✓ PASS" if result else "✗ FAIL"
                print(f"  {check_name:.<50} {status}")
                if not result:
                    all_valid = False
            except Exception as e:
                print(f"  {check_name:.<50} ✗ ERROR: {str(e)[:40]}")
                all_valid = False

        print("\n" + "=" * 80)
        if all_valid:
            print("✓ ALL SETTINGS VALID")
            return 0
        else:
            print("✗ SOME SETTINGS HAVE ISSUES")
            return 1

    except Exception as e:
        print(f"\n✗ FAILED TO LOAD SETTINGS: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(test_settings())
