"""Ollama integration for embeddings and LLM."""

import requests
import logging
from typing import List

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for Ollama embeddings and LLM."""

    def __init__(self, host: str = "http://localhost:11434"):
        """Initialize Ollama client.

        Args:
            host: Ollama server host (e.g., http://localhost:11434)
        """
        self.host = host
        self.embedding_endpoint = f"{host}/api/embeddings"
        self.generate_endpoint = f"{host}/api/generate"
        self.tags_endpoint = f"{host}/api/tags"
    
    def is_available(self, timeout: int = 5) -> bool:
        """Check if Ollama server is available.
        
        Args:
            timeout: Request timeout in seconds
            
        Returns:
            True if Ollama is available, False otherwise
        """
        try:
            response = requests.get(self.tags_endpoint, timeout=timeout)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama server not available: {e}")
            return False
    
    def get_available_models(self, timeout: int = 5) -> List[str]:
        """Get list of available models from Ollama.
        
        Args:
            timeout: Request timeout in seconds
            
        Returns:
            List of available model names
        """
        try:
            response = requests.get(self.tags_endpoint, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            models = [model.get("name", "") for model in data.get("models", [])]
            return models
        except Exception as e:
            logger.error(f"Failed to get models from Ollama: {e}")
            return []

    def embed_text(
        self,
        text: str,
        model: str = "all-minilm",
    ) -> List[float]:
        """Generate embedding for text using Ollama.

        Args:
            text: Text to embed
            model: Ollama model name for embeddings

        Returns:
            Embedding vector
        """
        try:
            response = requests.post(
                self.embedding_endpoint,
                json={"prompt": text, "model": model},
                timeout=60,  # Increased timeout for slower embeddings
            )
            response.raise_for_status()
            result = response.json()
            return result.get("embedding", [])
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Cannot connect to Ollama at {self.host}. Make sure Ollama is running: ollama serve")
            raise RuntimeError(f"Ollama connection failed. Is Ollama running at {self.host}?") from e
        except requests.exceptions.Timeout as e:
            logger.error(f"❌ Ollama request timeout (60s). Model '{model}' may be slow or not loaded. Check: ollama list")
            raise RuntimeError(f"Ollama request timed out. Try: ollama pull {model}") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.error(f"❌ Model '{model}' not found in Ollama. Pull it with: ollama pull {model}")
                raise RuntimeError(f"Model '{model}' not found. Run: ollama pull {model}") from e
            logger.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Embedding failed: {type(e).__name__}: {e}")
            raise

    def embed_texts(
        self,
        texts: List[str],
        model: str = "all-minilm",
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            model: Ollama model name for embeddings

        Returns:
            List of embedding vectors
        """
        embeddings = []
        for text in texts:
            embedding = self.embed_text(text, model)
            embeddings.append(embedding)
        return embeddings

    def generate(
        self,
        prompt: str,
        model: str = "mistral",
        stream: bool = False,
    ) -> str:
        """Generate text using Ollama LLM.

        Args:
            prompt: Input prompt
            model: Ollama model name
            stream: Whether to stream response

        Returns:
            Generated text
        """
        try:
            response = requests.post(
                self.generate_endpoint,
                json={"prompt": prompt, "model": model, "stream": stream},
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise

