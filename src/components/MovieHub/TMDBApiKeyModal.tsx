import React, { useState, useEffect } from 'react';
import {
  Key,
  Eye,
  EyeOff,
  Check,
  AlertCircle,
  Loader2,
  ShieldCheck,
  Trash2,
  X,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import {
  fetchTMDBKeyStatus,
  testTMDBKey,
  saveAndActivateTMDBKey,
  activateTMDBKey,
  deleteTMDBKeyHistory,
  TMDBKeyStatusResponse,
} from '../../api/movieApi';
import './TMDBApiKeyModal.css';

interface TMDBApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onKeyChanged?: () => void;
}

export const TMDBApiKeyModal: React.FC<TMDBApiKeyModalProps> = ({
  isOpen,
  onClose,
  onKeyChanged,
}) => {
  const [status, setStatus] = useState<TMDBKeyStatusResponse | null>(null);
  const [newKey, setNewKey] = useState('');
  const [keyLabel, setKeyLabel] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);
  const [alertSuccess, setAlertSuccess] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      const res = await fetchTMDBKeyStatus();
      setStatus(res);
    } catch (e: any) {
      console.error('Failed to load TMDB key status:', e);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadStatus();
      setNewKey('');
      setKeyLabel('');
      setShowKey(false);
      setTestResult(null);
      setAlertError(null);
      setAlertSuccess(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleTestConnection = async () => {
    const candidate = newKey.trim();
    setTesting(true);
    setTestResult(null);
    setAlertError(null);

    try {
      const res = await testTMDBKey(candidate || undefined);
      if (res.valid) {
        setTestResult({
          success: true,
          message: 'Connection verified! TMDB API authenticated successfully.',
        });
      } else {
        setTestResult({
          success: false,
          message: res.message || 'Verification failed. Please check the API key.',
        });
      }
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err?.message || 'Failed to verify key with TMDB service.',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSaveAndActivate = async () => {
    const candidate = newKey.trim();
    if (!candidate) {
      setAlertError('Please enter a TMDB API key before saving.');
      return;
    }

    setSaving(true);
    setAlertError(null);
    setAlertSuccess(null);
    setTestResult(null);

    try {
      const updated = await saveAndActivateTMDBKey(candidate, keyLabel.trim() || undefined);
      setStatus(updated);
      setNewKey('');
      setKeyLabel('');
      setAlertSuccess('TMDB API key successfully verified, encrypted, and activated!');
      if (onKeyChanged) onKeyChanged();
    } catch (err: any) {
      setAlertError(err?.message || 'Failed to activate key: Verification check rejected.');
    } finally {
      setSaving(false);
    }
  };

  const handleActivateHistoryKey = async (keyId: string) => {
    setAlertError(null);
    setAlertSuccess(null);
    try {
      const updated = await activateTMDBKey(keyId);
      setStatus(updated);
      setAlertSuccess(keyId === 'env' ? 'Reverted to .env fallback API key.' : 'Switched active TMDB API key.');
      if (onKeyChanged) onKeyChanged();
    } catch (err: any) {
      setAlertError(err?.message || 'Failed to activate key.');
    }
  };

  const handleDeleteHistoryKey = async (keyId: string) => {
    if (!window.confirm('Remove this API key from saved history?')) return;

    setAlertError(null);
    setAlertSuccess(null);
    try {
      const updated = await deleteTMDBKeyHistory(keyId);
      setStatus(updated);
      setAlertSuccess('API key removed from history.');
      if (onKeyChanged) onKeyChanged();
    } catch (err: any) {
      setAlertError(err?.message || 'Failed to delete history item.');
    }
  };

  return (
    <div className="tmdb-modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="tmdb-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="tmdb-modal-header">
          <div className="tmdb-modal-title-group">
            <div className="tmdb-modal-icon-badge">
              <Key size={20} />
            </div>
            <div>
              <h3 className="tmdb-modal-title">TMDB API Key</h3>
              <p className="tmdb-modal-subtitle">Manage personal and fallback credentials for Movie Hub</p>
            </div>
          </div>
          <button className="tmdb-modal-close-btn" onClick={onClose} title="Close modal" aria-label="Close modal">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="tmdb-modal-body">
          {/* Status Card */}
          <div className="tmdb-status-card">
            <div className="tmdb-status-row">
              <span className="tmdb-status-label">Current Status</span>
              <span className={`tmdb-status-badge ${status?.configured ? 'connected' : 'disconnected'}`}>
                <span className="tmdb-status-dot" />
                {status?.configured ? 'Connected & Active' : 'Not Configured'}
              </span>
            </div>

            <div className="tmdb-active-key-info">
              <span>{status?.masked_key || 'No active key'}</span>
              {status?.source === 'custom' && <span className="tmdb-source-tag">Custom Key</span>}
              {status?.source === 'env' && <span className="tmdb-source-tag env-tag">.env Fallback</span>}
            </div>
          </div>

          {/* Alert Notifications */}
          {alertSuccess && (
            <div className="tmdb-alert success">
              <Check size={16} />
              <span>{alertSuccess}</span>
            </div>
          )}

          {alertError && (
            <div className="tmdb-alert error">
              <AlertCircle size={16} />
              <span>{alertError}</span>
            </div>
          )}

          {testResult && (
            <div className={`tmdb-alert ${testResult.success ? 'success' : 'error'}`}>
              {testResult.success ? <Check size={16} /> : <AlertCircle size={16} />}
              <span>{testResult.message}</span>
            </div>
          )}

          {/* New Key Input Form */}
          <div className="tmdb-form-section">
            <h4 className="tmdb-section-heading">Configure New API Key</h4>

            <div className="tmdb-input-group">
              <label className="tmdb-input-label">TMDB API Key (v3 Key or v4 Read Access Token)</label>
              <div className="tmdb-key-input-wrapper">
                <input
                  type={showKey ? 'text' : 'password'}
                  className="tmdb-text-input"
                  placeholder="Paste your 32-character key or Bearer token..."
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  disabled={saving || testing}
                  autoComplete="off"
                  spellCheck="false"
                />
                <button
                  type="button"
                  className="tmdb-input-toggle-btn"
                  onClick={() => setShowKey(!showKey)}
                  title={showKey ? 'Hide Key' : 'Show Key'}
                  aria-label={showKey ? 'Hide Key' : 'Show Key'}
                >
                  {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div className="tmdb-input-group">
              <label className="tmdb-input-label">Label (Optional)</label>
              <input
                type="text"
                className="tmdb-label-input"
                placeholder="E.g. Personal Account Key"
                value={keyLabel}
                onChange={(e) => setKeyLabel(e.target.value)}
                disabled={saving || testing}
              />
            </div>

            <div className="tmdb-form-actions">
              <button
                type="button"
                className="tmdb-btn tmdb-btn-secondary"
                onClick={handleTestConnection}
                disabled={testing || saving || (!newKey.trim() && !status?.configured)}
                title="Verify connection to TMDB before saving"
              >
                {testing ? <Loader2 size={13} className="spin-loader" /> : <RotateCcw size={13} />}
                <span>{testing ? 'Testing...' : 'Test Connection'}</span>
              </button>

              <button
                type="button"
                className="tmdb-btn tmdb-btn-primary"
                onClick={handleSaveAndActivate}
                disabled={saving || testing || !newKey.trim()}
                title="Verify, encrypt with DPAPI, and activate key"
              >
                {saving ? <Loader2 size={13} className="spin-loader" /> : <Check size={13} />}
                <span>{saving ? 'Validating & Saving...' : 'Save & Activate'}</span>
              </button>
            </div>
          </div>

          {/* History / Previous Keys */}
          <div className="tmdb-history-section">
            <h4 className="tmdb-section-heading">Saved Keys &amp; History</h4>

            <div className="tmdb-history-list">
              {/* .env Fallback entry if available */}
              {status?.has_env_fallback && (
                <div className={`tmdb-history-item ${status.source === 'env' ? 'active' : ''}`}>
                  <div className="tmdb-history-info">
                    <div className="tmdb-history-label-row">
                      <span className="tmdb-history-label">System Initial Fallback (.env)</span>
                      {status.source === 'env' && <span className="tmdb-history-active-tag">Active</span>}
                    </div>
                    <span className="tmdb-history-meta">{status.env_masked_key}</span>
                  </div>

                  <div className="tmdb-history-actions">
                    {status.source !== 'env' && (
                      <button
                        type="button"
                        className="tmdb-history-btn"
                        onClick={() => handleActivateHistoryKey('env')}
                        title="Revert to system .env fallback key"
                      >
                        Activate
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Custom History Items */}
              {status?.history && status.history.length > 0 ? (
                status.history.map((item) => (
                  <div key={item.id} className={`tmdb-history-item ${item.is_active ? 'active' : ''}`}>
                    <div className="tmdb-history-info">
                      <div className="tmdb-history-label-row">
                        <span className="tmdb-history-label">{item.label}</span>
                        {item.is_active && <span className="tmdb-history-active-tag">Active</span>}
                      </div>
                      <span className="tmdb-history-meta">{item.masked_key}</span>
                    </div>

                    <div className="tmdb-history-actions">
                      {!item.is_active && (
                        <button
                          type="button"
                          className="tmdb-history-btn"
                          onClick={() => handleActivateHistoryKey(item.id)}
                          title="Activate this key"
                        >
                          Activate
                        </button>
                      )}
                      <button
                        type="button"
                        className="tmdb-history-del-btn"
                        onClick={() => handleDeleteHistoryKey(item.id)}
                        title="Delete key from history"
                        aria-label="Delete key"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                ))
              ) : !status?.has_env_fallback ? (
                <div className="tmdb-history-empty">No previous keys saved yet.</div>
              ) : null}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="tmdb-modal-footer">
          <ShieldCheck size={14} className="tmdb-footer-icon" />
          <span>
            Encrypted with OS credential protection (Windows DPAPI). Keys are never stored in plaintext or logged.
          </span>
        </div>
      </div>
    </div>
  );
};

