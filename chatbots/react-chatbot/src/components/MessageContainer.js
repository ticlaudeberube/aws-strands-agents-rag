import React from 'react';
import ChatMessage from './ChatMessage';
import './MessageContainer.css';

/**
 * MessageContainer - A DRY component for consistent message rendering
 *
 * This component ensures all messages (regular chat, cached, error)
 * are displayed with consistent styling and structure.
 *
 * @param {Array} messages - Array of message objects
 * @param {boolean} isLoading - Whether the chat is currently loading
 * @param {React.RefObject} messagesEndRef - Ref for scrolling to bottom
 */
function MessageContainer({ messages, isLoading, messagesEndRef, onClearChat }) {
  return (
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
          <button className="clear-btn" onClick={onClearChat}>
            Clear Chat
          </button>
        </div>
      )}
    </div>
  );
}

export default MessageContainer;
