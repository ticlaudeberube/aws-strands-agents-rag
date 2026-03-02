#!/usr/bin/env python3
"""Test suite for LLM-based comparative question detection.

Tests the modern LLM classification approach used in production.
Removed legacy regex-based pattern matching (no longer used).
"""

import sys
import os
import json
from unittest.mock import MagicMock, patch
from src.config.settings import Settings


# Add workspace to path
sys.path.insert(0, "/Users/claude/Documents/workspace/aws-strands-agents-rag")

# Set minimal environment
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# ============================================================================
# PART 1: Agent-Based Detection with LLM Mocking
# ============================================================================


def test_agent_llm_classification():
    """Test detection using the actual StrandsRAGAgent."""

    with (
        patch("src.agents.strands_rag_agent.MilvusVectorDB"),
        patch("src.agents.strands_rag_agent.WebSearchClient"),
    ):
        # Create a mock OllamaClient that returns proper JSON responses
        mock_ollama_class = MagicMock()
        mock_ollama_instance = MagicMock()
        mock_ollama_class.return_value = mock_ollama_instance

        with patch("src.agents.strands_rag_agent.OllamaClient", mock_ollama_class):
            from src.agents.strands_rag_agent import StrandsRAGAgent

            settings = Settings()
            agent = StrandsRAGAgent(settings=settings)

            test_cases = [
                ("What are Milvus advantages over Pinecone?", True),
                ("How does Milvus compare to Qdrant?", True),
                ("Milvus vs Weaviate advantages", True),
                ("Milvus versus Elasticsearch", True),
                ("Comparison between Milvus and Pinecone", True),
                ("What is Milvus?", False),
                ("Tell me about vector databases", False),
            ]

            print("\n" + "=" * 70)
            print("PART 1: AGENT-BASED DETECTION WITH LLM CLASSIFICATION")
            print("=" * 70 + "\n")

            passed = 0
            failed = 0

            for question, expected in test_cases:
                # Set up the mock to return appropriate JSON responses
                if expected:
                    # Return a comparative classification
                    mock_ollama_instance.generate_text.return_value = json.dumps(
                        {
                            "is_comparison": True,
                            "product1": "Product1",
                            "product2": "Product2",
                            "reason": "Asking for comparison",
                        }
                    )
                else:
                    # Return a non-comparative classification
                    mock_ollama_instance.generate_text.return_value = json.dumps(
                        {
                            "is_comparison": False,
                            "product1": None,
                            "product2": None,
                            "reason": "General question",
                        }
                    )

                is_comp, products = agent._detect_comparative_question(question)
                status = "✓ PASS" if is_comp == expected else "✗ FAIL"

                if is_comp == expected:
                    passed += 1
                else:
                    failed += 1

                print(f"{status}")
                print(f"  Question: {question}")
                print(f"  Expected: {expected}, Got: {is_comp}, Products: {products}")
                print()

            print("=" * 70)
            print(f"PART 1 RESULTS: {passed} passed, {failed} failed")
            print("=" * 70 + "\n")

            return failed == 0


# ============================================================================
# PART 2: LLM-Based Classification (Production Implementation)
# ============================================================================


def test_llm_classification():
    """Test LLM-based comparative question classification."""

    with (
        patch("src.agents.strands_rag_agent.MilvusVectorDB"),
        patch("src.agents.strands_rag_agent.WebSearchClient"),
    ):
        # Create a mock OllamaClient that simulates responses
        mock_ollama_class = MagicMock()
        mock_ollama_instance = MagicMock()
        mock_ollama_class.return_value = mock_ollama_instance

        with patch("src.agents.strands_rag_agent.OllamaClient", mock_ollama_class):
            from src.agents.strands_rag_agent import StrandsRAGAgent

            settings = Settings()
            agent = StrandsRAGAgent(settings=settings)

            # Define test cases with expected LLM responses
            test_cases = [
                {
                    "question": "What are Milvus advantages over Pinecone?",
                    "expected_comparative": True,
                    "llm_response": json.dumps(
                        {
                            "is_comparison": True,
                            "product1": "Milvus",
                            "product2": "Pinecone",
                            "reason": "Asking for comparison of advantages",
                        }
                    ),
                },
                {
                    "question": "How does Milvus compare to Qdrant?",
                    "expected_comparative": True,
                    "llm_response": json.dumps(
                        {
                            "is_comparison": True,
                            "product1": "Milvus",
                            "product2": "Qdrant",
                            "reason": "Asking for direct comparison",
                        }
                    ),
                },
                {
                    "question": "What is Milvus?",
                    "expected_comparative": False,
                    "llm_response": json.dumps(
                        {
                            "is_comparison": False,
                            "product1": None,
                            "product2": None,
                            "reason": "General question about Milvus",
                        }
                    ),
                },
                {
                    "question": "Explain how vector databases work",
                    "expected_comparative": False,
                    "llm_response": json.dumps(
                        {
                            "is_comparison": False,
                            "product1": None,
                            "product2": None,
                            "reason": "General explanation question",
                        }
                    ),
                },
            ]

            print("\n" + "=" * 70)
            print("PART 2: LLM-BASED CLASSIFICATION (PRODUCTION)")
            print("=" * 70 + "\n")

            passed = 0
            failed = 0

            for test in test_cases:
                question = test["question"]
                expected = test["expected_comparative"]
                llm_response = test["llm_response"]

                # Mock the LLM response
                mock_ollama_instance.generate_text.return_value = llm_response

                # Call detection
                is_comp, products = agent._detect_comparative_question(question)

                # Check result
                test_passed = is_comp == expected

                if test_passed:
                    passed += 1
                    status = "✓ PASS"
                else:
                    failed += 1
                    status = "✗ FAIL"

                print(f"{status}")
                print(f"  Question: {question}")
                print(f"  Expected: comparative={expected}")
                print(f"  Got:      comparative={is_comp}, products={products}")
                print()

            print("=" * 70)
            print(f"PART 2 RESULTS: {passed} passed, {failed} failed")
            print("=" * 70 + "\n")

            return failed == 0


# ============================================================================
# Main execution
# ============================================================================


def main():
    """Run all test suites."""
    print("\n" + "=" * 70)
    print("LLM-BASED COMPARATIVE QUESTION DETECTION TEST SUITE")
    print("=" * 70)

    results = {
        "Part 1 (Agent with Mocks)": test_agent_llm_classification(),
        "Part 2 (LLM Classification)": test_llm_classification(),
    }

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70 + "\n")

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())

    print("\n" + "=" * 70)
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print("=" * 70 + "\n")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        print("=" * 70 + "\n")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
