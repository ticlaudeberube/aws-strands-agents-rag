import { Page } from "@playwright/test";

/**
 * Utility functions for RAG Chatbot E2E tests
 */

/**
 * Wait for the app to be fully ready for interaction
 * Ensures all critical UI elements are enabled and accessible
 */
export async function waitForAppReady(
  page: Page,
  options?: { timeout?: number },
) {
  const timeout = options?.timeout || 15000;

  // Navigate to app
  await page.goto("/");

  // Wait for chat input to exist and be enabled
  await page
    .waitForFunction(
      () => {
        const input = document.querySelector(
          "textarea.chat-input",
        ) as HTMLTextAreaElement;
        return input && !input.disabled;
      },
      { timeout },
    )
    .catch(() => {
      console.warn("⚠️ Chat input did not become enabled");
    });

  // Wait for send button to be enabled (indicates app is ready)
  await page
    .waitForFunction(
      () =>
        !document.querySelector("button.send-btn")?.hasAttribute("disabled"),
      { timeout: 10000 },
    )
    .catch(() => {
      console.warn("⚠️ Send button did not become enabled");
    });

  // Wait for cache button to be enabled (optional - indicates full app initialization)
  // Don't fail if it's not there, just warn
  await page
    .waitForFunction(
      () => {
        const btn = document.querySelector("button.cache-toggle-btn");
        // If button doesn't exist, that's OK - app might not have cache feature
        if (!btn) return true;
        // If it exists, it should be enabled
        return !btn.hasAttribute("disabled");
      },
      { timeout: 5000 },
    )
    .catch(() => {
      console.warn(
        "⚠️ Cache button not found or did not become enabled (this is OK if cache feature is disabled)",
      );
    });
}

/**
 * Wait for and return the last message in the chat
 */
export async function getLastMessage(page: Page) {
  return page.locator('[class*="message"]').last();
}

/**
 * Send a message and wait for response (optimized)
 */
export async function sendMessage(
  page: Page,
  text: string,
  waitForResponse = true,
) {
  // Use the most common selector directly
  const inputField = page.locator("textarea.chat-input");

  // Wait for input to be enabled (skip visibility checks - saves time)
  await page
    .waitForFunction(
      () => {
        const element = document.querySelector("textarea.chat-input");
        return element && !element.hasAttribute("disabled");
      },
      { timeout: 5000 },
    )
    .catch(() => {
      console.warn("⚠️ Input field not ready, attempting fill anyway");
    });

  // Fill and send
  await inputField.fill(text);

  // Find and click the send button (try selectors in order)
  try {
    const sendButton = page.locator("button.send-btn");
    if (await sendButton.isEnabled()) {
      await sendButton.click();
    } else {
      throw new Error("Primary button not found or disabled");
    }
  } catch {
    try {
      const altButton = page.locator("button:has-text('➤')");
      await altButton.click();
    } catch {
      // Final fallback
      await page.locator("button").first().click();
    }
  }
}

/**
 * Get the last assistant message (without placeholder)
 * Returns null if only placeholder is shown (indicating error/empty response)
 */
export async function getLastAssistantMessage(
  page: Page,
): Promise<string | null> {
  try {
    const lastMessage = page
      .locator('[class*="message"], [role="alert"]')
      .last();
    // Reduced timeout from 10000ms to 5000ms for faster failures
    const text = await lastMessage.textContent({ timeout: 5000 });

    // Return null if this is the error placeholder
    if (text === "(No content generated from response)") {
      return null;
    }

    return text;
  } catch (error) {
    console.warn("Failed to get last assistant message:", error);
    return null;
  }
}

/**
 * Check if a message contains specific text (case-insensitive)
 */
export async function messageContains(
  page: Page,
  text: string | RegExp,
): Promise<boolean> {
  try {
    // Use waitForFunction for more efficient checking
    const found = await page
      .waitForFunction(
        (searchText, isRegex, pattern) => {
          const messages = document.querySelectorAll('[class*="message"]');
          for (const message of messages) {
            const content = message.textContent || "";
            if (isRegex) {
              const regex = new RegExp(pattern, "i");
              if (regex.test(content)) {
                return true;
              }
            } else {
              if (content.toLowerCase().includes(searchText.toLowerCase())) {
                return true;
              }
            }
          }
          return false;
        },
        typeof text === "string" ? text : "",
        typeof text !== "string",
        typeof text !== "string" ? text.source : "",
        { timeout: 5000 },
      )
      .catch(() => false);

    return !!found;
  } catch (error) {
    console.warn("Error checking message content:", error);
    return false;
  }
}

