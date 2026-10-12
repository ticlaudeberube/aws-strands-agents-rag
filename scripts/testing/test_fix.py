#!/usr/bin/env python3
"""Quick test of cache endpoint after filter fix."""

import requests
import time

# Wait for server to be ready
print("Waiting for server...")
time.sleep(4)

print("\nTesting /v1/cache/responses endpoint...")
try:
    response = requests.get("http://localhost:8001/v1/cache/responses?limit=5")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        cached = result.get("cached_responses", [])
        print(f"\n✅ SUCCESS: Found {len(cached)} cached responses!")

        if cached:
            print("\nFirst 3 responses:")
            for i, item in enumerate(cached[:3], 1):
                question = item.get("question", "N/A")[:80]
                answer = item.get("answer", "N/A")[:100]
                print(f"\n{i}. Q: {question}")
                print(f"   A: {answer}...")
        else:
            print("\n❌ No cached responses returned (still broken)")
    else:
        print(f"❌ HTTP Error: {response.status_code}")
        print(response.text[:500])

except Exception as e:
    print(f"❌ Error: {e}")
