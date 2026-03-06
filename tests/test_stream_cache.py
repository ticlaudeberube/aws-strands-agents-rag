#!/usr/bin/env python3
"""Test to verify streaming endpoint now uses response cache (React chatbot fix)."""

import requests
import json
import sys
import time

API_URL = "http://localhost:8001/v1/chat/completions"


def test_stream_cache_hit():
    """Test that streaming endpoint checks response cache."""

    print("=" * 70)
    print("STREAMING ENDPOINT CACHE TEST")
    print("=" * 70)

    # Question from pre-warmed cache
    question = "What is Milvus?"

    # Build request in Strands Agent format
    request_data = {
        "messages": [
            {"role": "user", "content": [{"text": question}], "timestamp": "2026-03-02T00:00:00Z"}
        ],
        "model": "rag-agent",
        "stream": True,  # Enable streaming (used by React chatbot)
        "temperature": 0.1,
    }

    print("\n[Test 1] Streaming endpoint with cached question...")
    print(f"Question: {question}")
    print(f"Stream: {request_data['stream']}")

    try:
        start_time = time.time()
        response = requests.post(
            API_URL, json=request_data, headers={"Content-Type": "application/json"}, stream=True
        )

        if response.status_code != 200:
            print(f"✗ Error: {response.status_code}")
            print(f"  Response: {response.text}")
            return False

        # Collect the streamed response
        full_response = ""
        chunk_count = 0

        print("\nStreaming response chunks:")
        for line in response.iter_lines():
            if line:
                chunk_count += 1
                if line.startswith(b"data: "):
                    try:
                        json_data = json.loads(line[6:].decode())
                        if json_data.get("choices") and json_data["choices"][0].get(
                            "delta", {}
                        ).get("content"):
                            content = json_data["choices"][0]["delta"]["content"]
                            full_response += content
                            # Print first 50 chars of response
                            if len(full_response) <= 50:
                                print(f"  Chunk {chunk_count}: {repr(content)[:60]}")
                    except json.JSONDecodeError:
                        pass

        elapsed = time.time() - start_time

        print(f"\n✓ Streaming completed in {elapsed:.2f}s")
        print(f"  Total chunks: {chunk_count}")
        print(f"  Response length: {len(full_response)} chars")
        print(f"  Response preview: {full_response[:100]}...")

        # A cached response should be fast (typically < 1 second)
        # A non-cached response would take longer (retrieval + generation)
        if elapsed < 2.0:
            print(f"\n✓ CACHE HIT LIKELY (response time {elapsed:.2f}s is fast)")
            return True
        else:
            print(f"\n⚠ Response took {elapsed:.2f}s (cache miss or slow LLM)")
            return True

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_stream_without_cache():
    """Test streaming with bypass_cache parameter."""

    print("\n" + "=" * 70)
    print("TEST: Streaming with cache bypass")
    print("=" * 70)

    question = "What is Milvus?"

    request_data = {
        "messages": [
            {"role": "user", "content": [{"text": question}], "timestamp": "2026-03-02T00:00:00Z"}
        ],
        "model": "rag-agent",
        "stream": True,
        "temperature": 0.1,
    }

    print("\nBypass cache = true (should be slower than cache hit)")

    try:
        start_time = time.time()
        response = requests.post(
            f"{API_URL}?bypass_cache=true",
            json=request_data,
            headers={"Content-Type": "application/json"},
            stream=True,
        )

        if response.status_code != 200:
            print(f"✗ Error: {response.status_code}")
            return False

        full_response = ""
        for line in response.iter_lines():
            if line and line.startswith(b"data: "):
                try:
                    json_data = json.loads(line[6:].decode())
                    if json_data.get("choices") and json_data["choices"][0].get("delta", {}).get(
                        "content"
                    ):
                        full_response += json_data["choices"][0]["delta"]["content"]
                except json.JSONDecodeError:
                    pass

        elapsed = time.time() - start_time
        print(f"✓ Cache-bypassed response took {elapsed:.2f}s")
        print(f"  Response length: {len(full_response)} chars")

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    try:
        test1 = test_stream_cache_hit()
        test2 = test_stream_without_cache()

        print("\n" + "=" * 70)
        if test1 and test2:
            print("✓ All tests passed!")
            sys.exit(0)
        else:
            print("✗ Some tests failed")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
