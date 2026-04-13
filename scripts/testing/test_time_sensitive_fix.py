#!/usr/bin/env python3
"""
Feature Testing: Test Time-Sensitive Query Detection and Web Search
Validates time-sensitive query routing works correctly.

Use Cases:
- Testing web search integration
- Validating query classification logic
- Feature development validation
"""

import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

try:
    from src.agents.strands_graph_agent import StrandsGraphRAGAgent
    from src.config.settings import get_settings
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Run from project root: python scripts/testing/test_time_sensitive_fix.py")
    sys.exit(1)


class TimeSensitiveQueryTester:
    """Test suite for time-sensitive query detection and routing."""

    def __init__(self):
        self.agent = StrandsGraphRAGAgent()
        self.settings = get_settings()

    def get_time_sensitive_queries(self) -> List[Dict[str, Any]]:
        """Get test queries that should trigger time-sensitive routing."""
        current_year = datetime.now().year
        recent_date = datetime.now() - timedelta(days=30)

        return [
            {
                "query": "What are the latest updates to Milvus?",
                "category": "latest_updates",
                "should_use_web_search": True,
                "expected_keywords": ["update", "latest", "recent", "new"],
            },
            {
                "query": f"What happened in the Milvus community in {current_year}?",
                "category": "current_events",
                "should_use_web_search": True,
                "expected_keywords": ["community", str(current_year)],
            },
            {
                "query": "What are the current trends in vector databases?",
                "category": "trends",
                "should_use_web_search": True,
                "expected_keywords": ["trend", "current", "vector", "database"],
            },
            {
                "query": "Latest news about AI and machine learning",
                "category": "ai_news",
                "should_use_web_search": True,
                "expected_keywords": ["news", "AI", "machine learning", "latest"],
            },
            {
                "query": "Recent developments in embedding models",
                "category": "recent_tech",
                "should_use_web_search": True,
                "expected_keywords": ["recent", "development", "embedding", "model"],
            },
        ]

    def get_non_time_sensitive_queries(self) -> List[Dict[str, Any]]:
        """Get test queries that should NOT trigger time-sensitive routing."""
        return [
            {
                "query": "What is Milvus?",
                "category": "basic_definition",
                "should_use_web_search": False,
                "expected_keywords": ["Milvus", "vector", "database"],
            },
            {
                "query": "How do vector embeddings work?",
                "category": "technical_concept",
                "should_use_web_search": False,
                "expected_keywords": ["vector", "embedding", "work"],
            },
            {
                "query": "What is the difference between FLAT and IVF_FLAT indexes?",
                "category": "technical_comparison",
                "should_use_web_search": False,
                "expected_keywords": ["FLAT", "IVF", "index", "difference"],
            },
            {
                "query": "How to create a collection in Milvus?",
                "category": "how_to",
                "should_use_web_search": False,
                "expected_keywords": ["create", "collection", "Milvus"],
            },
            {
                "query": "What are the benefits of vector databases?",
                "category": "general_benefits",
                "should_use_web_search": False,
                "expected_keywords": ["benefit", "vector", "database"],
            },
        ]

    def test_time_sensitive_detection(self) -> Dict[str, Any]:
        """Test time-sensitive query detection logic."""
        print("🕐 Testing time-sensitive query detection...")

        time_sensitive_queries = self.get_time_sensitive_queries()
        non_time_sensitive_queries = self.get_non_time_sensitive_queries()

        results = {
            "time_sensitive_tests": [],
            "non_time_sensitive_tests": [],
            "detection_accuracy": 0,
        }

        correct_classifications = 0
        total_tests = len(time_sensitive_queries) + len(non_time_sensitive_queries)

        # Test time-sensitive queries
        print(f"\n📅 Testing {len(time_sensitive_queries)} time-sensitive queries...")

        for i, test_case in enumerate(time_sensitive_queries, 1):
            query = test_case["query"]
            category = test_case["category"]

            print(f"   {i}. {category}: {query[:50]}...")

            try:
                start_time = time.time()
                result = self.agent.answer_question(query)
                response_time = time.time() - start_time

                # Analyze the response for web search indicators
                answer = result.answer if hasattr(result, "answer") else str(result)
                sources = result.sources if hasattr(result, "sources") else []

                # Check for web search indicators
                web_search_indicators = [
                    "latest",
                    "recent",
                    "current",
                    "today",
                    "news",
                    "update",
                    "2024",
                    "2025",
                    datetime.now().strftime("%Y"),
                ]

                has_web_indicators = any(
                    indicator in answer.lower() for indicator in web_search_indicators
                )

                # Check sources for web/external content
                has_external_sources = any(
                    "http" in str(source) or "web" in str(source).lower() for source in sources
                )

                test_result = {
                    "query": query,
                    "category": category,
                    "response_time": round(response_time, 2),
                    "has_web_indicators": has_web_indicators,
                    "has_external_sources": has_external_sources,
                    "likely_used_web_search": has_web_indicators or has_external_sources,
                    "answer_length": len(answer),
                    "source_count": len(sources),
                }

                results["time_sensitive_tests"].append(test_result)

                # Evaluate classification
                if test_result["likely_used_web_search"]:
                    correct_classifications += 1
                    print("      ✅ Likely used web search")
                else:
                    print("      ❌ No web search indicators")

            except Exception as e:
                print(f"      ❌ Error: {e}")
                results["time_sensitive_tests"].append(
                    {
                        "query": query,
                        "category": category,
                        "error": str(e),
                        "likely_used_web_search": False,
                    }
                )

        # Test non-time-sensitive queries
        print(f"\n📚 Testing {len(non_time_sensitive_queries)} non-time-sensitive queries...")

        for i, test_case in enumerate(non_time_sensitive_queries, 1):
            query = test_case["query"]
            category = test_case["category"]

            print(f"   {i}. {category}: {query[:50]}...")

            try:
                start_time = time.time()
                result = self.agent.answer_question(query)
                response_time = time.time() - start_time

                answer = result.answer if hasattr(result, "answer") else str(result)
                sources = result.sources if hasattr(result, "sources") else []

                # These should NOT have web search indicators
                web_search_indicators = ["latest", "recent", "current", "today", "news"]

                has_web_indicators = any(
                    indicator in answer.lower() for indicator in web_search_indicators
                )

                has_external_sources = any("http" in str(source) for source in sources)

                test_result = {
                    "query": query,
                    "category": category,
                    "response_time": round(response_time, 2),
                    "has_web_indicators": has_web_indicators,
                    "has_external_sources": has_external_sources,
                    "likely_used_web_search": has_web_indicators or has_external_sources,
                    "answer_length": len(answer),
                    "source_count": len(sources),
                }

                results["non_time_sensitive_tests"].append(test_result)

                # These should NOT use web search
                if not test_result["likely_used_web_search"]:
                    correct_classifications += 1
                    print("      ✅ Used cached/knowledge base")
                else:
                    print("      🟡 May have used web search (unexpected)")

            except Exception as e:
                print(f"      ❌ Error: {e}")
                results["non_time_sensitive_tests"].append(
                    {
                        "query": query,
                        "category": category,
                        "error": str(e),
                        "likely_used_web_search": False,
                    }
                )

        # Calculate accuracy
        results["detection_accuracy"] = (
            correct_classifications / total_tests if total_tests > 0 else 0
        )

        return results

    def test_web_search_integration(self) -> Dict[str, Any]:
        """Test web search integration functionality."""
        print("\n🌐 Testing web search integration...")

        # Use a clearly time-sensitive query
        test_query = "What are the latest updates to Milvus in 2024?"

        try:
            print(f"   Query: {test_query}")

            start_time = time.time()
            result = self.agent.answer_question(test_query)
            response_time = time.time() - start_time

            answer = result.answer if hasattr(result, "answer") else str(result)
            sources = result.sources if hasattr(result, "sources") else []

            # Analyze response for web search characteristics
            web_indicators = ["latest", "2024", "recent", "update", "new"]
            web_indicator_count = sum(
                1 for indicator in web_indicators if indicator in answer.lower()
            )

            # Check response quality
            response_quality = {
                "has_current_info": any(
                    indicator in answer.lower() for indicator in ["2024", "recent", "latest"]
                ),
                "good_length": len(answer) > 100,
                "has_sources": len(sources) > 0,
                "response_time_ok": response_time < 30,  # Web search may be slower
            }

            integration_result = {
                "query": test_query,
                "response_time": round(response_time, 2),
                "response_length": len(answer),
                "web_indicator_count": web_indicator_count,
                "source_count": len(sources),
                "quality_checks": response_quality,
                "integration_working": (
                    response_quality["has_current_info"]
                    and response_quality["good_length"]
                    and web_indicator_count >= 2
                ),
            }

            status = "✅ WORKING" if integration_result["integration_working"] else "❌ ISSUES"
            print(f"   {status} Web search integration")
            print(f"   Response time: {response_time:.2f}s")
            print(f"   Web indicators: {web_indicator_count}/{len(web_indicators)}")
            print(f"   Sources: {len(sources)}")

            return integration_result

        except Exception as e:
            print(f"   ❌ Web search integration error: {e}")
            return {"error": str(e), "integration_working": False}

    def run_full_time_sensitive_test(self) -> Dict[str, Any]:
        """Run complete time-sensitive query test suite."""
        print("=" * 80)
        print("🕐 TIME-SENSITIVE QUERY TEST SUITE")
        print("=" * 80)

        # Run detection tests
        detection_results = self.test_time_sensitive_detection()

        # Run integration tests
        integration_results = self.test_web_search_integration()

        # Compile overall results
        overall_results = {
            "timestamp": datetime.now().isoformat(),
            "detection": detection_results,
            "integration": integration_results,
            "summary": {
                "detection_accuracy": detection_results.get("detection_accuracy", 0),
                "integration_working": integration_results.get("integration_working", False),
                "overall_status": self._determine_overall_status(
                    detection_results, integration_results
                ),
            },
        }

        # Print summary
        print("\n" + "=" * 80)
        print("📊 TIME-SENSITIVE TEST SUMMARY")
        print("=" * 80)

        accuracy = overall_results["summary"]["detection_accuracy"]
        integration_ok = overall_results["summary"]["integration_working"]

        print(f"🎯 Detection Accuracy: {accuracy:.1%}")
        print(f"🌐 Web Search Integration: {'✅ Working' if integration_ok else '❌ Issues'}")

        status = overall_results["summary"]["overall_status"]
        status_icon = {"PASS": "🟢", "WARN": "🟡", "FAIL": "🔴"}[status]
        print(f"\n{status_icon} OVERALL STATUS: {status}")

        if status == "FAIL":
            print("\n🚨 Time-sensitive query handling has serious issues!")
        elif status == "WARN":
            print("\n⚠️ Some issues detected - review recommended")
        else:
            print("\n✅ Time-sensitive query handling working well")

        return overall_results

    def _determine_overall_status(self, detection_results: Dict, integration_results: Dict) -> str:
        """Determine overall test status."""
        accuracy = detection_results.get("detection_accuracy", 0)
        integration_working = integration_results.get("integration_working", False)

        if accuracy < 0.5 or not integration_working:
            return "FAIL"
        elif accuracy < 0.8:
            return "WARN"
        else:
            return "PASS"


def main():
    """Main function with command line support."""
    import argparse

    parser = argparse.ArgumentParser(description="Test time-sensitive query handling")
    parser.add_argument(
        "--component",
        choices=["detection", "integration", "all"],
        default="all",
        help="Which component to test",
    )

    args = parser.parse_args()

    tester = TimeSensitiveQueryTester()

    if args.component == "detection":
        results = tester.test_time_sensitive_detection()
        accuracy = results.get("detection_accuracy", 0)
        print(f"\nResult: {accuracy:.1%} detection accuracy")
        sys.exit(0 if accuracy >= 0.7 else 1)
    elif args.component == "integration":
        results = tester.test_web_search_integration()
        working = results.get("integration_working", False)
        print(f"\nResult: {'PASS' if working else 'FAIL'}")
        sys.exit(0 if working else 1)
    else:
        results = tester.run_full_time_sensitive_test()
        status = results["summary"]["overall_status"]
        sys.exit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