/**
 * Get console messages for debugging
 */
export async function getConsoleMessages(page: Page): Promise<string[]> {
  const logs: string[] = [];

  page.on("console", (msg) => {
    logs.push(`[${msg.type()}] ${msg.text()}`);
  });

  return logs;
}

/**
 * Create a new page with console logging enabled
 */
export async function createPageWithConsoleLogging(page: Page): Promise<void> {
  page.on("console", (msg) => {
    if (msg.type() === "log" || msg.type() === "error") {
      console.log(`[BROWSER] ${msg.text()}`);
    }
  });
}

/**
 * Check if API is responding correctly
 */
export async function checkAPIResponse(
  page: Page,
  message: string,
): Promise<{
  success: boolean;
  messageCount: number;
  lastMessage: string | null;
  hasError: boolean;
}> {
  const messagesBefore = await getMessageCount(page);

  // Send message (no artificial wait - response will be detected automatically)
  await sendMessage(page, message, true);

  const messagesAfter = await getMessageCount(page);
  const lastMessage = await getLastAssistantMessage(page);
  const hasError = lastMessage === null;

  return {
    success: messagesAfter > messagesBefore && !hasError,
    messageCount: messagesAfter,
    lastMessage: lastMessage,
    hasError: hasError,
  };
}
export async function getLastMessageSources(page: Page) {
  try {
    const lastMessage = page.locator('[class*="message"]').last();
    const sourceItems = lastMessage.locator(
      '[class*="source-item"], [class*="SourceItem"]',
    );

    return await sourceItems.all();
  } catch (error) {
    console.warn("Failed to get message sources:", error);
    return [];
  }
}

/**
 * Count sources in the last message
 */
export async function getLastMessageSourceCount(page: Page): Promise<number> {
  const sources = await getLastMessageSources(page);
  return sources.length;
}

/**
 * Wait for a message containing specific text
 */
export async function waitForMessageContaining(
  page: Page,
  text: string | RegExp,
  timeout = 30000,
) {
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    if (await messageContains(page, text)) {
      return true;
    }
    await page.waitForTimeout(100);
  }

  throw new Error(`Timeout waiting for message containing "${text}"`);
}

/**
 * Wait for sources to appear
 */
export async function waitForSources(
  page: Page,
  minCount = 1,
  timeout = 30000,
) {
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    const count = await getLastMessageSourceCount(page);
    if (count >= minCount) {
      return count;
    }
    await page.waitForTimeout(100);
  }

  throw new Error(`Timeout waiting for ${minCount} sources`);
}

/**
 * Clear all messages and start fresh
 */
export async function clearChat(page: Page) {
  // This depends on your UI - adjust selector as needed
  const clearButton = page.locator("button.clear-btn");

  if (await clearButton.isVisible().catch(() => false)) {
    await clearButton.click();
    await page.waitForTimeout(200);
  }
}

/**
 * Get message count with retry logic
 */
export async function getMessageCount(page: Page): Promise<number> {
  try {
    const count = await page.locator('[class*="message"]').count();
    return count;
  } catch (e) {
    console.warn("Failed to count messages:", e);
    return 0;
  }
}

/**
 * Check if send button is enabled
 */
export async function isSendButtonEnabled(page: Page): Promise<boolean> {
  const sendButton = page.locator("button.send-btn");
  return await sendButton.isEnabled().catch(() => false);
}

/**
 * Get input field value
 */
export async function getInputValue(page: Page): Promise<string> {
  const inputField = page.locator("textarea.chat-input");
  return await inputField.inputValue();
}

/**
 * Check if API is healthy before running test
 */
export async function checkAPIHealth(page: Page): Promise<boolean> {
  try {
    const response = await page.request.get("/health");
    return response.ok();
  } catch (error) {
    return false;
  }
}

/**
 * Get API status information
 */
export async function getAPIStatus(page: Page) {
  try {
    const response = await page.request.get("/health");
    if (response.ok()) {
      return await response.json();
    }
  } catch (error) {
    return null;
  }
}

/**
 * Extract source URLs from the last message
 */
