# Web Search Integration

## Overview

The RAG system supports web search via Tavily API with multiple modes:

1. **Automatic Fallback** (NEW) - Triggered when cached answer is empty or KB confidence is low
2. **Web-Only Mode** (`force_web_search: true`) - Searches only the web, bypasses knowledge base
3. **User-Explicit Mode** - User clicks the 🌐 button in UI

**Default**: Web search is OFF for normal queries. Feature is automatically triggered on fallback conditions or user request.

## Search Modes

| Mode | Trigger | Sources | Use Case |
|------|---------|---------|----------|
| **Cache** | Normal query | response_cache | Fast retrieval (40ms) |
| **Knowledge Base** | Cache miss or time-sensitive query | Milvus docs only | Technical documentation |
| **Web Fallback** (NEW) | Cache empty OR low KB confidence | Tavily API | Stale/empty cached entries |
| **Web-Only** | 🌐 button or `force_web_search: true` | Tavily API only | Latest trends, news |
| **Bypass Cache** | 🚫 button or `bypass_cache: true` | Fresh KB query | Updated answers |

## Automatic Web Search Fallback (NEW)

The system automatically triggers web search fallback in two scenarios:

### 1. Empty Cached Answer

When a cached response is found but the answer field is empty or blank:
```
User: "What are the latest trends in vector databases?"
    ↓
Cache hit: Found similar question
    ↓
Check answer content: EMPTY
    ↓
Trigger automatic web search
    ↓
Query Tavily API and synthesize answer from web results
```

**Log Example**:
```
[CACHE] Cache hit with similarity: 99.2%
[CACHE] ⚠ Cache hit but answer is EMPTY - triggering web search fallback
[WEB_SEARCH] Searching Tavily for: What are the latest trends...
[TAVILY] Found 5 results (time: 0.7s)
✓ Web search fallback completed successfully
```

### 2. Low Knowledge Base Confidence

When KB retrieval confidence falls below the threshold:
```
User: "Tell me about recent AI developments"
    ↓
KB search performed
    ↓
Check result confidence: 35% (below 50% threshold)
    ↓
Trigger automatic web search
    ↓
Combine KB + web results for comprehensive answer
```

**Configuration**:
```bash
# In .env
WEB_SEARCH_FALLBACK_THRESHOLD=0.5  # 50% KB confidence threshold
```

**When to Adjust**:
- **Lower threshold** (0.3-0.4): Web search triggers less often, prefer KB
- **Higher threshold** (0.6-0.8): Web search triggers more often for uncertain queries
- **Default (0.5)**: Balanced between KB and web sources

### Time-Sensitive Queries

Queries with temporal keywords automatically skip cache and use fresh KB/web retrieval:

**Detected Keywords**:
- Latest, recent, newest, current
- Trends, trending, emerging
- New, upcoming
- 2024, 2025, 2026 (year references)
- Today, this year, this month
- Breaking, just released, recently launched

**Behavior**:
```
User: "What is the latest news on vector databases?"
    ↓
Detect temporal keyword: "latest"
    ↓
Skip response cache (bypass Tier 1)
    ↓
Go directly to fresh KB search (Tier 2)
    ↓
If confidence low, trigger web search (Tier 3)
```

**Benefits**:
- Ensures up-to-date information for current events
- Avoids stale cached answers
- Maintains temporal accuracy

## Setup

### 1. Get Tavily API Key

Sign up at https://tavily.com (free tier available)

### 2. Configure `.env`

```bash
# Enable web search feature
ENABLE_WEB_SEARCH_SUPPLEMENT=true

# Add your Tavily API key
TAVILY_API_KEY=tvly-your-api-key-here

# Web search fallback threshold (0-1), default 0.5
WEB_SEARCH_FALLBACK_THRESHOLD=0.5
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

### Automatic Fallback Flow

**When Triggered**: Cache returns empty answer OR KB confidence is low

1. System detects empty cached answer or weak KB results
2. Sets `enable_web_search_fallback` flag in execution state
3. Proceeds to graph execution with fallback enabled
4. WebSearchClient queries Tavily API (5 results)
5. LLM synthesizes answer from web results
6. Returns answer with web source URLs and timestamps

### Web-Only Mode

**When Triggered**: User clicks 🌐 button or sends `force_web_search: true`

1. Query sent with web search flag
2. Tavily API searches web (5 results)
3. LLM generates answer using **only web snippets**
4. Response includes web URLs as sources
5. Badge shows **🌐 Web** (blue)

### Generic Answer Generation

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
