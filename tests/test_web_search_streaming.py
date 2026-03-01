#!/usr/bin/env python3
"""Test that web search streaming works correctly with force_web_search=true."""

import asyncio
import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.strands_rag_agent import StrandsRAGAgent
from src.config.settings import get_settings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@pytest.mark.asyncio
async def test_web_search_streaming():
    """Test the streaming web search path."""
    settings = get_settings()
    
    # Initialize the agent
    agent = StrandsRAGAgent(settings=settings)
    
    print("Testing stream_answer_web_search_only()...")
    print("=" * 70)
    
    question = "What is Milvus?"
    full_response = ""
    
    try:
        # Stream the answer
        async for chunk in agent.stream_answer_web_search_only(
            question=question,
            temperature=0.1,
            max_tokens=500,
        ):
            print(chunk, end="", flush=True)
            full_response += chunk
        
        print("\n" + "=" * 70)
        print(f"\n✓ Stream completed successfully!")
        print(f"  Total response length: {len(full_response)} characters")
        
        # Check the sources
        sources = agent._last_stream_sources
        print(f"\n  Sources returned: {len(sources) if sources else 0}")
        if sources:
            for i, source in enumerate(sources, 1):
                source_type = source.get("source_type", "unknown")
                title = source.get("title", source.get("document_name", "Unknown"))
                print(f"    {i}. [{source_type}] {title}")
        
        # Verify web search sources (NOT local docs)
        if sources:
            local_doc_count = 0
            web_count = 0
            for source in sources:
                if source.get("source_type") == "web_search":
                    web_count += 1
                elif ".md" in str(source.get("document_name", "")) or ".md" in str(source.get("title", "")):
                    local_doc_count += 1
            
            print(f"\n  Web search results: {web_count}")
            print(f"  Local doc results: {local_doc_count}")
            
            if web_count > local_doc_count:
                print("  ✓ Web search is being used (more web results than local docs)")
            elif local_doc_count > web_count:
                print("  ✗ WARNING: Local docs outnumber web results - web search may not be working")
        
        # Check for markdown links
        if "[" in full_response and "](" in full_response:
            print("\n  ⚠️  WARNING: Response contains markdown links [text](url)")
            print("     Expected HTML links: <a href=\"...\">text</a>")
        elif "<a href=" in full_response:
            print("\n  ✓ Response uses HTML links (correct format)")
        else:
            print("\n  ✓ Response has no links (acceptable)")
            
    except Exception as e:
        print(f"\n✗ Error during streaming: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_web_search_streaming())
    sys.exit(0 if success else 1)
