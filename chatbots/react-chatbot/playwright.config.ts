import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright Configuration for RAG Chatbot E2E Tests
 *
 * Comprehensive test suite covering all GUI features:
 * - Basic functionality (messages, UI flows)
 * - Cache management (toggle, bypass, drawer)
 * - Web search integration
 * - Mobile responsiveness
 * - Performance testing
 * - API health monitoring
 * - Source display and navigation
 */
export default defineConfig({
  testDir: "./e2e",

  // Test execution settings
  timeout: 120000, // Increased from 30000 to 120s to accommodate RAG response times
  expect: { timeout: 10000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,

  // Reporter configuration
  reporter: [
    ["html", { outputFolder: "playwright-report" }],
    ["json", { outputFile: "test-results/results.json" }],
    ["line"],
  ],

  // Global test settings
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 15000,
  },

  // Auto-start services before tests
  webServer: [
    {
      command: "npm start",
      port: 3000,
      timeout: 120000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "cd ../.. && python api_server.py",
      port: 8000,
      timeout: 120000,
      reuseExistingServer: true, // Use existing API server
    },
  ],

  // Test projects for different browsers
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },

    // Mobile device testing
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 5"] },
      testMatch: "**/chatbot-mobile.spec.ts", // Mobile-specific tests
    },
    {
      name: "mobile-safari",
      use: { ...devices["iPhone 12"] },
      testMatch: "**/chatbot-mobile.spec.ts", // Mobile-specific tests
    },

    // Performance testing (Chrome only for consistency)
    {
      name: "performance",
      use: { ...devices["Desktop Chrome"] },
      testMatch: "**/chatbot-performance.spec.ts",
    },
  ],

  // Test output directories
  outputDir: "test-results",
});
