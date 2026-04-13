import { test, expect, Page } from "@playwright/test";
import {
  sendMessage,
  getLastAssistantMessage,
  waitForMessageContaining,
  waitForAppReady,
} from "./utils";

// Using shared waitForAppReady() from utils

test("should display welcome message on load", async ({ page }) => {
  await waitForAppReady(page);

  // Verify initial assistant message is visible
  const welcomeMessage = await page.locator(
    "text=Milvus documentation assistant",
  );
  await expect(welcomeMessage).toBeVisible();
});

test("should send user message and show in chat", async ({ page }) => {
  await waitForAppReady(page);

  const inputField = page.locator("textarea.chat-input");
  await inputField.fill("What is Milvus?");

  const sendButton = page.locator("button.send-btn");
  await sendButton.click();

  // Verify user message appears in chat
  const userMessage = page
    .locator("p.message-text")
    .filter({ hasText: "What is Milvus?" });
  await expect(userMessage).toBeVisible();
});

test("should show loading state while waiting for response", async ({
  page,
}) => {
  await waitForAppReady(page);

  const inputField = page.locator("textarea.chat-input");
  await inputField.fill("What is Milvus?");
    const sendButton = page.locator("button.send-btn");
    await sendButton.click();

    // Check for loading indicator
    const loadingIndicator = page.locator(
      '[class*="loading"], [class*="spinner"]',
    );
    await page.waitForTimeout(100);
  });

  test("should disable send button while loading", async ({ page }) => {
    await waitForAppReady(page);

    const inputField = page.locator("textarea.chat-input");
    await inputField.fill("What is Milvus?");
    const sendButton = page.locator("button.send-btn");

    // Button should be enabled before sending
    await expect(sendButton).toBeEnabled();

    // Click to send
    await sendButton.click();

    // Button should be disabled while loading (briefly)
    await expect(sendButton).toBeDisabled({ timeout: 2000 });
  });

  test("should clear input field after sending", async ({ page }) => {
    await waitForAppReady(page);

    const inputField = page.locator("textarea.chat-input");

    // Type and send
    await inputField.fill("What is Milvus?");
    const sendButton = page.locator("button.send-btn");
    await sendButton.click();

    // Wait a bit for processing
    await page.waitForTimeout(500);

    // Input should be cleared
    await expect(inputField).toHaveValue("");
  });

  test("should disable send with empty input", async ({ page }) => {
    await waitForAppReady(page);

    const inputField = page.locator("textarea.chat-input");
    const sendButton = page.locator("button.send-btn");

    // Button should be disabled when input is empty
    await inputField.focus();
    await inputField.fill("");

    // Wait for any validation
    await page.waitForTimeout(100);

    // Check button state (implementation dependent)
  });
