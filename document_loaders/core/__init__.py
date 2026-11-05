"""Core utilities for the standalone document loader package.

The canonical loader-facing clients live in :mod:`document_loaders.core.tools`:
:class:`OpenSearchVectorDB` (local OpenSearch vector store) and
:class:`OllamaClient` (embeddings + model availability).
"""

from .tools import OllamaClient, OpenSearchVectorDB

__all__ = ["OpenSearchVectorDB", "OllamaClient"]
