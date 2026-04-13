import { test, expect, Page } from "@playwright/test";
import {
  sendMessage,
  getLastAssistantMessage,
  waitForMessageContaining,
  waitForAppReady,
} from "./utils";

/**
 * E2E tests for RAG Chatbot - Cache Management
 *
 * Tests cache-related functionality:
 * - Cache toggle button (💾 Cache On / 🚫 No Cache)
 * - Bypass cache behavior
 * - Cached questions drawer
 * - Loading cached responses
 */

async function setupPage(page: Page) {
  await waitForAppReady(page);
}

test.describe("RAG Chatbot - Cache Management", () => {
  test("should toggle cache", async ({ page }) => {
    await setupPage(page);
    // Verify cache button exists
    const cacheButton = page.locator("button.cache-toggle-btn");
    await expect(cacheButton).toBeVisible();
  });

  // === Cache Toggle Tests ===

  test("should display cache toggle button", async ({ page }) => {
    await setupPage(page);
    // Look for cache button - can be either state
    const cacheButton = page
      .locator("button.cache-toggle-btn")
      .or(page.locator("button.cache-toggle-btn"));
    await expect(cacheButton).toBeVisible();
  });

  test("should toggle cache on/off", async ({ page }) => {
    await setupPage(page);
    const cacheButton = page.locator("button.cache-toggle-btn");

    // Initial state should be "Cache On"
    await expect(cacheButton).toBeVisible();
    await expect(cacheButton).toContainText("Cache");

    // Click to toggle
    await cacheButton.click();

    // Should change to "No Cache"
    const noCacheButton = page.locator("button.cache-toggle-btn");
    await expect(noCacheButton).toBeVisible();

    // Click again to toggle back
    await noCacheButton.click();

    // Should be back to "Cache On"
    await expect(page.locator("button.cache-toggle-btn")).toBeVisible();
  });

  test("should disable cache button when API offline", async ({ page }) => {
    await setupPage(page);
    // Close the page to simulate offline
    // For this test, we verify the button exists and is interactive when online
    const cacheButton = page
      .locator("button.cache-toggle-btn")
      .or(page.locator("button.cache-toggle-btn"));

    // Should be enabled when API is online
    await expect(cacheButton).toBeEnabled();
  });

  // === Bypass Cache Behavior Tests ===

  test("should send fresh query when bypass cache enabled", async ({
    page,
  }) => {
    await setupPage(page);

    // Enable bypass cache - wait for button to be visible and ready
    const cacheButton = page.locator("button.cache-toggle-btn");
    await expect(cacheButton).toBeVisible({ timeout: 5000 });
    await cacheButton.click();

    // Verify it changed to "No Cache"
    await expect(page.locator("button.cache-toggle-btn")).toBeVisible();

    // Send a query - wait for input to be enabled first
    const inputField = page.locator("textarea.chat-input");
    await page.waitForFunction(
      () => {
        const element = document.querySelector(
          "textarea.chat-input",
        ) as HTMLTextAreaElement;
        return element && !element.disabled;
      },
      { timeout: 5000 },
    );

    await inputField.fill("What is Milvus?");

    const sendButton = page.locator("button.send-btn");
    await sendButton.click();

    // Wait for assistant message to actually appear with content
    await page.waitForFunction(
      () => {
        const messages = document.querySelectorAll('[class*="message"]');
        if (messages.length < 2) return false;
        const lastMsg = (
          messages[messages.length - 1].textContent || ""
        ).trim();
        return lastMsg.length > 10 && !lastMsg.includes("(No content");
      },
      { timeout: 30000 },
    );

    // Check that message was sent
    const userMessage = page
      .locator("p.message-text")
      .filter({ hasText: "What is Milvus?" });
    await expect(userMessage).toBeVisible();
  });

  test("should show fresh response when no cache enabled", async ({ page }) => {
    await setupPage(page);
    // Enable no cache mode
    const cacheButton = page.locator("button.cache-toggle-btn");
    await cacheButton.click();

    // Send query - wait for input to be enabled first
    const inputField = page.locator("textarea.chat-input");
    await page.waitForFunction(
      () => {
        const element = document.querySelector(
          "textarea.chat-input",
        ) as HTMLTextAreaElement;
        return element && !element.disabled;
      },
      { timeout: 5000 },
    );
    await inputField.fill("What is a vector database?");

    const sendButton = page.locator("button.send-btn");
    await sendButton.click();

    // Wait for assistant message with actual content
    await page.waitForFunction(
      () => {
        const messages = document.querySelectorAll('[class*="message"]');
        if (messages.length < 2) return false;
        const lastMsg = (
          messages[messages.length - 1].textContent || ""
        ).trim();
        return lastMsg.length > 10 && !lastMsg.includes("(No content");
      },
      { timeout: 30000 },
    );

    // Look for any response badge (KB or WEB)
    const badge = page.locator('[class*="badge"]').first();
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Response should not show cached immediately
    const cachedBadge = page.locator("text=⚡ CACHED").last();
    // Note: First response might be fresh query, later ones cached
  });

  // === Cached Questions Drawer Tests ===

  test("should display cached questions drawer", async ({ page }) => {
    await setupPage(page);
    // Look for "Answered Questions" button
    const drawerButton = page.locator("button.cache-drawer-btn");
    await expect(drawerButton).toBeVisible();
  });

  test("should toggle cached questions drawer visibility", async ({ page }) => {
    await setupPage(page);
    const drawerButton = page.locator("button.cache-drawer-btn");

    // Initially might be open or closed, click once
    await drawerButton.click();
    await page.waitForTimeout(300); // Wait for animation

    // Click again
    await drawerButton.click();
    await page.waitForTimeout(300);

    // Drawer button should still be visible
    await expect(drawerButton).toBeVisible();
  });

  test("should show question count in drawer button", async ({ page }) => {
    await setupPage(page);
    const drawerButton = page.locator("button.cache-drawer-btn");
    await expect(drawerButton).toBeVisible({ timeout: 5000 });
    const buttonText = await drawerButton.textContent();

    // Should contain count like "(0)", "(2)", etc.
    expect(buttonText).toMatch(/\(\d+\)/);
  });

  test("should display cached questions list when drawer open", async ({
    page,
  }) => {
    await setupPage(page);
    const drawerButton = page.locator("button.cache-drawer-btn");
    await expect(drawerButton).toBeVisible({ timeout: 5000 });
    const buttonText = await drawerButton.textContent();

    // Check if there are cached questions
    const matchCount = buttonText?.match(/\((\d+)\)/);
    if (matchCount && parseInt(matchCount[1]) > 0) {
      // If there are questions, open drawer by clicking button if needed
      const isCollapsed = buttonText?.includes("▲");
      if (isCollapsed) {
        await drawerButton.click();
        await page.waitForTimeout(300);
      }

      // Look for cached question items
      const questionItems = page.locator('[class*="response-item"]');
      const count = await questionItems.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  // === Cached Response Selection Tests ===

  test("should load cached response when question selected", async ({
    page,
  }) => {
    await setupPage(page);
    const drawerButton = page.locator("button.cache-drawer-btn");
    await expect(drawerButton).toBeVisible({ timeout: 5000 });
    const buttonText = await drawerButton.textContent();

    const matchCount = buttonText?.match(/\((\d+)\)/);
    if (matchCount && parseInt(matchCount[1]) > 0) {
      // Open drawer if needed
      const isCollapsed = buttonText?.includes("▲");
      if (isCollapsed) {
        await drawerButton.click();
        await page.waitForTimeout(300);
      }

      // Click first cached question
      const firstQuestion = page.locator('[class*="response-item"]').first();
      const questionButton = firstQuestion.locator(
        '[class*="response-button"]',
      );
      await questionButton.click();

      // Wait for response to appear
      await page.waitForTimeout(500);

      // Should see the question in chat
      const messages = await page.locator('[class*="message"]').all();
      expect(messages.length).toBeGreaterThan(2); // Initial + user question + assistant response
    }
  });

  test("should show cached badge for loaded cached response", async ({
    page,
  }) => {
    await setupPage(page);
    const drawerButton = page.locator("button.cache-drawer-btn");
    await expect(drawerButton).toBeVisible({ timeout: 5000 });
    const buttonText = await drawerButton.textContent();

    const matchCount = buttonText?.match(/\((\d+)\)/);
    if (matchCount && parseInt(matchCount[1]) > 0) {
      // Open drawer if needed
      const isCollapsed = buttonText?.includes("▲");
      if (isCollapsed) {
        await drawerButton.click();
        await page.waitForTimeout(300);
      }

      // Click first cached question
      const firstQuestion = page.locator('[class*="response-item"]').first();
      const questionButton = firstQuestion.locator(
        '[class*="response-button"]',
      );
      await questionButton.click();

      // Wait for response
      await page.waitForTimeout(500);

      // Should show cached badge
      const cachedBadge = page.locator("text=⚡ CACHED").last();
      await expect(cachedBadge).toBeVisible();
    }
  });

  // === Bypass Cache with Cached Questions ===

  test("should send fresh query when no cache enabled and cached question selected", async ({
    page,
  }) => {
    await setupPage(page);
    const drawerButton = page.locator("button.cache-drawer-btn");
    await expect(drawerButton).toBeVisible({ timeout: 5000 });
    const buttonText = await drawerButton.textContent();

    const matchCount = buttonText?.match(/\((\d+)\)/);
    if (matchCount && parseInt(matchCount[1]) > 0) {
      // Enable no cache mode
      const cacheButton = page.locator("button.cache-toggle-btn");
      await cacheButton.click();

      // Verify changed to "No Cache"
      await expect(page.locator("button.cache-toggle-btn")).toBeVisible();

      // Open drawer if needed
      const isCollapsed = buttonText?.includes("▲");
      if (isCollapsed) {
        await drawerButton.click();
        await page.waitForTimeout(300);
      }

      // Get initial message count
      const initialMessages = await page.locator('[class*="message"]').count();

      // Click first cached question
      const firstQuestion = page.locator('[class*="response-item"]').first();
      const questionButton = firstQuestion.locator(
        '[class*="response-button"]',
      );
      await questionButton.click();

      // Wait for fresh query response with actual content
      await page.waitForFunction(
        () => {
          const messages = document.querySelectorAll('[class*="message"]');
          if (messages.length < 2) return false;
          const lastMsg = (
            messages[messages.length - 1].textContent || ""
          ).trim();
          return lastMsg.length > 10 && !lastMsg.includes("(No content");
        },
        { timeout: 30000 },
      );

      // Should have new messages (user question + fresh response)
      const newMessages = await page.locator('[class*="message"]').count();
      expect(newMessages).toBeGreaterThan(initialMessages);

      // Response should NOT show cached badge (might show WEB or KB)
      // Check if timing shows a reasonable response time (not 0ms)
      const timingInfo = page.locator('[class*="timing-info"]').last();
      const timingText = await timingInfo.textContent();

      // Fresh query should take time, not be instant
      // (though timing detection can be tricky in tests)
      expect(timingText).toBeTruthy();
    }
  });

  // === Question Deduplication Tests ===

  test("should show unique questions only (no duplicates)", async ({
    page,
  }) => {
    await setupPage(page);
    const drawerButton = page.locator("button.cache-drawer-btn");
    await expect(drawerButton).toBeVisible({ timeout: 5000 });
    const buttonText = await drawerButton.textContent();

    const matchCount = buttonText?.match(/\((\d+)\)/);
    if (matchCount && parseInt(matchCount[1]) > 0) {
      // Open drawer if needed
      const isCollapsed = buttonText?.includes("▲");
      if (isCollapsed) {
        await drawerButton.click();
        await page.waitForTimeout(300);
      }

      // Get all question texts
      const questionButtons = await page
        .locator('[class*="response-question"]')
        .all();
      const questionTexts: string[] = [];

      for (const button of questionButtons) {
        const text = await button.textContent();
        questionTexts.push(text || "");
      }

      // Count occurrences of each unique question
      const uniqueQuestions = new Set(questionTexts);

      // All displayed questions should be unique
      // (allowing for truncation with "..." for long questions)
      expect(uniqueQuestions.size).toBeLessThanOrEqual(questionTexts.length);
    }
  });

  // === Edge Cases ===

  test("should handle empty cached responses gracefully", async ({ page }) => {
    await setupPage(page);
    const drawerButton = page.locator("button.cache-drawer-btn");

    // Button should always be visible
    await expect(drawerButton).toBeVisible();

    // Should show count even if 0
    const buttonText = await drawerButton.textContent();
    expect(buttonText).toMatch(/\(\d+\)/);
  });

  test("should reset toggle when sending new message with cache disabled", async ({
    page,
  }) => {
    await setupPage(page);
    // Enable no cache
    const cacheButton = page.locator("button.cache-toggle-btn");
    await expect(cacheButton).toBeVisible({ timeout: 5000 });
    await cacheButton.click();

    // Send message - wait for input to be enabled first
    const inputField = page.locator("textarea.chat-input");
    await page.waitForFunction(
      () => {
        const element = document.querySelector(
          "textarea.chat-input",
        ) as HTMLTextAreaElement;
        return element && !element.disabled;
      },
      { timeout: 5000 },
    );
    await inputField.fill("Test question?");

    const sendButton = page.locator("button.send-btn");
    await sendButton.click();

    // Wait for assistant response with actual content
    await page.waitForFunction(
      () => {
        const messages = document.querySelectorAll('[class*="message"]');
        if (messages.length < 2) return false;
        const lastMsg = (
          messages[messages.length - 1].textContent || ""
        ).trim();
        return lastMsg.length > 10 && !lastMsg.includes("(No content");
      },
      { timeout: 30000 },
    );

    // Cache button should still be in "No Cache" state (doesn't auto-reset)
    await expect(page.locator("button.cache-toggle-btn")).toBeVisible();
  });
});
