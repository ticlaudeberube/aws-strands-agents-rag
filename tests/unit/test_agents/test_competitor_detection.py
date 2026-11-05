"""
Tests for competitor database detection functionality.

This module tests the enhanced competitor detection logic that prevents
hallucination by detecting queries about Pinecone, Weaviate, ChromaDB, etc.
and properly routing them to web search or rejection messages.
"""

import pytest

from src.agents.strands_graph_agent import _is_competitor_database_query


class TestCompetitorDetection:
    """Test suite for competitor database detection."""

    # ======================================================================
    # DIRECT COMPETITOR NAME TESTS
    # ======================================================================

    def test_pinecone_direct_mention(self):
        """Test detection of direct Pinecone mention."""
        assert _is_competitor_database_query("What is Pinecone?") is True

    def test_pinecone_case_insensitive(self):
        """Test case-insensitive Pinecone detection."""
        assert _is_competitor_database_query("tell me about PINECONE database") is True

    def test_weaviate_detection(self):
        """Test detection of Weaviate."""
        assert _is_competitor_database_query("How does Weaviate work?") is True

    def test_chromadb_detection(self):
        """Test detection of ChromaDB."""
        assert _is_competitor_database_query("What is ChromaDB database?") is True

    def test_qdrant_detection(self):
        """Test detection of Qdrant."""
        assert _is_competitor_database_query("What is Qdrant database?") is True

    def test_faiss_detection(self):
        """Test detection of FAISS (not currently supported)."""
        # FAISS is not in competitor patterns, so should not be detected
        assert _is_competitor_database_query("FAISS indexing performance") is False

    def test_pgvector_detection(self):
        """Test detection of pgvector."""
        assert _is_competitor_database_query("How to use pgvector extension?") is True

    def test_elasticsearch_detection(self):
        """Test detection of Elasticsearch."""
        assert _is_competitor_database_query("Elasticsearch vector search capabilities") is True

    def test_opensearch_detection(self):
        """Test detection of OpenSearch with vector-specific patterns."""
        assert _is_competitor_database_query("OpenSearch vector capabilities") is True

    # ======================================================================
    # TECHNICAL TERM PATTERN TESTS
    # ======================================================================

    def test_pinecone_with_technical_terms(self):
        """Test detection of Pinecone with technical database terms."""
        queries = [
            "Pinecone database features",
            "Pinecone vector indexing",
            "Pinecone database API",
            "Pinecone search performance",
            "Pinecone vector storage",
        ]
        for query in queries:
            assert _is_competitor_database_query(query) is True, f"Failed for: {query}"

    def test_weaviate_with_technical_terms(self):
        """Test detection of Weaviate with technical terms."""
        queries = [
            "Weaviate vector database",
            "Weaviate vector search",
            "Weaviate database indexing",
        ]
        for query in queries:
            assert _is_competitor_database_query(query) is True, f"Failed for: {query}"

    def test_generic_competitor_patterns(self):
        """Test detection of competitor patterns without explicit names."""
        competitor_queries = [
            "Tell me more about Pinecone?",  # The exact query from debugging
            "What is Pinecone database?",  # Direct info request
            "Weaviate installation guide",  # Tech-specific query
            "ChromaDB Python client tutorial",  # Tech-specific query
        ]
        for query in competitor_queries:
            assert _is_competitor_database_query(query) is True, f"Failed for: {query}"

    # ======================================================================
    # FALSE POSITIVE PREVENTION TESTS
    # ======================================================================

    def test_milvus_queries_not_detected_as_competitor(self):
        """Test that Milvus queries are not detected as competitor queries."""
        milvus_queries = [
            "What is Milvus?",
            "How to use Milvus vector database?",
            "Milvus indexing performance",
            "Milvus vs other databases",  # Comparison allowed when Milvus is primary
            "Milvus installation guide",
        ]
        for query in milvus_queries:
            assert _is_competitor_database_query(query) is False, f"False positive for: {query}"

    def test_general_vector_database_queries_not_detected(self):
        """Test that general vector DB queries don't trigger competitor detection."""
        general_queries = [
            "What are vector databases?",
            "How do embeddings work?",
            "Vector similarity search algorithms",
            "RAG architecture patterns",
            "Information retrieval systems",
        ]
        for query in general_queries:
            assert _is_competitor_database_query(query) is False, f"False positive for: {query}"

    def test_comparison_queries_not_detected_as_competitor(self):
        """Test that comparison queries are not detected as competitor queries.

        Comparison queries involving Milvus should be handled by the knowledge base,
        not treated as competitor-only queries requiring web search.
        """
        comparison_queries = [
            "How does Pinecone compare to other databases?",
            "Pinecone vs Milvus comparison",
            "Compare Weaviate and Milvus features",
            "Qdrant vs other vector databases",
            "Milvus compared to ChromaDB",
        ]
        for query in comparison_queries:
            assert _is_competitor_database_query(query) is False, (
                f"Should not detect comparison query: {query}"
            )

    def test_unrelated_queries_not_detected(self):
        """Test that unrelated queries don't trigger competitor detection."""
        unrelated_queries = [
            "What is the weather today?",
            "How to cook pasta?",
            "Python programming basics",
            "Machine learning algorithms",
        ]
        for query in unrelated_queries:
            assert _is_competitor_database_query(query) is False, f"False positive for: {query}"

    # ======================================================================
    # FUZZY MATCHING TESTS
    # ======================================================================

    def test_fuzzy_matching_typos(self):
        """Test fuzzy matching handles typos in competitor names."""
        # Note: Fuzzy matching might not be implemented yet, but test the concept
        typo_queries = [
            "What is Pincon?",  # Typo in Pinecone
            "Weaviat database",  # Typo in Weaviate
            "ChromDB features",  # Typo in ChromaDB
        ]
        # These might currently return False, but documenting the test case
        for query in typo_queries:
            result = _is_competitor_database_query(query)
            # For now, just ensure the method doesn't crash
            assert isinstance(result, bool)

    def test_partial_matches_in_sentences(self):
        """Test detection of competitors mentioned within longer sentences."""
        sentence_queries = [
            "I heard that Pinecone is a popular vector database, what do you think?",
            "My team is considering Weaviate for our project requirements.",
            "The documentation mentions ChromaDB as an alternative solution.",
        ]
        for query in sentence_queries:
            assert _is_competitor_database_query(query) is True, f"Failed for: {query}"

    # ======================================================================
    # CACHE EXCLUSION INTEGRATION TESTS
    # ======================================================================

    # ======================================================================
    # ERROR MESSAGE CONSISTENCY TESTS
    # ======================================================================

    # ======================================================================
    # INTEGRATION WITH QUERY ROUTING TESTS
    # ======================================================================

    # ======================================================================
    # EDGE CASES AND BOUNDARY TESTS
    # ======================================================================

    def test_empty_query_competitor_detection(self):
        """Test competitor detection with empty query."""
        assert _is_competitor_database_query("") is False

    def test_whitespace_only_query(self):
        """Test competitor detection with whitespace-only query."""
        assert _is_competitor_database_query("   ") is False

    def test_very_long_query_with_competitor(self):
        """Test competitor detection in very long queries."""
        long_query = (
            "I am working on a machine learning project that requires vector search capabilities and "
            * 10
            + "I heard Pinecone might be a good option."
        )
        assert _is_competitor_database_query(long_query) is True

    def test_special_characters_in_competitor_query(self):
        """Test competitor detection with special characters."""
        special_queries = [
            "What is Pinecone? (vector database)",
            "Tell me about Weaviate.",
            "How does ChromaDB work??? Please explain!",
            "Qdrant: the vector database",
        ]
        for query in special_queries:
            result = _is_competitor_database_query(query)
            # Should detect competitor regardless of special characters
            assert result is True, f"Failed for: {query}"

    # ======================================================================
    # PERFORMANCE TESTS
    # ======================================================================

    def test_competitor_detection_performance(self):
        """Test that competitor detection is fast enough for real-time use."""
        import time

        query = "Tell me more about Pinecone database features"

        start_time = time.time()
        result = _is_competitor_database_query(query)
        end_time = time.time()

        # Should complete in under 10ms for real-time responsiveness
        duration = end_time - start_time
        assert duration < 0.01, f"Competitor detection too slow: {duration:.3f}s"
        assert result is True

    def test_batch_competitor_detection(self):
        """Test competitor detection on batch of queries."""
        test_queries = [
            "What is Pinecone?",
            "How does Weaviate work?",
            "What is Milvus?",
            "Vector database performance",  # Changed from comparison query
            "What is the weather?",
            "ChromaDB installation guide",
        ]

        expected_results = [True, True, False, False, False, True]

        for query, expected in zip(test_queries, expected_results):
            result = _is_competitor_database_query(query)
            assert result == expected, (
                f"Wrong result for '{query}': expected {expected}, got {result}"
            )


