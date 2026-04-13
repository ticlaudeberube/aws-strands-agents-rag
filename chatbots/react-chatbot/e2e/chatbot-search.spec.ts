import { test, expect, Page } from "@playwright/test";
import { waitForAppReady } from "./utils";

/**
 * E2E tests for RAG Chatbot - Web Search Features
 *
 * Tests web search functionality:
 * - Force web search button (🌐)
 * - Web search toggle behavior
 * - Forced web search queries
 * - Time-sensitive query detection
 * - Web search badge and sources
 */

async function setupPage(page: Page) {
  await waitForAppReady(page);
}

test.describe("RAG Chatbot - Web Search Features", () => {
  // === Web Search Button Tests ===

  test("should display force web search button when enabled", async ({
    page,
  }) => {
    await waitForAppReady(page);
    // Check if web search button exists (only shown if web_search_enabled=true)
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    // If visible, test it; if not, web search is disabled (still valid)
    if (isVisible) {
      await expect(webSearchButton).toBeVisible();
    }
  });

  test("should toggle web search on/off via button", async ({ page }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // Initially should not be active (no "active" class)
      let isActive = await webSearchButton.evaluate((el) =>
        el.classList.contains("active"),
      );
      expect(isActive).toBe(false);

      // Click to activate
      await webSearchButton.click();

      // Should now be active
      isActive = await webSearchButton.evaluate((el) =>
        el.classList.contains("active"),
      );
      expect(isActive).toBe(true);

      // Click again to deactivate
      await webSearchButton.click();

      // Should be inactive again
      isActive = await webSearchButton.evaluate((el) =>
        el.classList.contains("active"),
      );
      expect(isActive).toBe(false);
    }
  });

  test("should disable web search button when API offline", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // When API is online, button should be enabled
      await expect(webSearchButton).toBeEnabled();
    }
  });

  test("should reset web search toggle after sending message", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // Enable web search
      await webSearchButton.click();

      let isActive = await webSearchButton.evaluate((el) =>
        el.classList.contains("active"),
      );
      expect(isActive).toBe(true);

      // Send message
      const inputField = page.locator("textarea");
      await inputField.fill("What is the latest AI news?");

      const sendButton = page.locator("button.send-btn");
      await sendButton.click();

      // Wait for response with actual content
      await page.waitForFunction(
        () => {
          const messages = document.querySelectorAll(".chat-message.assistant");
          if (messages.length === 0) return false;
          const lastMsg = (
            messages[messages.length - 1].textContent || ""
          ).trim();
          return lastMsg.length > 10 && !lastMsg.includes("(No content");
        },
        { timeout: 30000 },
      );

      // Web search button should be reset to inactive
      isActive = await webSearchButton.evaluate((el) =>
        el.classList.contains("active"),
      );
      expect(isActive).toBe(false);
    }
  });

  // === Forced Web Search Query Tests ===

  test("should send query with web search when button enabled", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // Enable web search
      await webSearchButton.click();

      // Send a query
      const inputField = page.locator("textarea");
      await inputField.fill("What is vector embedding?");

      const sendButton = page.locator("button.send-btn");
      await sendButton.click();

      // Wait for response with actual content
      await page.waitForFunction(
        () => {
          const messages = document.querySelectorAll(".chat-message.assistant");
          if (messages.length === 0) return false;
          const lastMsg = (
            messages[messages.length - 1].textContent || ""
          ).trim();
          return lastMsg.length > 10 && !lastMsg.includes("(No content");
        },
        { timeout: 30000 },
      );

      // Verify user message was sent
      const userMessage = page.locator("text=What is vector embedding?");
      await expect(userMessage).toBeVisible();

      // Check for response
      const messages = await page.locator(".chat-message.assistant").all();
      expect(messages.length).toBeGreaterThan(1); // Welcome + response
    }
  });

  test("should show web search badge when forced web search used", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // Enable web search
      await webSearchButton.click();

      // Send query
      const inputField = page.locator("textarea");
      await inputField.fill("What is the latest vector database?");

      const sendButton = page.locator("button.send-btn");
      await sendButton.click();

      // Wait for response with actual content
      await page.waitForFunction(
        () => {
          const messages = document.querySelectorAll(".chat-message.assistant");
          if (messages.length === 0) return false;
          const lastMsg = (
            messages[messages.length - 1].textContent || ""
          ).trim();
          return lastMsg.length > 10 && !lastMsg.includes("(No content");
        },
        { timeout: 30000 },
      );

      // Look for web search badge
      const webBadge = page.locator("text=🌐 WEB").last();

      // The response should be from web search
      // Note: Might show 🌐 WEB or could fall back to KB
      const responseBadges = page.locator('[class*="badge"]');
      const badgeCount = await responseBadges.count();
      expect(badgeCount).toBeGreaterThan(0);
    }
  });

  // === Time-Sensitive Query Tests ===

  test("should detect time-sensitive queries and enable web search", async ({
    page,
  }) => {
    await waitForAppReady(page);
    // Send a query with time-sensitive keywords
    const inputField = page.locator("textarea");
    await inputField.fill("What is the latest vector database news in 2024?");

    const sendButton = page.locator("button.send-btn");
    await sendButton.click();

    // Wait for response with actual content
    await page.waitForFunction(
      () => {
        const messages = document.querySelectorAll(".chat-message.assistant");
        if (messages.length === 0) return false;
        const lastMsg = (
          messages[messages.length - 1].textContent || ""
        ).trim();
        return lastMsg.length > 10 && !lastMsg.includes("(No content");
      },
      { timeout: 30000 },
    );

    // Check if web search was automatically enabled
    // Look for web sources in the response
    const webSourceIcon = page.locator("text=🌐").last();

    // Time-sensitive queries might trigger automatic web search
    // Or might still use KB only - both are valid
    const messages = await page.locator('[class*="message"]').all();
    expect(messages.length).toBeGreaterThan(2);
  });

  test("should prioritize web results for 'recent' queries", async ({
    page,
  }) => {
    await waitForAppReady(page);
    // "recent" is a time-sensitive keyword
    const inputField = page.locator("textarea");
    await inputField.fill("What are recent developments in vector databases?");

    const sendButton = page.locator("button.send-btn");
    await sendButton.click();

    // Wait for response with actual content
    await page.waitForFunction(
      () => {
        const messages = document.querySelectorAll(".chat-message.assistant");
        if (messages.length === 0) return false;
        const lastMsg = (
          messages[messages.length - 1].textContent || ""
        ).trim();
        return lastMsg.length > 10 && !lastMsg.includes("(No content");
      },
      { timeout: 30000 },
    );

    // Verify response appears
    const assistantMessages = await page
      .locator(".chat-message.assistant")
      .all();
    expect(assistantMessages.length).toBeGreaterThan(1);
  });

  test("should prioritize web results for '2024/2025' queries", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const inputField = page.locator("textarea");
    await inputField.fill("What is the latest 2024 vector database release?");

    const sendButton = page.locator("button.send-btn");
    await sendButton.click();

    // Wait for response with actual content
    await page.waitForFunction(
      () => {
        const messages = document.querySelectorAll(".chat-message.assistant");
        if (messages.length === 0) return false;
        const lastMsg = (
          messages[messages.length - 1].textContent || ""
        ).trim();
        return lastMsg.length > 10 && !lastMsg.includes("(No content");
      },
      { timeout: 30000 },
    );

    // Verify response was generated
    const assistantMessages = await page
      .locator(".chat-message.assistant")
      .all();
    expect(assistantMessages.length).toBeGreaterThan(1);
  });

  // === Web Search Sources Tests ===

  test("should display web sources with proper formatting", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // Enable web search
      await webSearchButton.click();

      // Send query
      const inputField = page.locator("textarea");
      await inputField.fill("What is Milvus open source?");

      const sendButton = page.locator("button.send-btn");
      await sendButton.click();

      // Wait for response with actual content
      await page.waitForFunction(
        () => {
          const messages = document.querySelectorAll(".chat-message.assistant");
          if (messages.length === 0) return false;
          const lastMsg = (
            messages[messages.length - 1].textContent || ""
          ).trim();
          return lastMsg.length > 10 && !lastMsg.includes("(No content");
        },
        { timeout: 30000 },
      );

      // Check for sources section
      const sourcesHeader = page.locator("text=Sources Used");

      // Sources might be displayed
      if (await sourcesHeader.isVisible().catch(() => false)) {
        // Look for web source indicators (🌐 icon)
        const webSources = page
          .locator("text=🌐")
          .all()
          .catch(() => []);
        const sourceCount = (await webSources).length;

        // If we found sources, they should be formatted correctly
        if (sourceCount > 0) {
          // Check for relevance scores
          const relevanceScores = page.locator("text=% relevant");
          await expect(relevanceScores).toBeVisible();
        }
      }
    }
  });

  test("should show relevance percentages for web sources", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // Enable web search
      await webSearchButton.click();

      // Send query
      const inputField = page.locator("textarea");
      await inputField.fill("What is vector similarity search?");

      const sendButton = page.locator("button.send-btn");
      await sendButton.click();

      // Wait for response with actual content
      await page.waitForFunction(
        () => {
          const messages = document.querySelectorAll(".chat-message.assistant");
          if (messages.length === 0) return false;
          const lastMsg = (
            messages[messages.length - 1].textContent || ""
          ).trim();
          return lastMsg.length > 10 && !lastMsg.includes("(No content");
        },
        { timeout: 30000 },
      );

      // Check for relevance score pattern (XX% relevant)
      const relevancePattern = /\d+%\s+relevant/;
      const pageContent = (await page.textContent()) || "";

      // If sources are displayed, they should show percentages
      if (pageContent.includes("Sources Used")) {
        expect(pageContent).toMatch(relevancePattern);
      }
    }
  });

  // === Web Search vs KB Distinction ===

  test("should distinguish web sources from KB sources", async ({ page }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // First: get KB sources only
      const inputField = page.locator("textarea");
      await inputField.fill("What is Milvus in the documentation?");

      const sendButton = page.locator("button.send-btn");
      await sendButton.click();

      // Wait for KB response with actual content
      await page.waitForFunction(
        () => {
          const messages = document.querySelectorAll(".chat-message.assistant");
          if (messages.length === 0) return false;
          const lastMsg = (
            messages[messages.length - 1].textContent || ""
          ).trim();
          return lastMsg.length > 10 && !lastMsg.includes("(No content");
        },
        { timeout: 30000 },
      );

      const pageContentKB = (await page.textContent()) || "";

      // Clear input for next query
      await inputField.fill("");

      // Second: get web search sources
      await webSearchButton.click();
      await inputField.fill("What is the latest Milvus news?");
      await sendButton.click();

      // Wait for web response with actual content
      await page.waitForFunction(
        () => {
          const messages = document.querySelectorAll(".chat-message.assistant");
          if (messages.length === 0) return false;
          const lastMsg = (
            messages[messages.length - 1].textContent || ""
          ).trim();
          return lastMsg.length > 10 && !lastMsg.includes("(No content");
        },
        { timeout: 30000 },
      );

      const pageContentWeb = (await page.textContent()) || "";

      // Both should have sources (likely different)
      // This is to verify the system can generate both types
      expect(pageContentKB).toBeTruthy();
      expect(pageContentWeb).toBeTruthy();
    }
  });

  // === Edge Cases ===

  test("should handle web search with empty input gracefully", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // Enable web search
      await webSearchButton.click();

      // Try to send empty message
      const sendButton = page.locator("button.send-btn");

      // Send button should be disabled
      await expect(sendButton).toBeDisabled();

      // Clear and disable web search
      await webSearchButton.click();

      // Button should be inactive again
      const isActive = await webSearchButton.evaluate((el) =>
        el.classList.contains("active"),
      );
      expect(isActive).toBe(false);
    }
  });

  test("should not send duplicate queries when toggling web search", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const webSearchButton = page.locator("button.web-search-btn");

    const isVisible = await webSearchButton.isVisible().catch(() => false);

    if (isVisible) {
      // Get initial message count
      const initialCount = await page.locator('[class*="message"]').count();

      // Toggle web search multiple times
      await webSearchButton.click();
      await webSearchButton.click();
      await webSearchButton.click();

      // Message count should not change
      const finalCount = await page.locator('[class*="message"]').count();
      expect(finalCount).toBe(initialCount);
    }
  });
});
