#!/usr/bin/env python3
"""Test the cache responses endpoint and show results."""

import requests
import json
import time

print("Waiting for API server to start...")
time.sleep(3)

url = "http://localhost:8001/v1/cache/responses?limit=5"
print(f"\nTesting: {url}")
print("=" * 60)

try:
    response = requests.get(url, timeout=10)
    print(f"Status Code: {response.status_code}")

    data = response.json()
    print(f"\nResponse Keys: {list(data.keys())}")

    cached_responses = data.get("cached_responses", [])
    print(f"Number of cached responses: {len(cached_responses)}")

    if cached_responses:
        print("\n✅ SUCCESS! Found cached responses:\n")
        for i, item in enumerate(cached_responses, 1):
            print(f"{i}. Question: {item.get('question', 'N/A')}")
            answer = item.get("answer", "")[:100]
            print(f"   Answer: {answer}...")
            print(f"   Sources: {len(item.get('sources', []))}")
            print()
    else:
        print("\n❌ NO CACHED RESPONSES FOUND")
        print(f"Full response: {json.dumps(data, indent=2)}")

except requests.exceptions.ConnectionError:
    print("❌ Cannot connect to API server")
    print("   Make sure it's running on port 8001")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "=" * 60)
print("Now checking the log file...")
print("=" * 60)

try:
    with open("api_debug.log") as f:
        lines = f.readlines()

    # Find lines related to cache endpoint
    relevant_lines = []
    for i, line in enumerate(lines):
        if "cache/responses" in line.lower() or "querying cache collection" in line.lower():
            # Get context around the match
            start = max(0, i - 2)
            end = min(len(lines), i + 10)
            relevant_lines.extend(lines[start:end])
            relevant_lines.append("---\n")

    if relevant_lines:
        print("\nRelevant log entries:")
        print("".join(relevant_lines[-50:]))  # Last 50 lines
    else:
        print("\nNo cache endpoint calls found in log")
        print("Last 20 lines of log:")
        print("".join(lines[-20:]))

except FileNotFoundError:
    print("❌ Log file not found: api_debug.log")
except Exception as e:
    print(f"❌ Error reading log: {e}")
