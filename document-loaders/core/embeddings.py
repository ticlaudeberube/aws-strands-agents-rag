"""Embedding providers for text vectorization."""

import os
from typing import Optional, Union, List
import ollama
from .exceptions import EmbeddingError


class EmbeddingProvider:
    @staticmethod
    def embed_text(
        text: Union[str, List[str]], provider: str = "ollama", model: Optional[str] = None
    ):
        """Unified embedding method supporting Ollama provider."""
        if provider == "ollama":
            return EmbeddingProvider._embed_ollama(text, model)
        else:
            raise EmbeddingError(
                f"Unsupported embedding provider: {provider}. Only 'ollama' is supported."
            )

    @staticmethod
    def _embed_ollama(text: Union[str, List[str]], model: Optional[str] = None):
        """Embed text using Ollama."""
        # Ensure OLLAMA_NUM_THREADS is always set
        if not os.getenv("OLLAMA_NUM_THREADS"):
            os.environ["OLLAMA_NUM_THREADS"] = "4"

        # Check for both environment variable names for compatibility
        _model = model or os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5")

        if isinstance(text, list):
            return [ollama.embeddings(model=_model, prompt=t)["embedding"] for t in text]
        return ollama.embeddings(model=_model, prompt=text)["embedding"]
