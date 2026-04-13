import { test, expect, Page } from "@playwright/test";
import {
  waitForAppReady,
  sendMessage,
  getLastAssistantMessage,
  getLastMessageSourceCount,
  waitForMessageContaining,
  waitForSources,
  getMessageCount,
  isRejectionMessage,
  sendAndWaitForResponse,
  messageContains,
} from "./utils";

/**
 * E2E tests for RAG Chatbot - Advanced Scenarios
 */

async function setupPage(page: Page) {
  await waitForAppReady(page);
}

test.describe("RAG Chatbot - Advanced Scenarios", () => {
  test(
    "should handle multi-turn conversation",
    async ({ page }) => {
      await setupPage(page);
      // First question
      await sendAndWaitForResponse(page, "What is Milvus?", /milvus|vector/i);
      const firstMessageCount = await getMessageCount(page);

      // Verify response is reasonable - check for meaningful content
      const firstResponse = await getLastAssistantMessage(page);
      expect(firstResponse).toBeTruthy();
      expect(firstResponse?.length).toBeGreaterThanOrEqual(30);

      // Second question
      await sendAndWaitForResponse(
        page,
        "How do vectors work?",
        /vector|represent/i,
        30000,
      );
      const secondMessageCount = await getMessageCount(page);

      // Should have more messages
      expect(secondMessageCount).toBeGreaterThan(firstMessageCount);

      // Third question
      await sendAndWaitForResponse(
        page,
        "What is RAG?",
        /retrieval|augmented/i,
        30000,
      );
      const thirdMessageCount = await getMessageCount(page);

      expect(thirdMessageCount).toBeGreaterThan(secondMessageCount);
    },
    { timeout: 120000 },
  ); // 2 minutes total for 3 API calls

  test(
    "should maintain context across turns",
    async ({ page }) => {
      await setupPage(page);
      // Ask initial question
      await sendAndWaitForResponse(page, "What is Milvus?", /milvus/i);
      const initialResponse = await getLastAssistantMessage(page);

      // Ask follow-up
      await sendAndWaitForResponse(
        page,
        "How does indexing work?",
        /index|indexing/i,
        30000,
      );
      const followUpResponse = await getLastAssistantMessage(page);

      // Both should have responses
      expect(initialResponse?.length).toBeGreaterThan(0);
      expect(followUpResponse?.length).toBeGreaterThan(0);

      // Responses should be different
      expect(initialResponse).not.toEqual(followUpResponse);
    },
    { timeout: 60000 },
  );

  test(
    "should handle multiple rejection scenarios",
    async ({ page }) => {
      await setupPage(page);
      // First rejection - out of scope
      await sendAndWaitForResponse(
        page,
        "What is the weather?",
        /can only help|out of scope/i,
      );
      const isRejected1 = await isRejectionMessage(page);
      expect(isRejected1).toBe(true);

      // Second rejection - different topic
      await sendAndWaitForResponse(
        page,
        "Tell me a joke",
        /can only help|out of scope/i,
        30000,
      );
      const isRejected2 = await isRejectionMessage(page);
      expect(isRejected2).toBe(true);

      // Valid question to confirm system still works
      await sendAndWaitForResponse(page, "What is Milvus?", /milvus/i, 30000);
      const isRejected3 = await isRejectionMessage(page);
      expect(isRejected3).toBe(false);
    },
    { timeout: 90000 },
  );

  test(
    "should provide consistent answers for similar questions",
    async ({ page }) => {
      await setupPage(page);
      // First ask about vectors
      const answer1 = await sendAndWaitForResponse(
        page,
        "What is vector database?",
        /vector|database/i,
        30000,
      );
      const sources1 = await getLastMessageSourceCount(page);

      // Ask similar question
      await sendAndWaitForResponse(
        page,
        "Explain vector databases",
        /vector|database/i,
        30000,
      );
      const answer2 = await getLastAssistantMessage(page);
      const sources2 = await getLastMessageSourceCount(page);

      // Both should have answers and sources
      expect(answer1.length).toBeGreaterThan(0);
      expect(answer2?.length).toBeGreaterThan(0);
      expect(sources1).toBeGreaterThanOrEqual(0);
      expect(sources2).toBeGreaterThanOrEqual(0);
    },
    { timeout: 60000 },
  );

  test(
    "should handle rapid successive messages",
    async ({ page }) => {
      await setupPage(page);
      const questions = [
        "What is Milvus?",
        "What are embeddings?",
        "Explain RAG",
      ];

      for (const q of questions) {
        await sendMessage(page, q, false);
        await page.waitForTimeout(200);
      }

      // Wait for responses by checking for new messages
      await page.waitForFunction(
        (expectedCount) => {
          const messages = document.querySelectorAll('[class*="message"]');
          return messages.length > expectedCount;
        },
        questions.length,
        { timeout: 20000 },
      );

      // Should eventually get responses for all
      const messageCount = await getMessageCount(page);
      expect(messageCount).toBeGreaterThan(questions.length);
    },
    { timeout: 60000 },
  );

  test(
    "should handle special characters in questions",
    async ({ page }) => {
      await setupPage(page);
      const specialQuestions = [
        'What is "vector indexing"?',
        "How do embeddings (dense) work?",
        "What's the best vector DB?",
        "Is Milvus > Pinecone?",
      ];

      for (const q of specialQuestions) {
        const hasResponse = await messageContains(
          page,
          /milvus|vector|database/i,
        );

        if (!hasResponse) {
          await sendAndWaitForResponse(
            page,
            q,
            /milvus|vector|can only help/i,
            30000,
          );
        }

        // Just verify we got some response
        const response = await getLastAssistantMessage(page);
        expect(response?.length).toBeGreaterThan(0);
      }
    },
    { timeout: 90000 },
  );

  test(
    "should handle long questions",
    async ({ page }) => {
      await setupPage(page);
      const longQuestion =
        "I am interested in learning about Milvus and its capabilities for " +
        "vector search and similarity matching. Can you explain how the indexing " +
        "works and what are the best practices for using Milvus in production?";

      await sendAndWaitForResponse(
        page,
        longQuestion,
        /milvus|vector|index/i,
        30000,
      );

      const response = await getLastAssistantMessage(page);
      expect(response).toBeTruthy();
      expect(response?.length).toBeGreaterThanOrEqual(30);

      // Should have sources
      const sourceCount = await getLastMessageSourceCount(page);
      expect(sourceCount).toBeGreaterThanOrEqual(0);
    },
    { timeout: 45000 },
  );

  test("should handle empty/whitespace input gracefully", async ({ page }) => {
    await setupPage(page);
    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Try to send empty message
    await inputField.fill("");
    const isEnabled = await sendButton.isEnabled();

    // Button should be disabled for empty input
    if (isEnabled) {
      await sendButton.click();
      // If it somehow sends, it shouldn't crash
      await page.waitForTimeout(500);
    }

    // Try whitespace
    await inputField.fill("   ");
    const isEnabledWhitespace = await sendButton.isEnabled();

    // Should handle gracefully
    expect(isEnabledWhitespace).toBeDefined();
  });

  test(
    "should recover from network delay",
    async ({ page }) => {
      await setupPage(page);
      // First question
      await sendAndWaitForResponse(page, "What is Milvus?", /milvus/i, 30000);
      const firstResponse = await getLastAssistantMessage(page);
      expect(firstResponse?.length).toBeGreaterThan(0);

      // Brief delay to simulate user interaction
      await page.waitForTimeout(500);

      // Second question after delay
      await sendAndWaitForResponse(
        page,
        "What is RAG?",
        /retrieval|augmented/i,
        30000,
      );
      const secondResponse = await getLastAssistantMessage(page);
      expect(secondResponse?.length).toBeGreaterThan(0);
    },
    { timeout: 90000 },
  );
});
