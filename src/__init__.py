"""AWS Strands Agents RAG - Main package."""

from src.agents import StrandsRAGAgent
from src.config import Settings
from src.tools import OllamaClient

__version__ = "0.1.0"
__all__ = [
    "Settings",
    "StrandsRAGAgent",
    "OllamaClient",
]
