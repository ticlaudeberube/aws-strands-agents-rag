"""Ollama integration for embeddings and LLM."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for Ollama embeddings and LLM with connection pooling and timeouts."""

    def __init__(
        self,
        host: Optional[str] = None,
        timeout: Optional[int] = None,
        pool_size: Optional[int] = None,
    ):
        """Initialize Ollama client with connection pooling.

        Args:
            host: Ollama server host (falls back to settings.ollama_host)
            timeout: Default request timeout in seconds (falls back to settings.ollama_timeout)
            pool_size: Connection pool size (falls back to settings.ollama_pool_size)
        """
        # Load defaults from settings
        settings = get_settings()
        host = host or settings.ollama_host
        timeout = timeout or settings.ollama_timeout
        pool_size = pool_size or settings.ollama_pool_size

        self.host = host
        self.timeout = timeout
        self.pool_size = pool_size
        self.embedding_endpoint = f"{host}/api/embeddings"
        self.generate_endpoint = f"{host}/api/generate"
        self.tags_endpoint = f"{host}/api/tags"

        # Create session with connection pooling and retry logic
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "DELETE", "POST"],
        )

        # Apply retry strategy to both HTTP and HTTPS
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=pool_size,
            pool_maxsize=pool_size,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def is_available(self, timeout: Optional[int] = None) -> bool:
        """Check if Ollama server is available.

        Args:
            timeout: Request timeout in seconds (uses default if None)

        Returns:
            True if Ollama is available, False otherwise
        """
        _timeout = timeout if timeout is not None else self.timeout
        try:
            response = self.session.get(self.tags_endpoint, timeout=_timeout)
            return response.status_code == 200  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning(f"Ollama server not available: {e}")
            return False

    def get_available_models(self, timeout: Optional[int] = None) -> List[str]:
        """Get list of available models from Ollama.

        Args:
            timeout: Request timeout in seconds (uses default if None)

        Returns:
            List of available model names
        """
        _timeout = timeout if timeout is not None else self.timeout
        try:
            response = self.session.get(self.tags_endpoint, timeout=_timeout)
            response.raise_for_status()
            data = response.json()
            models = [model.get("name", "") for model in data.get("models", [])]
            return models
        except Exception as e:
            logger.error(f"Failed to get models from Ollama: {e}")
            return []

    def close(self):
        """Close the session and clean up resources."""
        if hasattr(self, "session"):
            self.session.close()
            logger.info("Ollama client session closed")

    def embed_text(
        self,
        text: str,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> List[float]:
        """Generate embedding for text using Ollama.

        Args:
            text: Text to embed
            model: Ollama model name for embeddings (uses OLLAMA_EMBED_MODEL from config if None)
            timeout: Request timeout in seconds (uses default if None)

        Returns:
            Embedding vector
        """
        if model is None:
            model = get_settings().ollama_embed_model or os.getenv(
                "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5"
            )
        _timeout = timeout if timeout is not None else self.timeout
        try:
            response = self.session.post(
                self.embedding_endpoint,
                json={"prompt": text, "model": model},
                timeout=_timeout,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("embedding", [])  # type: ignore[no-any-return]
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"❌ Cannot connect to Ollama at {self.host}. Make sure Ollama is running: ollama serve"
            )
            raise RuntimeError(
                f"Ollama connection failed. Is Ollama running at {self.host}?"
            ) from e
        except requests.exceptions.Timeout as e:
            logger.error(
                f"❌ Ollama request timeout ({_timeout}s). Model '{model}' may be slow or not loaded. Check: ollama list"
            )
            raise RuntimeError(f"Ollama request timed out. Try: ollama pull {model}") from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.error(
                    f"❌ Model '{model}' not found in Ollama. Pull it with: ollama pull {model}"
                )
                raise RuntimeError(f"Model '{model}' not found. Run: ollama pull {model}") from e
            logger.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Embedding failed: {type(e).__name__}: {e}")
            raise

    def embed_texts(
        self,
        texts: List[str],
        model: Optional[str] = None,
        batch_size: int = 32,
        max_workers: Optional[int] = None,
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts with batch processing.

        Args:
            texts: List of texts to embed
            model: Ollama model name for embeddings (uses OLLAMA_EMBED_MODEL from config if None)
            batch_size: Size of each batch for processing
            max_workers: Maximum number of concurrent workers (defaults to 4)

        Returns:
            List of embedding vectors in same order as input
        """
        if model is None:
            model = get_settings().ollama_embed_model or "nomic-embed-text:v1.5"
        if not texts:
            return []

        # Default to 4 workers for parallel embedding requests
        if max_workers is None:
            max_workers = 4

        embeddings: List[Optional[List[float]]] = [None] * len(
            texts
        )  # Pre-allocate to maintain order

        # Use ThreadPoolExecutor for parallel embedding requests
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks and track their original indices
            future_to_index = {
                executor.submit(self.embed_text, text, model): idx for idx, text in enumerate(texts)
            }

            # Collect results maintaining original order
            completed = 0
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    embeddings[idx] = future.result()  # type: ignore[assignment]
                    completed += 1
                    if completed % max(1, len(texts) // 10) == 0:
                        logger.debug(f"Embedded {completed}/{len(texts)} texts")
                except Exception as e:
                    logger.error(f"Failed to embed text at index {idx}: {e}")
                    raise

        logger.info(f"Batch embedded {len(texts)} texts using {max_workers} workers")
        return embeddings  # type: ignore[return-value]

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        stream: bool = False,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text using Ollama LLM.

        Args:
            prompt: Input prompt
            model: Ollama model name (uses OLLAMA_MODEL from config if None)
            stream: Whether to stream response
            temperature: Temperature for generation (0-2, lower=more deterministic)
            max_tokens: Maximum number of tokens to generate (Ollama uses 'num_predict', None = no limit)

        Returns:
            Generated text
        """
        if model is None:
            model = get_settings().ollama_model or "qwen2.5:0.5b"
        try:
            # Ollama uses 'num_predict' instead of 'max_tokens'
            # num_predict: number of tokens to predict (-1 = infinite, default behavior)
            payload = {
                "prompt": prompt,
                "model": model,
                "stream": stream,
                "temperature": temperature,
            }

            # Only add num_predict if max_tokens is explicitly set and > 0
            if max_tokens is not None and max_tokens > 0:
                payload["num_predict"] = max_tokens
                logger.info(
                    f"Using token limit: max_tokens={max_tokens} (num_predict={max_tokens})"
                )
            else:
                logger.info(f"No token limit (max_tokens={max_tokens})")

            response = self.session.post(
                self.generate_endpoint,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")  # type: ignore[no-any-return]
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"❌ Cannot connect to Ollama at {self.host}. Make sure Ollama is running: ollama serve"
            )
            raise RuntimeError(
                f"Ollama connection failed. Is Ollama running at {self.host}?"
            ) from e
        except requests.exceptions.Timeout as e:
            logger.error(
                f"❌ Ollama request timeout (120s). Model '{model}' may be slow or not loaded. Check: ollama list"
            )
            raise RuntimeError(
                f"Ollama request timed out loading model '{model}'. Try: ollama pull {model}"
            ) from e
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise

    def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ):
        """Stream text generation using Ollama LLM.

        Yields chunks of text as they are generated. Useful for real-time
        response streaming to clients.

        Args:
            prompt: Input prompt
            model: Ollama model name (uses OLLAMA_MODEL from config if None)
            temperature: Temperature for generation (0-2, lower=more deterministic)
            max_tokens: Maximum number of tokens to generate (Ollama uses 'num_predict', None = no limit)

        Yields:
            Chunks of generated text
        """
        if model is None:
            model = get_settings().ollama_model or "qwen2.5:0.5b"
        import json

        try:
            payload = {
                "prompt": prompt,
                "model": model,
                "stream": True,
                "temperature": temperature,
            }

            # Only add num_predict if max_tokens is explicitly set and > 0
            if max_tokens is not None and max_tokens > 0:
                payload["num_predict"] = max_tokens
                logger.debug(f"Streaming with token limit: {max_tokens}")

            response = self.session.post(
                self.generate_endpoint,
                json=payload,
                timeout=120,
                stream=True,
            )
            response.raise_for_status()

            # Stream chunks as they arrive
            # Ollama returns newline-delimited JSON objects
            chunk_count = 0
            empty_chunk_count = 0
            total_length = 0
            
            for line in response.iter_lines():
                if line:
                    try:
                        # Decode bytes to string and parse JSON
                        line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                        chunk_data = json.loads(line_str)

                        # Extract the response chunk from the JSON
                        chunk = chunk_data.get("response", "")
                        is_done = chunk_data.get("done", False)
                        
                        if chunk:
                            chunk_count += 1
                            total_length += len(chunk)
                            yield chunk
                        else:
                            empty_chunk_count += 1
                            
                        # Log completion info
                        if is_done:
                            logger.info(
                                f"[OLLAMA_STREAM] Stream complete: {chunk_count} chunks, "
                                f"{empty_chunk_count} empty chunks, {total_length} total chars from model '{model}'"
                            )
                    except json.JSONDecodeError as e:
                        logger.debug(f"Failed to parse JSON chunk: {e}")
                        continue
                    except Exception as e:
                        logger.debug(f"Failed to process chunk: {e}")
                        continue
            
            # Check if we got no chunks at all
            if chunk_count == 0:
                logger.warning(
                    f"[OLLAMA_STREAM] No content generated! "
                    f"Received {empty_chunk_count} empty chunks from model '{model}'. "
                    f"This usually means the model is not generating responses. "
                    f"Check: (1) Ollama is running, (2) Model '{model}' is loaded, (3) Compute capacity"
                )
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"❌ Cannot connect to Ollama at {self.host}. Make sure Ollama is running: ollama serve"
            )
            raise RuntimeError(
                f"Ollama connection failed. Is Ollama running at {self.host}?"
            ) from e
        except requests.exceptions.Timeout as e:
            logger.error(
                f"❌ Ollama streaming timeout (120s). Model '{model}' may be slow or not loaded."
            )
            raise RuntimeError(f"Ollama request timed out. Try: ollama pull {model}") from e
        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            raise
