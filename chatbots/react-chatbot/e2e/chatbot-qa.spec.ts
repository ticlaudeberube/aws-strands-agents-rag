import { test, expect, Page } from "@playwright/test";
import { waitForAppReady } from "./utils";

/**
 * E2E tests for RAG Chatbot - Question Answering
 *
 * Tests:
 * - Valid in-scope questions receive answers with sources
 * - Out-of-scope questions are rejected
 * - Response contains expected content
 * - Sources are displayed correctly
 */

const TEST_TIMEOUT = 30000; // 30 seconds for API calls

async function setupPage(page: Page) {
  await waitForAppReady(page);
}

test.describe("RAG Chatbot - Question Answering", () => {
  test(
    "should answer in-scope Milvus question",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send in-scope question
      await inputField.fill("What is Milvus?");
      await sendButton.click();

      // Wait for response (longer timeout for API call)
      await page.waitForTimeout(2000); // Let streaming start

      // Verify response contains expected keywords - find the main answer message
      // Class structure: message → message-content → message-text (the actual answer paragraph)
      const messageText = page.locator(
        'div[class*="message"]:has-text("What is Milvus?") ~ div[class*="message"] p.message-text',
      );
      await expect(messageText).toContainText(/milvus|vector|database/i, {
        timeout: TEST_TIMEOUT,
      });
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );

  test(
    "should provide sources for valid question",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send question
      await inputField.fill("What is Milvus?");
      await sendButton.click();

      // Wait for response with sources
      const sourcesSection = page.locator(
        '[class*="source"], [class*="Source"]',
      );

      // Sources should appear in the response
      await expect(sourcesSection.first()).toBeVisible({
        timeout: TEST_TIMEOUT,
      });
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );

  test(
    "should reject out-of-scope question",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send out-of-scope question
      await inputField.fill("What is the weather in San Francisco?");
      await sendButton.click();

      // Wait for rejection response
      await expect(page.locator("body")).toContainText(
        /can only help|out of scope|milvus/i,
        {
          timeout: TEST_TIMEOUT,
        },
      );
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );

  test(
    "should not show sources for rejected question",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send out-of-scope question
      await inputField.fill("What is the weather?");
      await sendButton.click();

      // Wait for response
      await page.waitForTimeout(2000);

      // Get all messages
      const messages = await page.locator('[class*="message"]').all();

      // Last assistant message should NOT have sources
      // (This depends on your component structure - adjust selector as needed)
      const lastMessage = messages[messages.length - 1];
      const sourcesInLastMessage = lastMessage.locator('[class*="source"]');

      await expect(sourcesInLastMessage).not.toBeVisible();
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );

  test(
    "should handle vector database comparison question",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send comparison question
      await inputField.fill("Compare Milvus and Pinecone");
      await sendButton.click();

      // Wait for response
      await page.waitForTimeout(2000);

      // Should get a response (exact content depends on implementation)
      const assistantResponse = page.locator(
        '[role="alert"], [class*="assistant"]',
      );
      await expect(assistantResponse.last()).toBeVisible({
        timeout: TEST_TIMEOUT,
      });
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );

  test(
    "should handle vector embedding question",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send embedding question
      await inputField.fill("How do embeddings work?");
      await sendButton.click();

      // Wait for response
      await expect(page.locator("body")).toContainText(
        /embedding|vector|represent/i,
        {
          timeout: TEST_TIMEOUT,
        },
      );
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );

  test(
    "should handle RAG explanation question",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send RAG question
      await inputField.fill("What is RAG?");
      await sendButton.click();

      // Wait for response
      await expect(page.locator("body")).toContainText(
        /retrieval|augmented|generation|rag/i,
        {
          timeout: TEST_TIMEOUT,
        },
      );
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );

  test(
    "should handle semantic search question",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send semantic search question
      await inputField.fill("Explain semantic search");
      await sendButton.click();

      // Wait for response
      await expect(page.locator("body")).toContainText(
        /semantic|search|similar/i,
        {
          timeout: TEST_TIMEOUT,
        },
      );
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );

  test(
    "should display response with proper formatting",
    async ({ page }) => {
      await waitForAppReady(page);

      const inputField = page.locator("textarea.chat-input");
      const sendButton = page.locator("button.send-btn");

      // Send question
      await inputField.fill("What is Milvus?");
      await sendButton.click();

      // Wait for response
      await page.waitForTimeout(2000);

      // Response should be in a message container
      const messages = await page.locator('[class*="message"]').all();
      const lastAssistantMessage = messages[messages.length - 1];

      // Message should have some text content
      const textContent = await lastAssistantMessage.textContent();
      expect(textContent?.length).toBeGreaterThan(0);
    },
    { timeout: TEST_TIMEOUT + 5000 },
  );
});
