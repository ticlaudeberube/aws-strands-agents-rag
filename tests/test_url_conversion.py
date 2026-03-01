#!/usr/bin/env python3
"""Test the URL-to-HTML conversion function."""

import re
import json

def convert_urls_to_html_links(text: str) -> str:
    """Convert markdown links and plain URLs to HTML clickable links."""
    if not text:
        return text
    
    # 1. Convert markdown links: [text](url) → <a href="url" target="_blank">text</a>
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" target="_blank">\1</a>',
        text
    )
    
    # 2. Convert plain URLs wrapped in angle brackets: <url> → <a href="url" target="_blank">url</a>
    text = re.sub(
        r'<(https?://[^\s>]+)>',
        r'<a href="\1" target="_blank">\1</a>',
        text
    )
    
    # 3. Convert plain HTTPS/HTTP URLs not already converted
    text = re.sub(
        r'(?<!href=")(?<!href=\')(?<!>)(https?://[^\s<)]+?)(?=[\s<\)\.\,\;:]|$)',
        r'<a href="\1" target="_blank">\1</a>',
        text
    )
    
    return text


# Test cases
test_cases = [
    {
        "name": "Markdown link",
        "input": "[Using strings to filter](https://milvus.io/blog/test)",
        "should_have": "<a href=",
    },
    {
        "name": "Plain URL",
        "input": "For more info, visit https://milvus.io/docs",
        "should_have": "<a href=",
    },
    {
        "name": "Multiple markdown links",
        "input": "- [Link 1](https://test1.com)\n- [Link 2](https://test2.com)",
        "should_have": "<a href=",
    },
]

print("=" * 60)
print("Testing URL-to-HTML Conversion Function")
print("=" * 60)

for test in test_cases:
    print(f"\nTest: {test['name']}")
    print(f"Input:  {test['input'][:80]}")
    result = convert_urls_to_html_links(test['input'])
    print(f"Output: {result[:100]}")
    has_html = test['should_have'] in result
    print(f"Result: {'✓ PASS' if has_html else '✗ FAIL'}")
    if not has_html:
        print("  FULL OUTPUT:", result)

# Test with actual cached answer format
cached_answer = """In Milvus, you can filter data using Bitset, which helps with attribute filtering and data deletion. For example, to filter data based on metadata like 'source', you can use the Milvus Scalar Filtering Rules as shown below:

```python
vectorstore.similarity_search( "What is CoT?", k=1, expr="source == 'https://lilianweng.github.io/posts/2023-06-23-agent/'", )
```

More information on using strings to filter search results and Hybrid Search can be found in these resources:

- [Using strings to filter](https://milvus.io/blog/2022-08-08-How-to-use-string-data-to-empower-your-similarity-search-applications.md)
- [Hybrid Search](https://milvus.io/docs/hybridsearch.md)

For loading data into Milvus, please refer to the provided documentation:

- [Load data into Milvus](https://milvus.io/docs/quickstart.md#load-data)"""

print("\n" + "=" * 60)
print("Test: Full Cached Answer Format")
print("=" * 60)
result = convert_urls_to_html_links(cached_answer)
html_links = result.count('<a href')
print(f"Number of <a href tags: {html_links}")
print(f"Result: {'✓ PASS' if html_links >= 3 else '✗ FAIL'}")
if html_links >= 3:
    print("\nFirst converted link:")
    idx = result.find('<a href')
    print(result[idx:idx+120])
else:
    print("\nNo HTML links found!")
    print("First markdown link still present:", "[Using strings to filter]" in result)
