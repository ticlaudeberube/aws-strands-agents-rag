#!/usr/bin/env python3
"""Simple endpoint test to avoid terminal output issues."""

import requests

# Test the endpoint
try:
    response = requests.get("http://localhost:8001/v1/cache/responses?limit=3", timeout=10)
    print(f"Status Code: {response.status_code}")
    data = response.json()
    print(f"\nCached Responses Count: {len(data.get('cached_responses', []))}")

    if data.get("cached_responses"):
        print("\nFirst cached response:")
        first = data["cached_responses"][0]
        print(f"  Question: {first.get('question', 'N/A')}")
        print(f"  Answer: {first.get('answer', 'N/A')[:100]}...")
        print(f"  Sources: {len(first.get('sources', []))} sources")
    else:
        print("\nNo cached responses returned")

except Exception as e:
    print(f"Error: {e}")
