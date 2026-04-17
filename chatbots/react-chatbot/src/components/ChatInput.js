import React, { useState } from 'react';
import DOMPurify from 'dompurify';
import './ChatInput.css';

// DOMPurify-based sanitization (industry standard)
const sanitizeInput = (text) => {
  if (!text || typeof text !== 'string') return '';
  
  // Use DOMPurify to sanitize input - removes all HTML/JS while keeping text content
  let sanitized = DOMPurify.sanitize(text, {
    ALLOWED_TAGS: [],       // No HTML tags allowed
    ALLOWED_ATTR: [],       // No attributes allowed  
    KEEP_CONTENT: true,     // Keep text content, remove tags
    RETURN_DOM: false,      // Return string not DOM
    RETURN_DOM_FRAGMENT: false
  });
  
  // Additional normalization
  sanitized = sanitized.replace(/\s+/g, ' ').trim();
  
  // Length limit (prevent extremely long inputs) - configurable
  const MAX_INPUT_LENGTH = parseInt(process.env.REACT_APP_MAX_MESSAGE_LENGTH) || 2000;
  if (sanitized.length > MAX_INPUT_LENGTH) {
    sanitized = sanitized.substring(0, MAX_INPUT_LENGTH);
  }
  
  return sanitized;
};

const validateInput = (text) => {
  if (!text || text.trim().length === 0) {
    return { isValid: false, error: 'Message cannot be empty' };
  }
  
  // Configurable minimum length
  const MIN_MESSAGE_LENGTH = parseInt(process.env.REACT_APP_MIN_MESSAGE_LENGTH) || 2;
  if (text.trim().length < MIN_MESSAGE_LENGTH) {
    return { isValid: false, error: `Message too short (minimum ${MIN_MESSAGE_LENGTH} characters)` };
  }
  
  // DOMPurify handles most XSS patterns, but add basic suspicious pattern check
  // mainly for user feedback on obvious malicious attempts
  const suspiciousPatterns = [
    /<script[^>]*>/i,
    /javascript:/i,
    /<iframe[^>]*>/i,
  ];
  
  for (const pattern of suspiciousPatterns) {
    if (pattern.test(text)) {
      return { isValid: false, error: 'HTML/script content detected and removed' };
    }
  }
  
  return { isValid: true, error: null };
};

function ChatInput({ onSendMessage, disabled, placeholder, webSearchEnabled }) {
  const [input, setInput] = useState('');
  const [forceWebSearch, setForceWebSearch] = useState(false);
  const [inputError, setInputError] = useState('');

  const handleSend = () => {
    // TODO: Parse structured GlobalErrorResponse from API
    // Currently shows generic client-side errors. Should also handle:
    // - error_code: VALIDATION_*, SECURITY_*, SERVICE_*, SYSTEM_*
    // - category: validation_error, security_error, service_error, system_error
    // - suggestion: Recovery hint from server
    // See docs/ERROR_HANDLING.md for full schema
    
    const sanitized = sanitizeInput(input);
    const validation = validateInput(sanitized);
    
    if (!validation.isValid) {
      setInputError(validation.error);
      return;
    }
    
    setInputError(''); // Clear any previous errors
    console.log(`[ChatInput] Sending sanitized message with forceWebSearch=${forceWebSearch}:`, sanitized);
    onSendMessage(sanitized, forceWebSearch);
    setInput('');
    setForceWebSearch(false);  // Reset after sending
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e) => {
    const newValue = e.target.value;
    setInput(newValue);
    
    // Clear error when user starts typing again
    if (inputError) {
      setInputError('');
    }
  };

  return (
    <div className="chat-input-container">
      {inputError && (
        <div className="input-error" data-testid="input-error">
          {inputError}
        </div>
      )}
      <div className="chat-input-controls">
        <textarea
          className={`chat-input ${inputError ? 'error' : ''}`}
          value={input}
          onChange={handleInputChange}
          onKeyPress={handleKeyPress}
          placeholder={placeholder || 'Type your message...'}
          disabled={disabled}
          rows="1"
          maxLength="2000"          data-testid="chat-input"          />      
        {webSearchEnabled && (
          <button
            className={`web-search-btn ${forceWebSearch ? 'active' : ''}`}
            onClick={() => setForceWebSearch(!forceWebSearch)}
            disabled={disabled}
            title={forceWebSearch ? 'Force web search enabled' : 'Click to enable web search'}
          >
            🌐
          </button>
        )}
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={!input.trim() || disabled || inputError}
          title="Send (Enter)"
          data-testid="send-button"
        >
          ➤
        </button>
      </div>
    </div>
  );
}

export default ChatInput;
