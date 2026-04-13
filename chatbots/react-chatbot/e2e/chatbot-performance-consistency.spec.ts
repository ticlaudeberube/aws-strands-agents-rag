import { test, expect } from '@playwright/test';

test.describe('RAG Chatbot - Performance & Badge Consistency (Updated)', () => {
  test('should maintain badge consistency across response types', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Test 1: Fresh Knowledge Base Response
    await inputField.fill('What is vector quantization in Milvus?');
    await sendButton.click();
    
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    // Should show KB badge
    const kbBadge = page.locator('.timing-info .generated-badge, :text("🔍 KB")').last();
    await expect(kbBadge).toBeVisible();
    
    // Test 2: Cached Response (same query)
    await inputField.fill('What is vector quantization in Milvus?');
    await sendButton.click();
    
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 30000 });
    
    // Should show CACHED badge or at least maintain consistency
    const lastBadge = page.locator('.timing-info span').last();
    await expect(lastBadge).toBeVisible();
    
    const badgeText = await lastBadge.textContent();
    expect(badgeText).toMatch(/⚡ CACHED|🔍 KB|🌐 WEB/);
  });

  test('should display timing metadata consistently', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send query and verify timing metadata
    await inputField.fill('Explain Milvus index types');
    await sendButton.click();
    
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    // Verify badge appears
    const badge = page.locator('.timing-info span').last();
    await expect(badge).toBeVisible();
    
    // Check for timing display (⏱️ X.XXs)
    const responseTime = page.locator('.response-time, :text("⏱️")').last();
    if (await responseTime.isVisible()) {
      await expect(responseTime).toContainText('⏱️');
      
      const timeText = await responseTime.textContent();
      // Should match pattern like "⏱️ 2.45s"
      expect(timeText).toMatch(/⏱️\s*\d+\.\d+s/);
    }
    
    // Timing data should be populated
    const timingSection = page.locator('.timing-info').last();
    await expect(timingSection).toBeVisible();
  });

  test('should handle rapid successive queries properly', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    const queries = [
      'What is HNSW index?',
      'How does IVF_FLAT work?', 
      'What is scalar filtering?'
    ];
    
    // Send queries in succession
    for (let i = 0; i < queries.length; i++) {
      const query = queries[i];
      
      await inputField.fill(query);
      await sendButton.click();
      
      // Wait for this response to complete before sending next
      await page.waitForFunction(() => {
        const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
        return input && !input.hasAttribute('disabled');
      }, { timeout: 60000 });
      
      // Verify each response gets appropriate badge
      const badge = page.locator('.timing-info span').last();
      await expect(badge).toBeVisible();
      
      // No badge state pollution between queries
      const badgeText = await badge.textContent();
      expect(badgeText).toMatch(/⚡ CACHED|🔍 KB|🌐 WEB/);
      
      // Interface should remain responsive
      await expect(inputField).toBeEnabled();
      
      // Brief pause between queries
      await page.waitForTimeout(1000);
    }
    
    // All responses should have completed properly
    const allMessages = page.locator('.chat-message.assistant');
    const messageCount = await allMessages.count();
    expect(messageCount).toBeGreaterThan(queries.length); // Welcome + responses
  });

  test('should respond within acceptable time limits', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Measure response time for typical query
    const startTime = Date.now();
    
    await inputField.fill('What is cosine similarity?');
    await sendButton.click();
    
    // Wait for response to complete
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    const endTime = Date.now();
    const responseTime = endTime - startTime;
    
    // Response should complete within 60 seconds (generous limit for CI)
    expect(responseTime).toBeLessThan(60000);
    
    // Should have badge and timing info
    const badge = page.locator('.timing-info span').last();
    await expect(badge).toBeVisible();
    
    // Log performance for debugging
    console.log(`Response completed in ${responseTime}ms`);
  });

  test('should cache responses for improved performance', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    const testQuery = 'What is approximate nearest neighbor search?';
    
    // First query (fresh generation)
    const start1 = Date.now();
    await inputField.fill(testQuery);
    await sendButton.click();
    
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    const time1 = Date.now() - start1;
    
    // Verify first response badge
    const firstBadge = page.locator('.timing-info span').last();
    await expect(firstBadge).toBeVisible();
    
    // Second query (should be cached)
    const start2 = Date.now();
    await inputField.fill(testQuery);
    await sendButton.click();
    
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 30000 });
    
    const time2 = Date.now() - start2;
    
    // Verify second response badge
    const secondBadge = page.locator('.timing-info span').last();
    await expect(secondBadge).toBeVisible();
    
    // Cached response should be faster (or at least not significantly slower)
    expect(time2).toBeLessThanOrEqual(time1 + 5000); // Allow 5s variance for network/processing
    
    console.log(`First query: ${time1}ms, Cached query: ${time2}ms`);
  });

  test('should handle streaming responses without badge issues', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send query that likely triggers streaming
    await inputField.fill('Provide a comprehensive overview of Milvus vector database architecture and features');
    await sendButton.click();
    
    // Badge should appear early in the streaming process
    const badge = page.locator('.timing-info span').last();
    await expect(badge).toBeVisible({ timeout: 10000 });
    
    // Content should stream in progressively
    const messageContent = page.locator('.message-text').last();
    await expect(messageContent).toBeVisible({ timeout: 15000 });
    
    // Wait for streaming to complete
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 90000 });
    
    // Final badge should still be present and correct
    await expect(badge).toBeVisible();
    
    const finalBadgeText = await badge.textContent();
    expect(finalBadgeText).toMatch(/⚡ CACHED|🔍 KB|🌐 WEB/);
    
    // Response should be substantial (streaming completed)
    const finalContent = await messageContent.textContent();
    expect(finalContent?.length || 0).toBeGreaterThan(50);
  });

  test('should maintain interface responsiveness during processing', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    const cacheButton = page.locator('button:text("💾 Cache On")');
    
    // Start a query
    await inputField.fill('Explain vector indexing algorithms in detail');
    await sendButton.click();
    
    // During processing, critical UI elements should show appropriate states
    await expect(inputField).toBeDisabled(); // Input disabled during processing
    await expect(sendButton).toBeDisabled(); // Send button disabled
    await expect(cacheButton).toBeDisabled(); // Cache button disabled
    
    // API Status should remain visible
    const apiStatus = page.locator('text=API Connected');
    await expect(apiStatus).toBeVisible();
    
    // Wait for processing to complete
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 90000 });
    
    // After completion, interface should re-enable
    await expect(inputField).toBeEnabled();
    await expect(cacheButton).toBeEnabled();
    
    // Badge should be present
    const badge = page.locator('.timing-info span').last();
    await expect(badge).toBeVisible();
  });

  test('should handle concurrent badge updates correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Test that badge system doesn't get confused with multiple rapid interactions
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send first query
    await inputField.fill('First test query');
    await sendButton.click();
    
    // Wait for first response
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    // Quickly send second query
    await inputField.fill('Second test query');
    await sendButton.click();
    
    // Wait for second response
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    // Both responses should have proper badges
    const badges = page.locator('.timing-info span');
    const badgeCount = await badges.count();
    expect(badgeCount).toBeGreaterThanOrEqual(2);
    
    // Last badge should be correctly associated with last response
    const lastBadge = badges.last();
    await expect(lastBadge).toBeVisible();
    
    const lastBadgeText = await lastBadge.textContent();
    expect(lastBadgeText).toMatch(/⚡ CACHED|🔍 KB|🌐 WEB/);
  });
});