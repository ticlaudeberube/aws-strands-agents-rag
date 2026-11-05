"""Agents module with Strands integration."""

from .local_opensearch_agent import LocalOpenSearchAgent

# Backward-compatibility alias: the OpenSearch-backed local agent is the main
# RAG agent entrypoint after the Milvus engine removal.
StrandsRAGAgent = LocalOpenSearchAgent

__all__ = ["StrandsRAGAgent", "LocalOpenSearchAgent"]
