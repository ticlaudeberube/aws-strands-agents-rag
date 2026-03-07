import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import ChatMessage from './components/ChatMessage';
import ChatInput from './components/ChatInput';
import CachedResponsesList from './components/CachedResponsesList';

// API Configuration from environment variables
const API_HOST = process.env.REACT_APP_API_HOST || 'localhost';
const API_PORT = process.env.REACT_APP_API_PORT || '8001';
const API_BASE_URL = `http://${API_HOST}:${API_PORT}`;

function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      text: "Hi! I'm a Milvus documentation assistant. Ask me anything about Milvus, vectors, or RAG systems.",
      role: 'assistant',
      isStreaming: false,
      sources: [],
      timing: {},
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [apiStatus, setApiStatus] = useState('checking');
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [bypassCache, setBypassCache] = useState(false);
  const [cachedResponses, setCachedResponses] = useState([]);
  const [cacheDrawerOpen, setCacheDrawerOpen] = useState(false);
  const messagesEndRef = useRef(null);
  const nextIdRef = useRef(2);

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
    const userMessage = {
      id: nextIdRef.current++,
      text: text,
      role: 'user',
      isStreaming: false,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    // Add assistant message placeholder
    const assistantMessageId = nextIdRef.current++;
    const assistantMessage = {
      id: assistantMessageId,
      text: '',
      role: 'assistant',
      isStreaming: true,
      sources: [],
      timing: {},
      timestamp: new Date().toISOString(),
    };
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

      // Helper function to parse streaming chunks
      const parseStreamChunk = (line, fullText, setFullText, assistantMessageId, sourcesRef) => {
        // Skip empty lines and comment lines
        if (!line || line.startsWith(':')) return fullText;

        // Parse SSE format: "data: {json}"
        if (line.startsWith('data: ')) {
          const jsonStr = line.substring(6).trim();
          if (!jsonStr) return fullText;

          try {
            const data = JSON.parse(jsonStr);

            // Extract sources if present in this chunk
            if (data.sources && Array.isArray(data.sources)) {
              console.log('📚 Sources received:', data.sources.length, 'sources');
              sourcesRef.current = data.sources;
            }

            // Extract text chunk from streaming response
            if (data.choices && data.choices[0]) {
              const delta = data.choices[0].delta || {};
              if (delta.content) {
                const newText = fullText + delta.content;

                // Update message with new text while streaming
                setMessages((prev) => {
                  const newMessages = [...prev];
                  const messageIndex = newMessages.findIndex(m => m.id === assistantMessageId);
                  if (messageIndex !== -1) {
                    newMessages[messageIndex].text = newText;
                    newMessages[messageIndex].isStreaming = true;
                    // Update sources if available
                    if (sourcesRef.current && sourcesRef.current.length > 0) {
                      newMessages[messageIndex].sources = sourcesRef.current;
                    }
                  }
                  return newMessages;
                });

                return newText;
              }
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

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');

          for (const line of lines) {
            fullText = parseStreamChunk(line, fullText, setMessages, assistantMessageId, sourcesRef);
          }
        }
      } finally {
        reader.releaseLock();
      }

      const endTime = Date.now();
      const totalTime = (endTime - startTime) / 1000;
      const isCached = totalTime < 0.2; // Cache hits typically <200ms

      // Finalize message when streaming completes
      setMessages((prev) => {
        const newMessages = [...prev];
        const messageIndex = newMessages.findIndex(m => m.id === assistantMessageId);
        if (messageIndex !== -1) {
          newMessages[messageIndex].text = fullText || 'No response received';
          newMessages[messageIndex].sources = sourcesRef.current;
          console.log('✅ Message finalized with sources:', sourcesRef.current?.length || 0);
          newMessages[messageIndex].timing = {
            total_time_ms: Math.round(totalTime * 1000),
            is_cached: isCached
          };
          newMessages[messageIndex].isStreaming = false;

          // Add to cached responses if it's a cache hit
          if (isCached && fullText) {
            const cachedResponse = {
              id: assistantMessageId,
              question: text,
              answer: fullText,
              sources: sourcesRef.current,
              timing: {
                total_time_ms: Math.round(totalTime * 1000),
                is_cached: isCached
              },
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
          newMessages[messageIndex].text = `❌ Error: ${error.message}`;
          newMessages[messageIndex].sources = [];
          newMessages[messageIndex].timing = {};
          newMessages[messageIndex].isStreaming = false;
        }
        return newMessages;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearCache = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/v1/cache/clear`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Cache clear failed: ${response.status}`);
      }

      const data = await response.json();
      console.log('Cache cleared:', data);

      // Add system message
      setMessages((prev) => [
        ...prev,
        {
          id: nextIdRef.current++,
          text: '✓ Cache cleared successfully!',
          role: 'system',
          isStreaming: false,
          sources: [],
          timing: {},
        },
      ]);
    } catch (error) {
      console.error('Error clearing cache:', error);
      setMessages((prev) => [
        ...prev,
        {
          id: nextIdRef.current++,
          text: `❌ Failed to clear cache: ${error.message}`,
          role: 'system',
          isStreaming: false,
          sources: [],
          timing: {},
        },
      ]);
    }
  };

  const handleClearChat = () => {
    setMessages([
      {
        id: nextIdRef.current++,
        text: "Chat cleared! Ask me anything about Milvus.",
        role: 'assistant',
        isStreaming: false,
        sources: [],
        timing: {},
      },
    ]);
  };

  const handleSelectCachedResponse = async (response) => {
    console.log('Selected cached question ID:', response.id);

    try {
      // Fetch the answer text from backend endpoint
      const fullResponseData = await fetch(`${API_BASE_URL}/v1/cache/responses/${response.id}`);
      if (!fullResponseData.ok) {
        throw new Error(`Failed to fetch response: ${fullResponseData.status}`);
      }

      // Endpoint now returns just the answer text as a JSON string
      const answerText = await fullResponseData.json();
      console.log('Fetched answer text:', answerText);

      const userMessage = {
        id: nextIdRef.current++,
        text: String(response.question || '').trim(),
        role: 'user',
        isStreaming: false,
        timestamp: new Date().toISOString(),
      };

      const assistantMessage = {
        id: nextIdRef.current++,
        text: String(answerText || '').trim(),
        role: 'assistant',
        isStreaming: false,
        sources: [],
        timing: {
          total_time_ms: 0,
          is_cached: true
        },
        timestamp: new Date().toISOString(),
      };

      console.log('User message:', userMessage);
      console.log('Assistant message:', assistantMessage);
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
    } catch (error) {
      console.error('Error loading cached response:', error);
      // Fallback: try to use the question from the list
      const userMessage = {
        id: nextIdRef.current++,
        text: String(response.question || '').trim(),
        role: 'user',
        isStreaming: false,
        timestamp: new Date().toISOString(),
      };

      const assistantMessage = {
        id: nextIdRef.current++,
        text: `❌ Error loading cached response: ${error.message}`,
        role: 'assistant',
        isStreaming: false,
        sources: [],
        timing: {}
      };

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
                  disabled={apiStatus !== 'connected'}
                  title={bypassCache ? 'Cache bypassed (direct KB query)' : 'Click to bypass cache'}
                >
                  {bypassCache ? '🚫 No Cache' : '💾 Cache On'}
                </button>
              </div>
            </div>

            <div className="messages-container">
              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}
              {isLoading && (
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              )}
              <div ref={messagesEndRef} />
              {messages.length > 1 && (
                <div className="clear-chat-container">
                  <button className="clear-btn" onClick={handleClearChat}>
                    Clear Chat
                  </button>
                </div>
              )}
            </div>

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
                disabled={isLoading || apiStatus !== 'connected'}
                webSearchEnabled={webSearchEnabled}
                placeholder={
                  apiStatus !== 'connected'
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
