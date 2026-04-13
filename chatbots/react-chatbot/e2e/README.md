# E2E Tests for RAG Chatbot (Playwright)

End-to-end tests for the React chatbot using [Playwright](https://playwright.dev/).

## Overview

Tests are organized into **8 comprehensive suites** covering all GUI features:

### Core Functionality (Existing)
| Suite | Purpose | Test Count |
|-------|---------|-----------|
| **chatbot-basic.spec.ts** | Message sending, input, UI flows | 6+ |
| **chatbot-qa.spec.ts** | In/out-of-scope questions, responses | 5+ |
| **chatbot-sources.spec.ts** | Source display, links, metadata | 5+ |
| **chatbot-advanced.spec.ts** | Complex queries, edge cases | 4+ |

### New Comprehensive Suites (Phase 3)
| Suite | Purpose | Test Count | Features |
|-------|---------|-----------|----------|
| **chatbot-cache.spec.ts** ✨ | Cache management, bypass behavior | 17 | Toggle, drawer, deduplication, badge display |
| **chatbot-search.spec.ts** ✨ | Web search, force search button | 13 | Web search toggle, time-sensitive queries, sources, badges |
| **chatbot-status.spec.ts** ✨ | API health, status indicator | 20 | Connected/Offline states, error handling, recovery |
| **chatbot-mobile.spec.ts** ✨ | Mobile responsive design | 24 | iPhone/Android viewports, touch, keyboard, orientation |
| **chatbot-performance.spec.ts** ✨ | Performance, stress testing | 18 | Response times, streaming, memory, rapid queries |

**Total: 112+ test cases** covering all documented GUI features

### Feature Coverage by Test Suite

See [CHATBOT_GUI_FEATURES.md](../../CHATBOT_GUI_FEATURES.md) for complete feature-to-test mapping:

## Prerequisites

### Install Playwright

```bash
npm install -D @playwright/test
npx playwright install
```

### Services (Auto-Started)

**NEW**: The `playwright.config.ts` is configured to **auto-start both services** before running tests:

1. **React Chatbot** (port 3000) - `npm start`
2. **Python API Server** (port 8001) - `python api_server.py` 

**Manual Start** (optional, if auto-start fails):
```bash
# Terminal 1: React Chatbot
cd chatbots/react-chatbot
npm start

# Terminal 2: Python API Server
cd /Users/claude/Documents/workspace/demos/aws-strands-agents-rag
python api_server.py
```

## Running Tests

### Quick Commands (using npm scripts)

```bash
# Run all E2E tests (auto-starts services)  
npm run test:e2e

# Interactive UI mode
npm run test:e2e:ui

# Specific test suites
npm run test:e2e:basic        # Basic functionality
npm run test:e2e:cache        # Cache management  
npm run test:e2e:mobile       # Mobile responsiveness
npm run test:e2e:performance  # Performance testing
npm run test:e2e:sources      # Source display
npm run test:e2e:search       # Web search
npm run test:e2e:status       # API health

# Specific browsers
npm run test:e2e:chromium     # Chrome
npm run test:e2e:firefox      # Firefox
npm run test:e2e:webkit       # Safari
```

### Direct Playwright Commands

```bash
# Run all tests
npx playwright test

# Run specific test file
npx playwright test e2e/chatbot-basic.spec.ts
npx playwright test e2e/chatbot-cache.spec.ts
npx playwright test e2e/chatbot-mobile.spec.ts
npx playwright test e2e/chatbot-performance.spec.ts
```

### Run tests in specific browser

```bash
# Chromium only
npx playwright test --project=chromium

# Firefox only
npx playwright test --project=firefox

# Safari only
npx playwright test --project=webkit
```

### Run tests in headed mode (see browser)

```bash
npx playwright test --headed
```

### Run tests with debugging

```bash
# Debug mode with inspector
npx playwright test --debug

# Pause on first test
npx playwright test --debug e2e/chatbot-basic.spec.ts
```

### Watch mode (re-run on file changes)

```bash
npx playwright test --watch
```

### Generate test report

```bash
npx playwright test
# Then view the report:
npx playwright show-report
```

## Environment Variables

Configure via `.env` or command line:

```bash
# Custom API base URL (default: http://localhost:8001)
export API_BASE_URL=http://my-api.com

# Custom chatbot URL (default: http://localhost:3000)
# Set in playwright.config.ts baseURL

# Run in CI mode (single worker, retries enabled)
export CI=true
```

## Test Structure

Each test file follows this pattern:

```typescript
test.describe('Feature Group', () => {
  test.beforeEach(async ({ page }) => {
    // Setup before each test
    await page.goto('/');
  });

  test('should do something', async ({ page }) => {
    // Test logic
    await page.fill('input', 'text');
    await expect(page).toContainText('expected');
  });
});
```

## Common Selectors

Based on typical React component structure:

| Element | Selector |
|---------|----------|
| Message input | `input[type="text"]` |
| Send button | `button:has-text("Send")` |
| Messages container | `[class*="message"]` |
| Source section | `[class*="source"], [class*="Source"]` |
| Loading indicator | `[class*="loading"], [class*="spinner"]` |
| Assistant message | `[role="alert"]` |

## Adjusting Selectors

If tests fail due to selector issues, update them to match your actual component structure:

```typescript
// Instead of:
await page.locator('button:has-text("Send")').click();

// Use a more specific selector:
await page.locator('[data-testid="send-button"]').click();

// Or get by role:
await page.locator('role=button[name=/Send/i]').click();
```

## Timeouts

Tests have reasonable timeouts for:
- API calls: **30 seconds** (configurable via `TEST_TIMEOUT`)
- Page interactions: **5 seconds** (default)
- Service startup: **5 seconds** (configured in `playwright.config.ts`)

Adjust timeouts in individual tests if needed:

```typescript
await expect(page).toContainText('text', { timeout: 15000 }); // 15 seconds
```

## Debugging Failed Tests

### View test output and steps
```bash
# View detailed test output
npx playwright test --reporter=list

# Show full trace of failed tests
npx playwright test --reporter=html
npx npx playwright show-report
```

## New Test Suites (Phase 3) - Detailed Overview

### chatbot-cache.spec.ts (17 tests) ✨
**Tests cache management and bypass behavior**

Features tested:
- Cache toggle button (display, enable/disable, offline handling)
- Cache bypass behavior (fresh query, response badges)
- Cached questions drawer (display, toggle, visibility)
- Response selection with cached content
- Deduplication verification
- Edge cases (state persistence, offline behavior)

Run: `npx playwright test e2e/chatbot-cache.spec.ts`

### chatbot-search.spec.ts (13 tests) ✨
**Tests web search functionality**

Features tested:
- Web search button (🌐) display and toggle
- Force web search behavior
- Time-sensitive query detection (latest, recent, 2024+)
- Web search vs KB source distinction
- Web source formatting (badges, relevance percentages)
- Edge cases (empty input, duplicate prevention)

Run: `npx playwright test e2e/chatbot-search.spec.ts`

### chatbot-status.spec.ts (20 tests) ✨
**Tests API health checking and status indicators**

Features tested:
- API status indicator (Connected/Checking/Offline)
- Health check on app mount
- Web search capability detection
- Button disabling when offline
- Error handling and connection recovery
- Status updates during conversation
- Real-time status monitoring

Run: `npx playwright test e2e/chatbot-status.spec.ts`

### chatbot-mobile.spec.ts (24 tests) ✨
**Tests mobile and responsive design**

Viewports tested:
- iPhone 12/13 (390x844)
- Android phones (360x720)
- Tablets (768x1024)

Features tested:
- Layout adaptation (stacked buttons, responsive)
- Touch interactions (focus, tap, scroll, swipe)
- Mobile keyboard handling
- Scroll behavior and auto-scroll
- Orientation changes (portrait ↔ landscape)
- Button sizing (44x44px touch targets)
- Font sizes for readability
- Complete user flows on mobile

Run: `npx playwright test e2e/chatbot-mobile.spec.ts`

### chatbot-performance.spec.ts (18 tests) ✨
**Tests performance and stress scenarios**

Performance metrics:
- Response time (<15 seconds for typical queries)
- Streaming efficiency and chunking
- Memory stability (no leaks with 5+ messages)
- Scroll performance without lag
- UI responsiveness during streaming
- Auto-scroll performance

Load testing:
- Rapid query handling (multiple queries immediately)
- Burst handling (10 messages in sequence)
- Cache performance (repeat queries faster)
- Error recovery speed

Run: `npx playwright test e2e/chatbot-performance.spec.ts`

## Test Organization Best Practices

### Running Tests by Category

```bash
# Run all core functionality tests (fast, ~2 min)
npx playwright test --grep "@core|basic|qa|sources|advanced"

# Run all new comprehensive tests (slower, ~5 min)
npx playwright test --grep "@new|cache|search|status|mobile|performance"

# Run critical path only (happy path, ~1 min)
npx playwright test --grep "@critical"

# Run mobile tests only
npx playwright test --grep "mobile"

# Run performance tests only
npx playwright test --grep "performance"
```

### Test Execution Order

For CI/CD pipelines, recommended order:

```bash
# Stage 1: Basic smoke tests (fail fast)
npx playwright test e2e/chatbot-basic.spec.ts

# Stage 2: Core functionality
npx playwright test e2e/chatbot-qa.spec.ts e2e/chatbot-sources.spec.ts

# Stage 3: Feature-specific (cache, search, status)
npx playwright test e2e/chatbot-cache.spec.ts e2e/chatbot-search.spec.ts e2e/chatbot-status.spec.ts

# Stage 4: Extended coverage (mobile, performance, advanced)
npx playwright test e2e/chatbot-mobile.spec.ts e2e/chatbot-performance.spec.ts e2e/chatbot-advanced.spec.ts
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Playwright E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18
      
      # Install dependencies
      - run: npm ci
      - run: npx playwright install
      
      # Start API and chatbot (or use docker-compose)
      - run: |
          cd chatbots/react-chatbot
          npm install
          npm start &
          cd ../..
          python api_server.py &
          sleep 3
      
      # Run tests
      - run: npx playwright test e2e/
      
      # Upload reports
      - uses: actions/upload-artifact@v3
        if: always()
        with:
          name: playwright-report
          path: playwright-report/
```

## Common Issues and Fixes

### Issue: Tests timing out waiting for API
**Solution**: Ensure API server is running on port 8001
```bash
python api_server.py
```

### Issue: Selectors not finding elements
**Solution**: Update selectors to match your component implementation
```typescript
// Add data-testid attributes for reliable selection:
<button data-testid="send-button">Send</button>

// Then use:
await page.locator('[data-testid="send-button"]').click();
```

### Issue: Mobile tests failing on desktop viewport
**Solution**: These are designed for mobile viewports (iPhone, Android). Run separately:
```bash
npx playwright test e2e/chatbot-mobile.spec.ts --project=chromium
```

### Issue: Performance tests flaky on slow CI
**Solution**: Increase timeouts for CI environment
```bash
TEST_TIMEOUT=30000 npx playwright test e2e/chatbot-performance.spec.ts
```

## Coverage Summary

**Features Covered:**
- ✅ Chat core (send/receive, history, UI)
- ✅ Response indicators (badges, timing, streaming)
- ✅ Source management (display, links, metadata)
- ✅ Cache features (toggle, bypass, drawer, deduplication)
- ✅ Web search (force button, time-sensitive, sources)
- ✅ API health (status indicator, error handling, recovery)
- ✅ Mobile design (iPhone, Android, tablet, touch, orientation)
- ✅ Performance (response time, streaming, memory, stress)

**Total Test Coverage: 112+ test cases**

For detailed feature-to-test mapping, see [CHATBOT_GUI_FEATURES.md](../../CHATBOT_GUI_FEATURES.md)
