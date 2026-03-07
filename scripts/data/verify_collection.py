#!/usr/bin/env python3
"""Verify collection configuration from .env file."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def verify_collection_config():
    """Verify collection configuration and existence."""
    from src.config.settings import Settings
    from src.tools import MilvusVectorDB

    print("\n" + "=" * 70)
    print("Collection Configuration Verification")
    print("=" * 70 + "\n")

    # Load settings
    settings = Settings()

    print("📋 Configuration from .env file:")
    print(f"   Collection Name: {settings.ollama_collection_name}")
    print(f"   Database: {settings.milvus_db_name}")
    print(f"   Milvus: {settings.milvus_host}:{settings.milvus_port}")
    print(f"   Embedding Model: {settings.ollama_embed_model}")
    print(f"   Embedding Dimension: {settings.embedding_dim}\n")

    # Check Milvus connection
    print("🔍 Checking Milvus connection...")
    try:
        db = MilvusVectorDB(
            host=settings.milvus_host, port=settings.milvus_port, db_name=settings.milvus_db_name
        )
        print("   ✓ Connected to Milvus\n")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        print("   Make sure Milvus is running: cd docker && docker-compose up -d\n")
        return False

    # List collections
    print("📦 Available collections in database:")
    try:
        collections = db.list_collections()
        if not collections:
            print("   ⚠️  No collections found")
        else:
            for coll in collections:
                is_configured = (
                    " ← CONFIGURED IN .ENV" if coll == settings.ollama_collection_name else ""
                )
                print(f"   - {coll}{is_configured}")
    except Exception as e:
        print(f"   ❌ Error listing collections: {e}")
        return False

    # Check if configured collection exists
    print("\n🎯 Status of configured collection:")
    configured_exists = settings.ollama_collection_name in collections

    if configured_exists:
        print(f"   ✓ Collection '{settings.ollama_collection_name}' EXISTS and is ready")

        # Get collection stats if available
        try:
            stats = db.client.get_collection_stats(collection_name=settings.ollama_collection_name)
            if stats:
                print(f"   Stats: {stats}")
        except Exception:
            pass  # Stats not critical

        print("\n✅ Configuration is CORRECT - ready to use!\n")
        return True
    else:
        print(f"   ⚠️  Collection '{settings.ollama_collection_name}' NOT FOUND")
        print("\n   To create and load the collection, run:")
        print("   python document-loaders/load_milvus_docs_ollama.py\n")
        return False


def main():
    """Main entry point."""
    try:
        success = verify_collection_config()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nAborted by user.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
