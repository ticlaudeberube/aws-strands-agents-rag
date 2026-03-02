import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import ChatMessage from './components/ChatMessage';
import ChatInput from './components/ChatInput';

// API Configuration from environment variables
const API_HOST = process.env.REACT_APP_API_HOST || 'localhost';
const API_PORT = process.env.REACT_APP_API_PORT || '8000';
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
  const messagesEndRef = useRef(null);
  const nextIdRef = useRef(2);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Check API status on mount
  useEffect(() => {
    checkApiStatus();
  }, []);

  const checkApiStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      if (response.ok) {
        setApiStatus('connected');
      } else {
        setApiStatus('error');
      }
    } catch (error) {
      setApiStatus('error');
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
      
      const response = await fetch(`${API_BASE_URL}/v1/chat/completions`, {
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
          newMessages[messageIndex].timing = { 
            total_time_ms: Math.round(totalTime * 1000),
            is_cached: isCached
          };
          newMessages[messageIndex].isStreaming = false;
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
          <div className={`api-status ${apiStatus}`}>
            <span className="status-dot"></span>
            {apiStatus === 'connected' && 'API Connected'}
            {apiStatus === 'checking' && 'Checking...'}
            {apiStatus === 'error' && 'API Offline'}
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
        </div>

            <div className="chat-footer">
              <ChatInput
                onSendMessage={handleSendMessage}
                disabled={isLoading || apiStatus !== 'connected'}
                placeholder={
                  apiStatus !== 'connected'
                    ? 'API not available - start the API server'
                    : 'Ask about Milvus...'
                }
              />
              {messages.length > 1 && (
                <div className="button-group">
                  <button className="clear-btn" onClick={handleClearChat}>
                    Clear Chat
                  </button>
                  <button 
                    className="clear-cache-btn" 
                    onClick={handleClearCache}
                    disabled={isLoading}
                    title="Clear all caches: embedding, search, answer, and response cache"
                  >
                    Clear Cache
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
