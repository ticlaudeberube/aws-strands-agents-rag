# Web Search Integration

## Overview

The RAG system supports web search via Tavily API with two modes:

1. **Web-Only Mode** (`force_web_search: true`) - Searches only the web, bypasses knowledge base
2. **Supplementary Mode** (future) - Combines KB + web results

**Default**: Web search is OFF. Feature must be explicitly enabled.

## Search Modes

| Mode | Trigger | Sources | Use Case |
|------|---------|---------|----------|
| **Knowledge Base** (default) | Normal query | Milvus docs only | Technical documentation |
| **Web-Only** | 🌐 button in UI or `force_web_search: true` | Web URLs only | Latest news, trends |
| **Bypass Cache** | 🚫 button in UI or `bypass_cache: true` | Fresh KB query | Updated answers |

## Setup

### 1. Get Tavily API Key

Sign up at https://tavily.com (free tier available)

### 2. Configure `.env`

```bash
# Enable web search feature
ENABLE_WEB_SEARCH_SUPPLEMENT=true

# Add your Tavily API key
TAVILY_API_KEY=tvly-your-api-key-here
```

### 3. Restart API Server

```bash
python api_server.py
```

The React UI will automatically show the 🌐 web search button when enabled.

## Using Web Search

### Via React UI

1. **Click the 🌐 button** (next to send button)
2. **Send your question** - will search web only
3. **Badge shows 🌐 Web** (blue) instead of 🔍 KB (green)
4. **Sources show web URLs** with clickable links

### Via API

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "messages": [{"role": "user", "content": "What is Milvus?"}],
        "force_web_search": true  # Web-only mode
    }
)
```

### Via curl

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Latest AI news"}],
    "force_web_search": true
  }'
```

## How It Works

**Web-Only Mode** (`force_web_search: true`):
1. Query sent with web search flag
2. Tavily API searches web (5 results)
3. LLM generates answer using **only web snippets**
4. Response includes web URLs as sources
5. Badge shows **🌐 Web** (blue)

**Prompt Engineering**: The system now uses strict prompts to ensure LLM quotes actual web content:
```
CRITICAL: Answer EXCLUSIVELY using the provided web search snippets.
DO NOT use training knowledge - only cite what's in the snippets.
```

## Testing

### Verify Feature is Enabled

```bash
# Check health endpoint
curl http://localhost:8000/health | jq '.web_search_enabled'
# Should return: true
```

### Test Web-Only Search

**React UI**:
1. Click 🌐 button (should be visible when enabled)
2. Ask: "What is Milvus?"
3. Verify badge shows **🌐 Web** (blue)
4. Verify sources show web URLs

**API**:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is Milvus?"}],
    "force_web_search": true
  }' | jq '.sources[0].source_type'
# Should return: "web_search"
```

### Check Logs

**API Server**:
```bash
# Look for web search activity
[STREAM_WEB_ONLY] 🌐 Forcing web search for: What is Milvus?
[TAVILY] Web search for: Milvus vector database
[TAVILY] Found 5 results (score: 0.7s)
[WEB_CONTEXT] Built context from 5 sources
✓ Web search completed: 5 sources
```

**Browser Console** (React UI):
```javascript
🌐 FORCE WEB SEARCH ACTIVE - Searching web only (no KB)
```

## UI Features

### Source Badges

The React chatbot shows different badges based on source type:

| Badge | Color | Meaning |
|-------|-------|---------|
| ⚡ CACHED | Default | Answer from cache |
| 🔍 KB | Green | Knowledge base search |
| 🌐 Web | Blue | Web search results |

### Control Buttons

| Button | Icon | Function |
|--------|------|----------|
| Cache Toggle | 💾 / 🚫 | Enable/disable response cache |
| Web Search | 🌐 | Force web-only search (per message) |
| Clear Chat | 🗑️ | Clear conversation history |

## Source Format

**Web Search Source**:
```json
{
  "source_type": "web_search",
  "url": "https://milvus.io",
  "title": "Milvus Official Site",
  "snippet": "Milvus is an open-source vector database...",
  "distance": 0.95
}
```

**Knowledge Base Source**:
```json
{
  "source_type": null,
  "document_name": "overview.md",
  "chunk_id": "chunk_123",
  "text": "Milvus provides...",
  "distance": 0.92
}
```

## Performance

| Mode | Latency | Cost |
|------|---------|------|
| KB Only | 1-2s | Free |
| Web Search | 3-6s | Tavily API credits |
| Cached | <50ms | Free |

## Troubleshooting

**Web search button not showing?**
- Check `ENABLE_WEB_SEARCH_SUPPLEMENT=true` in `.env`
- Restart API server
- Verify `/health` endpoint shows `web_search_enabled: true`

**Getting KB results instead of web?**
- Ensure 🌐 button is activated (highlighted)
- Check browser console for `🌐 FORCE WEB SEARCH ACTIVE`
- Verify API logs show `[STREAM_WEB_ONLY]`

**Tavily API errors?**
- Verify API key is valid: `TAVILY_API_KEY=tvly-...`
- Check API quota at https://tavily.com
- Review API server logs for error messages

## Best Practices

✅ **Use Web Search For**:
- Latest news and trends
- Recent product updates
- Current events
- Information not in KB

❌ **Don't Use Web Search For**:
- Technical documentation (use KB)
- Consistent answers (web varies)
- Fast responses (adds 3-5s latency)
- High-volume queries (API costs)

## Notes

- Web search mode uses **web-only** search (bypasses knowledge base)
- LLM is instructed to quote actual web snippets, not training data
- Sources include clickable web URLs
- Button auto-resets after each message
- Browser console shows active mode for debugging
   tail -100 /tmp/api_server.log | grep "web search"
   ```

### Web Search Timeout

Increase timeout in `.env`:
```bash
WEB_SEARCH_TIMEOUT=20  # Increased from 10s
```

### API Key Invalid

Get new key from https://tavily.com and update `.env`:
```bash
TAVILY_API_KEY=your_new_key_here
```

## Comparison: Old vs New Implementation

| Feature | Old (commit a0f1c64) | New (Current) |
|---------|---------------------|---------------|
| Feature flag | ❌ No (always on) | ✅ Yes (`ENABLE_WEB_SEARCH_SUPPLEMENT`) |
| Default state | ON | OFF |
| Web results in sources list | ✅ Yes | ✅ Yes |
| Web results in LLM context | ❌ No | ❌ No |
| Rollback strategy | Code change required | Toggle flag |
| Test coverage | ❌ None | ⏳ Needed |

## Next Steps (Future Enhancements)

### Recommended Improvements

1. **Add Tests:**
   ```python
   def test_web_search_disabled_by_default():
       result = agent.answer_question("What is Milvus?")
       web_sources = [s for s in result.sources if s["source_type"] == "web_search"]
       assert len(web_sources) == 0

   def test_web_search_enabled():
       settings.enable_web_search_supplement = True
       result = agent.answer_question("What is Milvus?")
       web_sources = [s for s in result.sources if s["source_type"] == "web_search"]
       assert len(web_sources) > 0
   ```

2. **Add Web Context to LLM (Optional):**
   - Combine KB context + web context
   - Risk: Hallucination increase
   - Benefit: More comprehensive answers

3. **Smart Fallback:**
   - If KB results < threshold → add web search automatically
   - Example: If only 2 KB sources found, supplement with web

4. **A/B Testing:**
   - Track metrics: answer quality, user satisfaction
   - Compare ON vs OFF groups
   - Decide on default setting based on data

## References

- Original Implementation: commit `a0f1c64`
- Tavily API Docs: https://docs.tavily.com
- Development Checklist: [docs/DEVELOPMENT_CHECKLIST.md](DEVELOPMENT_CHECKLIST.md)
