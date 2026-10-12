#!/usr/bin/env python3
"""Test the /v1/cache/responses endpoint."""

import requests
import json

url = "http://localhost:8001/v1/cache/responses?limit=3"

print(f"Testing endpoint: {url}\n")

try:
    response = requests.get(url)
    print(f"Status code: {response.status_code}\n")

    if response.ok:
        data = response.json()
        print(json.dumps(data, indent=2))
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Failed to connect: {e}")
