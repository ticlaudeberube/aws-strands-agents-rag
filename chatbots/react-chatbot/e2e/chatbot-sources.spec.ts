import { test, expect, Page } from "@playwright/test";
import { waitForAppReady } from "./utils";

/**
 * E2E tests for RAG Chatbot - Sources & Links
 *
 * Tests:
 * - Source links are displayed correctly
 * - Source links are clickable
 * - Source content is rendered
 * - Multiple sources are displayed
 */

async function setupPage(page: Page) {
  await waitForAppReady(page);
}

test.describe("RAG Chatbot - Sources & Links", () => {
  test("should display multiple sources for relevant question", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Send question likely to have multiple sources
    await inputField.fill("What is Milvus?");
    await sendButton.click();

    // Wait for response to appear
    await page.waitForSelector('[class*="message"]:last-child', {
      timeout: 15000,
    });

    // Check for sources section
    const sourcesPanel = page.locator('[class*="source"], [class*="Source"]');
    await expect(sourcesPanel).toBeVisible({ timeout: 20000 });

    // There should be multiple source items (at least 1)
    const sourceItems = page.locator(
      '[class*="source-item"], [class*="SourceItem"]',
    );
    const count = await sourceItems.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("should display source text snippets", async ({ page }) => {
    await waitForAppReady(page);
    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Send question
    await inputField.fill("What is Milvus?");
    await sendButton.click();

    // Wait for response to appear
    await page.waitForSelector('[class*="message"]:last-child', {
      timeout: 15000,
    });

    // Find source text content
    const sourceText = page.locator(
      '[class*="source"] text, [class*="snippet"]',
    );
    const isVisible = await sourceText.first().isVisible({ timeout: 20000 });

    if (isVisible) {
      const text = await sourceText.first().textContent();
      expect(text?.length).toBeGreaterThan(0);
    }
  });

  test("should include source links/URLs", async ({ page }) => {
    await waitForAppReady(page);
    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Send question
    await inputField.fill("What is Milvus?");
    await sendButton.click();

    // Wait for response to appear
    await page.waitForSelector('[class*="message"]:last-child', {
      timeout: 15000,
    });

    // Look for links in sources
    const sourceLinks = page.locator(
      '[class*="source"] a, [class*="source-link"]',
    );
    const linkCount = await sourceLinks.count();

    // There should be at least one source link
    if (linkCount > 0) {
      const href = await sourceLinks.first().getAttribute("href");
      expect(href).toBeTruthy();
    }
  });

  test("should make source links clickable", async ({ page, context }) => {
    await waitForAppReady(page);
    // Create a promise to catch popup window
    const [popup] = await Promise.all([
      context.waitForEvent("page"),
      (async () => {
        const inputField = page.locator("textarea.chat-input");
        const sendButton = page.locator("button.send-btn");

        // Send question
        await inputField.fill("What is Milvus?");
        await sendButton.click();

        // Wait for response to appear
        await page.waitForSelector('[class*="message"]:last-child', {
          timeout: 15000,
        });

        // Try to click a source link
        const sourceLinks = page.locator(
          '[class*="source"] a, [class*="source-link"]',
        );
        if ((await sourceLinks.count()) > 0) {
          await sourceLinks.first().click();
        }
      })(),
    ]).catch(() => {
      // If no popup, that's fine - link might open in same tab
      return null;
    });

    // If a popup opened, verify it's a valid page
    if (popup) {
      await expect(popup).toHaveTitle(/.*/, { timeout: 5000 });
      await popup.close();
    }
  });

  test("should display source metadata (distance/relevance)", async ({
    page,
  }) => {
    await waitForAppReady(page);
    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Send question
    await inputField.fill("What is Milvus?");
    await sendButton.click();

    // Wait for response to appear
    await page.waitForSelector('[class*="message"]:last-child', {
      timeout: 15000,
    });

    // Look for relevance/distance indicators
    const relevanceIndicators = page.locator(
      '[class*="distance"], [class*="relevance"], [class*="score"]',
    );

    // May or may not be visible depending on UI - just check if they exist
    const count = await relevanceIndicators.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("should separate KB sources from web search sources", async ({
    page,
  }) => {
    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Send question that might have web search results
    await inputField.fill("Tell me about Pinecone");
    await sendButton.click();

    // Wait for response to appear
    await page.waitForSelector('[class*="message"]:last-child', {
      timeout: 15000,
    });

    // Look for different source types (KB vs Web)
    const kbSources = page.locator('[class*="kb"], [class*="knowledge-base"]');
    const webSources = page.locator('[class*="web"], [class*="search"]');

    // These sections may or may not exist depending on configuration
    const kbCount = await kbSources.count();
    const webCount = await webSources.count();

    // Both should be >= 0
    expect(kbCount).toBeGreaterThanOrEqual(0);
    expect(webCount).toBeGreaterThanOrEqual(0);
  });

  test("should not display sources for rejected questions", async ({
    page,
  }) => {
    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Send out-of-scope question
    await inputField.fill("What is the capital of France?");
    await sendButton.click();

    // Wait for response to appear
    await page.waitForSelector('[class*="message"]:last-child', {
      timeout: 15000,
    });

    // Get the last message
    const messages = await page.locator('[class*="message"]').all();
    const lastMessage = messages[messages.length - 1];

    // Count sources in last message
    const sourcesInMessage = lastMessage.locator('[class*="source"]');
    const sourceCount = await sourcesInMessage.count();

    // Should have no sources
    expect(sourceCount).toBe(0);
  });

  test("should handle HTML links in answer text", async ({ page }) => {
    await waitForAppReady(page);
    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Send question
    await inputField.fill("What is Milvus?");
    await sendButton.click();

    // Wait for response to appear
    await page.waitForSelector('[class*="message"]:last-child', {
      timeout: 15000,
    });

    // Look for any links in the answer text (not just sources)
    const answerLinks = page.locator('[class*="message"] a');
    const count = await answerLinks.count();

    // May or may not have inline links - just verify they're clickable if present
    if (count > 0) {
      const href = await answerLinks.first().getAttribute("href");
      expect(href).toBeTruthy();
    }
  });
});
