import React, { useState } from 'react';
import './ChatInput.css';

function ChatInput({ onSendMessage, disabled, placeholder }) {
  const [input, setInput] = useState('');
  const [forceWebSearch, setForceWebSearch] = useState(false);

  const handleSend = () => {
    if (input.trim()) {
      console.log(`[ChatInput] Sending message with forceWebSearch=${forceWebSearch}:`, input);
      onSendMessage(input, forceWebSearch);
      setInput('');
      setForceWebSearch(false);  // Reset after sending
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-input-container">
      <textarea
        className="chat-input"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyPress={handleKeyPress}
        placeholder={placeholder || 'Type your message...'}
        disabled={disabled}
        rows="1"
      />
      <button
        className={`web-search-btn ${forceWebSearch ? 'active' : ''}`}
        onClick={() => setForceWebSearch(!forceWebSearch)}
        disabled={disabled}
        title={forceWebSearch ? 'Force web search enabled' : 'Force web search (disabled)'}
      >
        🌐
      </button>
      <button
        className="send-btn"
        onClick={handleSend}
        disabled={!input.trim() || disabled}
        title="Send (Enter)"
      >
        ➤
      </button>
    </div>
  );
}

export default ChatInput;
