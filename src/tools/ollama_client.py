"""Ollama integration for embeddings and LLM."""

import requests
import logging
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        batch_size: int = 32,
        max_workers: Optional[int] = None,
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts with batch processing.

        Args:
            texts: List of texts to embed
            model: Ollama model name for embeddings
            batch_size: Size of each batch for processing
            max_workers: Maximum number of concurrent workers (defaults to 4)

        Returns:
            List of embedding vectors in same order as input
        """
        if not texts:
            return []
        
        # Default to 4 workers for parallel embedding requests
        if max_workers is None:
            max_workers = 4
        
        embeddings = [None] * len(texts)  # Pre-allocate to maintain order
        
        # Use ThreadPoolExecutor for parallel embedding requests
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks and track their original indices
            future_to_index = {
                executor.submit(self.embed_text, text, model): idx
                for idx, text in enumerate(texts)
            }
            
            # Collect results maintaining original order
            completed = 0
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    embeddings[idx] = future.result()
                    completed += 1
                    if completed % max(1, len(texts) // 10) == 0:
                        logger.debug(f"Embedded {completed}/{len(texts)} texts")
                except Exception as e:
                    logger.error(f"Failed to embed text at index {idx}: {e}")
                    raise
        
        logger.info(f"Batch embedded {len(texts)} texts using {max_workers} workers")
        return embeddings

    def generate(
        self,
        prompt: str,
        model: str = "mistral",
        stream: bool = False,
        temperature: float = 0.1,
    ) -> str:
        """Generate text using Ollama LLM.

        Args:
            prompt: Input prompt
            model: Ollama model name
            stream: Whether to stream response
            temperature: Temperature for generation (0-2, lower=more deterministic)

        Returns:
            Generated text
        """
        try:
            response = requests.post(
                self.generate_endpoint,
                json={"prompt": prompt, "model": model, "stream": stream, "temperature": temperature},
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise

