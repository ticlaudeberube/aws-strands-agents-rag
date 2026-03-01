# Diagnostic Scripts

Helper scripts for debugging and testing the RAG system.

## Web Search Diagnostics

### Run the Full Diagnostic
```bash
python scripts/diagnose_web_search.py
```

This comprehensive tool tests:
1. **Network connectivity** - Can reach the internet
2. **Tavily API** - API is reachable and returns valid JSON
3. **WebSearchClient** - Python module works correctly
4. **RAG Agent Integration** - Agent uses web search in responses

### Quick Test
```bash
# Test with INFO logging
python -c "
from src.tools.web_search import WebSearchClient
client = WebSearchClient()
results = client.search('Milvus vector database', max_results=2)
print(f'Found {len(results)} results')
for r in results:
    print(f'  - {r[\"title\"]}: {r[\"url\"][:50]}...')
"
```

### Debug with Full Logs
```bash
# Enable DEBUG logging for detailed diagnostics
LOG_LEVEL=DEBUG python scripts/diagnose_web_search.py
```

## Output Examples

## Environment Variables

### Enable Debug Logging
```bash
export LOG_LEVEL=DEBUG
python scripts/diagnose_web_search.py
```

### Change Request Timeout
Web search client uses 10-second timeout by default. To test with different timeout:

```bash
python -c "
from src.tools.web_search import WebSearchClient
client = WebSearchClient(timeout=20)  # 20 seconds
results = client.search('test', max_results=2)
"
```

## Integration with CI/CD

To verify web search functionality in CI/CD:

```bash
#!/bin/bash
set -e

echo "Testing web search integration..."
python scripts/diagnose_web_search.py

if grep -q "WEB SOURCES FOUND" <<< "$output"; then
    echo "✓ Web search is working"
    exit 0
else
    echo "✗ Web search not working"
    exit 1
fi
```

## See Also

- [WEB_SEARCH_INTEGRATION.md](../docs/WEB_SEARCH_INTEGRATION.md) - Full integration documentation
- [DEVELOPMENT.md](../docs/DEVELOPMENT.md) - Development guidelines
