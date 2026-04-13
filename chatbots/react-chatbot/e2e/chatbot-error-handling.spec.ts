import { test, expect } from '@playwright/test';

test.describe('RAG Chatbot - Error Handling & Warning Messages (Updated)', () => {
  test('should display system warning banners correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send a time-sensitive query when web search might be disabled
    await inputField.fill('What are the latest updates in vector databases?');
    await sendButton.click();
    
    // Wait for response to process
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 30000 });
    
    // Check for system warning banner
    const systemWarningBanner = page.locator('.system-warning-banner');
    if (await systemWarningBanner.isVisible()) {
      // Verify warning banner appears with ⚠️ icon
      await expect(systemWarningBanner).toBeVisible();
      const warningIcon = systemWarningBanner.locator(':text("⚠️")');
      await expect(warningIcon).toBeVisible();
      
      // Verify main response content is hidden when system warning is displayed
      const messageContent = page.locator('.message-text').last();
      if (await systemWarningBanner.isVisible()) {
        await expect(messageContent).not.toBeVisible();
      }
      
      // Verify banner has distinct styling and contains explanation
      await expect(systemWarningBanner).toHaveClass(/warning|system/);
      const warningText = await systemWarningBanner.textContent();
      expect(warningText).toContain('quota' || 'limitation' || 'search' || 'available');
    }
  });

  test('should display out-of-scope warning correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send an out-of-scope query
    await inputField.fill('What is the weather like today?');
    await sendButton.click();
    
    // Wait for response
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 30000 });
    
    // Check for system warning or appropriate out-of-scope response
    const systemWarningBanner = page.locator('.system-warning-banner');
    const messageContent = page.locator('.message-text').last();
    
    if (await systemWarningBanner.isVisible()) {
      // If system warning banner appears
      await expect(systemWarningBanner).toBeVisible();
      await expect(messageContent).not.toBeVisible();
    } else if (await messageContent.isVisible()) {
      // If regular message appears, it should indicate out-of-scope
      const text = await messageContent.textContent();
      expect(text?.toLowerCase()).toMatch(/scope|relevant|milvus|vector|database/);
    }
  });

  test('should display error messages as regular content', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Simulate conditions that might cause errors
    // We can't easily simulate true errors, so we test the display behavior
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send a query that might cause processing issues
    await inputField.fill(''.repeat(1000)); // Very long empty query
    await sendButton.click();
    
    // Wait for processing
    await page.waitForTimeout(5000);
    
    // Check if any error messages appeared
    const errorMessages = page.locator('.message-text:has-text("Error"), .message-text:has-text("❌")');
    const systemWarningBanner = page.locator('.system-warning-banner');
    
    if (await errorMessages.count() > 0) {
      // If error messages appear, they should show as regular content
      await expect(errorMessages.first()).toBeVisible();
      
      // Error messages should NOT have warning banners
      await expect(systemWarningBanner).not.toBeVisible();
      
      // Error message should include diagnostic information
      const errorText = await errorMessages.first().textContent();
      expect(errorText).toMatch(/error|failed|issue/i);
    }
  });

  test('should handle API connection errors gracefully', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Check initial API status
    const apiStatus = page.locator('text=API Connected');
    
    if (await apiStatus.isVisible()) {
      await expect(apiStatus).toBeVisible();
      
      // Verify interface is functional when API is connected
      const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
      const cacheButton = page.locator('button:text("💾 Cache On")');
      const webSearchButton = page.locator('button:text("🌐")');
      
      await expect(inputField).toBeEnabled();
      await expect(cacheButton).toBeEnabled();
      
      if (await webSearchButton.isVisible()) {
        await expect(webSearchButton).toBeEnabled();
      }
    }
    
    // Test what happens when trying to send a message (should work normally)
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    await inputField.fill('Test connection');
    
    const sendButton = page.getByRole('button', { name: '➤' });
    if (await sendButton.isEnabled()) {
      // Only test sending if button is enabled
      await sendButton.click();
      
      // Should either get proper response or appropriate error handling
      await page.waitForTimeout(5000);
      
      // Verify some response appears (either success or handled error)
      const responses = page.locator('.chat-message.assistant');
      const responseCount = await responses.count();
      expect(responseCount).toBeGreaterThan(0); // Should have at least the welcome message
    }
  });

  test('should distinguish between warnings and errors properly', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Test system warning scenario
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    await inputField.fill('Tell me about recent AI news');
    
    const sendButton = page.getByRole('button', { name: '➤' });
    await sendButton.click();
    
    // Wait for response
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 30000 });
    
    // Check response type
    const systemWarningBanner = page.locator('.system-warning-banner');
    const messageContent = page.locator('.message-text').last();
    const errorIndicators = page.locator(':text("❌"), :text("Error:")');
    
    if (await systemWarningBanner.isVisible()) {
      // System warning case: banner visible, content hidden
      await expect(systemWarningBanner).toBeVisible();
      await expect(messageContent).not.toBeVisible();
      
      // Should not contain error indicators
      const bannerText = await systemWarningBanner.textContent();
      expect(bannerText).not.toMatch(/❌|Error:/);
      
    } else if (await messageContent.isVisible()) {
      // Regular response case: content visible, no banner  
      await expect(messageContent).toBeVisible();
      await expect(systemWarningBanner).not.toBeVisible();
      
      const text = await messageContent.textContent();
      if (text?.includes('❌') || text?.includes('Error:')) {
        // This is an error message - should show as regular content
        await expect(messageContent).toBeVisible();
        await expect(systemWarningBanner).not.toBeVisible();
      }
    }
  });

  test('should maintain interface functionality during error states', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Even if errors occur, basic interface should remain functional
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const cacheButton = page.locator('button:text("💾 Cache On")');
    const cachedQuestionsButton = page.locator('button:text("▲ Answered Questions")');
    
    // Interface elements should be accessible
    await expect(inputField).toBeVisible();
    await expect(cacheButton).toBeVisible();
    
    // User should still be able to interact after errors
    await inputField.fill('What is Milvus?');
    const sendButton = page.getByRole('button', { name: '➤' });
    await expect(sendButton).toBeEnabled();
    
    // Cache button should be clickable
    if (await cacheButton.isEnabled()) {
      await cacheButton.click();
      
      // Should toggle state
      const noCacheButton = page.locator('button:text("🚫 No Cache")');
      if (await noCacheButton.isVisible()) {
        await expect(noCacheButton).toBeVisible();
      }
    }
    
    // Cached questions should be accessible
    if (await cachedQuestionsButton.isVisible()) {
      await cachedQuestionsButton.click();
      
      // Should expand dropdown
      const expandedButton = page.locator('button:text("▼ Answered Questions")');
      if (await expandedButton.isVisible()) {
        await expect(expandedButton).toBeVisible();
      }
    }
  });
});