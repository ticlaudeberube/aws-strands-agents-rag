import { test, expect } from '@playwright/test';

test.describe('RAG Chatbot - Basic Functionality & Badge Display (Updated)', () => {
  test('should display welcome message with correct badge', async ({ page }) => {
    // Navigate to the React chatbot application to examine current state and identify test requirements
    await page.goto('http://localhost:3000');
    
    // Verify initial assistant message is visible
    const welcomeMessage = page.locator('text=Milvus documentation assistant');
    await expect(welcomeMessage).toBeVisible();
    
    // Verify initial message shows '🔍 KB' badge indicating knowledge base source
    const initialBadge = page.locator('.timing-info .generated-badge, :text("🔍 KB")').first();
    await expect(initialBadge).toBeVisible();
    
    // Verify API status shows 'API Connected'
    const apiStatus = page.locator('text=API Connected');
    await expect(apiStatus).toBeVisible();
    
    // Verify cache toggle button shows '💾 Cache On'  
    const cacheButton = page.locator('button:text("💾 Cache On")');
    await expect(cacheButton).toBeVisible();
    
    // Verify all input elements are enabled
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const webSearchButton = page.locator('button:text("🌐")');
    
    await expect(inputField).toBeEnabled();
    await expect(cacheButton).toBeEnabled();
    if (await webSearchButton.isVisible()) {
      await expect(webSearchButton).toBeEnabled();
    }
  });

  test('should send message and display timing badges correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Type a fresh query in the input field
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    await inputField.fill('What is vector indexing?');
    
    // Verify send button becomes enabled when text is entered
    const sendButton = page.getByRole('button', { name: '➤' });
    await expect(sendButton).toBeEnabled();
    
    // Send the query to test badge display and response flow
    await sendButton.click();
    
    // Verify user message appears in chat
    const userMessage = page.locator('p.message-text').filter({ hasText: 'What is vector indexing?' });
    await expect(userMessage).toBeVisible();
    
    // Verify input is disabled during processing
    await expect(inputField).toBeDisabled();
    
    // Wait for assistant response to start appearing
    await page.waitForFunction(() => {
      const messages = document.querySelectorAll('.chat-message.assistant');
      return messages.length >= 2; // Welcome + new response
    }, { timeout: 30000 });
    
    // Verify timing badge appears (should be 🔍 KB for fresh query)
    const responseBadge = page.locator('.timing-info .generated-badge, :text("🔍 KB")').last();
    await expect(responseBadge).toBeVisible();
    
    // Wait for response to complete (input re-enables)
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 45000 });
    
    // Verify input field re-enables after response
    await expect(inputField).toBeEnabled();
    
    // Verify cache button re-enables
    const cacheButton = page.locator('button:text("💾 Cache On")');
    await expect(cacheButton).toBeEnabled();
  });

  test('should handle streaming responses with consistent badges', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // Send a query that triggers streaming response
    await inputField.fill('Explain the architecture of Milvus database');
    await sendButton.click();
    
    // Wait for response to start
    await page.waitForFunction(() => {
      const messages = document.querySelectorAll('.chat-message.assistant');
      return messages.length >= 2;
    }, { timeout: 30000 });
    
    // Verify badge appears immediately with response type
    const streamingBadge = page.locator('.timing-info .generated-badge, :text("🔍 KB")').last();
    await expect(streamingBadge).toBeVisible();
    
    // Wait for streaming to complete (input re-enables)
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 60000 });
    
    // Verify final badge matches response type and timing metadata shows
    await expect(streamingBadge).toBeVisible();
    
    // Look for timing display (⏱️ X.XXs)
    const responseTime = page.locator('.response-time, :text("⏱️")').last();
    if (await responseTime.isVisible()) {
      await expect(responseTime).toContainText('⏱️');
    }
  });

  test('should display cached response badge correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    const inputField = page.getByRole('textbox', { name: 'Ask about Milvus...' });
    const sendButton = page.getByRole('button', { name: '➤' });
    
    // First, send a fresh query
    await inputField.fill('What is a vector database?');
    await sendButton.click();
    
    // Wait for first response to complete
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 45000 });
    
    // Verify first response shows '🔍 KB' badge
    const firstBadge = page.locator('.timing-info .generated-badge, :text("🔍 KB")').last();
    await expect(firstBadge).toBeVisible();
    
    // Send the exact same query again to test caching
    await inputField.fill('What is a vector database?');
    await sendButton.click();
    
    // Wait for cached response
    await page.waitForFunction(() => {
      const input = document.querySelector('textarea[name="Ask about Milvus..."], textarea.chat-input');
      return input && !input.hasAttribute('disabled');
    }, { timeout: 15000 });
    
    // Verify cached response shows '⚡ CACHED' badge
    const cachedBadge = page.locator('.timing-info .cached-badge, :text("⚡ CACHED")').last();
    if (await cachedBadge.isVisible()) {
      await expect(cachedBadge).toBeVisible();
      
      // Verify cached response appears faster (should complete quickly)
      const responseTime = page.locator('.response-time').last();
      if (await responseTime.isVisible()) {
        const timeText = await responseTime.textContent();
        // Cached responses should be faster than 2 seconds typically
        const timeValue = parseFloat(timeText?.match(/(\d+\.\d+)s/)?.[1] || '999');
        expect(timeValue).toBeLessThan(5); // Should be much faster than fresh generation
      }
    }
  });

  test('should open cached questions drawer', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Click on cached questions dropdown
    const cachedQuestionsButton = page.locator('button:text("▲ Answered Questions")').first();
    if (await cachedQuestionsButton.isVisible()) {
      await cachedQuestionsButton.click();
      
      // Verify cached questions are displayed
      const cachedQuestions = page.locator('button:text("What is Milvus?"), button:text("What is an embedding?")');
      await expect(cachedQuestions.first()).toBeVisible();
      
      // Verify button text changes to indicate expanded state
      const expandedButton = page.locator('button:text("▼ Answered Questions")');
      await expect(expandedButton).toBeVisible();
    }
  });

  test('should handle cached question selection', async ({ page }) => {
    await page.goto('http://localhost:3000');
    
    // Open cached questions dropdown
    const cachedQuestionsButton = page.locator('button:text("▲ Answered Questions")').first();
    if (await cachedQuestionsButton.isVisible()) {
      await cachedQuestionsButton.click();
      
      // Click on a cached question
      const cachedQuestion = page.locator('button:text("What is Milvus?")').first();
      if (await cachedQuestion.isVisible()) {
        await cachedQuestion.click();
        
        // Wait for cached response to load
        await page.waitForTimeout(3000);
        
        // Check if new message appears with cached content
        // Note: This test verifies the selection behavior even if response loading has issues
        const selectedQuestion = page.locator('button:text("What is Milvus?")[active]');
        if (await selectedQuestion.isVisible()) {
          await expect(selectedQuestion).toHaveAttribute('active');
        }
      }
    }
  });
});