#!/usr/bin/env python3
"""
Quick Health Check: Fast Diagnostic for Cache API Endpoints
Quick troubleshooting tool for rapid health checks during incidents.

Use Cases:
- Rapid health checks during incidents
- API endpoint validation
- Quick system status overview
"""

import sys
import time
from typing import Any, Dict

import requests

try:
    from src.config.settings import get_settings
    from src.tools.milvus_client import MilvusVectorDB
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Run from project root: python scripts/diagnostics/diagnostic_cache.py")
    sys.exit(1)


def check_api_endpoints(base_url: str = "http://localhost:8000") -> Dict[str, Any]:
    """Check API endpoint health."""
    results = {}

    endpoints = ["/health", "/metrics", "/v1/models", "/cache/stats"]

    print(f"\n🌐 Checking API endpoints at {base_url}...")

    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        try:
            start_time = time.time()
            response = requests.get(url, timeout=5)
            response_time = (time.time() - start_time) * 1000

            results[endpoint] = {
                "status_code": response.status_code,
                "response_time_ms": round(response_time, 2),
                "accessible": response.status_code < 400,
            }

            status_icon = "✅" if response.status_code < 400 else "❌"
            print(f"   {status_icon} {endpoint}: {response.status_code} ({response_time:.0f}ms)")

        except requests.exceptions.RequestException as e:
            results[endpoint] = {
                "status_code": None,
                "response_time_ms": None,
                "accessible": False,
                "error": str(e),
            }
            print(f"   ❌ {endpoint}: Connection failed - {e}")

    return results


def check_milvus_connection() -> Dict[str, Any]:
    """Check Milvus database connection."""
    print("\n🗄️  Checking Milvus connection...")

    try:
        settings = get_settings()
        db = MilvusVectorDB(
            host=settings.milvus_host,
            port=settings.milvus_port,
            db_name=settings.milvus_db_name,
        )

        # Test connection
        start_time = time.time()
        collections = db.client.list_collections(db_name=settings.milvus_db_name)
        connection_time = (time.time() - start_time) * 1000

        # Check cache collection
        cache_collection = settings.response_cache_collection_name
        cache_exists = cache_collection in collections

        result = {
            "connected": True,
            "connection_time_ms": round(connection_time, 2),
            "collections_count": len(collections),
            "cache_collection_exists": cache_exists,
            "collections": collections,
        }

        print(f"   ✅ Connected to Milvus ({connection_time:.0f}ms)")
        print(f"   ✅ Found {len(collections)} collections")

        if cache_exists:
            # Get cache stats
            try:
                stats = db.client.get_collection_stats(
                    collection_name=cache_collection, db_name=settings.milvus_db_name
                )
                cache_count = stats.get("row_count", 0)
                result["cache_entity_count"] = cache_count
                print(f"   ✅ Cache collection '{cache_collection}': {cache_count} entities")
            except Exception as e:
                print(f"   🟡 Cache collection exists but couldn't get stats: {e}")
        else:
            print(f"   ❌ Cache collection '{cache_collection}' not found")

        return result

    except Exception as e:
        print(f"   ❌ Milvus connection failed: {e}")
        return {"connected": False, "error": str(e)}


def quick_diagnostic() -> None:
    """Run quick diagnostic checks."""
    print("=" * 80)
    print("⚡ QUICK CACHE DIAGNOSTIC")
    print("=" * 80)

    # Check API endpoints
    api_results = check_api_endpoints()

    # Check Milvus
    milvus_results = check_milvus_connection()

    # Overall health assessment
    print("\n📊 OVERALL HEALTH ASSESSMENT")
    print("=" * 80)

    # API Health
    api_healthy = sum(1 for r in api_results.values() if r.get("accessible", False))
    api_total = len(api_results)

    if api_healthy == api_total:
        print("   🟢 API Endpoints: All healthy")
    elif api_healthy > api_total / 2:
        print(f"   🟡 API Endpoints: {api_healthy}/{api_total} healthy")
    else:
        print(f"   🔴 API Endpoints: {api_healthy}/{api_total} healthy")

    # Milvus Health
    if milvus_results.get("connected", False):
        cache_count = milvus_results.get("cache_entity_count", 0)
        if cache_count > 0:
            print("   🟢 Milvus: Connected with populated cache")
        elif milvus_results.get("cache_collection_exists", False):
            print("   🟡 Milvus: Connected but cache is empty")
        else:
            print("   🟡 Milvus: Connected but no cache collection")
    else:
        print("   🔴 Milvus: Connection failed")

    # Quick recommendations
    print("\n💡 QUICK RECOMMENDATIONS")
    print("=" * 80)

    issues = []

    # Check for common issues
    if not any(r.get("accessible", False) for r in api_results.values()):
        issues.append("🔴 API server not running - run: python api_server.py")

    if not milvus_results.get("connected", False):
        issues.append("🔴 Milvus not accessible - check Milvus server status")

    cache_count = milvus_results.get("cache_entity_count", 0)
    if milvus_results.get("connected", False) and cache_count == 0:
        issues.append("🟡 Cache is empty - run document loader to populate")

    if not issues:
        print("   🟢 No major issues detected - system appears healthy!")
    else:
        for issue in issues:
            print(f"   {issue}")

    print("\n" + "=" * 80)
    print("⚡ DIAGNOSTIC COMPLETE")
    print("=" * 80)


def main():
    """Main function with argument support."""
    import argparse

    parser = argparse.ArgumentParser(description="Quick cache diagnostic")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="API server URL to check"
    )

    args = parser.parse_args()

    # Override check function with custom URL
    global check_api_endpoints
    original_check = check_api_endpoints
    check_api_endpoints = lambda: original_check(args.api_url)

    quick_diagnostic()


if __name__ == "__main__":
    main()
