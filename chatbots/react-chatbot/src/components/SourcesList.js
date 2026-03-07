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

  // Separate web and local sources
  const webSources = uniqueSources.filter(s => s.source_type === 'web_search' || s.url);
  const localSources = uniqueSources.filter(s => s.source_type !== 'web_search' && !s.url);

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
        {/* Web sources first */}
        {webSources.length > 0 && (
          <div className="web-sources-section">
            {webSources.map((source, index) => (
              <div key={`web-${index}`} className="source-item web-source">
                <div className="source-number web-badge">🌐</div>
                <div className="source-content">
                  <p className="source-filename web-title">
                    {source.distance && (
                      <span className="relevance-badge">
                        ✓ {getRelevancePercentage(source.distance)}% relevant
                      </span>
                    )}
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="web-link"
                      title={source.url}
                    >
                      {source.title || 'Web Result'}
                    </a>
                  </p>

                </div>
              </div>
            ))}
          </div>
        )}

        {/* Local document sources */}
        {localSources.length > 0 && (
          <div className="local-sources-section">
            {localSources.map((source, index) => (
              <div key={`local-${index}`} className="source-item">
                <div className="source-number web-badge">📄</div>
                <div className="source-content">
                  <p className="source-filename">
                    {source.distance && (
                      <span className="relevance-badge">
                        ✓ {getRelevancePercentage(source.distance)}% relevant
                      </span>
                    )}
                    {source.url ? (
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="web-link"
                        title={source.url}
                      >
                        {source.document_name || source.text?.substring(0, 50) + '...' || 'Unknown'}
                      </a>
                    ) : (
                      <span>{source.document_name || source.text?.substring(0, 50) + '...' || 'Unknown'}</span>
                    )}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default SourcesList;
