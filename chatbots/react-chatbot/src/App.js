import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import MessageContainer from './components/MessageContainer';
import ChatInput from './components/ChatInput';
import CachedResponsesList from './components/CachedResponsesList';

// API Configuration from environment variables
const API_HOST = process.env.REACT_APP_API_HOST || 'localhost';
const API_PORT = process.env.REACT_APP_API_PORT || '8000';
const API_BASE_URL = `http://${API_HOST}:${API_PORT}`;

// Helper function to create consistent timing objects (DRY principle)
const createTimingData = (totalTimeMs = 0, responseType = 'rag', isCached = false) => ({
  total_time_ms: totalTimeMs,
  is_cached: isCached,
  response_type: responseType,
  _populated: true
});

function App() {
  const nextIdRef = useRef(2);

  // Helper function to create consistent message objects (DRY principle)  
  const createMessage = (text, role, options = {}) => ({
    id: options.id || nextIdRef.current++,
    text: typeof text === 'string' ? text : String(text || ''),
    role: role,
    isStreaming: options.isStreaming || false,
    sources: options.sources || [],
    timing: options.timing || createTimingData(),
    timestamp: options.timestamp || new Date().toISOString(),
  });
  const [messages, setMessages] = useState([
    {
      id: 1,
      text: "Hi! I'm a Milvus documentation assistant. Ask me anything about Milvus, vectors, or RAG systems.",
      role: 'assistant',
      isStreaming: false,
      sources: [],
      timing: createTimingData(0, 'system', false),
      timestamp: new Date().toISOString(),
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [apiStatus, setApiStatus] = useState('checking');
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [bypassCache, setBypassCache] = useState(false);
  const [cachedResponses, setCachedResponses] = useState([]);
  const [cacheDrawerOpen, setCacheDrawerOpen] = useState(false);
  const messagesEndRef = useRef(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Check API status on mount
  useEffect(() => {
    checkApiStatus();
    loadCachedResponses(); // Load cached responses on app startup
  }, []);

  const checkApiStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      if (response.ok) {
        const data = await response.json();
        setApiStatus('connected');
        setWebSearchEnabled(data.web_search_enabled || false);
        console.log('[App] Web search enabled:', data.web_search_enabled);
      } else {
        setApiStatus('error');
      }
    } catch (error) {
      setApiStatus('error');
    }
  };

  const loadCachedResponses = async () => {
    try {
      // Fetch just the questions list (lightweight)
      const response = await fetch(`${API_BASE_URL}/v1/cache/questions`);
      if (response.ok) {
        const data = await response.json();
        console.log('Cached questions loaded:', data);
        if (data.questions && Array.isArray(data.questions)) {
          // Store questions, answers will be loaded on demand
          setCachedResponses(data.questions);
        }
      }
    } catch (error) {
      console.error('Could not load cached questions from server:', error);
    }
  };

  const handleSendMessage = async (text, forceWebSearch = false) => {
    if (!text.trim() || isLoading) return;

    // Add user message with timestamp (AgentCore compatibility)
    const userMessage = createMessage(text, 'user');
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    // Add assistant message placeholder
    const assistantMessageId = nextIdRef.current++;
    const assistantMessage = createMessage('', 'assistant', {
      id: assistantMessageId,
      isStreaming: true
    });
    setMessages((prev) => [...prev, assistantMessage]);

    try {
      const startTime = Date.now();
      // Build conversation history for context awareness (Strands Agent standard format)
      // MIGRATION: When integrating AgentCore, keep this frontend message format.
      // AgentCore's SessionManager will handle server-side persistence automatically.
      // Content format matches Strands Agent/AgentCore signature: [{ text: "..." }]
      const conversationMessages = messages
        .filter(m => m.role && m.text)
        .map(m => ({
          role: m.role,
          content: [{ text: m.text }],  // Strands standard: content is list of ContentBlocks
          timestamp: m.timestamp,
        }))
        .concat([{
          role: 'user',
          content: [{ text: text }],  // Strands standard: wrap in ContentBlock
          timestamp: new Date().toISOString(),
        }]);

      const url = new URL(`${API_BASE_URL}/v1/chat/completions`);
      if (bypassCache) {
        url.searchParams.append('bypass_cache', 'true');
        console.log('🚫 BYPASS CACHE ACTIVE - Fresh KB query (no response cache)');
      } else {
        console.log('💾 Cache enabled - Using cached responses when available');
      }
      console.log('Request URL:', url.toString());

      if (forceWebSearch) {
        console.log('🌐 FORCE WEB SEARCH ACTIVE - Searching web only (no KB)');
      }

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: conversationMessages,
          model: 'rag-agent',
          temperature: 0.1,  // Low temperature for factual responses
          top_p: 0.9,
          stream: true,  // Enable streaming
          force_web_search: forceWebSearch,  // NEW: Force web search parameter
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      console.log('🚀 Starting to read response stream...'); 
      const contentType = response.headers.get('content-type') || '';
      console.log('📊 Response content-type:', contentType);

      // Helper function to parse streaming chunks
      const parseStreamChunk = (line, fullText, setFullText, assistantMessageId, sourcesRef) => {
        // Skip empty lines and comment lines
        if (!line || line.startsWith(':')) return fullText;

        // Parse SSE format: "data: {json}"
        if (line.startsWith('data: ')) {
          const jsonStr = line.substring(6).trim();
          if (!jsonStr) return fullText;
          
          if (jsonStr === '[STREAM_END]') {
            console.log('✅ [STREAM_END] marker received, total accumulated text:', fullText.length, 'chars');
            return fullText;
          }

          try {
            const data = JSON.parse(jsonStr);

            // Extract sources if present in this chunk
            if (data.sources) {
              console.log('📚 Sources field present:', { 
                isArray: Array.isArray(data.sources), 
                length: data.sources?.length, 
                type: typeof data.sources,
                sample: JSON.stringify(data.sources).substring(0, 200)
              });
              if (Array.isArray(data.sources)) {
                console.log('📚 Sources received:', data.sources.length, 'sources');
                console.log('📚 Sources content:', data.sources);
                sourcesRef.current = data.sources;
              } else {
                console.warn('⚠️ Sources is not an array:', typeof data.sources);
              }
            }

            // Extract text chunk from streaming response
            if (data.choices && data.choices[0]) {
              const delta = data.choices[0].delta || {};
              // Handle content chunks (may be empty string for final chunk, still needs update)
              if ('content' in delta) {
                // Ensure delta.content is always a string to prevent object concatenation
                const safeContent = typeof delta.content === 'string' ? delta.content : 
                  (delta.content && typeof delta.content === 'object') ? JSON.stringify(delta.content) : String(delta.content || '');
                const newText = fullText + safeContent;
                console.log(`📝 Chunk received (len=${safeContent.length}), total=${newText.length}`);

                // Update message with new text while streaming (even if content is empty)
                setMessages((prev) => {
                  const newMessages = [...prev];
                  const messageIndex = newMessages.findIndex(m => m.id === assistantMessageId);
                  if (messageIndex !== -1) {
                    // Ensure text is always a string to prevent "[object Object]" errors
                    const safeText = typeof newText === 'string' ? newText : 
                      (newText && typeof newText === 'object') ? JSON.stringify(newText) : String(newText || '');
                    newMessages[messageIndex].text = safeText || '(no content generated)';
                    newMessages[messageIndex].isStreaming = true;
                    
                    // ALWAYS update sources if available (critical for system messages)
                    if (sourcesRef.current && sourcesRef.current.length > 0) {
                      newMessages[messageIndex].sources = [...sourcesRef.current]; // Use spread to ensure new array reference
                      console.log('📚 Sources updated in message:', sourcesRef.current);
                      
                      // Special handling for system messages - don't show as text content if it's a system warning
                      const hasSystemMessage = sourcesRef.current.some(s => s.source_type === 'system_message');
                      console.log('🔍 System message check:', { hasSystemMessage, sources: sourcesRef.current.map(s => s.source_type) });
                      if (hasSystemMessage) {
                        // For system messages, the text should be empty since content comes from sources
                        newMessages[messageIndex].text = '';
                        console.log('🎯 System message detected - clearing text content, sources will handle display');
                      }
                    }
                  }
                  return newMessages;
                });

                return newText;
              }
            } else {
              // Log if format is unexpected
              console.warn('⚠️ Unexpected SSE format:', data);
            }
          } catch (e) {
            console.error('Failed to parse SSE data:', jsonStr, e);
          }
        }
        return fullText;
      };

      // Process streaming response using Server-Sent Events (SSE)
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullText = '';
      const sourcesRef = { current: [] };  // Use ref to track sources
      const responseTypeRef = { current: 'rag' };  // Track response type from API
      let chunkCount = 0;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            console.log(`✓ Stream ended. Total chunks read: ${chunkCount}, final text length: ${fullText.length}`);
            break;
          }

          const chunk = decoder.decode(value, { stream: true });
          chunkCount++;
          console.log(`📦 Raw chunk #${chunkCount} (${chunk.length} bytes):`, chunk.substring(0, 150).replace(/\n/g, '\\n'));
          const lines = chunk.split('\n');
          console.log(`   Split into ${lines.length} lines`);

          for (const line of lines) {
            if (line.trim().length === 0) continue;
            
            // Parse response_type and timing if present in this chunk
            if (line.startsWith('data: ')) {
              const jsonStr = line.substring(6).trim();
              if (!jsonStr) continue;
              try {
                const data = JSON.parse(jsonStr);
                // Check for timing data in the streaming response
                if (data.timing?.response_type) {
                  responseTypeRef.current = data.timing.response_type;
                  console.log('📊 Response type from API timing:', data.timing.response_type, 
                            'is_cached:', data.timing.is_cached);
                }
                // Fallback: check root level for backward compatibility
                else if (data.response_type) {
                  responseTypeRef.current = data.response_type;
                  console.log('📊 Response type from API root:', data.response_type);
                }
              } catch (e) {
                // Ignore parse errors, continue with chunk parsing
              }
            }
            
            fullText = parseStreamChunk(line, fullText, setMessages, assistantMessageId, sourcesRef);
          }
        }
      } finally {
        reader.releaseLock();
        console.log(`✅ Stream reader released. Final accumulated text: ${fullText.length} chars`);
      }

      const endTime = Date.now();
      const totalTime = (endTime - startTime) / 1000;

      // Finalize message when streaming completes
      setMessages((prev) => {
        const newMessages = [...prev];
        const messageIndex = newMessages.findIndex(m => m.id === assistantMessageId);
        if (messageIndex !== -1) {
          // Use accumulated fullText; provide helpful diagnostic if empty
          let finalText = fullText && fullText.trim() ? fullText : null;
          
          if (!finalText) {
            console.warn('[EMPTY_RESPONSE] No content generated. Check server logs and Ollama status');
            finalText = 
              '❌ No response generated.\n\n' +
              'This can happen if:\n' +
              '1. Ollama model is not running\n' +
              '2. Model is not loaded (try: ollama pull qwen2.5:0.5b)\n' +
              '3. Model ran out of memory\n' +
              '4. API server crashed\n\n' +
              'Check the server logs for details.';
          }
          
          // Ensure finalText is always a string to prevent "[object Object]" errors
          const safeFinalText = typeof finalText === 'string' ? finalText : 
            (finalText && typeof finalText === 'object') ? JSON.stringify(finalText) : String(finalText || '');
          
          // Set sources first, then determine if this is a system message
          newMessages[messageIndex].sources = [...(sourcesRef.current || [])]; // Use spread for new reference
          
          // Check if this is a system message that should display via warning banner instead of text
          const hasSystemMessage = sourcesRef.current && sourcesRef.current.some(s => s.source_type === 'system_message');
          
          if (hasSystemMessage) {
            // For system messages, clear the text content - the warning banner will display the message
            newMessages[messageIndex].text = '';
            console.log('🎯 System message finalized - text cleared, warning banner will display');
          } else {
            // For regular messages, set the accumulated text
            newMessages[messageIndex].text = safeFinalText;
          }
          console.log('✅ Message finalized:', {
            sourcesLength: sourcesRef.current?.length || 0,
            sourcesType: typeof sourcesRef.current,
            sourcesIsArray: Array.isArray(sourcesRef.current),
            textLength: finalText.length,
            firstSource: sourcesRef.current?.[0]
          });
          
          // Use response_type from API instead of guessing based on timing
          const isCached = responseTypeRef.current === 'cached';
          
          newMessages[messageIndex].timing = createTimingData(
            Math.round(totalTime * 1000),
            responseTypeRef.current,
            isCached
          );
          newMessages[messageIndex].isStreaming = false;

          // Add to cached responses only if it's actually a cache hit (API says so)
          if (isCached && fullText) {
            const cachedResponse = {
              id: assistantMessageId,
              question: text,
              answer: fullText,
              sources: sourcesRef.current,
              timing: createTimingData(
                Math.round(totalTime * 1000),
                responseTypeRef.current,
                isCached
              ),
              timestamp: new Date().toISOString(),
            };
            setCachedResponses((prev) => [cachedResponse, ...prev.slice(0, 19)]); // Keep last 20
          }
        }
        return newMessages;
      });
    } catch (error) {
      console.error('Error:', error);
      setMessages((prev) => {
        const newMessages = [...prev];
        const messageIndex = newMessages.findIndex(m => m.id === assistantMessageId);
        if (messageIndex !== -1) {
          // Use the same generic error message as when no response is generated
          console.warn('[NETWORK_ERROR] API request failed. Check server and Ollama status');
          const genericErrorMessage = 
            '❌ No response generated.\n\n' +
            'This can happen if:\n' +
            '1. Ollama model is not running\n' +
            '2. Model is not loaded (try: ollama pull qwen2.5:0.5b)\n' +
            '3. Model ran out of memory\n' +
            '4. API server crashed\n\n' +
            'Check the server logs for details.';
          
          newMessages[messageIndex].text = genericErrorMessage;
          newMessages[messageIndex].sources = [];
          newMessages[messageIndex].timing = createTimingData();
          newMessages[messageIndex].isStreaming = false;
        }
        return newMessages;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearChat = () => {
    setMessages([
      createMessage("Chat cleared! Ask me anything about Milvus.", 'assistant'),
    ]);
  };

  const handleSelectCachedResponse = async (response) => {
    const questionText = String(response.question || '').trim();
    console.log('Selected cached question ID:', response.id);
    console.log('Bypass cache active:', bypassCache);

    // If bypass cache is enabled, send as fresh query instead of loading cached answer
    if (bypassCache) {
      console.log('🚫 Bypass cache enabled - sending as fresh query:', questionText);
      handleSendMessage(questionText);
      return;
    }

    try {
      // Fetch the full response data from backend endpoint
      const fullResponseData = await fetch(`${API_BASE_URL}/v1/cache/responses/${response.id}`);
      if (!fullResponseData.ok) {
        throw new Error(`Failed to fetch response: ${fullResponseData.status}`);
      }

      // Endpoint now returns { answer, sources, response_type, metadata }
      const responseData = await fullResponseData.json();
      
      // Handle empty cached answers - re-ask the question instead
      if (!responseData.answer || responseData.answer.trim() === '') {
        console.log('⚠️ Cached response has empty answer - re-asking question with web search fallback');
        handleSendMessage(questionText);
        return;
      }
      
      const answerText = responseData.answer;
      const sources = responseData.sources || [];
      const responseType = responseData.response_type || 'cached';
      
      console.log('Fetched cached response:', { answerText, sources, responseType });

      // Ensure answerText is always a string to prevent "[object Object]" errors
      const safeAnswerText = typeof answerText === 'string' ? answerText : 
        (answerText && typeof answerText === 'object') ? JSON.stringify(answerText) : String(answerText || '');

      const userMessage = createMessage(String(questionText || '').trim(), 'user');

      const assistantMessage = createMessage(
        safeAnswerText.trim() || '(No content available)',
        'assistant',
        {
          sources: sources,
          timing: createTimingData(
            responseData.metadata?.response_time || 0,
            "cached",
            true
          )
        }
      );

      console.log('User message:', userMessage);
      console.log('Assistant message:', assistantMessage);
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
    } catch (error) {
      console.error('Error loading cached response:', error);
      // Fallback: try to use the question from the list
      const userMessage = createMessage(questionText, 'user');

      const assistantMessage = createMessage(
        `❌ Error loading cached response: ${error.message}`,
        'assistant'
      );

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
    }
  };

  const handleToggleCacheDrawer = () => {
    // Cached responses are pre-loaded on app startup, just toggle the drawer
    setCacheDrawerOpen(!cacheDrawerOpen);
  };

  return (
    <div className="app">
      <div className="app-layout">
        <div className="chat-column">
          <div className="chat-container">
            <div className="chat-header">
              <div className="header-content">
                <h1>🔍 Milvus RAG Chatbot</h1>
                <p>Ask questions about Milvus documentation</p>
              </div>
              <div className="header-controls">
                <div className={`api-status ${apiStatus}`}>
                  <span className="status-dot"></span>
                  {apiStatus === 'connected' && 'API Connected'}
                  {apiStatus === 'checking' && 'Checking...'}
                  {apiStatus === 'error' && 'API Offline'}
                </div>
                <button
                  className={`cache-toggle-btn ${bypassCache ? 'active' : ''}`}
                  onClick={() => setBypassCache(!bypassCache)}
                  disabled={apiStatus === 'error' || isLoading}
                  title={bypassCache ? 'Cache bypassed (direct KB query)' : 'Click to bypass cache'}
                >
                  {bypassCache ? '🚫 No Cache' : '💾 Cache On'}
                </button>
              </div>
            </div>

            <MessageContainer 
              messages={messages}
              isLoading={isLoading}
              messagesEndRef={messagesEndRef}
              onClearChat={handleClearChat}
            />

            <div className={`cache-drawer ${cacheDrawerOpen ? 'open' : 'closed'}`}>
              <CachedResponsesList
                cachedResponses={cachedResponses}
                onSelectResponse={handleSelectCachedResponse}
                isCollapsed={false}
                onToggleCollapse={handleToggleCacheDrawer}
              />
            </div>

            <div className="chat-footer">
              <div className="footer-top">
                <button
                  className="cache-drawer-btn"
                  onClick={handleToggleCacheDrawer}
                  title={cacheDrawerOpen ? 'Hide answered questions' : 'Show previously answered questions'}
                >
                  {cacheDrawerOpen ? '▼ Answered Questions' : '▲ Answered Questions'} ({cachedResponses.length})
                </button>
              </div>
              <ChatInput
                onSendMessage={handleSendMessage}
                disabled={isLoading || apiStatus === 'error'}
                webSearchEnabled={webSearchEnabled}
                placeholder={
                  apiStatus === 'error'
                    ? 'API not available - start the API server'
                    : 'Ask about Milvus...'
                }
              />

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
