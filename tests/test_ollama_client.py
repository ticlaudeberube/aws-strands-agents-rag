"""Unit tests for OllamaClient."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.tools.ollama_client import OllamaClient


class TestOllamaClientInit:
    """Test OllamaClient initialization."""
    
    def test_init_with_defaults(self):
        """Test initialization with default values."""
        client = OllamaClient()
        assert client.host == "http://localhost:11434"
        assert client.timeout == 30
        assert client.session is not None
    
    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        client = OllamaClient(
            host="http://10.0.0.1:11434",
            timeout=60,
            pool_size=10,
        )
        assert client.host == "http://10.0.0.1:11434"
        assert client.timeout == 60
        assert client.pool_size == 10


class TestOllamaClientHealthCheck:
    """Test health check functionality."""
    
    @patch('src.tools.ollama_client.requests.Session.get')
    def test_is_available_success(self, mock_get):
        """Test is_available returns True on success."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        client = OllamaClient()
        result = client.is_available()
        
        assert result is True
        mock_get.assert_called_once()
    
    @patch('src.tools.ollama_client.requests.Session.get')
    def test_is_available_failure(self, mock_get):
        """Test is_available returns False on failure."""
        mock_get.side_effect = Exception("Connection refused")
        
        client = OllamaClient()
        result = client.is_available()
        
        assert result is False


class TestOllamaClientEmbedding:
    """Test embedding generation."""
    
    @patch('src.tools.ollama_client.requests.Session.post')
    def test_embed_text_success(self, mock_post):
        """Test successful text embedding."""
        mock_response = Mock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_post.return_value = mock_response
        
        client = OllamaClient()
        result = client.embed_text("test text", model="test-model")
        
        assert result == [0.1, 0.2, 0.3]
        mock_post.assert_called_once()
    
    @patch('src.tools.ollama_client.requests.Session.post')
    def test_embed_text_timeout(self, mock_post):
        """Test embedding timeout handling."""
        from requests.exceptions import Timeout
        mock_post.side_effect = Timeout("Request timed out")
        
        client = OllamaClient()
        with pytest.raises(RuntimeError, match="timed out"):
            client.embed_text("test text", model="test-model")
    
    @patch('src.tools.ollama_client.requests.Session.post')
    def test_embed_text_custom_timeout(self, mock_post):
        """Test embedding with custom timeout."""
        mock_response = Mock()
        mock_response.json.return_value = {"embedding": [0.1]}
        mock_post.return_value = mock_response
        
        client = OllamaClient(timeout=30)
        client.embed_text("test", model="test", timeout=60)
        
        # Verify custom timeout was used
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['timeout'] == 60


class TestOllamaClientBatchEmbedding:
    """Test batch embedding operations."""
    
    @patch('src.tools.ollama_client.OllamaClient.embed_text')
    def test_embed_texts_success(self, mock_embed_text):
        """Test successful batch embedding."""
        mock_embed_text.return_value = [0.1, 0.2, 0.3]
        
        client = OllamaClient()
        texts = ["text1", "text2", "text3"]
        results = client.embed_texts(texts, max_workers=2)
        
        assert len(results) == 3
        assert all(len(r) > 0 for r in results)
    
    @patch('src.tools.ollama_client.OllamaClient.embed_text')
    def test_embed_texts_empty_list(self, mock_embed_text):
        """Test batch embedding with empty list."""
        client = OllamaClient()
        results = client.embed_texts([])
        
        assert results == []
        mock_embed_text.assert_not_called()


class TestOllamaClientSession:
    """Test session management."""
    
    def test_session_close(self):
        """Test session closure."""
        client = OllamaClient()
        assert client.session is not None
        
        client.close()
        # Session should be closed (this would require checking internal state)
