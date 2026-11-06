import React, { useState, useEffect } from 'react';
import {
  X,
  Key,
  Eye,
  EyeOff,
  Check,
  AlertCircle,
  RotateCcw,
  Trash2,
  ShieldCheck,
} from 'lucide-react';
import {
  TMDBKeyStatusResponse,
  testTMDBKey,
  saveAndActivateTMDBKey,
  activateTMDBKey,
  deleteTMDBKeyHistory,
} from '../../api/movieApi';
import './MovieHubSubModals.css';

interface TMDBConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  status: TMDBKeyStatusResponse | null;
  onStatusChange: (status: TMDBKeyStatusResponse) => void;
}

export const TMDBConfigModal: React.FC<TMDBConfigModalProps> = ({
  isOpen,
  onClose,
  status,
  onStatusChange,
}) => {
  const [newKey, setNewKey] = useState('');
  const [keyLabel, setKeyLabel] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) {
      setNewKey('');
      setKeyLabel('');
      setShowKey(false);
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

  const handleTestKey = async () => {
    const candidate = newKey.trim();
    setTesting(true);
    setNotice(null);

    try {
      const res = await testTMDBKey(candidate || undefined);
      if (res.valid) {
        setNotice({
          type: 'success',
          message: 'Connection verified! TMDB API authenticated successfully.',
        });
      } else {
        setNotice({
          type: 'error',
          message: res.message || 'Verification failed. Please check the API key.',
        });
      }
    } catch (err: any) {
      setNotice({
        type: 'error',
        message: err?.message || 'Failed to verify key with TMDB service.',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSaveKey = async () => {
    const candidate = newKey.trim();
    if (!candidate) {
      setNotice({ type: 'error', message: 'Please enter a TMDB API key before saving.' });
      return;
    }

    setSaving(true);
    setNotice(null);

    try {
      const updated = await saveAndActivateTMDBKey(candidate, keyLabel.trim() || undefined);
      onStatusChange(updated);
      setNewKey('');
      setKeyLabel('');
      setNotice({
        type: 'success',
        message: 'TMDB API key successfully verified, encrypted with DPAPI, and activated!',
      });
    } catch (err: any) {
      setNotice({
        type: 'error',
        message: err?.message || 'Failed to activate key: Verification check rejected.',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleActivateKey = async (keyId: string) => {
    setNotice(null);
    try {
      const updated = await activateTMDBKey(keyId);
      onStatusChange(updated);
      setNotice({
        type: 'success',
        message: keyId === 'env' ? 'Reverted to .env fallback API key.' : 'Switched active TMDB API key.',
      });
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Failed to activate key.' });
    }
  };

  const handleDeleteKey = async (keyId: string) => {
    if (!window.confirm('Remove this API key from saved history?')) return;
    setNotice(null);
    try {
      const updated = await deleteTMDBKeyHistory(keyId);
      onStatusChange(updated);
      setNotice({ type: 'success', message: 'API key removed from history.' });
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Failed to delete history item.' });
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
            <div className="settings-submodal-badge badge-indigo">
              <Key size={20} />
            </div>
            <div className="settings-submodal-title-group">
              <h3 className="settings-submodal-title">TMDB API Key Configuration</h3>
              <p className="settings-submodal-subtitle">
                Manage TMDB API credentials, OS-level secure storage, and active metadata keys.
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

          {/* Group 1: Connection Status & Active Key */}
          <div className="apple-grouped-inset">
            <div className="setting-row">
              <div className="setting-meta">
                <span className="setting-title">TMDB Connection Status</span>
                <span className="setting-caption">Real-time authentication reachability to TMDB API</span>
              </div>
              <span className={`settings-tmdb-status-pill ${status?.configured ? 'connected' : 'disconnected'}`}>
                <span className="settings-status-dot" />
                {status?.configured ? 'Connected & Active' : 'Not Configured'}
              </span>
            </div>

            <div className="setting-row">
              <div className="setting-meta">
                <span className="setting-title">Active API Key</span>
                <span className="setting-caption">Key currently powering Movie Hub searches and metadata</span>
              </div>
              <div className="settings-active-key-box">
                <span className="settings-masked-text">{status?.masked_key || 'None'}</span>
                {status?.source === 'custom' && (
                  <span className="settings-source-tag custom">Custom Key</span>
                )}
                {status?.source === 'env' && (
                  <span className="settings-source-tag env">.env Fallback</span>
                )}
              </div>
            </div>

            {status?.source === 'custom' && status?.has_env_fallback && (
              <div className="setting-row">
                <div className="setting-meta">
                  <span className="setting-title">System .env Fallback</span>
                  <span className="setting-caption">Revert to original key configured in local .env</span>
                </div>
                <button
                  type="button"
                  className="settings-inline-btn settings-inline-btn-secondary"
                  onClick={() => handleActivateKey('env')}
                >
                  <RotateCcw size={12} />
                  <span>Revert to .env</span>
                </button>
              </div>
            )}
          </div>

          {/* Group 2: Update TMDB API Key */}
          <h4 className="submodal-section-heading">
            Update TMDB API Key
          </h4>
          <div className="apple-grouped-inset">
            <div className="submodal-field-group">
              <div className="setting-meta">
                <span className="setting-title">API Key or Read Token</span>
                <span className="setting-caption">Supports 32-character v3 keys or v4 Bearer access tokens</span>
              </div>
              <div className="submodal-input-wrapper">
                <input
                  type={showKey ? 'text' : 'password'}
                  className="apple-input-text"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  placeholder="Paste new TMDB API key or Bearer access token..."
                  autoComplete="off"
                  spellCheck="false"
                  disabled={saving || testing}
                />
                <button
                  type="button"
                  className="submodal-eye-btn"
                  onClick={() => setShowKey(!showKey)}
                  title={showKey ? 'Hide key' : 'Show key'}
                >
                  {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div className="submodal-field-group">
              <div className="setting-meta">
                <span className="setting-title">Key Label (Optional)</span>
                <span className="setting-caption">Friendly identifier saved in local key history</span>
              </div>
              <input
                type="text"
                className="apple-input-text"
                value={keyLabel}
                onChange={(e) => setKeyLabel(e.target.value)}
                placeholder="E.g., Personal TMDB Account"
                disabled={saving || testing}
              />
            </div>

            <div className="submodal-action-row">
              <button
                type="button"
                className="settings-inline-btn settings-inline-btn-secondary"
                onClick={handleTestKey}
                disabled={testing || saving || (!newKey.trim() && !status?.configured)}
                title="Verify reachability and authentication with TMDB"
              >
                {testing ? <RotateCcw size={12} className="spin-loader" /> : <RotateCcw size={12} />}
                <span>{testing ? 'Testing...' : 'Test Connection'}</span>
              </button>

              <button
                type="button"
                className="settings-inline-btn settings-inline-btn-primary"
                onClick={handleSaveKey}
                disabled={saving || testing || !newKey.trim()}
                title="Verify, encrypt with DPAPI, and activate key"
              >
                <Check size={12} />
                <span>{saving ? 'Validating & Saving...' : 'Save & Activate'}</span>
              </button>
            </div>
          </div>

          {/* Group 3: Saved API Keys & History */}
          <h4 className="submodal-section-heading">
            Saved API Keys &amp; History
          </h4>
          <div className="apple-grouped-inset">
            {/* System .env fallback entry */}
            {status?.has_env_fallback && (
              <div className="settings-history-row">
                <div className="settings-history-item-left">
                  <div className="settings-history-label-row">
                    <span className="settings-history-item-label">System Initial Fallback (.env)</span>
                    {status.source === 'env' && (
                      <span className="settings-active-badge">Active</span>
                    )}
                  </div>
                  <span className="settings-history-item-meta">{status.env_masked_key}</span>
                </div>
                <div className="settings-history-item-actions">
                  {status.source !== 'env' && (
                    <button
                      type="button"
                      className="settings-history-activate-btn"
                      onClick={() => handleActivateKey('env')}
                      title="Activate this key"
                    >
                      Activate
                    </button>
                  )}
                </div>
              </div>
            )}

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
                    <span className="settings-history-item-meta">{item.masked_key}</span>
                  </div>
                  <div className="settings-history-item-actions">
                    {!item.is_active && (
                      <button
                        type="button"
                        className="settings-history-activate-btn"
                        onClick={() => handleActivateKey(item.id)}
                        title="Activate this key"
                      >
                        Activate
                      </button>
                    )}
                    <button
                      type="button"
                      className="settings-history-delete-btn"
                      onClick={() => handleDeleteKey(item.id)}
                      title="Remove key from history"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))
            ) : !status?.has_env_fallback ? (
              <div style={{ padding: '14px', fontSize: '12px', color: '#8E8E93', fontStyle: 'italic' }}>
                No previous keys configured yet.
              </div>
            ) : null}
          </div>

          {/* Security Note */}
          <div className="settings-security-note">
            <ShieldCheck size={14} style={{ color: '#30D158', flexShrink: 0 }} />
            <span>
              Keys are securely encrypted using Windows DPAPI. Plaintext keys are never stored in settings or logs.
            </span>
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

