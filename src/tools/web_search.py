"""Web search integration for comparative product analysis.

Supports multiple search providers:
- Tavily: AI-optimized search (recommended, requires API key)

Deployment modes
----------------
- ``local`` (default): the Tavily API key is read from ``settings.tavily_api_key``
  (``.env`` / ``TAVILY_API_KEY``) exactly as before. No AWS SDK is imported.
- ``serverless``: when ``settings.secrets_tavily_api_key`` names a Secrets Manager
  secret, the key is resolved from AWS Secrets Manager once per Lambda cold start
  and cached in the execution environment for the warm invocation (Requirement 10.1).
  ``boto3`` is imported lazily inside the resolver so local mode never requires it.
"""

import json
import logging
import os
from datetime import datetime, timezone

import requests

from src.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# Automatic web-search fallback threshold (Requirement 10.4). Mirrors
# ``settings.web_search_fallback_threshold`` (default 0.15) so callers can import
# the shared constant without re-deriving it.
WEB_SEARCH_FALLBACK_THRESHOLD: float = Settings.model_fields[
    "web_search_fallback_threshold"
].default

# Module-level cache for the resolved Tavily key. In a Lambda execution
# environment this persists across warm invocations so Secrets Manager is only
# called once per cold start (Requirement 10.1). The sentinel distinguishes
# "never resolved" from "resolved to no key".
_UNRESOLVED = object()
_cached_tavily_api_key: object | str | None = _UNRESOLVED


def _resolve_tavily_api_key(settings: Settings | None = None) -> str | None:
    """Resolve the Tavily API key for the active deployment mode.

    Local mode (default) reads ``settings.tavily_api_key`` (populated from the
    ``.env`` / ``TAVILY_API_KEY`` environment variable) and never touches AWS.

    Serverless mode fetches the key from AWS Secrets Manager when
    ``settings.secrets_tavily_api_key`` is set, caching the resolved value at
    module level so the lookup happens once per cold start. ``boto3`` is
    imported lazily here so importing this module in local mode has no AWS
    dependency.

    Returns:
        The Tavily API key, or ``None`` if it could not be resolved.
    """
    global _cached_tavily_api_key

    if _cached_tavily_api_key is not _UNRESOLVED:
        return _cached_tavily_api_key  # type: ignore[return-value]

    settings = settings or get_settings()

    # Serverless cold-start path: pull the key from Secrets Manager.
    if settings.deployment_mode == "serverless" and settings.secrets_tavily_api_key:
        key = _load_tavily_key_from_secrets_manager(
            settings.secrets_tavily_api_key, settings.aws_region
        )
        _cached_tavily_api_key = key
        return key

    # Local mode (unchanged behavior): read from settings/.env.
    _cached_tavily_api_key = settings.tavily_api_key
    return settings.tavily_api_key


def _load_tavily_key_from_secrets_manager(secret_id: str, region: str | None) -> str | None:
    """Fetch the Tavily API key from AWS Secrets Manager (serverless only).

    ``boto3`` is imported inside the function so local mode never needs it. The
    secret value may be a raw string or a JSON document; when JSON, the common
    key names (``TAVILY_API_KEY``, ``tavily_api_key``, ``api_key``) are tried.
    """
    try:
        import boto3  # imported lazily; serverless-only dependency

        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_id)
        secret_string: str | None = response.get("SecretString")
        if not secret_string:
            logger.error("[TAVILY] Secrets Manager returned no SecretString for %s", secret_id)
            return None

        secret_string = secret_string.strip()
        if secret_string.startswith("{"):
            try:
                data = json.loads(secret_string)
                for name in ("TAVILY_API_KEY", "tavily_api_key", "api_key"):
                    if data.get(name):
                        return str(data[name])
                logger.error("[TAVILY] No recognized Tavily key field in secret %s", secret_id)
                return None
            except json.JSONDecodeError:
                # Not actually JSON; fall through and treat as a raw string.
                pass

        return secret_string
    except Exception as e:  # pragma: no cover - exercised in serverless env
        logger.error(
            "[TAVILY] Failed to load Tavily API key from Secrets Manager (%s): %s",
            secret_id,
            e,
        )
        return None


def reset_tavily_api_key_cache() -> None:
    """Reset the cached Tavily key (test helper / forced cold-start simulation)."""
    global _cached_tavily_api_key
    _cached_tavily_api_key = _UNRESOLVED


