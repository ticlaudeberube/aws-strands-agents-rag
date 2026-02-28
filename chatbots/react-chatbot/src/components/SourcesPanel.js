import React from 'react';
import './SourcesPanel.css';

function SourcesPanel({ sources, isLoading, timing }) {
  const formatTime = (milliseconds) => {
    if (typeof milliseconds !== 'number' || milliseconds < 0) return 'N/A';
    if (milliseconds === 0) return '0ms';
    if (milliseconds < 1000) return Math.round(milliseconds) + 'ms';
    return (milliseconds / 1000).toFixed(2) + 's';
  };

  // Deduplicate sources by document_name, URL, or text to avoid showing duplicates
  const getUniqueSources = () => {
    if (!sources || sources.length === 0) return [];
    const seen = new Set();
    const unique = [];
    for (const source of sources) {
      const key = source.url || source.document_name || source.text || '';
      if (key && !seen.has(key)) {
        seen.add(key);
        unique.push(source);
      }
    }
    return unique;
  };

  const uniqueSources = getUniqueSources();

  if (isLoading) {
    return (
      <div className="sources-panel">
        <div className="sources-panel-header">
          <h3>📚 Retrieved Documents</h3>
          <span className="loading-indicator">Searching...</span>
        </div>
      </div>
    );
  }

  if (!sources || sources.length === 0) {
    return (
      <div className="sources-panel empty">
        <div className="sources-panel-header">
          <h3>📚 Retrieved Documents</h3>
        </div>
        <div className="sources-empty">No documents retrieved yet. Ask a question to see sources.</div>
      </div>
    );
  }

  return (
    <div className="sources-panel">
      <div className="sources-panel-header">
        <h3>📚 Retrieved Documents</h3>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {timing && timing.total_time_ms && (
            <span className="panel-timing">⏱️ {formatTime(timing.total_time_ms)}</span>
          )}
          <span className="sources-count">{uniqueSources.length} source{uniqueSources.length !== 1 ? 's' : ''}</span>
        </div>
      </div>
      <div className="sources-panel-list">
        {uniqueSources.map((source, index) => {
          const isWebSource = source.source_type === 'web_search' || source.url;
          
          if (isWebSource) {
            return (
              <div key={index} className="sources-panel-item web-source-item">
                <div className="sources-panel-number web-badge">🌐</div>
                <div className="sources-panel-content">
                  <p className="sources-panel-text web-source-title">
                    <a href={source.url} target="_blank" rel="noopener noreferrer" className="web-source-link">
                      {source.title || 'Web Result'}
                    </a>
                  </p>
                  {source.snippet && <p className="sources-panel-text web-snippet">{source.snippet}</p>}
                  <div className="sources-panel-meta">
                    <span className="web-source-badge">🔗 Web Search</span>
                    <span className="web-domain">{new URL(source.url).hostname}</span>
                    {source.distance && (
                      <span className="relevance-badge" style={{marginLeft: '8px'}}>
                        ✓ {Math.round(source.distance * 100)}% relevant
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          }
          
          // Show document name if available, otherwise show text snippet
          const displayName = source.document_name || (source.text ? source.text.substring(0, 100) + '...' : 'Unnamed source');
          const isDocumentName = !!source.document_name;
          
          // Extract filename from metadata
          let metadata = source.metadata;
          if (typeof metadata === 'string') {
            try {
              metadata = JSON.parse(metadata);
            } catch {
              metadata = {};
            }
          }
          const filename = metadata?.filename || metadata?.document_name || '';
          
          return (
            <div key={index} className="sources-panel-item">
              <div className="sources-panel-number">{index + 1}</div>
              <div className="sources-panel-content">
                <p className={`sources-panel-text ${isDocumentName ? 'document-name' : 'text-snippet'}`}>
                  {displayName}
                </p>
                {filename && <div className="sources-panel-filename">{filename}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default SourcesPanel;
