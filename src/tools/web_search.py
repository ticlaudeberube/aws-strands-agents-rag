"""Web search integration for comparative product analysis."""

import requests
import logging
from typing import List, Dict, Optional
import json
from urllib.parse import quote

logger = logging.getLogger(__name__)


class WebSearchClient:
    """Client for web search using DuckDuckGo API (no key required)."""

    def __init__(self, timeout: int = 10):
        """Initialize web search client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.duckduckgo_url = "https://api.duckduckgo.com/"
        self.session = requests.Session()

    def search(
        self,
        query: str,
        max_results: int = 5,
        safe_search: bool = True,
    ) -> List[Dict[str, str]]:
        """Search the web using DuckDuckGo API.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            safe_search: Enable safe search filtering

        Returns:
            List of search results with title, snippet, and URL
        """
        try:
            logger.info(f"Web search for: {query}")

            params = {
                "q": query,
                "format": "json",
                "no_redirect": 1,
                "skip_disambig": 1,
            }

            if safe_search:
                params["kp"] = 1  # Safe search enabled

            response = self.session.get(
                self.duckduckgo_url,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()

            data = response.json()
            results = []

            # Parse DuckDuckGo response
            # Note: DuckDuckGo's instant answer and related topics
            if "AbstractText" in data and data["AbstractText"]:
                results.append(
                    {
                        "title": "Answer",
                        "snippet": data["AbstractText"],
                        "url": data.get("AbstractURL", ""),
                        "source": "DuckDuckGo",
                    }
                )

            # Parse related topics (if available)
            if "RelatedTopics" in data:
                for i, topic in enumerate(data["RelatedTopics"]):
                    if i >= max_results - 1:  # Leave room for abstract
                        break

                    if "Text" in topic:
                        results.append(
                            {
                                "title": topic.get("Text", "").split(" - ")[0][:60],
                                "snippet": topic.get("Text", "")[:200],
                                "url": topic.get("FirstURL", ""),
                                "source": "DuckDuckGo",
                            }
                        )

            logger.info(f"Found {len(results)} web results")
            return results[:max_results]

        except requests.exceptions.RequestException as e:
            logger.error(f"Web search failed: {e}")
            return []
        except json.JSONDecodeError:
            logger.error("Failed to parse web search response")
            return []

    def search_comparison(
        self,
        product1: str,
        product2: str,
        max_results: int = 5,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Search for comparison between two products with feature-focused queries.

        Args:
            product1: First product name
            product2: Second product name
            max_results: Maximum results per product

        Returns:
            Dictionary with results for each product and feature comparisons
        """
        # Broader comparison query
        comparison_query = f"{product1} vs {product2} features comparison"
        combined_results = self.search(
            comparison_query, max_results=max_results
        )

        # Vector database specific feature searches
        vector_db_features = [
            "vector indexing algorithms",
            "search performance scalability",
            "supported vector dimensions",
            "query latency",
            "pricing cost",
        ]

        # Search for each product with specific feature queries
        product1_results = {}
        product2_results = {}

        for feature in vector_db_features:
            p1_query = f"{product1} {feature}"
            p2_query = f"{product2} {feature}"
            
            if feature not in product1_results:
                product1_results[feature] = self.search(
                    p1_query, max_results=2, safe_search=True
                )
            if feature not in product2_results:
                product2_results[feature] = self.search(
                    p2_query, max_results=2, safe_search=True
                )

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
            snippet = result.get("snippet", "No snippet available")
            url = result.get("url", "")
            title = result.get("title", "Result")

            part = f"\n{i}. {title}"
            if snippet:
                part += f"\n   {snippet[:200]}..."
            if url:
                part += f"\n   Source: {url}"

            summary_parts.append(part)

        return "\n".join(summary_parts)
