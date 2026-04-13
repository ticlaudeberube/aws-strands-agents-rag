#!/usr/bin/env python3
"""Diagnostic script to check RAG system setup."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def check_env():
    """Check environment configuration."""
    print("\n🔍 Checking Environment Configuration...")

    env_file = Path(".env")
    if not env_file.exists():
        print(f"  ⚠️  .env file not found at {env_file.absolute()}")
        print("     Copy from .env.example: cp .env.example .env")
        return False

    print(f"  ✓ .env file found at {env_file.absolute()}")

    # Load and display key settings
    try:
        from src.config.settings import Settings

        settings = Settings()

        print("\n  Configuration loaded:")
        print(f"    Ollama Host: {settings.ollama_host}")
        print(f"    Ollama Model: {settings.ollama_model}")
        print(f"    Ollama Embed Model: {settings.ollama_embed_model}")
        print(f"    Milvus Host: {settings.milvus_host}:{settings.milvus_port}")
        print(f"    Milvus DB: {settings.milvus_db_name}")
        print(f"    Collection Name: {settings.ollama_collection_name}")
        print(f"    Embedding Dim: {settings.embedding_dim}")

        return True
    except Exception as e:
        print(f"  ❌ Error loading settings: {e}")
        return False


def check_ollama():
    """Check Ollama availability and models."""
    print("\n🔍 Checking Ollama...")
    try:
        from src.tools import OllamaClient
        from src.config.settings import Settings

        settings = Settings()
        client = OllamaClient(host=settings.ollama_host)

        # Check connection
        if not client.is_available(timeout=3):
            print(f"  ❌ Cannot connect to Ollama at {settings.ollama_host}")
            print("     Run: ollama serve")
            return False

        print(f"  ✓ Ollama is running at {settings.ollama_host}")

        # Get models
        models = client.get_available_models(timeout=3)
        if not models:
            print("  ⚠️  Warning: Could not retrieve model list")
            return False

        print(f"  ✓ Available models: {len(models)}")
        for model in models:
            print(f"    - {model}")

        # Check required models
        if settings.ollama_embed_model not in models:
            print(f"\n  ❌ Missing embedding model: {settings.ollama_embed_model}")
            print(f"     Run: ollama pull {settings.ollama_embed_model}")
            return False

        print(f"  ✓ Embedding model available: {settings.ollama_embed_model}")
        return True

    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        print("     Run: pip install -e .")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def check_milvus():
    """Check Milvus availability."""
    print("\n🔍 Checking Milvus...")
    try:
        from src.tools import MilvusVectorDB
        from src.config.settings import Settings

        settings = Settings()
        db = MilvusVectorDB(
            host=settings.milvus_host, port=settings.milvus_port, db_name=settings.milvus_db_name
        )

        print(f"  ✓ Milvus is available at {settings.milvus_host}:{settings.milvus_port}")
        print(f"  ✓ Database: {settings.milvus_db_name}")

        # Check configured collection name from .env
        print("\n  Configuration from .env:")
        print(f"    Collection (OLLAMA_COLLECTION_NAME): {settings.ollama_collection_name}")

        # Check collections
        try:
            collections = db.list_collections()
            print(f"\n  ✓ Collections found: {len(collections)}")
            if collections:
                for coll in collections:
                    is_configured = (
                        " ← configured in .env" if coll == settings.ollama_collection_name else ""
                    )
                    print(f"    - {coll}{is_configured}")

                if settings.ollama_collection_name not in collections:
                    print(
                        f"\n  ⚠️  Warning: Configured collection '{settings.ollama_collection_name}' not found"
                    )
                    print("     Run: python document-loaders/load_milvus_docs_ollama.py")
                else:
                    print(f"\n  ✓ Configured collection '{settings.ollama_collection_name}' exists")
            else:
                print("\n  ⚠️  Warning: No collections found. Run the data loader:")
                print("     python document-loaders/load_milvus_docs_ollama.py")
        except Exception as e:
            print(f"  ⚠️  Warning: Could not list collections: {e}")

        return True

    except RuntimeError as e:
        print(f"  ❌ {e}")
        return False
    except Exception as e:
        print(f"  ❌ Milvus connection error: {e}")
        print("     Make sure Milvus is running:")
        print("     cd docker && docker-compose up -d")
        return False


def main():
    """Run all checks."""
    print("=" * 60)
    print("AWS Strands Agents RAG - Setup Diagnostic")
    print("=" * 60)

    results = {
        "Environment": check_env(),
        "Ollama": check_ollama(),
        "Milvus": check_milvus(),
    }

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)

    for service, status in results.items():
        symbol = "✓" if status else "❌"
        print(f"{symbol} {service}: {'OK' if status else 'FAILED'}")

    if all(results.values()):
        print("\n✓ All checks passed! System is ready.")
        return 0
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
