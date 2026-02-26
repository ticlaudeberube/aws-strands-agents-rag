import React from 'react';
import './SourcesList.css';

function SourcesList({ sources, timing }) {
  if (!sources || sources.length === 0) {
    return null;
  }

  // Deduplicate sources by document_name or text to avoid showing duplicates
  const getUniqueKey = (source) => source.document_name || source.text || '';
  const seen = new Set();
  const uniqueSources = sources.filter((source) => {
    const key = getUniqueKey(source);
    if (key && seen.has(key)) {
      return false;
    }
    if (key) {
      seen.add(key);
    }
    return true;
  });

  if (uniqueSources.length === 0) {
    return null;
  }

  const getRelevancePercentage = (distance) => {
    // For COSINE metric: distance is similarity score (0-1, where 1 is perfect match)
    // Convert to relevance percentage (0-100)
    return Math.max(0, Math.round(distance * 100));
  };

  const formatTime = (milliseconds) => {
    if (typeof milliseconds !== 'number' || milliseconds < 0) return 'N/A';
    if (milliseconds === 0) return '0ms';
    if (milliseconds < 1000) return Math.round(milliseconds) + 'ms';
    return (milliseconds / 1000).toFixed(2) + 's';
  };

  return (
    <div className="sources-container">
      <div className="sources-header">
        <span className="sources-icon">📚</span>
        <span className="sources-title">Sources Used</span>
        <span className="sources-count">({uniqueSources.length})</span>
        {timing && timing.total_time_ms && (
          <span className="query-timing">⏱️ {formatTime(timing.total_time_ms)}</span>
        )}
      </div>
      <div className="sources-list">
        {uniqueSources.map((source, index) => (
          <div key={index} className="source-item">
            <div className="source-number">{index + 1}</div>
            <div className="source-content">
              <p className="source-filename">{source.document_name || source.text?.substring(0, 50) + '...' || 'Unknown'}</p>
              <p className="source-text">{source.text}</p>
              <div className="source-meta">
                <span className="relevance-badge">
                  ✓ {getRelevancePercentage(source.distance)}% relevant
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default SourcesList;
