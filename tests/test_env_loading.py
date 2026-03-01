#!/usr/bin/env python3
"""Test script to verify environment variables are loaded correctly."""

import os
import sys
from pathlib import Path

# Test 1: Check without loading .env
print("=" * 60)
print("TEST 1: Environment variables BEFORE loading .env")
print("=" * 60)
print(f"TAVILY_API_KEY (direct os.environ.get): {os.environ.get('TAVILY_API_KEY', 'NOT SET')}")
print()

# Test 2: Load .env file
print("=" * 60)
print("TEST 2: Loading .env file with python-dotenv")
print("=" * 60)
from dotenv import load_dotenv
env_file = Path(__file__).parent.parent / ".env"
print(f"Loading from: {env_file}")
print(f"File exists: {env_file.exists()}")

loaded = load_dotenv(env_file)
print(f"Load result: {loaded}")
print()

# Test 3: Check after loading .env  
print("=" * 60)
print("TEST 3: Environment variables AFTER loading .env")
print("=" * 60)
tavily_key = os.environ.get('TAVILY_API_KEY', 'NOT SET')
if tavily_key and tavily_key != 'NOT SET':
    preview = f"{tavily_key[:10]}..." if len(tavily_key) > 10 else "***"
    print(f"✓ TAVILY_API_KEY is SET: {preview}")
else:
    print(f"✗ TAVILY_API_KEY is NOT SET")
print()

# Test 4: Check WebSearchClient
print("=" * 60)
print("TEST 4: WebSearchClient initialization")
print("=" * 60)
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.tools.web_search import WebSearchClient

web_search = WebSearchClient()
if web_search.tavily.api_key:
    preview = f"{web_search.tavily.api_key[:10]}..." if len(web_search.tavily.api_key) > 10 else "***"
    print(f"✓ WebSearchClient has API key: {preview}")
else:
    print(f"✗ WebSearchClient has NO API key")
print()

# Test 5: Try a search
print("=" * 60)
print("TEST 5: Attempting a test web search")
print("=" * 60)
try:
    results = web_search.search("Milvus vector database", max_results=2)
    print(f"Search results: {len(results)} found")
    if results:
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result.get('title', 'No title')[:50]}")
            print(f"     URL: {result.get('url', 'No URL')}")
    else:
        print("✗ No results returned - API key may not be valid")
except Exception as e:
    print(f"✗ Search error: {e}")
