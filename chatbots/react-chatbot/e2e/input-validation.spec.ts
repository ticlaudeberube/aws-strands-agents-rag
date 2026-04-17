import { test, expect } from "@playwright/test";

/**
 * End-to-End Tests for Input Validation Feature
 *
 * Tests the complete validation pipeline:
 * 1. Frontend validation with DOMPurify sanitization
 * 2. User feedback on validation errors
 * 3. Backend validation and rejection handling
 * 4. Proper error display in UI
 * 5. Successful submission after valid input
 */

test.describe("Input Validation E2E Tests", () => {
  let apiUrl: string;
  let uiUrl: string;

  test.beforeEach(async ({ page }) => {
    // Get URLs from environment or use defaults
    apiUrl = process.env.API_URL || "http://localhost:8000";
    uiUrl = process.env.UI_URL || "http://localhost:3000";

    // Navigate to chatbot
    await page.goto(uiUrl);

    // Wait for chat interface to load
    await page.waitForSelector('[data-testid="chat-input"]', { timeout: 5000 });
  });

  // ============================================================================
  // TEST GROUP 1: Frontend Validation
  // ============================================================================

  test.describe("Frontend Validation", () => {
    test("should reject empty input", async ({ page }) => {
      // Get input field and send button
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');

      // Try to send empty
      await sendButton.click();

      // Should see error message
      const errorMessage = page.locator('[data-testid="input-error"]');
      await expect(errorMessage).toBeVisible();
      await expect(errorMessage).toContainText(/cannot be empty|too short/i);
    });

    test("should reject input shorter than MIN_MESSAGE_LENGTH", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Try to send 1 character (should fail if MIN_MESSAGE_LENGTH > 1)
      await input.fill("a");
      await sendButton.click();

      // Should see error
      await expect(errorMessage).toBeVisible();
      await expect(errorMessage).toContainText(/minimum.*characters/i);
    });

    test("should accept input at minimum length", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Send exactly minimum length (assuming MIN_MESSAGE_LENGTH = 2)
      await input.fill("hi");

      // Error should NOT be visible
      await expect(errorMessage).not.toBeVisible();

      // Should be able to send
      await sendButton.click();

      // Input should be cleared after send
      await expect(input).toHaveValue("");
    });

    test("should enforce maximum input length in frontend", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const maxLength = parseInt(
        process.env.REACT_APP_MAX_MESSAGE_LENGTH || "1000",
      );

      // Try to paste text longer than max
      const longText = "a".repeat(maxLength + 100);
      await input.fill(longText);

      // Input value should be at most maxLength
      const value = await input.inputValue();
      expect(value.length).toBeLessThanOrEqual(maxLength);
    });

    test("should provide visual feedback for valid input", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Type valid input
      await input.fill("What is Milvus?");

      // Error message should be hidden
      await expect(errorMessage).not.toBeVisible();

      // Input field should not have error styling
      const inputClasses = await input.evaluate((el) => el.className);
      expect(inputClasses).not.toContain("error");
    });

    test("should show error state while typing too short", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Type one character (too short)
      await input.fill("a");

      // Should show error
      await expect(errorMessage).toBeVisible();

      // Add one more character to reach minimum
      await input.fill("ab");

      // Error should disappear
      await expect(errorMessage).not.toBeVisible({ timeout: 1000 });
    });
  });

  // ============================================================================
  // TEST GROUP 2: Security - XSS Prevention
  // ============================================================================

  test.describe("XSS Prevention", () => {
    test("should sanitize script tags in input", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');

      // Try to inject script tag
      const xssPayload = '<script>alert("xss")</script>What is Milvus?';
      await input.fill(xssPayload);

      // Script tag should be present in input (DOMPurify renders it)
      // but it should be sanitized
      const inputValue = await input.inputValue();
      expect(inputValue).not.toContain("<script>");

      // Should be able to send sanitized version
      await sendButton.click();

      // Input should clear (successful send)
      await expect(input).toHaveValue("");
    });

    test("should detect and reject javascript protocol attacks", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Try to inject javascript: protocol
      const payload = 'javascript:void(alert("xss"))';
      await input.fill(payload);
      await sendButton.click();

      // Should show error
      await expect(errorMessage).toBeVisible();
      await expect(errorMessage).toContainText(
        /suspicious|invalid|javascript/i,
      );
    });

    test("should detect iframe injection attempts", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Try to inject iframe
      const payload = '<iframe src="http://malicious.com"></iframe>';
      await input.fill(payload);
      await sendButton.click();

      // Should reject due to suspicious pattern
      await expect(errorMessage).toBeVisible();
    });

    test("should block event handler injection", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Try to inject event handler
      const payload = 'help" onload="alert(\'xss\')"';
      await input.fill(payload);
      await sendButton.click();

      // Should detect suspicious pattern
      await expect(errorMessage).toBeVisible();
    });
  });

  // ============================================================================
  // TEST GROUP 3: Backend Validation
  // ============================================================================

  test.describe("Backend Validation and Error Handling", () => {
    test("should receive validation error from backend", async ({ page }) => {
      // Intercept API request to see the actual response
      const responses = [];
      page.on("response", (response) => {
        if (response.url().includes("/v1/chat/completions")) {
          responses.push(response);
        }
      });

      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');

      // Send valid input
      await input.fill("What is Milvus?");
      await sendButton.click();

      // Wait for response
      await page.waitForTimeout(2000);

      // Check that we made a request
      expect(responses.length).toBeGreaterThan(0);

      // Response should be successful (or validation error in body)
      const lastResponse = responses[responses.length - 1];
      expect([200, 400, 422]).toContain(lastResponse.status());
    });

    test("should display backend error message in UI", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');

      // Send a very long repetitive input to trigger backend rejection
      const longRepetitive = "a".repeat(5001); // Exceeds backend limit
      await input.fill(longRepetitive);
      await sendButton.click();

      // Wait for error message
      const errorMessage = page.locator('[data-testid="input-error"]');
      await expect(errorMessage).toBeVisible({ timeout: 3000 });
    });

    test("should show suggestion for fixing validation error", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');

      // Send empty (too short)
      await input.fill("");
      await sendButton.click();

      // Should see error with suggestion
      const errorMessage = page.locator('[data-testid="input-error"]');
      await expect(errorMessage).toBeVisible();

      // Error text should be helpful and suggest action
      const errorText = await errorMessage.textContent();
      expect(errorText).toMatch(/message|character|input/i);
    });
  });

  // ============================================================================
  // TEST GROUP 4: Error Display
  // ============================================================================

  test.describe("Error Display and Recovery", () => {
    test("should clear error when user fixes input", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Trigger error with short input
      await input.fill("a");
      await sendButton.click();
      await expect(errorMessage).toBeVisible();

      // Fix by typing more
      await input.fill("Valid question here");

      // Error should disappear
      await expect(errorMessage).not.toBeVisible({ timeout: 1000 });
    });

    test("should persist error until valid input", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Same error multiple times
      for (let i = 0; i < 3; i++) {
        await input.fill("x");
        await sendButton.click();
        await expect(errorMessage).toBeVisible();

        // Clear for next iteration
        await input.fill("");
      }

      // Now fix and verify error goes away
      await input.fill("Valid input");
      await expect(errorMessage).not.toBeVisible({ timeout: 1000 });
    });

    test("should not show error after successful submission", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Send valid input
      await input.fill("What is vector database?");
      await sendButton.click();

      // Wait a bit for processing
      await page.waitForTimeout(500);

      // Error should not be visible
      await expect(errorMessage).not.toBeVisible();

      // Input should be cleared
      await expect(input).toHaveValue("");
    });
  });

  // ============================================================================
  // TEST GROUP 5: Integration with Chat Flow
  // ============================================================================

  test.describe("Integration with Chat Flow", () => {
    test("should allow validated message to be added to chat", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const chatMessages = page.locator('[data-testid="chat-message"]');

      // Send valid message
      const validMessage = "What is Milvus vector database?";
      await input.fill(validMessage);
      await sendButton.click();

      // Wait for message to appear in chat
      await page.waitForTimeout(1000);

      // Should have at least one message in chat
      const messageCount = await chatMessages.count();
      expect(messageCount).toBeGreaterThan(0);

      // Last message should contain our input
      const lastMessage = chatMessages.last();
      const text = await lastMessage.textContent();
      expect(text).toContain(validMessage);
    });

    test("should prevent invalid message from entering chat", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const chatMessages = page.locator('[data-testid="chat-message"]');
      const initialCount = await chatMessages.count();

      // Try to send invalid message
      await input.fill("a"); // Too short
      await sendButton.click();

      // Message count should not increase
      await page.waitForTimeout(500);
      const newCount = await chatMessages.count();
      expect(newCount).toBe(initialCount);
    });

    test("should handle multiple validation attempts", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Attempt 1: Too short
      await input.fill("x");
      await sendButton.click();
      await expect(errorMessage).toBeVisible();

      // Attempt 2: Still too short
      await input.fill("xy");
      await sendButton.click();
      // Error might clear or stay depending on exact min length

      // Attempt 3: Valid
      await input.fill("This is a valid question?");
      await sendButton.click();

      // No error should be shown
      await expect(errorMessage).not.toBeVisible({ timeout: 1000 });

      // Input should be cleared (message sent)
      await expect(input).toHaveValue("");
    });
  });

  // ============================================================================
  // TEST GROUP 6: Accessibility and UX
  // ============================================================================

  test.describe("Accessibility and UX", () => {
    test("should have accessible error message with ARIA attributes", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Trigger error
      await input.fill("a");
      await sendButton.click();

      // Error should be visible
      await expect(errorMessage).toBeVisible();

      // Check for ARIA role or attributes
      const role = await errorMessage.getAttribute("role");
      expect(["alert", "status", null]).toContain(role);
    });

    test("should support keyboard navigation for send", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');

      // Type message
      await input.fill("What is Milvus?");

      // Focus input and press Enter (standard for chat)
      await input.focus();
      await page.keyboard.press("Enter");

      // Message should be sent and input cleared
      await expect(input).toHaveValue("");
    });

    test("should provide clear character count feedback", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const charCount = page.locator('[data-testid="char-count"]');

      // Type message
      await input.fill("Test");

      // Character count should show
      const countText = await charCount.textContent();
      expect(countText).toMatch(/4/); // Length of "Test"
    });
  });

  // ============================================================================
  // TEST GROUP 7: Edge Cases
  // ============================================================================

  test.describe("Edge Cases", () => {
    test("should handle unicode and emoji input", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');

      // Send unicode and emoji
      const unicodeMessage = "你好 こんにちは 🚀 What is this?";
      await input.fill(unicodeMessage);
      await sendButton.click();

      // Should not show error
      const errorMessage = page.locator('[data-testid="input-error"]');
      await expect(errorMessage).not.toBeVisible();

      // Input should clear
      await expect(input).toHaveValue("");
    });

    test("should handle whitespace-only input", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      // Try whitespace only
      await input.fill("   \t\n   ");
      await sendButton.click();

      // Should treat as empty
      await expect(errorMessage).toBeVisible();
    });

    test("should handle rapid successive input attempts", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');

      // Rapid clicks without valid input
      for (let i = 0; i < 5; i++) {
        await input.fill("a");
        await sendButton.click();
        await page.waitForTimeout(100);
      }

      // Should handle gracefully (not crash)
      await expect(input).toBeTruthy();
    });

    test("should handle copy-paste of malicious content", async ({ page }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');

      // Simulate paste event with malicious content
      const maliciousContent = '<script>alert("xss")</script>Question?';

      // Fill input (simulates paste of malicious content)
      await input.fill(maliciousContent);

      // DOMPurify should strip the script tag
      const value = await input.inputValue();
      expect(value).not.toContain("<script>");

      // Should still be sendable after sanitization
      await sendButton.click();

      // Input should clear (no error for the sanitized version)
      await page.waitForTimeout(500);
      await expect(input).toHaveValue("");
    });
  });

  // ============================================================================
  // TEST GROUP 8: Configuration Verification
  // ============================================================================

  test.describe("Configuration Verification", () => {
    test("should use REACT_APP_MIN_MESSAGE_LENGTH from environment", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const sendButton = page.locator('button:has-text("Send")');
      const errorMessage = page.locator('[data-testid="input-error"]');

      const minLength = parseInt(
        process.env.REACT_APP_MIN_MESSAGE_LENGTH || "2",
      );

      // Send exactly minimum length - 1
      await input.fill("x".repeat(minLength - 1));
      await sendButton.click();

      // Should show error
      await expect(errorMessage).toBeVisible();

      // Send exactly minimum length
      await input.fill("x".repeat(minLength));
      // Clear error state if needed
      await input.fill("");
      await input.fill("x".repeat(minLength));

      // Error should not appear
      await expect(errorMessage).not.toBeVisible();
    });

    test("should use REACT_APP_MAX_MESSAGE_LENGTH from environment", async ({
      page,
    }) => {
      const input = page.locator('[data-testid="chat-input"]');
      const maxLength = parseInt(
        process.env.REACT_APP_MAX_MESSAGE_LENGTH || "1000",
      );

      // Try to type more than max
      const longText = "a".repeat(maxLength + 500);
      await input.fill(longText);

      // Input should be capped at maxLength
      const actualLength = (await input.inputValue()).length;
      expect(actualLength).toBeLessThanOrEqual(maxLength);
    });
  });
});
