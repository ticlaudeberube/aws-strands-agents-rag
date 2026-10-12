#!/usr/bin/env python3
"""Verify that loader and API use the same database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Check loader settings
from document_loaders.local_settings import get_loader_settings as get_loader_settings_local

loader_settings = get_loader_settings_local()
print("Loader settings:")
print(f"  milvus_host: {loader_settings.milvus_host}")
print(f"  milvus_port: {loader_settings.milvus_port}")
print(f"  milvus_db_name: {loader_settings.milvus_db_name}")
print(f"  loader_milvus_db_name: {loader_settings.loader_milvus_db_name}")
print(f"  response_cache_collection_name: {loader_settings.response_cache_collection_name}")
print()

# Check API settings
from src.config.settings import get_settings as get_api_settings  # noqa: E402

api_settings = get_api_settings()
print("API settings:")
print(f"  milvus_host: {api_settings.milvus_host}")
print(f"  milvus_port: {api_settings.milvus_port}")
print(f"  milvus_db_name: {api_settings.milvus_db_name}")
print(f"  response_cache_collection_name: {api_settings.response_cache_collection_name}")
print()

# Check if they match
if loader_settings.milvus_db_name == api_settings.milvus_db_name:
    print("✓ DB names match")
else:
    print(
        f"❌ DB names DON'T match: {loader_settings.milvus_db_name} != {api_settings.milvus_db_name}"
    )

if loader_settings.response_cache_collection_name == api_settings.response_cache_collection_name:
    print("✓ Collection names match")
else:
    print(
        f"❌ Collection names DON'T match: {loader_settings.response_cache_collection_name} != {api_settings.response_cache_collection_name}"
    )