class TavilySearchClient:
    """Client for web search using Tavily API (AI-optimized for research).

    Tavily is specifically designed for AI research and has better coverage
    for technical products like Pinecone, Weaviate, etc.
    """

    def __init__(self, api_key: str | None = None, timeout: int | None = None):
        """Initialize Tavily search client.

        Args:
            api_key: Tavily API key. If not provided, will try to use TAVILY_API_KEY env var
            timeout: Request timeout in seconds (falls back to settings.web_search_timeout)
        """
        # Load defaults from settings
        settings = get_settings()
        if timeout is None:
            timeout = settings.web_search_timeout

        # Key resolution order:
        #   1. Explicit api_key argument (callers / tests)
        #   2. TAVILY_API_KEY env var (preserves prior local behavior exactly)
        #   3. Deployment-mode resolver: local -> settings.tavily_api_key;
        #      serverless -> Secrets Manager (cached once per cold start)
        self.api_key = (
            api_key or os.environ.get("TAVILY_API_KEY") or _resolve_tavily_api_key(settings)
        )
        self.timeout = timeout
        self.tavily_url = "https://api.tavily.com/search"
        self.session = requests.Session()

        if not self.api_key:
            logger.warning(
                "Tavily API key not provided. Tavily search will not work. Set TAVILY_API_KEY env var or pass api_key parameter."
            )

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = False,
    ) -> tuple[list[dict[str, str]], str]:
        """Search using Tavily API.

        Args:
            query: Search query
            max_results: Maximum number of results to return (1-20)
            search_depth: "basic" (default, 1 credit) or "advanced" (2 credits)
            include_answer: Whether to include LLM-generated answer

        Returns:
            Tuple of (results, status) where status is 'success', 'api_unavailable', or 'no_results'
        """
        if not self.api_key:
            logger.warning("[TAVILY] API key not available, skipping Tavily search")
            return [], "api_unavailable"

        try:
            logger.info(f"[TAVILY] Web search for: {query}")

            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": min(max_results, 20),
                "search_depth": search_depth,
                "include_answer": include_answer,
                "topic": "general",
            }

            response = self.session.post(
                self.tavily_url,
                json=payload,
                timeout=self.timeout,
            )

            # Check for specific Tavily error codes
            if response.status_code == 401:
                logger.error("[TAVILY] Authentication failed - invalid API key")
                return [], "api_unavailable"
            elif response.status_code == 429:
                logger.error("[TAVILY] Rate limit exceeded - too many requests")
                return [], "api_unavailable"
            elif response.status_code == 432:
                logger.error("[TAVILY] Quota exceeded or API key invalid")
                return [], "api_unavailable"
            elif not response.ok:
                logger.error(f"[TAVILY] API error: {response.status_code} - {response.text}")
                return [], "api_unavailable"

            response.raise_for_status()

            data = response.json()

            if "results" not in data:
                logger.warning(f"[TAVILY] No results field in response: {list(data.keys())}")
                return [], "no_results"

            retrieved_at = datetime.now(timezone.utc).isoformat()
            results = []
            for result in data.get("results", []):
                # Per the shared response schema (design "Response Schema
                # (both modes)") every web source must carry a non-empty `url`
                # and `timestamp`. Tavily results without a URL are not usable
                # as citable sources, so they are skipped (Requirement 10.5).
                url = (result.get("url") or "").strip()
                if not url:
                    logger.debug("[TAVILY] Skipping result with empty URL: %s", result.get("title"))
                    continue
                results.append(
                    {
                        "title": result.get("title", ""),
                        "snippet": result.get("content", ""),
                        "url": url,
                        "timestamp": retrieved_at,
                        "source": "Tavily",
                        "score": result.get("score", 0),
                    }
                )

            logger.info(
                f"[TAVILY] Found {len(results)} results (score: {data.get('response_time', 'N/A')}s)"
            )
            status = "success" if results else "no_results"
            return results, status

        except requests.exceptions.RequestException as e:
            logger.error(f"[TAVILY] Search error: {type(e).__name__}: {e}")
            return [], "api_unavailable"
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"[TAVILY] Response parsing error: {e}")
            return [], "api_unavailable"


