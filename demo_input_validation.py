#!/usr/bin/env python3
"""Demo script showing bleach HTML sanitization (Python's DOMPurify equivalent)."""

from api_server import sanitize_user_input, validate_user_input
from src.config.settings import get_settings


def demo_sanitization():
    """Demonstrate bleach sanitization vs DOMPurify patterns."""

    print("🧪 Python Bleach vs JavaScript DOMPurify Demo")
    print("=" * 60)

    settings = get_settings()

    test_cases = [
        # XSS Script Injection
        '<script>alert("XSS_TEST")</script>What is Milvus?',
        # HTML Iframe Injection
        '<iframe src="https://evil.com"></iframe>Tell me about RAG',
        # Image with JavaScript
        "<img src=x onerror=alert(1)>How does vector search work?",
        # JavaScript Protocol
        'javascript:alert("hack") What is embeddings?',
        # Event Handler Injection
        "<div onclick=\"alert('click')\">How does indexing work?</div>",
        # Legitimate content with emojis
        "👤 Can you tell me about Pinecone? 🌲",
        # Short input (should fail validation)
        "a",
        # Empty input (should fail validation)
        "",
        # Long legitimate question
        "What are the performance differences between HNSW and IVF_FLAT indexing algorithms in Milvus?",
        # HTML comments
        "<!-- malicious comment -->What is vector similarity?",
    ]

    print("Test Results:")
    print("-" * 60)

    for i, test_input in enumerate(test_cases, 1):
        print(f"\n{i}. Input: {test_input[:50]}{'...' if len(test_input) > 50 else ''}")

        # Step 1: Sanitization
        sanitized = sanitize_user_input(test_input, settings)
        print(f"   Sanitized: {sanitized[:50]}{'...' if len(sanitized) > 50 else ''}")

        # Step 2: Validation
        is_valid, error = validate_user_input(sanitized, settings)

        if is_valid:
            print("   ✅ Valid: Ready for processing")
        else:
            print(f"   ❌ Invalid: {error}")

        print()

    print("💡 Configuration (adjustable via environment variables):")
    print(f"   MIN_MESSAGE_LENGTH: {settings.min_message_length}")
    print(f"   MAX_MESSAGE_LENGTH: {settings.max_message_length}")
    print(f"   ENABLE_HTML_SANITIZATION: {settings.enable_html_sanitization}")

    print("\n🔧 To adjust validation:")
    print("   Frontend: Set REACT_APP_MIN_MESSAGE_LENGTH=3 in .env")
    print("   Backend:  Set MIN_MESSAGE_LENGTH=3 in .env")
    print("   Disable sanitization: Set ENABLE_HTML_SANITIZATION=false")


if __name__ == "__main__":
    demo_sanitization()
