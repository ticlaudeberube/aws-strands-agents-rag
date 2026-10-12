#!/usr/bin/env python3
"""Minimal test - create HTTP request and save response to file."""

import requests
import json

output_file = "endpoint_response.json"

try:
    # Test endpoint
    response = requests.get("http://localhost:8001/v1/cache/responses?limit=5", timeout=10)

    # Save response to file
    with open(output_file, "w") as f:
        json.dump(
            {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.json() if response.ok else response.text,
            },
            f,
            indent=2,
        )

    print(f"Response saved to {output_file}")

except Exception as e:
    with open(output_file, "w") as f:
        json.dump({"error": str(e)}, f, indent=2)
    print(f"Error saved to {output_file}: {e}")
