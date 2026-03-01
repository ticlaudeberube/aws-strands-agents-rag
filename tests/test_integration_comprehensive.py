#!/usr/bin/env python3
"""
Comprehensive Integration Test Suite for AWS Strands Agents RAG

Tests the complete end-to-end flow:
  - Cache validation with entity extraction
  - Force web search (globe icon) feature
  - Source deduplication and formatting
  - Pre-loaded answers and answer cache
  - Cross-product hallucination prevention

Run: python test_integration_comprehensive.py
"""

import requests
import json
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

API_BASE = "http://localhost:8001"
TIMEOUT = 30

@dataclass
class TestResult:
    """Result of a test case."""
    name: str
    passed: bool
    message: str
    elapsed_time: float = 0.0
    details: Optional[Dict[str, Any]] = None


class IntegrationTestSuite:
    """Comprehensive integration test suite."""
    
    def __init__(self):
        self.results = []
        self.total_tests = 0
        self.passed_tests = 0
    
    def api_call(self, question: str, force_web_search: bool = False) -> Dict[str, Any]:
        """Make an API call and return full response."""
        start = time.time()
        response = requests.post(
            f"{API_BASE}/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
                "force_web_search": force_web_search
            },
            timeout=TIMEOUT
        )
        elapsed = time.time() - start
        
        data = response.json()
        return {
            "status": response.status_code,
            "elapsed": elapsed,
            "answer": data.get("choices", [{}])[0].get("message", {}).get("content", ""),
            "sources": data.get("sources", []),
            "full_response": data
        }
    
    def test_1_cache_hit_fast_response(self) -> TestResult:
        """Test that cached queries respond quickly (<1 second)."""
        self.total_tests += 1
        try:
            result = self.api_call("What is Milvus?")
            elapsed = result["elapsed"]
            
            if result["status"] == 200:
                # First call might not be cached, so just check it works
                # Second call should be cached
                result2 = self.api_call("What is Milvus?")
                if result2["elapsed"] < 1.0:
                    self.passed_tests += 1
                    return TestResult(
                        name="Cache Hit - Fast Response",
                        passed=True,
                        message=f"✅ Cached query responded in {result2['elapsed']:.3f}s (expected <1s)",
                        elapsed_time=result2["elapsed"],
                        details={"first_call": elapsed, "cached_call": result2["elapsed"]}
                    )
            
            return TestResult(
                name="Cache Hit - Fast Response",
                passed=False,
                message=f"❌ Response time {result['elapsed']:.3f}s (expected <1s for cached)",
                elapsed_time=result["elapsed"]
            )
        except Exception as e:
            return TestResult(
                name="Cache Hit - Fast Response",
                passed=False,
                message=f"❌ Error: {str(e)}"
            )
    
    def test_2_entity_validation_prevents_hallucination(self) -> TestResult:
        """Test that cache entity validation prevents returning wrong product answers."""
        self.total_tests += 1
        try:
            # Ask about Milvus first
            r1 = self.api_call("What is Milvus?")
            milvus_any = "milvus" in r1["answer"].lower()
            
            time.sleep(0.5)
            
            # Ask about Pinecone - should NOT return cached Milvus answer
            r2 = self.api_call("What is Pinecone?")
            pinecone_any = "pinecone" in r2["answer"].lower()
            milvus_in_pinecone = "milvus" in r2["answer"].lower()
            
            if milvus_any and pinecone_any and not milvus_in_pinecone:
                self.passed_tests += 1
                return TestResult(
                    name="Entity Validation - Prevents Hallucination",
                    passed=True,
                    message="✅ Pinecone query returned Pinecone answer (not cached Milvus)",
                    elapsed_time=r2["elapsed"],
                    details={"has_pinecone": pinecone_any, "has_milvus": milvus_in_pinecone}
                )
            
            return TestResult(
                name="Entity Validation - Prevents Hallucination",
                passed=False,
                message=f"❌ Validation failed: pinecone={pinecone_any}, milvus_in_pinecone={milvus_in_pinecone}",
                details={"answer": r2["answer"][:200]}
            )
        except Exception as e:
            return TestResult(
                name="Entity Validation - Prevents Hallucination",
                passed=False,
                message=f"❌ Error: {str(e)}"
            )
    
    def test_3_force_web_search_returns_sources(self) -> TestResult:
        """Test that force_web_search=true returns web sources."""
        self.total_tests += 1
        try:
            result = self.api_call("What is PostgreSQL?", force_web_search=True)
            sources = result["sources"]
            
            # Should have web sources URLs
            has_urls = all("url" in s for s in sources)
            has_titles = all("title" in s for s in sources)
            web_sources = all(s.get("source_type") == "web_search" for s in sources)
            
            if len(sources) >= 3 and has_urls and has_titles and web_sources:
                self.passed_tests += 1
                return TestResult(
                    name="Force Web Search - Returns Sources",
                    passed=True,
                    message=f"✅ Got {len(sources)} web sources with URLs and titles",
                    elapsed_time=result["elapsed"],
                    details={
                        "sources_count": len(sources),
                        "has_urls": has_urls,
                        "has_titles": has_titles,
                        "web_sources": web_sources
                    }
                )
            
            return TestResult(
                name="Force Web Search - Returns Sources",
                passed=False,
                message=f"❌ Expected ≥3 web sources, got {len(sources)}. has_urls={has_urls}, has_titles={has_titles}, web_sources={web_sources}",
                elapsed_time=result["elapsed"],
                details={"sources": sources}
            )
        except Exception as e:
            return TestResult(
                name="Force Web Search - Returns Sources",
                passed=False,
                message=f"❌ Error: {str(e)}"
            )
    
    def test_4_force_web_search_is_slower(self) -> TestResult:
        """Test that force_web_search is slower than cached responses."""
        self.total_tests += 1
        try:
            # Cached response
            r1 = self.api_call("What is Qdrant?", force_web_search=False)
            cached_time = r1["elapsed"]
            
            time.sleep(1)
            
            # Force web search
            r2 = self.api_call("What is Qdrant?", force_web_search=True)
            web_time = r2["elapsed"]
            
            # Web search should be slower (unless first call wasn't cached)
            if web_time > cached_time:
                self.passed_tests += 1
                return TestResult(
                    name="Force Web Search - Slower than Cache",
                    passed=True,
                    message=f"✅ Web search {web_time:.2f}s > cached {cached_time:.2f}s",
                    elapsed_time=web_time,
                    details={"cached": cached_time, "web_search": web_time}
                )
            
            return TestResult(
                name="Force Web Search - Slower than Cache",
                passed=False,
                message=f"⚠️ Web search {web_time:.2f}s not slower than cached {cached_time:.2f}s (might be first call)",
                elapsed_time=web_time,
                details={"cached": cached_time, "web_search": web_time}
            )
        except Exception as e:
            return TestResult(
                name="Force Web Search - Slower than Cache",
                passed=False,
                message=f"❌ Error: {str(e)}"
            )
    
    def test_5_sources_format_correct(self) -> TestResult:
        """Test that sources have correct format (title, url, snippet, distance)."""
        self.total_tests += 1
        try:
            result = self.api_call("What is Elasticsearch?", force_web_search=True)
            sources = result["sources"]
            
            if not sources:
                return TestResult(
                    name="Sources Format",
                    passed=False,
                    message="❌ No sources returned",
                    elapsed_time=result["elapsed"]
                )
            
            # Check first source has required fields
            first_source = sources[0]
            required_fields = ["source_type", "url", "title"]
            has_all_fields = all(field in first_source for field in required_fields)
            
            if has_all_fields:
                self.passed_tests += 1
                return TestResult(
                    name="Sources Format",
                    passed=True,
                    message=f"✅ Sources have correct format (title, url, source_type, etc)",
                    elapsed_time=result["elapsed"],
                    details={"fields": list(first_source.keys())}
                )
            
            return TestResult(
                name="Sources Format",
                passed=False,
                message=f"❌ Missing required fields. Has: {list(first_source.keys())}",
                details={"first_source": first_source}
            )
        except Exception as e:
            return TestResult(
                name="Sources Format",
                passed=False,
                message=f"❌ Error: {str(e)}"
            )
    
    def test_6_no_snippet_in_response(self) -> TestResult:
        """Test that snippet/text is not shown in GUI (removed in recent update)."""
        self.total_tests += 1
        try:
            result = self.api_call("What is Weaviate?", force_web_search=True)
            sources = result["sources"]
            
            if not sources:
                return TestResult(
                    name="No Snippet in Sources",
                    passed=False,
                    message="❌ No sources to check",
                    elapsed_time=result["elapsed"]
                )
            
            # Check that snippets are NOT included (we removed them)
            # but web search should have url, title, distance
            first_source = sources[0]
            
            # Should NOT have snippet or text fields in web sources
            has_snippet = "snippet" in first_source
            has_text = "text" in first_source
            has_required = all(f in first_source for f in ["url", "title"])
            
            if not has_snippet and not has_text and has_required:
                self.passed_tests += 1
                return TestResult(
                    name="No Snippet in Sources",
                    passed=True,
                    message="✅ Snippet/text removed from sources (URL, title only)",
                    elapsed_time=result["elapsed"],
                    details={"fields": list(first_source.keys())}
                )
            
            return TestResult(
                name="No Snippet in Sources",
                passed=False,
                message=f"❌ Snippet still present: has_snippet={has_snippet}, has_text={has_text}",
                details={"first_source": first_source}
            )
        except Exception as e:
            return TestResult(
                name="No Snippet in Sources",
                passed=False,
                message=f"❌ Error: {str(e)}"
            )
    
    def test_7_api_response_structure(self) -> TestResult:
        """Test that API response has correct structure."""
        self.total_tests += 1
        try:
            result = self.api_call("What is MongoDB?", force_web_search=True)
            response = result["full_response"]
            
            required_top_level = ["choices", "sources", "timing"]
            has_required = all(field in response for field in required_top_level)
            
            has_message = len(response.get("choices", [])) > 0 and "message" in response["choices"][0]
            has_content = response["choices"][0].get("message", {}).get("content", "")
            
            if has_required and has_message and len(has_content) > 10:
                self.passed_tests += 1
                return TestResult(
                    name="API Response Structure",
                    passed=True,
                    message="✅ Response has correct structure (choices, sources, timing)",
                    elapsed_time=result["elapsed"],
                    details={"top_level_keys": list(response.keys())}
                )
            
            return TestResult(
                name="API Response Structure",
                passed=False,
                message=f"❌ Missing required fields: {[k for k in required_top_level if k not in response]}",
                details={"keys": list(response.keys())}
            )
        except Exception as e:
            return TestResult(
                name="API Response Structure",
                passed=False,
                message=f"❌ Error: {str(e)}"
            )
    
    def run_all_tests(self):
        """Run all integration tests."""
        print("\n" + "=" * 80)
        print("COMPREHENSIVE INTEGRATION TEST SUITE")
        print("=" * 80)
        print("\nRunning tests...\n")
        
        # Run all tests
        self.results.append(self.test_1_cache_hit_fast_response())
        time.sleep(1)
        
        self.results.append(self.test_2_entity_validation_prevents_hallucination())
        time.sleep(1)
        
        self.results.append(self.test_3_force_web_search_returns_sources())
        time.sleep(1)
        
        self.results.append(self.test_4_force_web_search_is_slower())
        time.sleep(1)
        
        self.results.append(self.test_5_sources_format_correct())
        time.sleep(1)
        
        self.results.append(self.test_6_no_snippet_in_response())
        time.sleep(1)
        
        self.results.append(self.test_7_api_response_structure())
        
        # Print results
        print("\n" + "=" * 80)
        print("TEST RESULTS")
        print("=" * 80)
        
        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"\n{status} - {result.name}")
            print(f"  Message: {result.message}")
            if result.elapsed_time > 0:
                print(f"  Time: {result.elapsed_time:.2f}s")
            if result.details:
                for key, value in result.details.items():
                    if isinstance(value, (str, int, float, bool)):
                        print(f"  {key}: {value}")
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        self.passed_tests = sum(1 for r in self.results if r.passed)
        print(f"Passed: {self.passed_tests}/{self.total_tests}")
        
        if self.passed_tests == self.total_tests:
            print("\n🎉 ALL TESTS PASSED!")
        else:
            print(f"\n⚠️  {self.total_tests - self.passed_tests} test(s) failed")
        
        print("=" * 80 + "\n")


def main():
    """Run the test suite."""
    suite = IntegrationTestSuite()
    suite.run_all_tests()


if __name__ == "__main__":
    main()
