"""Agents module with Strands integration."""

from .strands_graph_agent import StrandsGraphRAGAgent

# Backward compatibility: export graph agent as main RAG agent
StrandsRAGAgent = StrandsGraphRAGAgent

__all__ = ["StrandsRAGAgent", "StrandsGraphRAGAgent"]
