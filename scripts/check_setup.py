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
        print(f"    Local Vector Backend: {settings.local_vector_backend}")
        print(
            f"    OpenSearch (local): {settings.opensearch_local_host}:{settings.opensearch_local_port}"
        )
        print(f"    KB Index: {settings.opensearch_kb_index}")

        return True
    except Exception as e:
        print(f"  ❌ Error loading settings: {e}")
        return False


def check_ollama():
    """Check Ollama availability and models."""
    print("\n🔍 Checking Ollama...")
    try:
        from src.config.settings import Settings
        from src.tools import OllamaClient

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


def check_opensearch():
    """Check the local OpenSearch vector store availability."""
    print("\n🔍 Checking OpenSearch (local)...")
    try:
        from src.config.settings import Settings
        from src.tools.opensearch_client import OpenSearchClient

        settings = Settings()
        client = OpenSearchClient.for_local(settings)
        if not client.client.ping():
            print(
                f"  ❌ Cannot reach OpenSearch at "
                f"{settings.opensearch_local_host}:{settings.opensearch_local_port}"
            )
            print("     Start it: docker compose -f docker/docker-compose.yml up -d opensearch")
            return False

        print(
            f"  ✓ OpenSearch is available at "
            f"{settings.opensearch_local_host}:{settings.opensearch_local_port}"
        )

        kb_index = settings.opensearch_kb_index
        if client.client.indices.exists(index=kb_index):
            try:
                count = client.client.count(index=kb_index).get("count", 0)
                print(f"  ✓ KB index '{kb_index}' exists ({count} documents)")
                if count == 0:
                    print("  ⚠️  KB index is empty. Ingest documents:")
                    print("     uv run python scripts/ingest_local_opensearch.py")
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  Could not count documents: {e}")
        else:
            print(f"  ⚠️  KB index '{kb_index}' not found. Ingest documents:")
            print("     uv run python scripts/ingest_local_opensearch.py")
        return True

    except Exception as e:  # noqa: BLE001
        print(f"  ❌ OpenSearch check error: {e}")
        print("     Start it: docker compose -f docker/docker-compose.yml up -d opensearch")
        return False


def main():
    """Run all checks."""
    print("=" * 60)
    print("AWS Strands Agents RAG - Setup Diagnostic")
    print("=" * 60)

    results = {
        "Environment": check_env(),
        "Ollama": check_ollama(),
        "OpenSearch": check_opensearch(),
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
