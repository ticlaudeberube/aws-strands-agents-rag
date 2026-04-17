# Playwright E2E Test Optimization

## Changes Made

This document summarizes the optimization to ensure the Playwright test suite starts the server and client **only once** for all tests.

### 1. **Global Setup File** (`playwright.global-setup.ts`)
- Starts both React dev server and API server before tests run
- Verifies servers are ready with health checks
- Simplifies server lifecycle management
- Provides clear startup logging

### 2. **Updated `playwright.config.ts`**
- Added `globalSetup` configuration pointing to `playwright.global-setup.ts`
- Changed `fullyParallel: true` → `fullyParallel: false` (prevents race conditions during startup)
- Set workers to 4 (parallel test files, not test methods within a file)
- Updated `webServer` timeouts to 120s for slower systems
- Both servers reuse existing instances via `reuseExistingServer`

### 3. **Enhanced Fixtures** (`e2e/fixtures.ts`)
- Added `readyPage` fixture that:
  - Navigates to home page with `waitUntil: "networkidle"`
  - Waits for chatbot to be ready (multiple fallback indicators)
  - Returns a fully initialized page for tests
  - Eliminates duplicate navigation code in `beforeEach` hooks

### 4. **Updated All Test Files**
All test files now use the `readyPage` fixture:
- ✅ `chatbot-basic.spec.ts`
- ✅ `chatbot-cache.spec.ts`
- ✅ `chatbot-advanced.spec.ts`
- ✅ `chatbot-mobile.spec.ts`
- ✅ `chatbot-sources.spec.ts`
- ✅ `chatbot-status.spec.ts`
- ✅ `chatbot-search.spec.ts`
- ✅ `chatbot-qa.spec.ts`
- ✅ `chatbot-performance.spec.ts`

Changes:
- Import: `import { test, expect } from "./fixtures"` (not `@playwright/test`)
- Removed `test.beforeEach` hooks
- Updated test signatures: `async ({ page })` → `async ({ readyPage: page })`

## How It Works

```
┌─────────────────────────────────────┐
│  Global Setup (Once at Start)       │
├─────────────────────────────────────┤
│  • Start npm dev server (port 3000) │
│  • Start API server (port 8000)     │
│  • Verify both are healthy          │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│  Test Execution (Parallel Files)    │
├─────────────────────────────────────┤
│  • Each test gets readyPage fixture │
│  • No server restarts               │
│  • No duplicate page navigation     │
│  • ~4 test files run in parallel    │
└─────────────────────────────────────┘
```

## Benefits

1. **Single Server Startup** - Both servers start once, reused across all test files
2. **No Redundant Navigation** - `readyPage` fixture includes page load logic
3. **Faster Overall Execution** - No per-test server restart or navigation overhead
4. **Cleaner Test Code** - Removed `beforeEach` boilerplate from all files
5. **Better Error Messages** - Global setup logs clearly show startup progress
6. **Race Condition Prevention** - Disabled `fullyParallel` at test level, parallel at file level

## Running Tests

```bash
# Run all tests (servers start once, tests run in parallel)
npx playwright test

# Run specific test file
npx playwright test e2e/chatbot-basic.spec.ts

# Run with UI mode
npx playwright test --ui

# Debug mode (sequential execution)
npm run test:debug
```

## Configuration Details

### webServer Reuse Strategy
- **Development**: `reuseExistingServer: true` - Reuses existing server if on port 3000/8000
- **CI**: `reuseExistingServer: false` - Always starts fresh servers for clean test environment

### Fixture Benefits
The `readyPage` fixture provides a "ready to interact" page:
- ✅ Full page load (`waitUntil: "networkidle"`)
- ✅ Chatbot UI is present
- ✅ Input field is visible and interactive
- ✅ Same initialization for all tests

## Troubleshooting

If servers fail to start:
1. Check ports 3000 and 8000 are not in use: `lsof -i :3000 :8000`
2. Kill existing processes: `kill -9 $(lsof -t -i :3000)`
3. Clear node_modules and reinstall: `rm -rf node_modules && npm install`
4. Check API server health: `curl http://localhost:8000/health`
