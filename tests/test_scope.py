#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from src.config.settings import get_settings
from src.tools.ollama_client import OllamaClient

settings = get_settings()
ollama = OllamaClient(
    host=settings.ollama_host,
    timeout=settings.ollama_timeout,
    pool_size=settings.ollama_pool_size,
)

question = "What are Milvus advantages over Pinecone?"

scope_check_prompt = """You are a question classifier. Respond with ONLY "YES" or "NO".

Is this question about any of these topics:
- Vector databases or vector search
- Embeddings or semantic similarity
- RAG (Retrieval-Augmented Generation)
- Information retrieval or database indexing
- Machine learning with vector operations

Question: {question}

Respond with only "YES" or "NO":"""

response = ollama.generate(
    prompt=scope_check_prompt.format(question=question),
    model=settings.ollama_model,
    temperature=0.0,
    max_tokens=5,
).strip().upper()

print(f"Question: {question}")
print(f"Scope check response: {response}")
print(f"Classification: {'IN-SCOPE' if response.startswith('YES') else 'OUT-OF-SCOPE'}")
