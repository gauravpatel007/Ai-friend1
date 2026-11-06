import React, { useState, useEffect } from 'react';
import {
  X,
  Tv,
  Check,
  AlertCircle,
  RotateCcw,
  Search,
  ExternalLink,
  Film,
} from 'lucide-react';
import {
  WatchProviderConfigItem,
  fetchWatchProviderTemplates,
  saveWatchProviderTemplates,
  resetWatchProviderTemplates,
  resolveWatchProviderUrl,
} from '../../api/movieApi';
import './MovieHubSubModals.css';

interface WatchProvidersConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export const WatchProvidersConfigModal: React.FC<WatchProvidersConfigModalProps> = ({
  isOpen,
  onClose,
  onSaved,
}) => {
  const [providers, setProviders] = useState<WatchProviderConfigItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [sampleMovie, setSampleMovie] = useState('Law & Order: Special Victims Unit');
  const [editedTemplates, setEditedTemplates] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Load provider templates on open
  useEffect(() => {
    if (!isOpen) {
      setSearchTerm('');
      setNotice(null);
      return;
    }

    setLoading(true);
    fetchWatchProviderTemplates(sampleMovie)
      .then((res) => {
        setProviders(res.providers || []);
        const initialMap: Record<string, string> = {};
        res.providers.forEach((p) => {
          initialMap[p.key] = p.template;
        });
        setEditedTemplates(initialMap);
      })
      .catch((err) => {
        setNotice({ type: 'error', message: err?.message || 'Failed to load streaming templates.' });
      })
      .finally(() => setLoading(false));
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleTemplateChange = (key: string, value: string) => {
    setEditedTemplates((prev) => ({ ...prev, [key]: value }));
  };

  const handleResetSingle = (key: string, defaultTmpl: string) => {
    setEditedTemplates((prev) => ({ ...prev, [key]: defaultTmpl }));
  };

  const handleSaveAll = async () => {
    setSaving(true);
    setNotice(null);

    try {
      const res = await saveWatchProviderTemplates(editedTemplates);
      setProviders(res.providers || []);
      const updatedMap: Record<string, string> = {};
      res.providers.forEach((p) => {
        updatedMap[p.key] = p.template;
      });
      setEditedTemplates(updatedMap);
      setNotice({
        type: 'success',
        message: 'Streaming search templates saved successfully!',
      });
      onSaved?.();
    } catch (err: any) {
      setNotice({
        type: 'error',
        message: err?.message || 'Failed to save streaming templates.',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleResetAll = async () => {
    if (!window.confirm('Reset all streaming search URL templates to system defaults?')) return;
    setSaving(true);
    setNotice(null);

    try {
      const res = await resetWatchProviderTemplates();
      setProviders(res.providers || []);
      const updatedMap: Record<string, string> = {};
      res.providers.forEach((p) => {
        updatedMap[p.key] = p.template;
      });
      setEditedTemplates(updatedMap);
      setNotice({
        type: 'success',
        message: 'All streaming search templates have been reset to defaults.',
      });
      onSaved?.();
    } catch (err: any) {
      setNotice({
        type: 'error',
        message: err?.message || 'Failed to reset streaming templates.',
      });
    } finally {
      setSaving(false);
    }
  };

  const filteredProviders = providers.filter((p) => {
    const q = searchTerm.trim().toLowerCase();
    if (!q) return true;
    return (
      p.label.toLowerCase().includes(q) ||
      p.key.toLowerCase().includes(q) ||
      p.description.toLowerCase().includes(q)
    );
  });

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
            <div className="settings-submodal-badge badge-teal">
              <Tv size={20} />
            </div>
            <div className="settings-submodal-title-group">
              <h3 className="settings-submodal-title">Where to Watch &amp; Streaming Links</h3>
              <p className="settings-submodal-subtitle">
                Configure search URL templates with dynamic movie name replacement for JioHotstar, Netflix, and 20+ services.
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

          {/* Group 1: Live Sample Movie Substitution Preview Control */}
          <div className="apple-grouped-inset">
            <div className="setting-row">
              <div className="setting-meta">
                <span className="setting-title">Target Sample Movie Title</span>
                <span className="setting-caption">
                  Whatever title is entered here dynamically replaces &apos;{'{title}'}&apos; in previews and test links
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Film size={14} style={{ color: '#0A84FF' }} />
                <input
                  type="text"
                  className="apple-input-text"
                  style={{ width: '280px' }}
                  value={sampleMovie}
                  onChange={(e) => setSampleMovie(e.target.value)}
                  placeholder="e.g. Law & Order: Special Victims Unit"
                />
              </div>
            </div>
          </div>

          {/* Group 2: Filter and Bulk Actions */}
          <div className="submodal-section-header-row">
            <div style={{ position: 'relative', width: '260px' }}>
              <Search
                size={14}
                style={{
                  position: 'absolute',
                  left: '10px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'rgba(255, 255, 255, 0.4)',
                }}
              />
              <input
                type="text"
                className="apple-input-text"
                style={{ width: '100%', paddingLeft: '32px' }}
                placeholder="Filter services (hotstar, netflix...)"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                className="settings-quick-fill-btn"
                onClick={handleResetAll}
                disabled={saving}
                title="Reset all streaming templates back to system defaults"
              >
                Reset All to Defaults
              </button>
              <button
                type="button"
                className="settings-inline-btn settings-inline-btn-primary"
                onClick={handleSaveAll}
                disabled={saving}
                title="Save all changes to streaming templates"
              >
                <Check size={12} />
                <span>{saving ? 'Saving...' : 'Save Changes'}</span>
              </button>
            </div>
          </div>

          {/* Group 3: Provider Templates List */}
          <h4 className="submodal-section-heading">
            Streaming Platforms &amp; Search URL Templates ({filteredProviders.length})
          </h4>

          <div className="apple-grouped-inset">
            {loading ? (
              <div style={{ padding: '24px', textAlign: 'center', color: '#8E8E93', fontSize: '12.5px' }}>
                Loading streaming templates...
              </div>
            ) : filteredProviders.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: '#8E8E93', fontSize: '12.5px' }}>
                No streaming platforms match &ldquo;{searchTerm}&rdquo;
              </div>
            ) : (
              filteredProviders.map((prov) => {
                const currentVal = editedTemplates[prov.key] ?? prov.template;
                const isModifiedFromDefault = currentVal.trim() !== prov.default_template.trim();
                const resolvedPreview = resolveWatchProviderUrl(
                  prov.key,
                  sampleMovie,
                  { [prov.key]: currentVal }
                );

                return (
                  <div key={prov.key} className="submodal-field-group">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div className="setting-meta">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span className="setting-title">{prov.label}</span>
                          {isModifiedFromDefault ? (
                            <span className="settings-source-tag custom">Custom Template</span>
                          ) : (
                            <span className="settings-source-tag env">Default</span>
                          )}
                        </div>
                        <span className="setting-caption">{prov.description}</span>
                      </div>

                      {isModifiedFromDefault && (
                        <button
                          type="button"
                          className="settings-quick-fill-btn"
                          onClick={() => handleResetSingle(prov.key, prov.default_template)}
                          title="Restore default URL for this service"
                        >
                          <RotateCcw size={10} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                          Reset to Default
                        </button>
                      )}
                    </div>

                    {/* URL Template Input */}
                    <input
                      type="text"
                      className="apple-input-text"
                      value={currentVal}
                      onChange={(e) => handleTemplateChange(prov.key, e.target.value)}
                      placeholder={prov.default_template}
                      spellCheck="false"
                      disabled={saving}
                    />

                    {/* Live Preview & Open Test Link */}
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
                          fontSize: '11px',
                          minWidth: 0,
                          flex: '1 1 auto',
                        }}
                        title={resolvedPreview}
                      >
                        {resolvedPreview}
                      </span>
                      <a
                        href={resolvedPreview}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="settings-open-preview-btn"
                        title="Open this generated search link in your default browser"
                      >
                        <ExternalLink size={11} />
                        <span>Open Link</span>
                      </a>
                    </div>
                  </div>
                );
              })
            )}
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

