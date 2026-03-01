"""Web search integration for comparative product analysis.

Supports multiple search providers:
- Tavily: AI-optimized search (recommended, requires API key)
"""

import requests
import logging
from typing import List, Dict, Optional
import json
from urllib.parse import quote
import os

logger = logging.getLogger(__name__)


class TavilySearchClient:
    """Client for web search using Tavily API (AI-optimized for research).
    
    Tavily is specifically designed for AI research and has better coverage
    for technical products like Pinecone, Weaviate, etc.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        """Initialize Tavily search client.

        Args:
            api_key: Tavily API key. If not provided, will try to use TAVILY_API_KEY env var
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self.timeout = timeout
        self.tavily_url = "https://api.tavily.com/search"
        self.session = requests.Session()
        
        if not self.api_key:
            logger.warning("Tavily API key not provided. Tavily search will not work. Set TAVILY_API_KEY env var or pass api_key parameter.")

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = False,
    ) -> List[Dict[str, str]]:
        """Search using Tavily API.

        Args:
            query: Search query
            max_results: Maximum number of results to return (1-20)
            search_depth: "basic" (default, 1 credit) or "advanced" (2 credits)
            include_answer: Whether to include LLM-generated answer

        Returns:
            List of search results with title, snippet, url, and score
        """
        if not self.api_key:
            logger.warning("[TAVILY] API key not available, skipping Tavily search")
            return []
        
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
            response.raise_for_status()

            data = response.json()
            
            if "results" not in data:
                logger.warning(f"[TAVILY] No results field in response: {list(data.keys())}")
                return []
            
            results = []
            for result in data.get("results", []):
                results.append({
                    "title": result.get("title", ""),
                    "snippet": result.get("content", ""),
                    "url": result.get("url", ""),
                    "source": "Tavily",
                    "score": result.get("score", 0),
                })
            
            logger.info(f"[TAVILY] Found {len(results)} results (score: {data.get('response_time', 'N/A')}s)")
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[TAVILY] Search error: {type(e).__name__}: {e}")
            return []
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"[TAVILY] Response parsing error: {e}")
            return []


class WebSearchClient:
    """Web search client using Tavily (AI-optimized search).
    
    Uses Tavily API for comprehensive coverage of technical products and databases.
    """

    def __init__(self, tavily_api_key: Optional[str] = None, timeout: int = 10):
        """Initialize the web search client.

        Args:
            tavily_api_key: Tavily API key (optional, will check TAVILY_API_KEY env var)
            timeout: Request timeout in seconds
        """
        self.tavily = TavilySearchClient(api_key=tavily_api_key, timeout=timeout)
        
        # Diagnostic logging
        if self.tavily.api_key:
            api_key_preview = f"{self.tavily.api_key[:10]}..." if len(self.tavily.api_key) > 10 else "***"
            logger.info(f"[WEB_SEARCH_INIT] ✓ Tavily API key loaded: {api_key_preview}")
        else:
            logger.warning(f"[WEB_SEARCH_INIT] ⚠️ NO Tavily API key found!")
            logger.warning(f"[WEB_SEARCH_INIT] ⚠️ Check that TAVILY_API_KEY is set in .env or environment")

    def search(
        self,
        query: str,
        max_results: int = 5,
        safe_search: bool = False,
    ) -> List[Dict[str, str]]:
        """Search using Tavily API.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            safe_search: Enable safe search filtering (unused, kept for API compatibility)

        Returns:
            List of search results with title, snippet, and URL
        """
        if not self.tavily.api_key:
            logger.warning("[WEB_SEARCH] Tavily API key not available. Web search will not work.")
            return []
        
        results = self.tavily.search(query, max_results=max_results)
        logger.info(f"[WEB_SEARCH] Got {len(results)} results from Tavily")
        return results

    def search_comparison(
        self,
        product1: str,
        product2: str,
        max_results: int = 2,
    ) -> Dict[str, List[Dict[str, str]]]:
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
        combined_results = []
        if self.tavily.api_key:
            comparison_query = f"{product1} vs {product2} comparison features advantages"
            combined_results = self.tavily.search(comparison_query, max_results=max_results)
            if combined_results:
                logger.info(f"[COMPARISON_SEARCH] Got {len(combined_results)} results from direct comparison query")

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

        logger.info(f"[COMPARISON_SEARCH] Collected results - direct: {len(combined_results)}, "
                   f"product1: {sum(len(r) for r in product1_results.values())}, "
                   f"product2: {sum(len(r) for r in product2_results.values())}")

        return {
            "comparison": combined_results,
            "product1": {
                "name": product1,
                "results": product1_results,
            },
            "product2": {
                "name": product2,
                "results": product2_results,
            },
        }

    def extract_text_summary(self, results: List[Dict[str, str]]) -> str:
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