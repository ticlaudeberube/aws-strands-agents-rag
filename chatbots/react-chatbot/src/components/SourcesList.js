import React from 'react';
import './SourcesList.css';

function SourcesList({ sources }) {
  if (!sources || sources.length === 0) {
    return null;
  }

  const getRelevancePercentage = (distance) => {
    // For COSINE metric: distance is similarity score (0-1, where 1 is perfect match)
    // Convert to relevance percentage (0-100)
    return Math.max(0, Math.round(distance * 100));
  };

  return (
    <div className="sources-container">
      <div className="sources-header">
        <span className="sources-icon">📚</span>
        <span className="sources-title">Sources Used</span>
        <span className="sources-count">({sources.length})</span>
      </div>
      <div className="sources-list">
        {sources.map((source, index) => (
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
