#!/usr/bin/env python3

import requests

url = "http://localhost:8000/v1/chat/completions"
payload = {
    "messages": [
        {
            "role": "user",
            "content": [{"type": "text", "text": "What is the latest vector database news?"}],
        }
    ],
    "model": "gpt-4",
}

print("Testing latest news query with prioritized web search context...")
print("=" * 80)

try:
    response = requests.post(url, json=payload, timeout=60)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        sources = data.get("sources", [])
        response_type = data.get("response_type", "unknown")

        print(f"✅ RESPONSE TYPE: {response_type}")
        print(f"✅ ANSWER LENGTH: {len(answer)} chars")
        print()

        if len(answer) > 300:
            print("✅ Answer has substantial content!")
            print(f"Preview:\n{answer[:400]}...")
        else:
            print(f"⚠️ Answer is short ({len(answer)} chars):")
            print(answer)

        print()
        web = [s for s in sources if s.get("source_type") == "web_search"]
        kb = [s for s in sources if s.get("source_type") not in ["web_search", "cached"]]
        cached = [s for s in sources if s.get("source_type") == "cached"]

        print(f"✅ SOURCES: {len(web)} web + {len(kb)} KB + {len(cached)} cached")

        if len(web) > 0:
            print("\nWEB SOURCES:")
            for i, s in enumerate(web[:3], 1):
                print(f"  {i}. {s.get('title', 'Untitled')}")

        print("\n" + "=" * 80)
        if len(answer) > 300 and len(web) > 0:
            print("✅ SUCCESS: Proper web search integration with substantive answer!")
        else:
            print("⚠️ Partial: Check if answer is properly using web search context")
    else:
        print(f"Error response: {response.text[:500]}")
except Exception as e:
    print(f"Request failed: {e}")