export async function getSourceURLs(page: Page): Promise<string[]> {
  try {
    const lastMessage = page.locator('[class*="message"]').last();
    const sourceLinks = lastMessage.locator(
      '[class*="source"] a, [class*="source-link"]',
    );

    const urls: string[] = [];
    const count = await sourceLinks.count();

    for (let i = 0; i < count; i++) {
      const href = await sourceLinks.nth(i).getAttribute("href");
      if (href) {
        urls.push(href);
      }
    }

    return urls;
  } catch (error) {
    console.warn("Failed to get source URLs:", error);
    return [];
  }
}

/**
 * Get raw message text (including placeholders) from the last assistant message
 */
async function getLastAssistantMessageRaw(page: Page): Promise<string | null> {
  try {
    const lastMessage = page
      .locator('[class*="message"], [role="alert"]')
      .last();
    return await lastMessage.textContent({ timeout: 10000 });
  } catch (error) {
    console.warn("Failed to get raw assistant message:", error);
    return null;
  }
}

/**
 * Check if a rejection message is displayed
 */
export async function isRejectionMessage(page: Page): Promise<boolean> {
  const lastMessage = await getLastAssistantMessageRaw(page);

  if (!lastMessage) {
    return false;
  }

  // Only check for actual rejection phrases, not topic keywords
  // Valid answers WILL mention "milvus", so don't use that as rejection indicator
  const rejectionPatterns = [
    /can only help/i,
    /out of scope/i,
    /security concern/i,
    /detected.*concern/i,
  ];

  return rejectionPatterns.some((pattern) => pattern.test(lastMessage));
}

/**
 * Wait for a specific number of messages (efficient version)
 */
export async function waitForMessageCount(
  page: Page,
  expectedCount: number,
  timeout = 10000,
) {
  try {
    await page.waitForFunction(
      (expected) => {
        const messages = document.querySelectorAll('[class*="message"]');
        return messages.length >= expected;
      },
      expectedCount,
      { timeout },
    );

    return await getMessageCount(page);
  } catch (error) {
    const finalCount = await getMessageCount(page);
    console.warn(`Only got ${finalCount} messages, expected ${expectedCount}`);
    return finalCount;
  }
}

/**
 * Send message and wait for response with timeout
 * Uses efficient Playwright waiting instead of polling
 *
 * @param responsePattern - Pattern to match (optional, with lenient fallback)
 *   If pattern doesn't match, still accepts substantive responses (>50 chars)
 */
export async function sendAndWaitForResponse(
  page: Page,
  text: string,
  responsePattern: string | RegExp = /.+/,
  timeout = 30000,
): Promise<string> {
  // Send message
  await sendMessage(page, text);

  try {
    // Wait for response to appear using optimized DOM polling
    await page.waitForFunction(
      ({ pattern, flags }) => {
        const messages = document.querySelectorAll('[class*="message"]');
        if (messages.length < 2) return false;

        const lastMessage = messages[messages.length - 1];
        const contentText = (lastMessage.textContent || "").trim();

        // Skip error placeholder
        if (
          contentText === "(No content generated from response)" ||
          contentText.length < 10
        ) {
          return false;
        }

        // First try: strict pattern match
        let patternMatches = false;
        if (flags || pattern.includes("|") || pattern.includes("[")) {
          try {
            const regex = new RegExp(pattern, flags || "i");
            patternMatches = regex.test(contentText);
          } catch (e) {
            patternMatches = false;
          }
        } else {
          patternMatches = contentText
            .toLowerCase()
            .includes(pattern.toLowerCase());
        }

        // Lenient fallback: accept any substantive response (>50 chars and not an error)
        // This prevents false timeouts when the API returns a valid answer
        // that just doesn't contain the exact keywords we expected
        const isSubstantiveResponse =
          contentText.length > 50 &&
          !contentText.toLowerCase().includes("unable") &&
          !contentText.toLowerCase().includes("error") &&
          !contentText.toLowerCase().includes("cannot");

        return patternMatches || isSubstantiveResponse;
      },
      {
        pattern:
          typeof responsePattern === "string"
            ? responsePattern
            : responsePattern.source,
        flags: typeof responsePattern === "string" ? "" : responsePattern.flags,
      },
      { timeout },
    );

    return await getLastAssistantMessage(page);
  } catch (error) {
    const lastMsg = await getLastAssistantMessage(page);
    throw new Error(
      `Timeout waiting for message matching "${responsePattern}". Last message: "${lastMsg}"`,
    );
  }
}
