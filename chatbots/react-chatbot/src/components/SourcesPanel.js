import React from 'react';
import './SourcesPanel.css';

function SourcesPanel({ sources, isLoading }) {
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
        <span className="sources-count">{sources.length} source{sources.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="sources-panel-list">
        {sources.map((source, index) => {
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
