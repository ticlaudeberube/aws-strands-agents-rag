import React from 'react';
import SourcesList from './SourcesList';
import './ChatMessage.css';

function ChatMessage({ message }) {
  const isUser = message.role === 'user';

  // Extract system messages for warning banner
  const systemMessages = message.sources?.filter(s => s.source_type === 'system_message') || [];
  const nonSystemSources = message.sources?.filter(s => s.source_type !== 'system_message') || [];

  // Debug logging for system messages
  if (!isUser && systemMessages.length > 0) {
    console.log('🎯 ChatMessage: System message detected!', {
      messageId: message.id,
      systemMessages: systemMessages,
      messageText: message.text,
      allSources: message.sources
    });
  }

  // Check if message contains error content (these keep original style)
  // const isErrorMessage = message.text && (
  //   message.text.includes('❌') ||
  //   message.text.includes('No response generated') ||
  //   message.text.includes('Error:') ||
  //   message.text.startsWith('Error') ||
  //   message.text.includes('server crashed') ||
  //   message.text.includes('model is not running') ||
  //   message.text.includes('ran out of memory')
  // );

  // System messages take priority over error messages - show only warning banner
  const shouldShowWarningOnly = !isUser && systemMessages.length > 0;

  // Hide content only if we have system messages (not for error messages)
  const shouldHideContent = shouldShowWarningOnly || (!message.text?.trim() && !isUser);

  // Determine response type: prefer API response_type, fallback to source detection
  const responseType = message.timing?.response_type;
  const isWebSearch = message.sources && message.sources.length > 0 &&
    message.sources.some(s => s.source_type === 'web_search');

  const determineBadge = () => {
    if (responseType === 'cached') {
      return <span className="cached-badge">⚡ CACHED</span>;
    } else if (responseType === 'web_search') {
      return <span className="web-search-badge">🌐 WEB</span>;
    } else if (isWebSearch) {
      // Fallback: detect web search from sources if response_type not available
      return <span className="web-search-badge">🌐 WEB</span>;
    } else {
      return <span className="generated-badge">🔍 KB</span>;
    }
  };

  // Debug logging
  if (message.role === 'assistant' && message.id >= 3) {
    console.log('ChatMessage rendering assistant message:', {
      id: message.id,
      responseType: responseType,
      hasSources: message.sources && message.sources.length > 0,
      sourceTypes: message.sources?.map(s => s.source_type) || [],
      text_length: message.text ? String(message.text).length : 'N/A',
    });
  }

  return (
    <div 
      className={`chat-message ${isUser ? 'user' : 'assistant'}`}
      data-testid={isUser ? 'user-message' : 'assistant-message'}
    >
      <div className="message-avatar">
        {isUser ? '👤' : '🤖'}
      </div>
      <div className="message-content">
        {!isUser && message.timing && (
          <div className="timing-info">
            {determineBadge()}
            {message.timing.total_time_ms > 0 && (
              <span className="response-time">
                ⏱️ {(message.timing.total_time_ms / 1000).toFixed(2)}s
              </span>
            )}
          </div>
        )}

        {/* Main message content - show error messages in original style, hide only for system warnings */}
        {!shouldHideContent && (
          <p className="message-text" data-testid="message-text">
            {(() => {
              // Defensive programming: ensure message.text is always rendered as string
              let displayText = message.text;

              // Handle case where message.text might be an object (prevents "[object Object]")
              if (typeof displayText === 'object' && displayText !== null) {
                console.warn('ChatMessage: message.text is an object, converting to string:', displayText);
                displayText = JSON.stringify(displayText, null, 2);
              } else if (displayText === null || displayText === undefined) {
                displayText = '(No content)';
              } else {
                displayText = String(displayText);
              }

              // Render HTML links safely if text contains HTML
              if (displayText && displayText.includes('<a')) {
                return <span dangerouslySetInnerHTML={{ __html: displayText }} />;
              } else {
                return displayText;
              }
            })()}
            {message.isStreaming && (
              <span className="streaming-indicator">
                <span className="dot"></span>
                <span className="dot"></span>
                <span className="dot"></span>
              </span>
            )}
          </p>
        )}

        {/* System warning banners - only for system messages, not error messages */}
        {shouldShowWarningOnly && (
          <div className="system-warning-banner">
            {systemMessages.map((msg, index) => (
              <div key={`warning-${index}`} className="system-warning">
                <span className="warning-icon">⚠️</span>
                <span className="warning-text">{msg.text}</span>
              </div>
            ))}
          </div>
        )}

        {/* Regular sources (excluding system messages) - show when content is visible */}
        {!isUser && !shouldHideContent && nonSystemSources && nonSystemSources.length > 0 && (
          <SourcesList sources={nonSystemSources} timing={message.timing} />
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
