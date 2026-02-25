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
          {message.text}
          {message.isStreaming && <span className="cursor">|</span>}
        </p>
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourcesList sources={message.sources} />
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
