# Milvus RAG Chatbot - GUI Features & Test Coverage

## Overview

Complete feature list for the React chatbot UI with corresponding Playwright E2E test coverage.

## Features by Category

### 1. Core Chat Functionality

#### 1.1 Message Sending
- **Send Message via Input**: User can type in textarea and send using send button
- **Send Message via Enter**: User can press Enter to send (Shift+Enter for newline)
- **Input Validation**: Send button disabled when input empty
- **Message Display**: User messages appear in chat with "👤" avatar
- **Timestamp**: Each message includes timestamp

#### 1.2 Message Receiving
- **Streaming Responses**: Assistant responses stream in real-time
- **Response Avatar**: Assistant messages show "🤖" avatar
- **Loading State**: Show loading indicator while waiting for response
- **Send Button Disabled**: Send button disabled during loading
- **Auto-scroll**: Chat auto-scrolls to latest message
- **Error Display**: Error messages show "❌ Error:" prefix

#### 1.3 Chat History
- **Initial Welcome**: Shows welcome message on page load
- **Multiple Messages**: Support multiple Q&A exchanges
- **Clear Chat**: Clear button resets conversation (shows welcome message again)
- **Conversation Context**: Previous messages sent to API for context

---

### 2. Response Indicators

#### 2.1 Response Type Badges
- **Cached Badge**: "⚡ CACHED" (from response cache)
- **Web Search Badge**: "🌐 WEB" (from Tavily web search)
- **Knowledge Base Badge**: "🔍 KB" (from Milvus knowledge base)
- **Badge Display**: Appear in timing-info section above response text

#### 2.2 Response Timing
- **Response Time Display**: Shows "⏱️ X.XXs" format
- **Time Accuracy**: Reflects actual response latency
- **Zero-time Detection**: Cached responses show very small or zero time

#### 2.3 Streaming Indicator
- **Animated Dots**: Three dots (. . .) animate while streaming
- **Active During Stream**: Shows only during streaming, not after complete

---

### 3. Source Management

#### 3.1 Sources List Display
- **Sources Header**: "📚 Sources Used (N)" shows count
- **Source Items**: Each source shows as numbered item
- **Relevance Score**: "✓ XX% relevant" displayed for each source
- **Source Icon**: Shows 🌐 icon for web sources, 🔍 for KB sources

#### 3.2 Source Links
- **Clickable Links**: Source URLs are clickable
- **Link Target**: Opens in browser without affecting chat
- **Link Title**: Source title shown as link text
- **Link Types**: Handles KB docs, web articles, LinkedIn posts, YouTube videos

#### 3.3 Source Types
- **Knowledge Base Sources**: From Milvus documentation
  - Show document name in relevance line
  - Icon: 🔍
- **Web Sources**: From Tavily web search
  - Show URL
  - Icon: 🌐
  - Different styling for distinction

---

### 4. Cache Management

#### 4.1 Cache Toggle Button
- **Location**: Top right of chat header
- **States**: 
  - "💾 Cache On" (cache enabled)
  - "🚫 No Cache" (cache bypassed)
- **Functionality**: Toggles `bypassCache` state
- **Disabled When**: API offline

#### 4.2 Bypass Cache Behavior
- **Query Parameter**: Sends `bypass_cache=true` to API
- **Fresh Queries**: Skips response cache, queries LLM+KB
- **Cached Question Selection**: When "No Cache" enabled and cached question selected
  - Should send fresh query (not load cached answer)
  - Should show fresh response with fresh badge/timing
  - Should include web search results if time-sensitive

#### 4.3 Cached Questions Drawer
- **Location**: Bottom of chat
- **Toggle Button**: "▲ Answered Questions (N)" / "▼ Answered Questions (N)"
- **Open/Close**: Click to toggle visibility
- **Count Display**: Shows number of unique cached questions
- **List Content**: Shows deduplicated cached questions

#### 4.4 Cached Response Selection
- **Select Question**: Click on question in list
- **Load Answer**: Loads cached answer with "⚡ CACHED" badge
- **Timing**: Shows "⚡ Cached" with original response time
- **No Cache Override**: If "No Cache" enabled, sends fresh query instead
- **Sources**: Shows original sources or cached sources

---

### 5. Web Search Features

#### 5.1 Force Web Search Button
- **Location**: Chat input area (left of send button)
- **Appearance**: "🌐" button
- **Visibility**: Only shows when `webSearchEnabled=true`
- **States**:
  - Inactive: Normal appearance
  - Active: Highlighted/selected appearance
  - Disabled: When API offline or loading