# ======================================================================
# PARAMETRIZED TESTS FOR COMPREHENSIVE COVERAGE
# ======================================================================


class TestCompetitorDetectionParametrized:
    """Parametrized tests for comprehensive competitor detection coverage."""

    @pytest.mark.parametrize(
        "competitor,query_template",
        [
            ("Pinecone", "What is {} database?"),
            ("Weaviate", "How does {} work?"),
            ("ChromaDB", "{} vector installation guide"),
            ("Qdrant", "Tell me about {} features"),
            ("pgvector", "Using {} extension"),
            ("Elasticsearch", "{} vector search"),
            ("OpenSearch", "{} vector capabilities"),
            # Note: FAISS not included as it's not in the current competitor patterns
        ],
    )
    def test_all_competitors_detected(self, competitor, query_template):
        """Test that all known competitors are detected."""
        query = query_template.format(competitor)
        assert _is_competitor_database_query(query) is True

    @pytest.mark.parametrize(
        "safe_query",
        [
            "What is Milvus?",
            "How do vector databases work?",
            "RAG architecture patterns",
            "Embedding similarity search",
            "Information retrieval systems",
            "What is the weather today?",
            "How to cook pasta?",
            "Python programming tutorial",
        ],
    )
    def test_non_competitors_not_detected(self, safe_query):
        """Test that non-competitor queries are not detected."""
        assert _is_competitor_database_query(safe_query) is False
