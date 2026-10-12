#!/usr/bin/env python3
"""Test the streaming endpoint directly to diagnose issues."""

from fastapi.testclient import TestClient

from api_server import app


def test_streaming_endpoint():
    """Test the /v1/chat/completions streaming endpoint."""
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "What is Milvus?"}]}
            ],
            "stream": True,
        },
    )

    print(f"Status Code: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    print()

    print("Response chunks:")
    chunk_count = 0
    for line in response.iter_lines():
        if line:
            chunk_count += 1
            line_str = line.encode().decode("utf-8") if isinstance(line, bytes) else line
            print(f"Chunk {chunk_count}: {line_str[:150]}")
            if chunk_count >= 10:
                print("... (more chunks)")
                break

    print(f"\nTotal chunks received: {chunk_count}")


if __name__ == "__main__":
    test_streaming_endpoint()
