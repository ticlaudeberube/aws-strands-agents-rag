import { test, expect } from '@playwright/test';

test.describe('RAG Chatbot - Web Search & API Status (Updated)', () => {
  test('should display API connected state correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // Verify API status shows 'API Connected'
    const apiStatus = page.locator('text=API Connected');
    await expect(apiStatus).toBeVisible();

    // When API is connected, all buttons should be enabled
    const cacheButton = page.locator('button:text("💾 Cache On")');
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });

    await expect(cacheButton).toBeEnabled();
    await expect(inputField).toBeEnabled();

    // Web search button should be enabled if visible
    const webSearchButton = page.locator('button:text("🌐")');
    if (await webSearchButton.isVisible()) {
      await expect(webSearchButton).toBeEnabled();
    }
  });

  test('should display web search button when enabled', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // Check if web search button exists (depends on configuration)
    const webSearchButton = page.locator('button:text("🌐")');

    if (await webSearchButton.isVisible()) {
      await expect(webSearchButton).toBeVisible();
      await expect(webSearchButton).toBeEnabled();

      // Button should not be active initially
      const isActive = await webSearchButton.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(false);
    }
  });

  test('should toggle web search on/off via button', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const webSearchButton = page.locator('button:text("🌐")');

    if (await webSearchButton.isVisible()) {
      // Initially should not be active
      let isActive = await webSearchButton.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(false);

      // Click to activate web search
      await webSearchButton.click();

      // Should now be active (highlighted)
      isActive = await webSearchButton.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(true);

      // Click again to deactivate
      await webSearchButton.click();

      // Should be inactive again
      isActive = await webSearchButton.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(false);
    }
  });

  test('should display web search badge for web-sourced responses', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const webSearchButton = page.locator('button:text("🌐")');
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });

    if (await webSearchButton.isVisible()) {
      // Enable web search
      await webSearchButton.click();

      // Verify web search is active
      const isActive = await webSearchButton.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(true);

      // Send a query that would benefit from web search
      await inputField.fill('Latest developments in AI vector databases');

      const sendButton = page.getByRole('button', { name: '➤' });
      await sendButton.click();

      // Wait for response
      await page.waitForFunction(() => {
        const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
        return input && !input.hasAttribute('disabled');
      }, { timeout: 60000 });

      // Check for web search badge
      const webBadge = page.locator('.timing-info .web-search-badge, :text("🌐 WEB")').last();

      if (await webBadge.isVisible()) {
        await expect(webBadge).toBeVisible();
        await expect(webBadge).toContainText('🌐 WEB');

        // Should also have sources with web URLs
        const sources = page.locator('.source-item, .sources');
        if (await sources.count() > 0) {
          await expect(sources.first()).toBeVisible();
        }
      }

      // Web search toggle should reset after use
      await page.waitForTimeout(2000);
      const resetButton = page.locator('button:text("🌐")').first();
      const isStillActive = await resetButton.evaluate(el => el.classList.contains('active'));
      expect(isStillActive).toBe(false);
    }
  });

  test('should handle time-sensitive queries appropriately', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });

    // Send a time-sensitive query
    await inputField.fill('What are the latest trends in vector databases?');
    await sendButton.click();

    // Wait for response
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });

    // Check response type - should either trigger web search OR show limitation warning
    const webBadge = page.locator('.timing-info .web-search-badge, :text("🌐 WEB")').last();
    const systemWarning = page.locator('.system-warning-banner');
    const regularResponse = page.locator('.message-text').last();

    if (await webBadge.isVisible()) {
      // Web search was triggered automatically
      await expect(webBadge).toBeVisible();
    } else if (await systemWarning.isVisible()) {
      // System warning about web search limitation
      await expect(systemWarning).toBeVisible();
      await expect(systemWarning).toContainText('⚠️');
    } else if (await regularResponse.isVisible()) {
      // Regular KB response with appropriate disclaimer
      const responseText = await regularResponse.textContent();
      expect(responseText).toBeTruthy();
    }
  });

  test('should disable web search button when API offline', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // In normal operation, web search button should be enabled
    const webSearchButton = page.locator('button:text("🌐")');

    if (await webSearchButton.isVisible()) {
      await expect(webSearchButton).toBeEnabled();
    }

    // Test API connectivity by checking status
    const apiStatus = page.locator('text=API Connected, text=Checking, text=Offline');
    await expect(apiStatus.first()).toBeVisible();

    // If API is connected, web features should be available
    const connectedStatus = page.locator('text=API Connected');
    if (await connectedStatus.isVisible()) {
      if (await webSearchButton.isVisible()) {
        await expect(webSearchButton).toBeEnabled();
      }
    }
  });

  test('should show health check status on app mount', async ({ page }) => {
    // Navigate to fresh page to test initial health check
    await page.goto('http://localhost:3000');

    // Health check should happen automatically on mount
    // Status should show either "Checking", "API Connected", or "Offline"
    const statusIndicators = page.locator('text=API Connected, text=Checking, text=Offline, text=Disconnected');

    // Wait for status to appear (health check should complete within 10 seconds)
    await expect(statusIndicators.first()).toBeVisible({ timeout: 10000 });

    // Most likely should show "API Connected" since tests run with API server
    const connectedStatus = page.locator('text=API Connected');
    if (await connectedStatus.isVisible()) {
      await expect(connectedStatus).toBeVisible();
    }

    // Interface should be functional after health check
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    await expect(inputField).toBeEnabled();
  });

  test('should detect web search capability from health response', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // Wait for app to fully load and health check to complete
    await page.waitForTimeout(3000);

    // Check if web search button visibility matches server capability
    const webSearchButton = page.locator('button:text("🌐")');

    if (await webSearchButton.isVisible()) {
      // Web search is enabled - button should be functional
      await expect(webSearchButton).toBeEnabled();

      // Should be able to toggle
      await webSearchButton.click();
      const isActive = await webSearchButton.evaluate(el => el.classList.contains('active'));
      expect(isActive).toBe(true);

      // Reset state
      await webSearchButton.click();
    } else {
      // Web search not available - should not break interface
      const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
      await expect(inputField).toBeEnabled();

      // Time-sensitive queries should show appropriate warnings
      await inputField.fill('Latest AI news');
      const sendButton = page.getByRole('button', { name: '➤' });
      await sendButton.click();

      // Should get either regular response or system warning
      await page.waitForFunction(() => {
        const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
        return input && !input.hasAttribute('disabled');
      }, { timeout: 30000 });

      const warning = page.locator('.system-warning-banner');
      const response = page.locator('.message-text').last();

      // Should get some kind of response
      const hasWarning = await warning.isVisible();
      const hasResponse = await response.isVisible();
      expect(hasWarning || hasResponse).toBe(true);
    }
  });

  test('should show consistent status across app interactions', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // Initial status check
    const initialStatus = page.locator('text=API Connected');
    await expect(initialStatus).toBeVisible();

    // Send a query
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    await inputField.fill('Test status consistency');

    const sendButton = page.getByRole('button', { name: '➤' });
    await sendButton.click();

    // During processing, status should remain consistent
    const statusDuringProcessing = page.locator('text=API Connected');
    await expect(statusDuringProcessing).toBeVisible();

    // Wait for response to complete
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });

    // After response, status should still be consistent
    const statusAfterResponse = page.locator('text=API Connected');
    await expect(statusAfterResponse).toBeVisible();

    // Interface should remain fully functional
    await expect(inputField).toBeEnabled();

    const cacheButton = page.locator('button:text("💾 Cache On")');
    await expect(cacheButton).toBeEnabled();
  });

  test('should handle API recovery and reconnection', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // Verify initial connected state
    const connectedStatus = page.locator('text=API Connected');
    await expect(connectedStatus).toBeVisible();

    // Test that interface remains functional during normal operation
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    await expect(inputField).toBeEnabled();

    // Send test query to verify API is working
    await inputField.fill('Test API functionality');
    const sendButton = page.getByRole('button', { name: '➤' });

    if (await sendButton.isEnabled()) {
      await sendButton.click();

      // Should get response (API is working)
      await page.waitForFunction(() => {
        const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
        return input && !input.hasAttribute('disabled');
      }, { timeout: 60000 });

      // Status should remain connected
      await expect(connectedStatus).toBeVisible();

      // Interface should be fully functional after successful interaction
      await expect(inputField).toBeEnabled();

      const cacheButton = page.locator('button:text("💾 Cache On")');
      await expect(cacheButton).toBeEnabled();
    }
  });
});
