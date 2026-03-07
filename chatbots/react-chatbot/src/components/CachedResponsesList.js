import React, { useState } from 'react';
import './CachedResponsesList.css';

function CachedResponsesList({ cachedResponses, onSelectResponse, isCollapsed, onToggleCollapse }) {
  const [expandedId, setExpandedId] = useState(null);

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const getTimingLabel = (timing) => {
    if (!timing || !timing.total_time_ms) return '';
    const isCached = timing.is_cached ? '⚡ Cached' : '📡 Live';
    const time = timing.total_time_ms < 1000 ? `${timing.total_time_ms}ms` : `${(timing.total_time_ms / 1000).toFixed(1)}s`;
    return `${isCached} · ${time}`;
  };

  return (
    <div className={`cached-responses-sidebar`}>
      <div className="responses-list">
        {cachedResponses.length === 0 ? (
          <div className="empty-state">
            <p>No cached responses yet</p>
            <small>Responses will appear here</small>
          </div>
        ) : (
          cachedResponses.map((response) => {
            const questionText = String(response.question || '').trim();
            const answerText = String(response.answer || '').trim();
            const displayQuestion = questionText.substring(0, 40);

            return (
            <div
              key={response.id}
              className={`response-item ${expandedId === response.id ? 'expanded' : ''}`}
            >
              <button
                className="response-button"
                onClick={() => {
                  console.log('===== CLICKED RESPONSE =====');
                  console.log('Full response object:', JSON.stringify(response, null, 2));
                  console.log('response.id:', response.id);
                  console.log('response.question:', response.question);
                  console.log('response.answer:', response.answer);
                  console.log('response.answer type:', typeof response.answer);
                  console.log('response.answer length:', response.answer ? response.answer.length : 'undefined');
                  console.log('All keys in response:', Object.keys(response));
                  console.log('=============================');
                  onSelectResponse(response);
                  toggleExpand(response.id);
                  onToggleCollapse();
                }}
                title={questionText}
              >
                <div className="response-header">
                  <span className="response-question">
                    {displayQuestion}
                    {questionText.length > 40 ? '...' : ''}
                  </span>
                  <span className="response-timing">
                    {getTimingLabel(response.timing)}
                  </span>
                </div>
              </button>

              {expandedId === response.id && answerText && (
                <div className="response-preview">
                  {response.sources && response.sources.length > 0 && (
                    <div className="preview-sources">
                      <strong>Sources: {response.sources.length}</strong>
                    </div>
                  )}
                </div>
              )}
            </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default CachedResponsesList;