#### 5.2 Web Search Toggle Behavior
- **Click to Enable**: User can click 🌐 to force web search
- **Active State**: Button shows as "active" when enabled
- **Reset After Send**: Automatically resets to inactive after sending
- **Exclusive Mode**: Forces web-search-only (no knowledge base)

#### 5.3 Time-Sensitive Queries
- **Auto Detection**: Backend detects queries with "latest", "recent", "2024", etc.
- **Auto Web Search**: Backend automatically adds web search even without toggle
- **Context Priority**: Web sources appear first in LLM context
- **Badge Indicator**: Shows "🌐 WEB" badge for auto web search results

#### 5.4 Web Search Results
- **Multiple Sources**: Returns 3 results from Tavily API
- **Relevance Scores**: Shows relevance % for each source
- **Web Source Styling**: Different styling from KB sources
- **Web Icons**: 🌐 icon for web sources

---

### 6. API Status & Connection

#### 6.1 API Status Indicator
- **Location**: Top right (next to cache button)
- **States**:
  - "API Connected" (✓ green dot)
  - "Checking..." (checking on load)
  - "API Offline" (✗ red dot)
- **Status Dot**: Colored indicator dot

#### 6.2 API Error Handling
- **Connection Error**: Shows "API Offline" when fetch fails
- **Error Message**: Displays error text in response
- **Disabled Features**: Input disabled when API offline
- **Reconnection**: User can refresh to reconnect

#### 6.3 Health Check
- **On Mount**: Checks `/health` endpoint on app load
- **Status Update**: Sets API status based on response
- **Web Search Flag**: Reads `web_search_enabled` from health response

---

### 7. UI/UX Features

#### 7.1 Input Field Behavior
- **Textarea**: Multi-line input with auto-expand
- **Placeholder**: "Ask about Milvus..." or custom
- **Disabled State**: Disabled when API offline or loading
- **Focus Management**: Auto-focus on send

#### 7.2 Button States
- **Send Button**:
  - Enabled: When input has text and not loading
  - Disabled: When input empty or loading
  - Tooltip: "Send (Enter)"
- **Web Search Button**:
  - Enabled/Disabled: Based on API status and loading
  - Tooltip: State-dependent message
  - Active State: Visual indication when enabled

#### 7.3 Responsive Layout
- **Chat Container**: Scrollable messages area
- **Fixed Header**: Chat header stays at top
- **Fixed Footer**: Chat input stays at bottom
- **Auto-scroll**: Latest message always visible
- **Mobile Support**: Works on mobile browsers

#### 7.4 Dark/Light Theme
- **Colors**: Blue-based theme for messages
- **Contrast**: Readable text on backgrounds
- **Consistent Styling**: All components match theme
- **Icons**: Unicode emoji for platform independence

---

### 8. Error Handling & Edge Cases

#### 8.1 Empty Response Handling
- **No Content**: Shows "(No content generated from response)" if blank
- **Placeholder Text**: Informs user response was empty
- **Error Not Shown**: Not treated as error, just empty

#### 8.2 Failed Responses
- **API Error**: Shows "❌ Error: [message]"
- **Network Error**: Shows connection error
- **Timeout**: Shows timeout error
- **Recovery**: User can send new message to retry

#### 8.3 Missing Data
- **No Sources**: Valid response with no sources section
- **No Timing**: Messages may not have timing data
- **No Answer**: Graceful handling of missing answer

#### 8.4 Duplicate Handling
- **Question Deduplication**: API returns unique questions only
- **Message Ordering**: Latest responses appear first in cache list

---

### 9. Data Flow & State Management

#### 9.1 Message State
- **Message Structure**: 
  ```javascript
  {
    id: number,
    text: string,
    role: 'user' | 'assistant',
    isStreaming: boolean,
    sources: Array,
    timing: { total_time_ms, is_cached, response_type },
    timestamp: string
  }
  ```

#### 9.2 Response Type Values
- **"cached"**: From response cache
- **"web_search"**: From web search
- **"rag"**: From knowledge base

#### 9.3 Streaming Protocol
- **Format**: Server-Sent Events (SSE)
- **Chunks**: `data: {json}\n\n`
- **Content**: Choices with delta.content
- **Sources**: Sent in final chunk
- **End Marker**: `[STREAM_END]`

#### 9.4 Conversation Context
- **Message Format**: Matches Strands Agent standard
- **Content Blocks**: `{ text: "..." }`
- **Full History**: All previous messages sent with new query
- **Timestamps**: Preserved for each message

