import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import ChatMessage from './components/ChatMessage';
import ChatInput from './components/ChatInput';

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

  const handleSendMessage = async (text) => {
    if (!text.trim() || isLoading) return;

    // Add user message
    const userMessage = {
      id: nextIdRef.current++,
      text: text,
      role: 'user',
      isStreaming: false,
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
    };
    setMessages((prev) => [...prev, assistantMessage]);

    try {
      const startTime = Date.now();
      const response = await fetch(`${API_BASE_URL}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: [{ role: 'user', content: text }],
          model: 'rag-agent',
          temperature: 0.1,  // Low temperature for factual responses
          top_p: 0.9,
          stream: false,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      const assistantText =
        data.choices?.[0]?.message?.content || 'No response received';
      const sources = data.sources || [];
      
      const endTime = Date.now();
      const totalTime = (endTime - startTime) / 1000;

      setMessages((prev) => {
        const newMessages = [...prev];
        const messageIndex = newMessages.findIndex(m => m.id === assistantMessageId);
        if (messageIndex !== -1) {
          newMessages[messageIndex].text = assistantText;
          newMessages[messageIndex].sources = sources;
          newMessages[messageIndex].timing = { total_time_ms: Math.round(totalTime * 1000) };
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
                <button className="clear-btn" onClick={handleClearChat}>
                  Clear Chat
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