class WebSearchClient:
    """Web search client using Tavily (AI-optimized search).

    Uses Tavily API for comprehensive coverage of technical products and databases.
    """

    def __init__(self, tavily_api_key: str | None = None, timeout: int | None = None):
        """Initialize the web search client.

        Args:
            tavily_api_key: Tavily API key (optional, will check TAVILY_API_KEY env var)
            timeout: Request timeout in seconds (falls back to settings.web_search_timeout)
        """
        # Load defaults from settings
        if timeout is None:
            timeout = get_settings().web_search_timeout

        self.tavily = TavilySearchClient(api_key=tavily_api_key, timeout=timeout)

        # Diagnostic logging
        if self.tavily.api_key:
            api_key_preview = (
                f"{self.tavily.api_key[:10]}..." if len(self.tavily.api_key) > 10 else "***"
            )
            logger.info(f"[WEB_SEARCH_INIT] ✓ Tavily API key loaded: {api_key_preview}")
        else:
            logger.warning("[WEB_SEARCH_INIT] ⚠️ NO Tavily API key found!")
            logger.warning(
                "[WEB_SEARCH_INIT] ⚠️ Check that TAVILY_API_KEY is set in .env or environment"
            )

    def search(
        self,
        query: str,
        max_results: int = 5,
        safe_search: bool = False,
    ) -> tuple[list[dict[str, str]], str]:
        """Search using Tavily API.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            safe_search: Enable safe search filtering (unused, kept for API compatibility)

        Returns:
            Tuple of (results, status) where status is 'success', 'api_unavailable', or 'no_results'
        """
        if not self.tavily.api_key:
            logger.warning("[WEB_SEARCH] Tavily API key not available. Web search will not work.")
            return [], "api_unavailable"

        results, status = self.tavily.search(query, max_results=max_results)
        logger.info(f"[WEB_SEARCH] Got {len(results)} results from Tavily (status: {status})")
        return results, status

    def search_comparison(
        self,
        product1: str,
        product2: str,
        max_results: int = 2,
    ) -> dict[str, list[dict[str, str]]]:
        """Search for comparison between two products using feature-focused queries.

        Performance Optimizations:
        - Reduced features from 5 to 3 (biggest impact on latency)
        - Reduced results per feature from 2 to 1
        - Estimated speedup: 6-8x faster web search component

        Args:
            product1: First product name
            product2: Second product name
            max_results: Maximum results per feature (default: 2 for speed)

        Returns:
            Dictionary with results for each product and feature comparisons
        """
        logger.info(f"[COMPARISON_SEARCH] Searching for comparison: {product1} vs {product2}")

        # Try direct comparison query first
        combined_results: list[dict[str, str]] = []
        if self.tavily.api_key:
            comparison_query = f"{product1} vs {product2} comparison features advantages"
            search_results, search_status = self.tavily.search(
                comparison_query, max_results=max_results
            )
            if search_status == "success" and search_results:
                combined_results = search_results
                logger.info(
                    f"[COMPARISON_SEARCH] Got {len(combined_results)} results from direct comparison query"
                )

        # Vector database specific feature searches
        # Optimized to 3 most critical features for speed
        vector_db_features = [
            "vector database indexing",
            "vector database performance",
            "vector database scalability",
        ]

        # Search for each product with specific feature queries
        product1_results = {}
        product2_results = {}

        for feature in vector_db_features:
            p1_query = f"{product1} {feature}"
            p2_query = f"{product2} {feature}"

            if feature not in product1_results:
                product1_results[feature] = self.search(p1_query, max_results=1)
            if feature not in product2_results:
                product2_results[feature] = self.search(p2_query, max_results=1)

        logger.info(
            f"[COMPARISON_SEARCH] Collected results - direct: {len(combined_results)}, "
            f"product1: {sum(len(r) for r in product1_results.values())}, "
            f"product2: {sum(len(r) for r in product2_results.values())}"
        )

        return {  # type: ignore[return-value]
            "comparison": combined_results,
            "product1": {  # type: ignore[dict-item]
                "name": product1,
                "results": product1_results,
            },
            "product2": {  # type: ignore[dict-item]
                "name": product2,
                "results": product2_results,
            },
        }

    def extract_text_summary(self, results: list[dict[str, str]]) -> str:
        """Extract and format search results into readable text.

        Args:
            results: List of search results

        Returns:
            Formatted text summary
        """
        if not results:
            return "No search results found."

        summary_parts = []
        for i, result in enumerate(results, 1):
            snippet = result.get("snippet", result.get("content", "No snippet available"))
            url = result.get("url", "")
            title = result.get("title", "Result")

            part = f"\n{i}. {title}"
            if snippet:
                part += f"\n   {snippet[:200]}..."
            if url:
                part += f"\n   Source: {url}"

            summary_parts.append(part)

        return "\n".join(summary_parts)
