import React from 'react';
import SourcesList from './SourcesList';
import './ChatMessage.css';

function ChatMessage({ message }) {
  const isUser = message.role === 'user';

  // Determine source type for badge
  const isWebSearch = message.sources && message.sources.length > 0 &&
    message.sources[0].source_type === 'web_search';

  // Debug logging
  if (message.role === 'assistant' && message.id >= 3) {
    console.log('ChatMessage rendering assistant message:', {
      id: message.id,
      text: message.text,
      text_type: typeof message.text,
      text_length: message.text ? String(message.text).length : 'N/A',
      full_message: message
    });
  }

  return (
    <div className={`chat-message ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">
        {isUser ? '👤' : '🤖'}
      </div>
      <div className="message-content">
        {message.timing && (message.timing.total_time_ms > 0 || message.timing.is_cached) && (
          <div className="timing-info">
            {message.timing.is_cached ? (
              <span className="cached-badge">⚡ CACHED</span>
            ) : isWebSearch ? (
              <span className="web-search-badge">🌐 Web</span>
            ) : (
              <span className="generated-badge">🔍 KB</span>
            )}
            {message.timing.total_time_ms > 0 && (
              <span className="response-time">
                ⏱️ {(message.timing.total_time_ms / 1000).toFixed(2)}s
              </span>
            )}
          </div>
        )}
        <p className="message-text">
          {message.text && typeof message.text === 'string' && message.text.includes('<a') ? (
            // Render HTML links safely
            <span dangerouslySetInnerHTML={{ __html: message.text }} />
          ) : (
            // Render plain text
            message.text
          )}
          {message.isStreaming && (
            <span className="streaming-indicator">
              <span className="dot"></span>
              <span className="dot"></span>
              <span className="dot"></span>
            </span>
          )}
        </p>
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourcesList sources={message.sources} timing={message.timing} />
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
