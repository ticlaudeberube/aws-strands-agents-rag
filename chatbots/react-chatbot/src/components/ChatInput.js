import React, { useState } from 'react';
import './ChatInput.css';

function ChatInput({ onSendMessage, disabled, placeholder }) {
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (input.trim()) {
      onSendMessage(input);
      setInput('');
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
