import React from 'react';
import './SourcesList.css';

function SourcesList({ sources, timing }) {
  if (!sources || sources.length === 0) {
    return null;
  }

  // Deduplicate sources by document_name, URL, or text to avoid showing duplicates
  const getUniqueKey = (source) => source.url || source.document_name || source.text || '';
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
    // For web sources: distance is already the relevance score (0-1)
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
        {uniqueSources.map((source, index) => {
          const isWebSource = source.source_type === 'web_search' || source.url;
          return (
            <div key={index} className={`source-item ${isWebSource ? 'web-source' : ''}`}>
              <div className={`source-number ${isWebSource ? 'web-badge' : ''}`}>
                {isWebSource ? '🌐' : index + 1}
              </div>
              <div className="source-content">
                {isWebSource ? (
                  <>
                    <p className="source-filename web-title">
                      <a href={source.url} target="_blank" rel="noopener noreferrer" className="web-link">
                        {source.title || 'Web Result'}
                      </a>
                    </p>
                    {source.snippet && <p className="source-text">{source.snippet}</p>}
                    <div className="source-meta">
                      <span className="web-source-badge">🔗 Web Search</span>
                      <span className="source-url">{new URL(source.url).hostname}</span>
                      {source.distance && (
                        <span className="relevance-badge">
                          ✓ {getRelevancePercentage(source.distance)}% relevant
                        </span>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <p className="source-filename">{source.document_name || source.text?.substring(0, 50) + '...' || 'Unknown'}</p>
                    <p className="source-text">{source.text}</p>
                    <div className="source-meta">
                      <span className="relevance-badge">
                        ✓ {getRelevancePercentage(source.distance)}% relevant
                      </span>
                    </div>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default SourcesList;
