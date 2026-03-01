import React from 'react';
import SourcesList from './SourcesList';
import './ChatMessage.css';

function ChatMessage({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`chat-message ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">
        {isUser ? '👤' : '🤖'}
      </div>
      <div className="message-content">
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
        {!isUser && message.timing && message.timing.total_time_ms && (
          <div className="timing-info">
            ⏱️ Response time: {(message.timing.total_time_ms / 1000).toFixed(2)}s
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
