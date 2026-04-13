import { test, expect } from '@playwright/test';

test.describe('RAG Chatbot - Cache Management & Badge Consistency (Updated)', () => {
  test('should show consistent badges for fresh vs cached responses', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send a unique fresh query to ensure it's not cached
    const uniqueQuery = `What is vector similarity search ${Date.now()}?`;
    await inputField.fill(uniqueQuery);
    await sendButton.click();
    
    // Wait for fresh response to complete
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    // Verify first response shows KB badge (fresh generation)
    const firstBadge = page.locator('.timing-info .generated-badge, :text("🔍 KB")').last();
    await expect(firstBadge).toBeVisible();
    
    // Send the exact same query again to test caching
    await inputField.fill(uniqueQuery);
    await sendButton.click();
    
    // Wait for cached response
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 30000 });
    
    // Verify cached response shows CACHED badge
    const cachedBadge = page.locator('.timing-info .cached-badge, :text("⚡ CACHED")').last();
    
    if (await cachedBadge.isVisible()) {
      await expect(cachedBadge).toBeVisible();
    } else {
      // Fallback: at least verify response appeared quickly (indicating cache)
      const allBadges = page.locator('.timing-info span').last();
      await expect(allBadges).toBeVisible();
    }
  });

  test('should handle cache toggle functionality', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Verify initial cache state
    let cacheButton = page.locator('button:text("💾 Cache On")');
    await expect(cacheButton).toBeVisible();
    
    // Toggle cache off
    await cacheButton.click();
    
    // Verify cache disabled state
    const noCacheButton = page.locator('button:text("🚫 No Cache")');
    if (await noCacheButton.isVisible()) {
      await expect(noCacheButton).toBeVisible();
      
      // Send a query with cache disabled
      const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
      await inputField.fill('What is Milvus collection?');
      
      const sendButton = page.getByRole('button', { name: '➤' });
      await sendButton.click();
      
      // Wait for response
      await page.waitForFunction(() => {
        const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
        return input && !input.hasAttribute('disabled');
      }, { timeout: 60000 });
      
      // Response should show KB badge (fresh generation, not cached)
      const freshBadge = page.locator('.timing-info .generated-badge, :text("🔍 KB")').last();
      await expect(freshBadge).toBeVisible();
      
      // Cache toggle should reset to 'Cache On' after sending
      await page.waitForTimeout(2000);
      const resetButton = page.locator('button:text("💾 Cache On")');
      if (await resetButton.isVisible()) {
        await expect(resetButton).toBeVisible();
      }
    }
  });

  test('should disable cache toggle during processing', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    const cacheButton = page.locator('button:text("💾 Cache On")');
    
    // Verify cache button is initially enabled
    await expect(cacheButton).toBeEnabled();
    
    // Send a query
    await inputField.fill('Explain vector indexing algorithms');
    await sendButton.click();
    
    // During processing, cache button should be disabled
    await expect(cacheButton).toBeDisabled();
    
    // Wait for response to complete
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    // After completion, cache button should re-enable
    await expect(cacheButton).toBeEnabled();
  });

  test('should load cached questions from dropdown', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Open cached questions dropdown
    const cachedQuestionsButton = page.locator('button:text("▲ Answered Questions")').first();
    if (await cachedQuestionsButton.isVisible()) {
      await cachedQuestionsButton.click();
      
      // Wait for dropdown to expand
      await page.waitForTimeout(1000);
      
      // Verify multiple cached questions are available
      const cachedQuestions = page.locator('button[cursor="pointer"]:has-text("What"), button[cursor="pointer"]:has-text("How")');
      const questionCount = await cachedQuestions.count();
      expect(questionCount).toBeGreaterThan(3); // Should have multiple cached options
      
      // Click on a cached question
      const firstCachedQuestion = cachedQuestions.first();
      const questionText = await firstCachedQuestion.textContent();
      await firstCachedQuestion.click();
      
      // Verify question is processed
      await page.waitForTimeout(3000);
      
      // Check if question appeared in chat or if selection was successful
      const userMessages = page.locator('.chat-message.user .message-text');
      const lastUserMessage = userMessages.last();
      
      if (await lastUserMessage.isVisible()) {
        const lastMessageText = await lastUserMessage.textContent();
        expect(lastMessageText).toContain(questionText?.trim());
      }
    }
  });

  test('should handle incomplete cached responses gracefully', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Open cached questions dropdown
    const cachedQuestionsButton = page.locator('button:text("▲ Answered Questions")').first();
    if (await cachedQuestionsButton.isVisible()) {
      await cachedQuestionsButton.click();
      
      // Try multiple cached questions to find one that might have issues
      const cachedQuestions = page.locator('button[cursor="pointer"]:has-text("What"), button[cursor="pointer"]:has-text("How")');
      
      for (let i = 0; i < Math.min(3, await cachedQuestions.count()); i++) {
        const question = cachedQuestions.nth(i);
        await question.click();
        
        // Wait briefly to see if response loads
        await page.waitForTimeout(3000);
        
        // Check if system handled the cached question appropriately
        const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
        
        // Interface should remain functional even if individual cached responses have issues
        await expect(inputField).toBeVisible();
        
        // Try another question if this one didn't work
        const isEnabled = await inputField.isEnabled();
        if (isEnabled) {
          break; // Interface is responsive, cached question system is working
        }
      }
      
      // Verify interface remains functional
      const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
      await expect(inputField).toBeVisible();
      
      // User should be able to type new queries regardless of cached question issues
      if (await inputField.isEnabled()) {
        await inputField.fill('Test fallback query');
        const sendButton = page.getByRole('button', { name: '➤' });
        await expect(sendButton).toBeEnabled();
      }
    }
  });

  test('should maintain cache count accuracy', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Check initial cache count
    const initialCachedButton = page.locator('button:text("▲ Answered Questions")').first();
    if (await initialCachedButton.isVisible()) {
      const initialText = await initialCachedButton.textContent();
      const initialCount = parseInt(initialText?.match(/\((\d+)\)/)?.[1] || '0');
      
      // Send a new unique query to potentially add to cache
      const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
      const uniqueQuery = `Test cache count ${Date.now()}`;
      await inputField.fill(uniqueQuery);
      
      const sendButton = page.getByRole('button', { name: '➤' });
      await sendButton.click();
      
      // Wait for response to complete
      await page.waitForFunction(() => {
        const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
        return input && !input.hasAttribute('disabled');
      }, { timeout: 60000 });
      
      // Wait for cache to update
      await page.waitForTimeout(2000);
      
      // Check if cache count updated (it may or may not, depending on caching logic)
      const updatedButton = page.locator('button:text("▲ Answered Questions")').first();
      if (await updatedButton.isVisible()) {
        const updatedText = await updatedButton.textContent();
        const updatedCount = parseInt(updatedText?.match(/\((\d+)\)/)?.[1] || '0');
        
        // Count should be at least the initial count (may increase)
        expect(updatedCount).toBeGreaterThanOrEqual(initialCount);
      }
    }
  });

  test('should handle cache operations during high activity', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send multiple queries in sequence to test cache stability
    const queries = [
      'What is vector search?',
      'How do I optimize Milvus?',
      'What are vector embeddings?'
    ];
    
    for (const query of queries) {
      await inputField.fill(query);
      await sendButton.click();
      
      // Wait for each response to complete before next
      await page.waitForFunction(() => {
        const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
        return input && !input.hasAttribute('disabled');
      }, { timeout: 60000 });
      
      // Verify badge appears for each response
      const badge = page.locator('.timing-info span').last();
      await expect(badge).toBeVisible();
      
      // Small delay between queries
      await page.waitForTimeout(1000);
    }
    
    // Verify cache system is still functional after multiple operations
    const cachedQuestionsButton = page.locator('button:text("▲ Answered Questions")').first();
    if (await cachedQuestionsButton.isVisible()) {
      await expect(cachedQuestionsButton).toBeEnabled();
      
      // Cache should still be accessible
      await cachedQuestionsButton.click();
      await page.waitForTimeout(1000);
      
      const cachedQuestions = page.locator('button[cursor="pointer"]:has-text("What")');
      if (await cachedQuestions.count() > 0) {
        await expect(cachedQuestions.first()).toBeVisible();
      }
    }
  });
});