---

## Test Coverage Matrix

### Feature → Test Mapping

| Feature | Test File | Test Name | Status |
|---------|-----------|-----------|--------|
| Send message via button | basic.spec.ts | should send user message | ✅ |
| Send message via Enter | basic.spec.ts | should send with Enter key | ✅ |
| Input validation | basic.spec.ts | should disable send button when empty | ✅ |
| Welcome message | basic.spec.ts | should display welcome message | ✅ |
| Loading state | basic.spec.ts | should show loading state | ✅ |
| Auto-scroll | basic.spec.ts | should auto-scroll to latest | ✅ |
| Clear chat | advanced.spec.ts | should clear chat history | ✅ |
| Cached badge | sources.spec.ts | should show cached badge | ✅ |
| Web search badge | sources.spec.ts | should show web search badge | ✅ |
| KB badge | sources.spec.ts | should show KB badge | ✅ |
| Response time display | sources.spec.ts | should display response timing | ✅ |
| Sources list | sources.spec.ts | should display sources | ✅ |
| Relevance scores | sources.spec.ts | should show relevance % | ✅ |
| Clickable links | sources.spec.ts | should have clickable source links | ✅ |
| Cache toggle | cache.spec.ts | **NEW** | ⏳ |
| Bypass cache behavior | cache.spec.ts | **NEW** | ⏳ |
| Cached questions drawer | cache.spec.ts | **NEW** | ⏳ |
| Load cached response | cache.spec.ts | **NEW** | ⏳ |
| Force web search button | search.spec.ts | **NEW** | ⏳ |
| Web search toggle | search.spec.ts | **NEW** | ⏳ |
| Web search forced | search.spec.ts | **NEW** | ⏳ |
| Time-sensitive detection | search.spec.ts | **NEW** | ⏳ |
| API status indicator | status.spec.ts | **NEW** | ⏳ |
| API error handling | status.spec.ts | **NEW** | ⏳ |
| Multi-turn conversation | advanced.spec.ts | should handle multiple exchanges | ✅ |
| Streaming indicator | advanced.spec.ts | should show streaming dots | ✅ |
| Error message display | advanced.spec.ts | should display error messages | ✅ |
| Mobile responsiveness | mobile.spec.ts | **NEW** | ⏳ |
| Duplicate question handling | cache.spec.ts | **NEW** | ⏳ |

---

## New Test Suites Needed

✅ **Existing**: chatbot-basic.spec.ts, chatbot-qa.spec.ts, chatbot-sources.spec.ts, chatbot-advanced.spec.ts

⏳ **Need to Create**:
1. **chatbot-cache.spec.ts** - Cache toggles, bypass cache, cached questions
2. **chatbot-search.spec.ts** - Force web search, web search button, time-sensitive queries
3. **chatbot-status.spec.ts** - API status, error handling, connection states
4. **chatbot-mobile.spec.ts** - Responsive design, mobile interactions
5. **chatbot-performance.spec.ts** - Response times, streaming efficiency

---

## Running All Tests

```bash
# Install dependencies
npm install -D @playwright/test

# Run all E2E tests
npx playwright test e2e --ui

# With HTML report
npx playwright show-report

# Headed mode (see browser)
npx playwright test --headed

# Debug mode
npx playwright test --debug

# Specific test file
npx playwright test e2e/chatbot-cache.spec.ts
```

---

## Key Test Patterns

### 1. Wait for Response
```javascript
// Wait for assistant message to appear
await expect(page.locator('[role="assistant"]')).toBeVisible();
```

### 2. Check Badges
```javascript
// Verify cache badge
await expect(page.locator('⚡ CACHED')).toBeVisible();
```

### 3. Sources Verification
```javascript
// Check sources list
const sources = await page.locator('[data-testid="sources"]').all();
expect(sources.length).toBeGreaterThan(0);
```

### 4. Streaming Check
```javascript
// Wait for streaming dots
await expect(page.locator('.streaming-indicator')).toBeVisible();
```

### 5. Cache Toggle
```javascript
// Toggle cache
await page.click('button:has-text("Cache")');
// Verify button state changed
await expect(page.locator('button:has-text("No Cache")')).toBeVisible();
```

---

## Documentation Updates

- ✅ [PLAYWRIGHT_SETUP.md](#) - Updated with new test locations
- ✅ [chatbots/react-chatbot/e2e/README.md](#) - Updated test coverage matrix
- ⏳ Test fixture documentation
- ⏳ Utility function documentation

