import React, { useState, useEffect } from 'react';
import {
  X,
  Globe,
  Check,
  AlertCircle,
  RotateCcw,
  Trash2,
  ExternalLink,
} from 'lucide-react';
import {
  HDHub4uStatusResponse,
  testHDHub4uUrl,
  saveAndActivateHDHub4uUrl,
  activateHDHub4uUrl,
  deleteHDHub4uHistory,
  resetHDHub4uUrl,
  resolveHdHub4uUrl,
  sanitizeHdHub4uUrl,
} from '../../api/movieApi';
import './MovieHubSubModals.css';

interface HDHub4uConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  status: HDHub4uStatusResponse | null;
  onStatusChange: (status: HDHub4uStatusResponse) => void;
}

export const HDHub4uConfigModal: React.FC<HDHub4uConfigModalProps> = ({
  isOpen,
  onClose,
  status,
  onStatusChange,
}) => {
  const [newUrl, setNewUrl] = useState('');
  const [label, setLabel] = useState('');
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) {
      setNewUrl('');
      setLabel('');
      setNotice(null);
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleUrlChange = (val: string) => {
    // Auto-clean pasted duplicated schemes immediately
    if (val.includes('http://') && val.indexOf('http://') !== val.lastIndexOf('http://')) {
      setNewUrl(sanitizeHdHub4uUrl(val));
    } else if (val.includes('https://') && val.indexOf('https://') !== val.lastIndexOf('https://')) {
      setNewUrl(sanitizeHdHub4uUrl(val));
    } else {
      setNewUrl(val);
    }
  };

  const handleFillDefault = () => {
    setNewUrl('https://new10.hdhub4u.cl/search.html?q=pixels');
    setLabel('Default HDHub4u (.cl)');
    setNotice(null);
  };

  const handleFillCurrent = () => {
    if (status?.active_url) {
      setNewUrl(status.active_url);
      setNotice(null);
    }
  };

  const handleTestUrl = async () => {
    const candidate = newUrl.trim() ? sanitizeHdHub4uUrl(newUrl.trim()) : undefined;
    setTesting(true);
    setNotice(null);

    try {
      const res = await testHDHub4uUrl(candidate);
      if (res.valid) {
        setNotice({
          type: 'success',
          message: `${res.message} Preview: ${res.preview_url}`,
        });
      } else {
        setNotice({
          type: 'error',
          message: res.message || 'Validation failed for HDHub4u URL.',
        });
      }
    } catch (err: any) {
      setNotice({
        type: 'error',
        message: err?.message || 'Failed to verify HDHub4u URL.',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSaveUrl = async () => {
    const rawCandidate = newUrl.trim();
    if (!rawCandidate) {
      setNotice({ type: 'error', message: 'Please enter an HDHub4u search URL before saving.' });
      return;
    }

    const candidate = sanitizeHdHub4uUrl(rawCandidate);
    setSaving(true);
    setNotice(null);

    try {
      const updated = await saveAndActivateHDHub4uUrl(candidate, label.trim() || undefined);
      onStatusChange(updated);
      setNewUrl('');
      setLabel('');
      setNotice({
        type: 'success',
        message: 'HDHub4u URL template saved into mirror history and activated!',
      });
    } catch (err: any) {
      setNotice({
        type: 'error',
        message: err?.message || 'Failed to save HDHub4u template.',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleActivateUrl = async (id: string) => {
    setNotice(null);
    try {
      const updated = await activateHDHub4uUrl(id);
      onStatusChange(updated);
      setNotice({
        type: 'success',
        message: id === 'default' ? 'Reverted HDHub4u URL to default template.' : 'Switched active HDHub4u mirror.',
      });
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Failed to activate mirror.' });
    }
  };

  const handleDeleteHistory = async (id: string) => {
    if (!window.confirm('Remove this mirror from HDHub4u history?')) return;
    setNotice(null);
    try {
      const updated = await deleteHDHub4uHistory(id);
      onStatusChange(updated);
      setNotice({ type: 'success', message: 'Mirror removed from HDHub4u history.' });
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Failed to delete mirror.' });
    }
  };

  const handleResetUrl = async () => {
    setNotice(null);
    try {
      const updated = await resetHDHub4uUrl();
      onStatusChange(updated);
      setNotice({ type: 'success', message: 'Reset HDHub4u URL to default template.' });
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Failed to reset URL.' });
    }
  };

  return (
    <div
      className="settings-submodal-scrim"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
      onMouseDown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="settings-submodal-card"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="settings-submodal-header">
          <div className="settings-submodal-header-left">
            <div className="settings-submodal-badge badge-purple">
              <Globe size={20} />
            </div>
            <div className="settings-submodal-title-group">
              <h3 className="settings-submodal-title">HDHub4u Link &amp; Mirror Configuration</h3>
              <p className="settings-submodal-subtitle">
                Configure search templates with dynamic <code style={{ color: '#BF5AF2' }}>pixels</code> movie title replacement.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="settings-submodal-close-btn"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            title="Close window"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="settings-submodal-body">
          {notice && (
            <div className={`settings-notice-banner ${notice.type}`}>
              {notice.type === 'success' ? <Check size={14} /> : <AlertCircle size={14} />}
              <span>{notice.message}</span>
            </div>
          )}

          {/* Group 1: Active Template & Dynamic Substitution */}
          <div className="apple-grouped-inset">
            <div className="setting-row">
              <div className="setting-meta">
                <span className="setting-title">Active HDHub4u Template</span>
                <span className="setting-caption">Search link currently powering the Movie Hub &ldquo;Download here&rdquo; button</span>
              </div>
              <span className={`settings-tmdb-status-pill ${status?.active_url ? 'connected' : 'disconnected'}`}>
                <span className="settings-status-dot" />
                {status?.is_custom ? 'Custom Mirror Active' : 'Default (.cl) Active'}
              </span>
            </div>

            <div className="setting-row">
              <div className="setting-meta">
                <span className="setting-title">Current Search URL</span>
                <span className="setting-caption">Contains &apos;pixels&apos; title placeholder</span>
              </div>
              <div className="settings-active-key-box" style={{ maxWidth: '420px' }}>
                <span className="settings-masked-text" style={{ wordBreak: 'break-all', fontFamily: 'monospace' }}>
                  {sanitizeHdHub4uUrl(status?.active_url || 'https://new10.hdhub4u.cl/search.html?q=pixels')}
                </span>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-meta">
                <span className="setting-title">Dynamic Keyword Substitution Preview</span>
                <span className="setting-caption">Whatever movie is open replaces the &apos;pixels&apos; keyword</span>
              </div>
              <div className="settings-preview-code-box">
                Movie: &ldquo;Premalu&rdquo; &rarr; {resolveHdHub4uUrl(status?.active_url, 'Premalu')}
              </div>
            </div>

            {status?.is_custom && (
              <div className="setting-row">
                <div className="setting-meta">
                  <span className="setting-title">Reset to Default Template</span>
                  <span className="setting-caption">Revert back to https://new10.hdhub4u.cl/search.html?q=pixels</span>
                </div>
                <button
                  type="button"
                  className="settings-inline-btn settings-inline-btn-secondary"
                  onClick={handleResetUrl}
                >
                  <RotateCcw size={12} />
                  <span>Revert to Default</span>
                </button>
              </div>
            )}
          </div>

          {/* Group 2: Update HDHub4u Link */}
          <div className="submodal-section-header-row">
            <h4 className="submodal-section-heading">
              Update HDHub4u Link or Mirror
            </h4>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                className="settings-quick-fill-btn"
                onClick={handleFillDefault}
                title="Fill input with default HDHub4u (.cl) template"
              >
                Use Default (.cl)
              </button>
              {status?.active_url && (
                <button
                  type="button"
                  className="settings-quick-fill-btn"
                  onClick={handleFillCurrent}
                  title="Copy current active template into input for editing"
                >
                  Use Current
                </button>
              )}
            </div>
          </div>

          <div className="apple-grouped-inset">
            <div className="submodal-field-group">
              <div className="setting-meta">
                <span className="setting-title">Search URL or Mirror Link</span>
                <span className="setting-caption">
                  Include &apos;pixels&apos; keyword (e.g. <code style={{ color: '#BF5AF2' }}>https://new10.hdhub4u.cl/search.html?q=pixels</code>)
                </span>
              </div>
              <input
                type="text"
                className="apple-input-text"
                value={newUrl}
                onChange={(e) => handleUrlChange(e.target.value)}
                onBlur={() => newUrl.trim() && setNewUrl(sanitizeHdHub4uUrl(newUrl))}
                placeholder="https://new10.hdhub4u.cl/search.html?q=pixels"
                spellCheck="false"
                disabled={saving || testing}
              />
            </div>

            {/* Live Search URL Preview for Sample Movie */}
            <div className="submodal-field-group">
              <div className="setting-meta">
                <span className="setting-title">Target Movie Search Preview</span>
                <span className="setting-caption">
                  How movie searches (e.g. &ldquo;Premalu&rdquo;) will be generated
                </span>
              </div>
              <div
                className="settings-preview-code-box"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '10px',
                  width: '100%',
                  boxSizing: 'border-box',
                }}
              >
                <span
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontFamily: 'monospace',
                    fontSize: '11.5px',
                    minWidth: 0,
                    flex: '1 1 auto',
                  }}
                  title={resolveHdHub4uUrl(newUrl || status?.active_url, 'Premalu')}
                >
                  {resolveHdHub4uUrl(newUrl || status?.active_url, 'Premalu')}
                </span>
                <a
                  href={resolveHdHub4uUrl(newUrl || status?.active_url, 'Premalu')}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="settings-open-preview-btn"
                  title="Test opening this sample search in your browser"
                >
                  <ExternalLink size={11} />
                  <span>Open Link</span>
                </a>
              </div>
            </div>

            <div className="submodal-field-group">
              <div className="setting-meta">
                <span className="setting-title">Mirror Label (Optional)</span>
                <span className="setting-caption">Friendly identifier saved in mirror history</span>
              </div>
              <input
                type="text"
                className="apple-input-text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="E.g., HDHub4u Mirror 10 (.cl)"
                disabled={saving || testing}
              />
            </div>

            <div className="submodal-action-row">
              <button
                type="button"
                className="settings-inline-btn settings-inline-btn-secondary"
                onClick={handleTestUrl}
                disabled={testing || saving || (!newUrl.trim() && !status?.active_url)}
                title="Test URL format, reachability, and replacement preview"
              >
                {testing ? <RotateCcw size={12} className="spin-loader" /> : <RotateCcw size={12} />}
                <span>{testing ? 'Testing Link...' : 'Test Link'}</span>
              </button>

              <button
                type="button"
                className="settings-inline-btn settings-inline-btn-primary"
                onClick={handleSaveUrl}
                disabled={saving || testing || !newUrl.trim()}
                title="Save URL to history and activate immediately"
              >
                <Check size={12} />
                <span>{saving ? 'Saving...' : 'Save & Activate'}</span>
              </button>
            </div>
          </div>

          {/* Group 3: Saved Mirrors & History */}
          <h4 className="submodal-section-heading">
            Saved Mirrors &amp; History
          </h4>
          <div className="apple-grouped-inset">
            {/* Default Template Entry */}
            <div className="settings-history-row">
              <div className="settings-history-item-left">
                <div className="settings-history-label-row">
                  <span className="settings-history-item-label">Default HDHub4u (.cl)</span>
                  {!status?.is_custom && (
                    <span className="settings-active-badge">Active</span>
                  )}
                </div>
                <span className="settings-history-item-meta">https://new10.hdhub4u.cl/search.html?q=pixels</span>
              </div>
              <div className="settings-history-item-actions">
                {status?.is_custom && (
                  <button
                    type="button"
                    className="settings-history-activate-btn"
                    onClick={() => handleActivateUrl('default')}
                    title="Activate default template"
                  >
                    Activate
                  </button>
                )}
              </div>
            </div>

            {/* Custom History Entries */}
            {status?.history && status.history.length > 0 ? (
              status.history.map((item) => (
                <div key={item.id} className="settings-history-row">
                  <div className="settings-history-item-left">
                    <div className="settings-history-label-row">
                      <span className="settings-history-item-label">{item.label}</span>
                      {item.is_active && (
                        <span className="settings-active-badge">Active</span>
                      )}
                    </div>
                    <span className="settings-history-item-meta">{item.url_template}</span>
                  </div>
                  <div className="settings-history-item-actions">
                    {!item.is_active && (
                      <button
                        type="button"
                        className="settings-history-activate-btn"
                        onClick={() => handleActivateUrl(item.id)}
                        title="Activate this mirror"
                      >
                        Activate
                      </button>
                    )}
                    <button
                      type="button"
                      className="settings-history-delete-btn"
                      onClick={() => handleDeleteHistory(item.id)}
                      title="Remove mirror from history"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))
            ) : null}
          </div>
        </div>

        {/* Footer */}
        <div className="settings-submodal-footer">
          <button
            type="button"
            className="settings-inline-btn settings-inline-btn-primary"
            onClick={onClose}
          >
            <span>Done</span>
          </button>
        </div>
      </div>
    </div>
  );
};

