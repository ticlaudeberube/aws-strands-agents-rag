#!/usr/bin/env python3
"""
Regression Testing: Test Specific Cached Questions Regression Fixes
Good for testing after infrastructure changes.

Use Cases:
- Testing after Milvus updates
- Validating streaming response fixes
- Integration testing
"""

import json
import sys
import time
from typing import Any, Dict, List

try:
    from src.agents.strands_graph_agent import StrandsGraphRAGAgent
    from src.config.settings import get_settings
    from src.tools.milvus_client import MilvusVectorDB
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Run from project root: python scripts/testing/test_regression_fix.py")
    sys.exit(1)


class RegressionTester:
    """Test suite for regression validation."""

    def __init__(self):
        self.agent = StrandsGraphRAGAgent()
        self.settings = get_settings()
        self.results = []

    def test_cached_questions(self) -> List[Dict[str, Any]]:
        """Test known cached questions for regression issues."""

        # Common questions that should be cached
        test_questions = [
            {
                "question": "What is Milvus?",
                "expected_keywords": ["vector", "database", "search", "similarity"],
                "category": "basic_info",
            },
            {
                "question": "How do I create a collection in Milvus?",
                "expected_keywords": ["create", "collection", "schema", "field"],
                "category": "operations",
            },
            {
                "question": "What are vector embeddings?",
                "expected_keywords": ["vector", "embedding", "representation", "numerical"],
                "category": "concepts",
            },
            {
                "question": "How do I search vectors in Milvus?",
                "expected_keywords": ["search", "query", "similarity", "vector"],
                "category": "search",
            },
            {
                "question": "What is the difference between FLAT and IVF_FLAT indexes?",
                "expected_keywords": ["index", "FLAT", "IVF", "performance"],
                "category": "indexing",
            },
        ]

        print("🧪 Testing cached questions for regressions...")

        test_results = []

        for i, test_case in enumerate(test_questions, 1):
            question = test_case["question"]
            expected_keywords = test_case["expected_keywords"]
            category = test_case["category"]

            print(f"\n📝 Test {i}/{len(test_questions)}: {category}")
            print(f"   Question: {question}")

            try:
                # Measure response time
                start_time = time.time()
                result = self.agent.answer_question(question)
                response_time = time.time() - start_time

                # Validate response
                answer = result.answer if hasattr(result, "answer") else str(result)
                sources = result.sources if hasattr(result, "sources") else []

                # Check for expected keywords
                keywords_found = sum(
                    1 for keyword in expected_keywords if keyword.lower() in answer.lower()
                )
                keyword_score = keywords_found / len(expected_keywords)

                # Check response quality
                response_length = len(answer)
                has_sources = len(sources) > 0

                test_result = {
                    "test_id": i,
                    "question": question,
                    "category": category,
                    "response_time": round(response_time, 2),
                    "response_length": response_length,
                    "keyword_score": keyword_score,
                    "keywords_found": keywords_found,
                    "total_keywords": len(expected_keywords),
                    "has_sources": has_sources,
                    "source_count": len(sources),
                    "passed": self._evaluate_test_result(
                        keyword_score, response_length, has_sources
                    ),
                    "answer_preview": answer[:100] + "..." if len(answer) > 100 else answer,
                }

                test_results.append(test_result)

                # Display results
                status = "✅ PASS" if test_result["passed"] else "❌ FAIL"
                print(f"   {status} ({response_time:.2f}s, {response_length} chars)")
                print(
                    f"   Keywords: {keywords_found}/{len(expected_keywords)} ({keyword_score:.1%})"
                )
                print(f"   Sources: {len(sources)}")

                if not test_result["passed"]:
                    print(f"   🔍 Preview: {test_result['answer_preview']}")

            except Exception as e:
                print(f"   ❌ ERROR: {e}")
                test_results.append(
                    {
                        "test_id": i,
                        "question": question,
                        "category": category,
                        "error": str(e),
                        "passed": False,
                    }
                )

        return test_results

    def _evaluate_test_result(
        self, keyword_score: float, response_length: int, has_sources: bool
    ) -> bool:
        """Evaluate if test result meets regression criteria."""
        return (
            keyword_score >= 0.5  # At least 50% keywords found
            and response_length >= 50  # Reasonable response length
            and has_sources  # Should have source attribution
        )

    def test_cache_performance(self) -> Dict[str, Any]:
        """Test cache performance for regression."""
        print("\n🚀 Testing cache performance...")

        # Test question that should be cached
        cached_question = "What is Milvus?"

        # First request (may not be cached)
        start_time = time.time()
        result1 = self.agent.answer_question(cached_question)
        first_response_time = time.time() - start_time

        # Second request (should be cached)
        start_time = time.time()
        result2 = self.agent.answer_question(cached_question)
        second_response_time = time.time() - start_time

        # Check if caching is working (second request should be faster)
        cache_speedup = (
            first_response_time / second_response_time if second_response_time > 0 else 1
        )
        caching_effective = second_response_time < first_response_time * 0.8  # 20% faster

        performance_result = {
            "first_response_time": round(first_response_time, 2),
            "second_response_time": round(second_response_time, 2),
            "cache_speedup": round(cache_speedup, 2),
            "caching_effective": caching_effective,
            "responses_identical": str(result1) == str(result2),
        }

        status = "✅ EFFECTIVE" if caching_effective else "🟡 UNCLEAR"
        print(f"   {status} Cache performance:")
        print(f"   First request: {first_response_time:.2f}s")
        print(f"   Second request: {second_response_time:.2f}s")
        print(f"   Speedup: {cache_speedup:.1f}x")

        return performance_result

    def check_cache_integrity(self) -> Dict[str, Any]:
        """Check cache data integrity."""
        print("\n🔍 Checking cache integrity...")

        try:
            db = MilvusVectorDB(
                host=self.settings.milvus_host,
                port=self.settings.milvus_port,
                db_name=self.settings.milvus_db_name,
            )

            cache_collection = self.settings.response_cache_collection_name

            # Check collection exists
            collections = db.client.list_collections(db_name=self.settings.milvus_db_name)
            if cache_collection not in collections:
                return {"cache_exists": False, "error": "Cache collection not found"}

            # Get cache stats
            stats = db.client.get_collection_stats(
                collection_name=cache_collection, db_name=self.settings.milvus_db_name
            )

            entity_count = stats.get("row_count", 0)

            # Sample some cached responses
            results = db.client.query(
                collection_name=cache_collection,
                db_name=self.settings.milvus_db_name,
                limit=10,
                output_fields=["id", "metadata", "response"],
            )

            # Validate sample data
            valid_responses = 0
            total_response_length = 0

            for result in results:
                response = result.get("response", "")
                metadata = result.get("metadata", "{}")

                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        continue

                if (
                    isinstance(response, str)
                    and len(response) > 10
                    and isinstance(metadata, dict)
                    and "question" in metadata
                ):
                    valid_responses += 1
                    total_response_length += len(response)

            integrity_result = {
                "cache_exists": True,
                "entity_count": entity_count,
                "sample_size": len(results),
                "valid_responses": valid_responses,
                "integrity_score": valid_responses / len(results) if results else 0,
                "avg_response_length": total_response_length / valid_responses
                if valid_responses > 0
                else 0,
            }

            print(f"   ✅ Cache collection: {entity_count} entities")
            print(
                f"   ✅ Data integrity: {valid_responses}/{len(results)} valid ({integrity_result['integrity_score']:.1%})"
            )
            print(f"   ✅ Avg response length: {integrity_result['avg_response_length']:.0f} chars")

            return integrity_result

        except Exception as e:
            print(f"   ❌ Cache integrity check failed: {e}")
            return {"cache_exists": False, "error": str(e)}

    def run_full_regression_test(self) -> Dict[str, Any]:
        """Run complete regression test suite."""
        print("=" * 80)
        print("🔧 REGRESSION TEST SUITE")
        print("=" * 80)

        # Run all test components
        question_results = self.test_cached_questions()
        performance_results = self.test_cache_performance()
        integrity_results = self.check_cache_integrity()

        # Calculate overall results
        passed_tests = sum(1 for result in question_results if result.get("passed", False))
        total_tests = len(question_results)

        overall_results = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "question_tests": {
                "passed": passed_tests,
                "total": total_tests,
                "pass_rate": passed_tests / total_tests if total_tests > 0 else 0,
            },
            "performance": performance_results,
            "integrity": integrity_results,
            "overall_status": self._determine_overall_status(
                passed_tests, total_tests, performance_results, integrity_results
            ),
        }

        # Print summary
        print("\n" + "=" * 80)
        print("📊 REGRESSION TEST SUMMARY")
        print("=" * 80)

        print(
            f"📋 Question Tests: {passed_tests}/{total_tests} passed ({overall_results['question_tests']['pass_rate']:.1%})"
        )
        print(
            f"🚀 Cache Performance: {'✅ Effective' if performance_results.get('caching_effective', False) else '🟡 Unclear'}"
        )
        print(
            f"🔍 Data Integrity: {'✅ Good' if integrity_results.get('integrity_score', 0) > 0.8 else '🟡 Issues'}"
        )

        status_icon = {"PASS": "🟢", "WARN": "🟡", "FAIL": "🔴"}[overall_results["overall_status"]]
        print(f"\n{status_icon} OVERALL STATUS: {overall_results['overall_status']}")

        if overall_results["overall_status"] == "FAIL":
            print("\n🚨 REGRESSION DETECTED - Investigation required!")
        elif overall_results["overall_status"] == "WARN":
            print("\n⚠️ Some issues detected - monitoring recommended")
        else:
            print("\n✅ No regressions detected - system healthy")

        return overall_results

    def _determine_overall_status(
        self,
        passed_tests: int,
        total_tests: int,
        performance_results: Dict,
        integrity_results: Dict,
    ) -> str:
        """Determine overall test status."""
        pass_rate = passed_tests / total_tests if total_tests > 0 else 0

        if pass_rate < 0.5 or not integrity_results.get("cache_exists", False):
            return "FAIL"
        elif pass_rate < 0.8 or not performance_results.get("caching_effective", False):
            return "WARN"
        else:
            return "PASS"


def main():
    """Main function with command line support."""
    import argparse

    parser = argparse.ArgumentParser(description="Run regression tests")
    parser.add_argument(
        "--component",
        choices=["questions", "performance", "integrity", "all"],
        default="all",
        help="Which component to test",
    )

    args = parser.parse_args()

    tester = RegressionTester()

    if args.component == "questions":
        results = tester.test_cached_questions()
        passed = sum(1 for r in results if r.get("passed", False))
        print(f"\nResult: {passed}/{len(results)} tests passed")
    elif args.component == "performance":
        results = tester.test_cache_performance()
        print(f"\nResult: {'PASS' if results.get('caching_effective', False) else 'FAIL'}")
    elif args.component == "integrity":
        results = tester.check_cache_integrity()
        print(f"\nResult: {'PASS' if results.get('cache_exists', False) else 'FAIL'}")
    else:
        results = tester.run_full_regression_test()
        exit_code = 0 if results["overall_status"] == "PASS" else 1
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
