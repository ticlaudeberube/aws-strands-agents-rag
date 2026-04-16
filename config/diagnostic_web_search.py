#!/usr/bin/env python3
"""Diagnostic script to trace web search context and answer generation."""

import logging

from src.config.settings import Settings
from src.tools import MilvusVectorDB, OllamaClient, WebSearchClient

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Monkey patch the generation tool to see what context is being passed
original_generate = None


def debug_wrapper(generation_tool_orig):
    """Wrap generation tool to log context."""

    def wrapped(question, context, sources, temperature=None, max_tokens=None):
        logger.warning(f"[DEBUG] Context type: {type(context)}")
        logger.warning(f"[DEBUG] Context length: {len(context) if context else 0} chars")
        logger.warning(f"[DEBUG] Context first 200 chars: {context[:200] if context else 'EMPTY'}")
        logger.warning(f"[DEBUG] Sources count: {len(sources)}")

        web_sources = [s for s in sources if s.get("source_type") == "web_search"]
        logger.warning(f"[DEBUG] Web sources in sources list: {len(web_sources)}")
        for s in web_sources[:2]:
            logger.warning(f"  - {s.get('title', 'Untitled')}: {s.get('text', '')[:100]}")

        result = generation_tool_orig(question, context, sources, temperature, max_tokens)
        logger.warning(f"[DEBUG] Generated answer length: {len(result.answer)} chars")
        logger.warning(f"[DEBUG] Generated answer: {result.answer}")
        return result

    return wrapped


def test_diagnostic():
    """Run diagnostic test."""
    settings = Settings()
    print("=" * 80)
    print("DIAGNOSTIC: Web Search for Latest Vector Database News")
    print("=" * 80)

    # Create clients directly
    ollama = OllamaClient(
        host=settings.ollama_host,
        timeout=settings.ollama_timeout,
        pool_size=settings.ollama_pool_size,
    )

    milvus = MilvusVectorDB(
        host=settings.milvus_host,
        port=settings.milvus_port,
        db_name=settings.milvus_db_name,
        user=settings.milvus_user,
        password=settings.milvus_password,
    )

    web_search = WebSearchClient()

    # Test web search directly
    question = "What is the latest vector database news?"
    print("\n[1] Testing web search directly...")
    print(f"    Question: {question}")

    web_results = web_search.search(question, max_results=3)
    print(f"    Web results found: {len(web_results)}")
    for idx, result in enumerate(web_results, 1):
        print(f"      [{idx}] {result.get('title', 'Untitled')[:60]}")
        print(f"          Snippet: {result.get('snippet', '')[:100]}...")

    # Test KB retrieval
    print("\n[2] Testing KB retrieval...")
    embedding = ollama.embed_text(question, model=settings.ollama_embed_model)
    kb_results = milvus.search("milvus_docs", embedding, limit=5)
    print(f"    KB results found: {len(kb_results)}")
    for idx, result in enumerate(kb_results[:3], 1):
        print(f"      [{idx}] {result.get('text', '')[:100]}...")

    # Test context formatting
    print("\n[3] Testing context building...")
    web_context_parts = []
    for idx, web_result in enumerate(web_results, 1):
        snippet = web_result.get("snippet", "")
        title = web_result.get("title", "Web Result")
        web_context_parts.append(f"[Web Result {idx}] {title}\n{snippet}\n")

    context_text = "\n".join(web_context_parts)
    print(f"    Built context length: {len(context_text)} chars")
    print(f"    Context preview:\n{context_text[:300]}...")

    # Test answer generation with web context
    print("\n[4] Testing answer generation with web context...")
    from src.agents.strands_graph_agent import create_answer_generation_tool

    gen_tool = create_answer_generation_tool(ollama, settings)

    sources = []
    for idx, web_result in enumerate(web_results, 1):
        sources.append(
            {
                "source_type": "web_search",
                "url": web_result.get("url", ""),
                "title": web_result.get("title", "Web Result"),
                "text": web_result.get("snippet", ""),
                "distance": 0.7,
            }
        )

    result = gen_tool(question, context_text, sources)
    print(f"    Generated answer length: {len(result.answer)} chars")
    print(f"    Answer:\n{result.answer}")
    print(f"    Sources in result: {len(result.sources)}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        test_diagnostic()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
