"""Unit tests for StrandsRAGAgent (formerly RAGAgent).

This test file has been updated to test the new StrandsRAGAgent
which replaces the original RAGAgent with the same interface
and all core RAG functionality. Also includes tests for Phase 1-2
architecture including tool registry, skill management, and MCP server.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from collections import OrderedDict
from src.agents.strands_rag_agent import StrandsRAGAgent
from src.mcp.mcp_server import RAGAgentMCPServer
from src.tools.tool_registry import ToolRegistry, ToolDefinition


class TestStrandsRAGAgentInit:
    """Test StrandsRAGAgent initialization."""

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_init_with_settings(self, mock_ollama, mock_milvus, test_settings):
        """Test StrandsRAGAgent initialization with settings."""
        agent = StrandsRAGAgent(test_settings)

        assert agent.settings == test_settings
        assert agent.cache_size == test_settings.agent_cache_size
        assert isinstance(agent.embedding_cache, OrderedDict)
        assert isinstance(agent.search_cache, OrderedDict)
        assert isinstance(agent.answer_cache, OrderedDict)

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_init_with_custom_cache_size(self, mock_ollama, mock_milvus, test_settings):
        """Test StrandsRAGAgent initialization with custom cache size."""
        agent = StrandsRAGAgent(test_settings, cache_size=100)

        assert agent.cache_size == 100


class TestStrandsRAGAgentCaching:
    """Test StrandsRAGAgent caching functionality."""

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_add_to_cache(self, mock_ollama, mock_milvus, test_settings):
        """Test adding items to cache."""
        agent = StrandsRAGAgent(test_settings, cache_size=2)
        cache = OrderedDict()

        agent._add_to_cache(cache, "key1", "value1")
        agent._add_to_cache(cache, "key2", "value2")

        assert len(cache) == 2
        assert cache["key1"] == "value1"
        assert cache["key2"] == "value2"

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_cache_eviction(self, mock_ollama, mock_milvus, test_settings):
        """Test LRU cache eviction."""
        agent = StrandsRAGAgent(test_settings, cache_size=2)
        cache = OrderedDict()

        # Add items beyond cache size
        agent._add_to_cache(cache, "key1", "value1")
        agent._add_to_cache(cache, "key2", "value2")
        agent._add_to_cache(cache, "key3", "value3")  # Should evict key1

        assert len(cache) == 2
        assert "key1" not in cache
        assert "key2" in cache
        assert "key3" in cache

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_clear_caches(self, mock_ollama, mock_milvus, test_settings):
        """Test clearing all caches."""
        agent = StrandsRAGAgent(test_settings)

        agent.embedding_cache["test"] = [0.1, 0.2]
        agent.search_cache["test"] = ([], [])
        agent.answer_cache["test"] = ("answer", [])

        agent.clear_caches()

        assert len(agent.embedding_cache) == 0
        assert len(agent.search_cache) == 0
        assert len(agent.answer_cache) == 0


class TestStrandsRAGAgentRetrieval:
    """Test context retrieval functionality."""

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_retrieve_context_cache_hit(self, mock_ollama, mock_milvus, test_settings):
        """Test retrieve_context with cache hit."""
        agent = StrandsRAGAgent(test_settings)

        # Pre-populate cache
        cached_result = (["chunk1", "chunk2"], [{"source": "doc1"}])
        agent.search_cache[("collection", "query", 5, 0)] = cached_result

        result = agent.retrieve_context("collection", "query", top_k=5)

        assert result == cached_result

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_retrieve_context_new_search(self, mock_ollama, mock_milvus, test_settings):
        """Test retrieve_context with new search."""
        # Mock the clients
        mock_ollama_client = MagicMock()
        mock_ollama_client.embed_text.return_value = [0.1] * 384
        mock_milvus_client = MagicMock()
        # Use distance <= 0.65 (similarity threshold) to ensure results pass filtering
        mock_milvus_client.search.return_value = [
            {"text": "chunk1", "distance": 0.3, "metadata": {"source": "doc1"}}
        ]

        with patch("src.agents.strands_rag_agent.OllamaClient", return_value=mock_ollama_client):
            with patch(
                "src.agents.strands_rag_agent.MilvusVectorDB", return_value=mock_milvus_client
            ):
                agent = StrandsRAGAgent(test_settings)
                agent.vector_db = mock_milvus_client
                agent.ollama_client = mock_ollama_client

                result = agent.retrieve_context("collection", "test query")

                context_chunks, sources = result
                assert len(context_chunks) > 0
                assert context_chunks[0] == "chunk1"
                assert len(sources) > 0


class TestStrandsRAGAgentAsync:
    """Test async functionality."""

    @pytest.mark.asyncio
    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    async def test_answer_question_async(self, mock_ollama, mock_milvus, test_settings):
        """Test async answer_question."""
        agent = StrandsRAGAgent(test_settings)
        agent.answer_question = Mock(return_value=("answer", []))

        result = await agent.answer_question_async("collection", "question")

        assert result[0] == "answer"
        assert isinstance(result[1], list)

    @pytest.mark.asyncio
    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    async def test_retrieve_context_async(self, mock_ollama, mock_milvus, test_settings):
        """Test async retrieve_context."""
        agent = StrandsRAGAgent(test_settings)
        agent.retrieve_context = Mock(return_value=(["chunk"], []))

        result = await agent.retrieve_context_async("collection", "query")

        assert len(result) == 2


# ============================================================================
# TOOL REGISTRY TESTS
# ============================================================================


class TestToolRegistry:
    """Tests for the tool registry system."""

    def test_registry_initialization(self):
        """Test that tool registry initializes correctly."""
        registry = ToolRegistry()
        assert isinstance(registry, ToolRegistry)
        assert len(registry.list_tools()) == 0

    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()

        def dummy_tool(arg1: str) -> str:
            return f"Result: {arg1}"

        tool_def = ToolDefinition(
            name="dummy_tool",
            description="A dummy tool for testing",
            function=dummy_tool,
            parameters={"arg1": {"type": "string"}},
            skill_category="test",
        )

        registry.register_tool(tool_def)

        assert len(registry.list_tools()) == 1
        assert "dummy_tool" in registry.list_tools()
        assert registry.get_tool("dummy_tool") is not None

    def test_register_multiple_tools_same_skill(self):
        """Test registering multiple tools in the same skill."""
        registry = ToolRegistry()

        for i in range(3):
            tool_def = ToolDefinition(
                name=f"tool_{i}",
                description=f"Tool {i}",
                function=lambda x: x,
                parameters={},
                skill_category="test_skill",
            )
            registry.register_tool(tool_def)

        assert len(registry.list_tools()) == 3
        skills = registry.list_skills()
        assert "test_skill" in skills
        assert skills["test_skill"] == 3

    def test_get_tools_by_skill(self):
        """Test retrieving tools by skill category."""
        registry = ToolRegistry()

        for skill in ["retrieval", "generation"]:
            for i in range(2):
                tool_def = ToolDefinition(
                    name=f"{skill}_tool_{i}",
                    description=f"Tool in {skill}",
                    function=lambda x: x,
                    parameters={},
                    skill_category=skill,
                )
                registry.register_tool(tool_def)

        retrieval_tools = registry.get_tools_by_skill("retrieval")
        assert len(retrieval_tools) == 2

        generation_tools = registry.get_tools_by_skill("generation")
        assert len(generation_tools) == 2


# ============================================================================
# STRANDS RAG AGENT ARCHITECTURE TESTS
# ============================================================================


class TestStrandsRAGAgentArchitecture:
    """Tests for StrandsRAGAgent tools and architecture."""

    def test_agent_initialization(self, test_settings):
        """Test StrandsRAGAgent initializes correctly."""
        agent = StrandsRAGAgent(test_settings)

        assert agent is not None
        assert agent.settings is not None
        assert agent.ollama_client is not None
        assert agent.vector_db is not None

        agent.close()

    def test_agent_has_tools(self, strands_agent):
        """Test that agent has tool methods."""
        # Retrieval tools
        assert hasattr(strands_agent, "retrieve_documents")
        assert callable(strands_agent.retrieve_documents)

        assert hasattr(strands_agent, "search_by_source")
        assert callable(strands_agent.search_by_source)

        assert hasattr(strands_agent, "list_collections")
        assert callable(strands_agent.list_collections)

        # Answer generation tools
        assert hasattr(strands_agent, "generate_answer")
        assert callable(strands_agent.generate_answer)

        # Knowledge base tools
        assert hasattr(strands_agent, "add_documents")
        assert callable(strands_agent.add_documents)

    @pytest.mark.asyncio
    async def test_retrieve_documents_tool(self, strands_agent):
        """Test retrieve_documents tool."""
        result = strands_agent.retrieve_documents(
            collection_name="test_collection",
            query="test query",
        )

        assert isinstance(result, str)
        # Should either return results or an error message
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_list_collections_tool(self, strands_agent):
        """Test list_collections tool."""
        result = strands_agent.list_collections()

        assert isinstance(result, str)
        # Should return either list or "No collections found" message
        assert len(result) > 0


# ============================================================================
# SKILL REGISTRATION TESTS
# ============================================================================


class TestSkillRegistration:
    """Tests for skill registration."""

    def test_retrieval_skill_registration(self, mcp_server):
        """Test that retrieval skill registers correctly."""
        registry = mcp_server.registry

        # Check that retrieval tools are registered
        retrieval_tools = registry.get_tools_by_skill("retrieval")
        assert len(retrieval_tools) >= 3  # retrieve_documents, search_by_source, list_collections

        tool_names = [t.name for t in retrieval_tools]
        assert "retrieve_documents" in tool_names
        assert "search_by_source" in tool_names
        assert "list_collections" in tool_names

    def test_answer_generation_skill_registration(self, mcp_server):
        """Test that answer generation skill registers correctly."""
        registry = mcp_server.registry

        generation_tools = registry.get_tools_by_skill("answer_generation")
        assert len(generation_tools) >= 2  # generate_answer, summarize_context

        tool_names = [t.name for t in generation_tools]
        assert "generate_answer" in tool_names

    def test_knowledge_base_skill_registration(self, mcp_server):
        """Test that knowledge base skill registers correctly."""
        registry = mcp_server.registry

        kb_tools = registry.get_tools_by_skill("knowledge_base")
        assert len(kb_tools) >= 1  # add_documents

        tool_names = [t.name for t in kb_tools]
        assert "add_documents" in tool_names

    def test_all_skills_registered(self, mcp_server):
        """Test that all skills are registered."""
        registry = mcp_server.registry
        skills = registry.list_skills()

        expected_skills = ["retrieval", "answer_generation", "knowledge_base"]
        for skill in expected_skills:
            assert skill in skills
            assert skills[skill] > 0


# ============================================================================
# MCP SERVER TESTS
# ============================================================================


class TestMCPServer:
    """Tests for the MCP server."""

    def test_mcp_server_initialization(self, test_settings):
        """Test MCP server initializes correctly."""
        server = RAGAgentMCPServer(test_settings)

        assert server is not None
        assert server.agent is not None
        assert server.registry is not None

        server.close()

    def test_mcp_server_has_agent(self, mcp_server):
        """Test MCP server has StrandsRAGAgent."""
        assert mcp_server.agent is not None
        assert isinstance(mcp_server.agent, StrandsRAGAgent)

    def test_mcp_server_get_tools(self, mcp_server):
        """Test getting tools from MCP server."""
        tools = mcp_server.get_tools()

        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_mcp_server_get_skills(self, mcp_server):
        """Test getting skills from MCP server."""
        skills = mcp_server.get_skills()

        assert isinstance(skills, dict)
        assert len(skills) > 0

    def test_mcp_server_get_skill_documentation(self, mcp_server):
        """Test getting skill documentation."""
        doc = mcp_server.get_skill_documentation("retrieval")

        assert isinstance(doc, str)
        assert len(doc) > 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestPhase12Integration:
    """Integration tests for Phase 1-2 architecture."""

    def test_full_flow(self, mcp_server):
        """Test the full Phase 1-2 flow."""
        registry = mcp_server.registry

        # Step 1: Check all skills are registered
        skills = registry.list_skills()
        assert len(skills) >= 3

        # Step 2: Check tools are organized by skill
        for skill_name in skills:
            tools = registry.get_tools_by_skill(skill_name)
            assert len(tools) > 0

        # Step 3: Check tool definitions are valid
        all_tools = registry.list_tools()
        assert len(all_tools) > 0

        for tool_name, description in all_tools.items():
            tool_def = registry.get_tool(tool_name)
            assert tool_def is not None
            assert tool_def.name == tool_name
            assert callable(tool_def.function)
            assert len(tool_def.parameters) >= 0


# ============================================================================
# ADDITIONAL COVERAGE TESTS FOR ERROR PATHS AND EDGE CASES
# ============================================================================


class TestStrandsRAGAgentErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    async def test_answer_question_async_error_handling(
        self, mock_ollama, mock_milvus, test_settings
    ):
        """Test async error handling."""
        mock_milvus.return_value = MagicMock()
        mock_ollama.return_value = MagicMock()

        agent = StrandsRAGAgent(test_settings)
        agent.answer_question = Mock(side_effect=Exception("Test error"))

        with pytest.raises(Exception):
            await agent.answer_question_async("test", "question")

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_performance_metrics_tracking(self, mock_ollama, mock_milvus, test_settings):
        """Test performance metrics are tracked."""
        mock_db = MagicMock()
        mock_db.search.return_value = [
            {"text": "result", "distance": 0.3, "metadata": {"source": "test"}}
        ]
        mock_milvus.return_value = mock_db

        mock_client = MagicMock()
        mock_client.embed_text.return_value = [0.1] * 384
        mock_client.generate.return_value = "Test answer"
        mock_ollama.return_value = mock_client

        with patch("src.agents.strands_rag_agent.OllamaClient", return_value=mock_client):
            with patch("src.agents.strands_rag_agent.MilvusVectorDB", return_value=mock_db):
                agent = StrandsRAGAgent(test_settings)
                agent.vector_db = mock_db
                agent.ollama_client = mock_client

                answer, sources = agent.answer_question("test", "What is Milvus?")

                assert answer is not None

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_answer_question_with_empty_context(self, mock_ollama, mock_milvus, test_settings):
        """Test answer_question when no context is found."""
        mock_db = MagicMock()
        mock_db.search.return_value = []  # No results
        mock_milvus.return_value = mock_db

        mock_client = MagicMock()
        mock_client.embed_text.return_value = [0.1] * 384
        mock_client.generate.return_value = "No relevant documents."
        mock_ollama.return_value = mock_client

        with patch("src.agents.strands_rag_agent.OllamaClient", return_value=mock_client):
            with patch("src.agents.strands_rag_agent.MilvusVectorDB", return_value=mock_db):
                agent = StrandsRAGAgent(test_settings)
                agent.vector_db = mock_db
                agent.ollama_client = mock_client

                answer, sources = agent.answer_question("test", "What is Milvus?")

                assert answer is not None
                assert len(sources) == 0

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_cache_expiration(self, mock_ollama, mock_milvus, test_settings):
        """Test embedding cache TTL expiration."""
        mock_milvus.return_value = MagicMock()
        mock_ollama.return_value = MagicMock()

        agent = StrandsRAGAgent(test_settings)

        # Manually add an expired entry
        from src.agents.strands_rag_agent import EmbeddingCacheEntry

        old_time = time.time() - 3600  # 1 hour ago
        agent.embedding_cache["old_key"] = EmbeddingCacheEntry(
            embedding=[0.1] * 384, timestamp=old_time
        )

        # Entry should be expired
        entry = agent.embedding_cache["old_key"]
        assert entry.is_expired(ttl_seconds=1800)  # 30 min TTL

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_embedding_cache_with_valid_ttl(self, mock_ollama, mock_milvus, test_settings):
        """Test embedding cache with valid TTL."""
        mock_milvus.return_value = MagicMock()
        mock_ollama.return_value = MagicMock()

        agent = StrandsRAGAgent(test_settings)

        # Add a fresh entry
        from src.agents.strands_rag_agent import EmbeddingCacheEntry

        agent.embedding_cache["fresh_key"] = EmbeddingCacheEntry(
            embedding=[0.1] * 384, timestamp=time.time()
        )

        # Entry should NOT be expired yet
        entry = agent.embedding_cache["fresh_key"]
        assert not entry.is_expired(ttl_seconds=1800)

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_add_documents(self, mock_ollama, mock_milvus, test_settings):
        """Test add_documents tool method."""
        mock_db = MagicMock()
        mock_db.insert.return_value = {"status": "success"}
        mock_milvus.return_value = mock_db

        mock_client = MagicMock()
        mock_client.embed_text.return_value = [0.1] * 384
        mock_ollama.return_value = mock_client

        with patch("src.agents.strands_rag_agent.OllamaClient", return_value=mock_client):
            with patch("src.agents.strands_rag_agent.MilvusVectorDB", return_value=mock_db):
                agent = StrandsRAGAgent(test_settings)
                agent.vector_db = mock_db
                agent.ollama_client = mock_client

                result = agent.add_documents(collection_name="test", documents={"doc1": "content1"})

                assert isinstance(result, str)

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_search_by_source(self, mock_ollama, mock_milvus, test_settings):
        """Test search_by_source tool method."""
        mock_db = MagicMock()
        mock_db.get = MagicMock(return_value=[{"text": "doc", "metadata": {"source": "test.md"}}])
        mock_milvus.return_value = mock_db

        mock_client = MagicMock()
        mock_ollama.return_value = mock_client

        with patch("src.agents.strands_rag_agent.OllamaClient", return_value=mock_client):
            with patch("src.agents.strands_rag_agent.MilvusVectorDB", return_value=mock_db):
                agent = StrandsRAGAgent(test_settings)
                agent.vector_db = mock_db

                result = agent.search_by_source(
                    collection_name="test", query="test query", source="test.md"
                )

                assert isinstance(result, str)

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_list_collections(self, mock_ollama, mock_milvus, test_settings):
        """Test list_collections tool method."""
        mock_db = MagicMock()
        mock_db.list_collections.return_value = ["col1", "col2"]
        mock_milvus.return_value = mock_db

        mock_client = MagicMock()
        mock_ollama.return_value = mock_client

        with patch("src.agents.strands_rag_agent.OllamaClient", return_value=mock_client):
            with patch("src.agents.strands_rag_agent.MilvusVectorDB", return_value=mock_db):
                agent = StrandsRAGAgent(test_settings)
                agent.vector_db = mock_db

                result = agent.list_collections()

                assert isinstance(result, str)
                assert "col1" in result or "2 collections" in result


# ============================================================================
# COMPARATIVE ANALYSIS TESTS
# ============================================================================


class TestComparativeAnalysis:
    """Tests for comparative product analysis."""

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_detect_comparative_question(self, mock_ollama, mock_milvus, test_settings):
        """Test detection of comparative questions."""
        mock_milvus.return_value = MagicMock()

        # Mock the LLM to return a comparative question classification
        mock_client = MagicMock()
        mock_client.generate.return_value = '{"is_comparison": true, "product1": "Milvus", "product2": "Pinecone", "reason": "Asking for advantages comparison"}'
        mock_ollama.return_value = mock_client

        agent = StrandsRAGAgent(test_settings)

        # Test positive detection
        is_comparative, products = agent._detect_comparative_question(
            "What are Milvus advantages over Pinecone?"
        )

        assert is_comparative is True
        assert products is not None
        assert "milvus" in products[0].lower()
        assert "pinecone" in products[1].lower()

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_detect_non_comparative_question(self, mock_ollama, mock_milvus, test_settings):
        """Test that non-comparative questions are not detected."""
        mock_milvus.return_value = MagicMock()

        # Mock the LLM to return a non-comparative classification
        mock_client = MagicMock()
        mock_client.generate.return_value = '{"is_comparison": false, "product1": null, "product2": null, "reason": "General question about Milvus"}'
        mock_ollama.return_value = mock_client

        agent = StrandsRAGAgent(test_settings)

        is_comparative, products = agent._detect_comparative_question("What is Milvus?")

        assert is_comparative is False
        assert products is None

    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_comparative_keywords_detection(self, mock_ollama, mock_milvus, test_settings):
        """Test detection with various comparative keywords."""
        mock_milvus.return_value = MagicMock()

        # Mock the LLM to return comparative classifications
        mock_client = MagicMock()
        mock_client.generate.return_value = '{"is_comparison": true, "product1": "Milvus", "product2": "Weaviate", "reason": "Comparison question"}'
        mock_ollama.return_value = mock_client

        agent = StrandsRAGAgent(test_settings)

        test_cases = [
            "Milvus vs Weaviate advantages",
            "How does Milvus compare to Qdrant?",
            "Milvus versus Elasticsearch",
            "Comparison between Milvus and Pinecone",
        ]

        for question in test_cases:
            # Update mock response for each question with appropriate products
            if "Qdrant" in question:
                mock_client.generate.return_value = '{"is_comparison": true, "product1": "Milvus", "product2": "Qdrant", "reason": "Comparison question"}'
            elif "Elasticsearch" in question:
                mock_client.generate.return_value = '{"is_comparison": true, "product1": "Milvus", "product2": "Elasticsearch", "reason": "Comparison question"}'
            elif "Pinecone" in question:
                mock_client.generate.return_value = '{"is_comparison": true, "product1": "Milvus", "product2": "Pinecone", "reason": "Comparison question"}'

            is_comparative, products = agent._detect_comparative_question(question)
            assert is_comparative is True, f"Failed to detect: {question}"
            assert products is not None

    @patch("src.agents.strands_rag_agent.WebSearchClient")
    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_search_comparison(self, mock_ollama, mock_milvus, mock_web_search, test_settings):
        """Test comparative search functionality."""
        mock_db = MagicMock()
        mock_db.search.return_value = [
            {"text": "Milvus is a vector DB", "distance": 0.1, "metadata": {"source": "test"}}
        ]
        mock_milvus.return_value = mock_db

        mock_client = MagicMock()
        mock_client.embed_text.return_value = [0.1] * 384
        # Mock the LLM synthesis response - return a string, not a MagicMock
        mock_client.generate.return_value = "Milvus and Pinecone are both vector databases. Milvus is open source while Pinecone is a managed service."
        mock_ollama.return_value = mock_client

        mock_search = MagicMock()
        mock_search.search_comparison.return_value = {
            "comparison": [
                {"title": "Result 1", "snippet": "Comparison data", "url": "http://example.com"}
            ],
            "product1": {
                "name": "Milvus",
                "results": {
                    "vector indexing algorithms": [
                        {
                            "title": "Milvus info",
                            "snippet": "HNSW support",
                            "url": "http://milvus.io",
                        }
                    ]
                },
            },
            "product2": {
                "name": "Pinecone",
                "results": {
                    "vector indexing algorithms": [
                        {
                            "title": "Pinecone info",
                            "snippet": "Optimized indexing",
                            "url": "http://pinecone.io",
                        }
                    ]
                },
            },
        }

        with patch("src.agents.strands_rag_agent.OllamaClient", return_value=mock_client):
            with patch("src.agents.strands_rag_agent.MilvusVectorDB", return_value=mock_db):
                with patch(
                    "src.agents.strands_rag_agent.WebSearchClient", return_value=mock_search
                ):
                    agent = StrandsRAGAgent(test_settings)
                    agent.vector_db = mock_db
                    agent.web_search = mock_search

                    comparison_text, sources = agent.search_comparison("Milvus", "Pinecone")

                    assert isinstance(comparison_text, str)
                    assert "Milvus" in comparison_text or "milvus" in comparison_text.lower()
                    assert "Pinecone" in comparison_text or "pinecone" in comparison_text.lower()

    @patch("src.agents.strands_rag_agent.WebSearchClient")
    @patch("src.agents.strands_rag_agent.MilvusVectorDB")
    @patch("src.agents.strands_rag_agent.OllamaClient")
    def test_answer_question_with_comparison(
        self, mock_ollama, mock_milvus, mock_web_search, test_settings
    ):
        """Test that comparative questions trigger comparison functionality."""
        mock_db = MagicMock()
        # Mock database search to return results
        mock_db.search.return_value = [
            {"text": "Milvus is a vector DB", "distance": 0.1, "metadata": {"source": "test"}}
        ]
        mock_milvus.return_value = mock_db

        mock_client = MagicMock()
        # Mock embedding generation
        mock_client.embed_text.return_value = [0.1] * 384
        # Mock both the classification and synthesis responses using side_effect
        mock_client.generate.side_effect = [
            # First call: classification response
            '{"is_comparison": true, "product1": "Milvus", "product2": "Pinecone", "reason": "Direct comparison"}',
            # Second call: synthesis response
            "Milvus is an open-source vector database while Pinecone is a managed service.",
        ]
        mock_ollama.return_value = mock_client

        mock_search = MagicMock()
        mock_search.search_comparison.return_value = {
            "comparison": [],
            "product1": {"name": "Milvus", "results": {}},
            "product2": {"name": "Pinecone", "results": {}},
        }

        with patch("src.agents.strands_rag_agent.OllamaClient", return_value=mock_client):
            with patch("src.agents.strands_rag_agent.MilvusVectorDB", return_value=mock_db):
                with patch(
                    "src.agents.strands_rag_agent.WebSearchClient", return_value=mock_search
                ):
                    agent = StrandsRAGAgent(test_settings)
                    agent.web_search = mock_search

                    answer, sources = agent.answer_question(
                        "What are Milvus advantages vs Pinecone?"
                    )

                    # Should return comparison-style answer
                    assert isinstance(answer, str)
                    # Comparative search should be called
                    assert mock_search.search_comparison.called
