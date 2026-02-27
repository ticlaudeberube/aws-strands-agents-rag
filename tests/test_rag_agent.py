"""Unit tests for StrandsRAGAgent (formerly RAGAgent).

This test file has been updated to test the new StrandsRAGAgent
which replaces the original RAGAgent with the same interface
and all core RAG functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from collections import OrderedDict
from src.agents.strands_rag_agent import StrandsRAGAgent


class TestStrandsRAGAgentInit:
    """Test StrandsRAGAgent initialization."""
    
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
    def test_init_with_settings(self, mock_ollama, mock_milvus, test_settings):
        """Test StrandsRAGAgent initialization with settings."""
        agent = StrandsRAGAgent(test_settings)
        
        assert agent.settings == test_settings
        assert agent.cache_size == test_settings.agent_cache_size
        assert isinstance(agent.embedding_cache, OrderedDict)
        assert isinstance(agent.search_cache, OrderedDict)
        assert isinstance(agent.answer_cache, OrderedDict)
    
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
    def test_init_with_custom_cache_size(self, mock_ollama, mock_milvus, test_settings):
        """Test StrandsRAGAgent initialization with custom cache size."""
        agent = StrandsRAGAgent(test_settings, cache_size=100)
        
        assert agent.cache_size == 100


class TestStrandsRAGAgentCaching:
    """Test StrandsRAGAgent caching functionality."""
    
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
    def test_add_to_cache(self, mock_ollama, mock_milvus, test_settings):
        """Test adding items to cache."""
        agent = StrandsRAGAgent(test_settings, cache_size=2)
        cache = OrderedDict()
        
        agent._add_to_cache(cache, "key1", "value1")
        agent._add_to_cache(cache, "key2", "value2")
        
        assert len(cache) == 2
        assert cache["key1"] == "value1"
        assert cache["key2"] == "value2"
    
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
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
    
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
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
    
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
    def test_retrieve_context_cache_hit(self, mock_ollama, mock_milvus, test_settings):
        """Test retrieve_context with cache hit."""
        agent = StrandsRAGAgent(test_settings)
        
        # Pre-populate cache
        cached_result = (["chunk1", "chunk2"], [{"source": "doc1"}])
        agent.search_cache[("collection", "query", 5, 0)] = cached_result
        
        result = agent.retrieve_context("collection", "query", top_k=5)
        
        assert result == cached_result
    
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
    def test_retrieve_context_new_search(self, mock_ollama, mock_milvus, test_settings):
        """Test retrieve_context with new search."""
        # Mock the clients
        mock_ollama_client = MagicMock()
        mock_ollama_client.embed_text.return_value = [0.1] * 384
        mock_milvus_client = MagicMock()
        mock_milvus_client.search.return_value = [
            {"text": "chunk1", "distance": 0.9, "metadata": {}}
        ]
        
        with patch('src.agents.strands_rag_agent.OllamaClient', return_value=mock_ollama_client):
            with patch('src.agents.strands_rag_agent.MilvusVectorDB', return_value=mock_milvus_client):
                agent = StrandsRAGAgent(test_settings)
                agent.vector_db = mock_milvus_client
                agent.ollama_client = mock_ollama_client
                
                result = agent.retrieve_context("collection", "test query")
                
                context_chunks, sources = result
                assert len(context_chunks) > 0


class TestStrandsRAGAgentAsync:
    """Test async functionality."""
    
    @pytest.mark.asyncio
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
    async def test_answer_question_async(self, mock_ollama, mock_milvus, test_settings):
        """Test async answer_question."""
        agent = StrandsRAGAgent(test_settings)
        agent.answer_question = Mock(return_value=("answer", []))
        
        result = await agent.answer_question_async("collection", "question")
        
        assert result[0] == "answer"
        assert isinstance(result[1], list)
    
    @pytest.mark.asyncio
    @patch('src.agents.strands_rag_agent.MilvusVectorDB')
    @patch('src.agents.strands_rag_agent.OllamaClient')
    async def test_retrieve_context_async(self, mock_ollama, mock_milvus, test_settings):
        """Test async retrieve_context."""
        agent = StrandsRAGAgent(test_settings)
        agent.retrieve_context = Mock(return_value=(["chunk"], []))
        
        result = await agent.retrieve_context_async("collection", "query")
        
        assert len(result) == 2
