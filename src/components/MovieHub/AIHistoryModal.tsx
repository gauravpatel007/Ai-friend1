import React, { useState, useEffect, useRef } from 'react';
import {
  History,
  X,
  Trash2,
  Sparkles,
  Search,
  Play,
  Clock,
  ArrowRight,
  RotateCcw,
} from 'lucide-react';
import './AIHistoryModal.css';

export interface AIHistoryItem {
  id: string;
  query: string;
  timestamp: number;
}

interface AIHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  history: AIHistoryItem[];
  onSelectQuery: (query: string) => void;
  onDeleteQuery: (id: string) => void;
  onClearHistory: () => void;
}

/** Format timestamp into human-readable relative or short date string */
function formatTimestamp(ts: number): string {
  const diffMs = Date.now() - ts;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHours = Math.floor(diffMin / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSec < 45) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;

  const date = new Date(ts);
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const AIHistoryModal: React.FC<AIHistoryModalProps> = ({
  isOpen,
  onClose,
  history,
  onSelectQuery,
  onDeleteQuery,
  onClearHistory,
}) => {
  const [filterText, setFilterText] = useState<string>('');
  const [confirmClear, setConfirmClear] = useState<boolean>(false);
  const filterInputRef = useRef<HTMLInputElement>(null);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) {
      setFilterText('');
      setConfirmClear(false);
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const filteredHistory = history.filter((item) =>
    item.query.toLowerCase().includes(filterText.toLowerCase().trim())
  );

  const handleClearClick = () => {
    if (confirmClear) {
      onClearHistory();
      setConfirmClear(false);
    } else {
      setConfirmClear(true);
      setTimeout(() => setConfirmClear(false), 3000);
    }
  };

  return (
    <div
      className="hub-ai-history-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="AI Recommendation Search History"
    >
      <div
        className="hub-ai-history-modal"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="hub-ai-history-header">
          <div className="hub-ai-history-title-wrap">
            <div className="hub-ai-history-icon-badge">
              <History size={18} className="hub-ai-history-icon-glow" />
            </div>
            <div>
              <h3 className="hub-ai-history-title">AI Search History</h3>
              <p className="hub-ai-history-subtitle">
                {history.length === 0
                  ? 'No past searches in database'
                  : `${history.length} ${history.length === 1 ? 'query' : 'queries'} stored in database`}
              </p>
            </div>
          </div>

          <div className="hub-ai-history-header-actions">
            {history.length > 0 && (
              <button
                type="button"
                className={`hub-ai-history-clear-btn ${confirmClear ? 'confirm-mode' : ''}`}
                onClick={handleClearClick}
                title={confirmClear ? 'Click again to confirm' : 'Clear all search history'}
              >
                <Trash2 size={14} />
                <span>{confirmClear ? 'Confirm Clear?' : 'Clear All'}</span>
              </button>
            )}
            <button
              type="button"
              className="hub-ai-history-close-btn"
              onClick={onClose}
              title="Close history (Esc)"
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Filter Input if history is not empty */}
        {history.length > 1 && (
          <div className="hub-ai-history-search-bar">
            <Search size={14} className="hub-ai-history-search-icon" />
            <input
              ref={filterInputRef}
              type="text"
              className="hub-ai-history-search-input"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Filter past searches..."
            />
            {filterText && (
              <button
                type="button"
                className="hub-ai-history-filter-clear"
                onClick={() => setFilterText('')}
                title="Clear filter"
              >
                <X size={12} />
              </button>
            )}
          </div>
        )}

        {/* Query List */}
        <div className="hub-ai-history-list-wrap">
          {history.length === 0 ? (
            <div className="hub-ai-history-empty">
              <div className="hub-ai-history-empty-icon-wrap">
                <Clock size={36} className="hub-ai-history-empty-icon" />
              </div>
              <h4 className="hub-ai-history-empty-title">No Search History Yet</h4>
              <p className="hub-ai-history-empty-desc">
                Every AI query you submit or prompt chip you explore will be saved here so you can re-run recommendations with one click.
              </p>
            </div>
          ) : filteredHistory.length === 0 ? (
            <div className="hub-ai-history-empty">
              <p className="hub-ai-history-empty-desc">
                No past queries match "{filterText}".
              </p>
            </div>
          ) : (
            <ul className="hub-ai-history-list" role="list">
              {filteredHistory.map((item) => (
                <li
                  key={item.id}
                  className="hub-ai-history-item"
                  onClick={() => onSelectQuery(item.query)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelectQuery(item.query);
                    }
                  }}
                  title={`Run search: "${item.query}"`}
                >
                  <div className="hub-ai-history-item-icon">
                    <Sparkles size={15} />
                  </div>

                  <div className="hub-ai-history-item-content">
                    <div className="hub-ai-history-item-query">{item.query}</div>
                    <div className="hub-ai-history-item-time">
                      <Clock size={11} className="time-clock-icon" />
                      <span>{formatTimestamp(item.timestamp)}</span>
                    </div>
                  </div>

                  <div className="hub-ai-history-item-actions">
                    <span className="hub-ai-history-run-hint">
                      <Play size={11} fill="currentColor" />
                      <span>Search</span>
                    </span>

                    <button
                      type="button"
                      className="hub-ai-history-item-delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteQuery(item.id);
                      }}
                      title="Delete from history"
                      aria-label={`Delete "${item.query}" from history`}
                    >
                      <X size={14} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Modal Footer hint */}
        {history.length > 0 && (
          <div className="hub-ai-history-footer">
            <span className="hub-ai-history-footer-hint">
              💡 Tip: Click any query to immediately execute recommendation search.
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

