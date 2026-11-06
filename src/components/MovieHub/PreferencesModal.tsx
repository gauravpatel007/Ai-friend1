import React, { useState, useEffect } from 'react';
import {
  X,
  SlidersHorizontal,
  RotateCcw,
  Check,
  Sparkles,
  Globe,
  Languages,
  Film,
  Key,
  ThumbsDown,
  EyeOff,
  Award,
  Clock,
} from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import {
  fetchMoviePreferences,
  updateMoviePreferences,
  resetMoviePreferences,
  MovieUserPreferences,
} from '../../api/movieApi';
import './PreferencesModal.css';

interface PreferencesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPreferencesSaved?: (prefs: MovieUserPreferences) => void;
}

const AVAILABLE_GENRES = [
  'Action',
  'Adventure',
  'Animation',
  'Comedy',
  'Crime',
  'Documentary',
  'Drama',
  'Family',
  'Fantasy',
  'History',
  'Horror',
  'Music',
  'Mystery',
  'Romance',
  'Science Fiction',
  'Thriller',
  'War',
];

const AVAILABLE_LANGUAGES: { code: string; label: string }[] = [
  { code: 'hi', label: 'Hindi (हिंदी)' },
  { code: 'te', label: 'Telugu (తెలుగు)' },
  { code: 'ta', label: 'Tamil (தமிழ்)' },
  { code: 'ml', label: 'Malayalam (മലയാളം)' },
  { code: 'kn', label: 'Kannada (ಕನ್ನಡ)' },
  { code: 'bn', label: 'Bengali (বাংলা)' },
  { code: 'en', label: 'English' },
  { code: 'ko', label: 'Korean (한국어)' },
  { code: 'ja', label: 'Japanese (日本語)' },
  { code: 'es', label: 'Spanish (Español)' },
  { code: 'fr', label: 'French (Français)' },
];

const AVAILABLE_REGIONS: { id: string; label: string }[] = [
  { id: 'indian', label: 'Indian Cinema (Pan-India)' },
  { id: 'south_indian', label: 'South Indian Cinema' },
  { id: 'bollywood', label: 'Bollywood / Hindi' },
  { id: 'hollywood', label: 'Hollywood' },
  { id: 'international', label: 'International / World Cinema' },
];

export const PreferencesModal: React.FC<PreferencesModalProps> = ({
  isOpen,
  onClose,
  onPreferencesSaved,
}) => {
  const { openSettings } = useChatStore();
  const [prefs, setPrefs] = useState<MovieUserPreferences>({
    preferred_genres: [],
    preferred_languages: ['all'],
    preferred_regions: ['all'],
    recommendation_settings: { min_rating: 6.0, include_watched: false },
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>('');

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setStatusMessage('');
    fetchMoviePreferences()
      .then((data) => {
        setPrefs(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load preferences:', err);
        setLoading(false);
      });
  }, [isOpen]);

  if (!isOpen) return null;

  const toggleGenre = (genre: string) => {
    setPrefs((prev) => {
      const exists = prev.preferred_genres.includes(genre);
      const updated = exists
        ? prev.preferred_genres.filter((g) => g !== genre)
        : [...prev.preferred_genres, genre];
      return { ...prev, preferred_genres: updated };
    });
  };

  const toggleDislikedGenre = (genre: string) => {
    setPrefs((prev) => {
      const current = prev.disliked_genres || [];
      const exists = current.includes(genre);
      const updated = exists ? current.filter((g) => g !== genre) : [...current, genre];
      return { ...prev, disliked_genres: updated };
    });
  };

  const toggleSetting = (key: keyof MovieUserPreferences) => {
    setPrefs((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const toggleLanguage = (code: string) => {
    setPrefs((prev) => {
      let current = prev.preferred_languages.filter((c) => c !== 'all');
      if (current.includes(code)) {
        current = current.filter((c) => c !== code);
      } else {
        current.push(code);
      }
      return {
        ...prev,
        preferred_languages: current.length > 0 ? current : ['all'],
      };
    });
  };

  const toggleRegion = (regionId: string) => {
    setPrefs((prev) => {
      let current = prev.preferred_regions.filter((r) => r !== 'all');
      if (current.includes(regionId)) {
        current = current.filter((r) => r !== regionId);
      } else {
        current.push(regionId);
      }
      return {
        ...prev,
        preferred_regions: current.length > 0 ? current : ['all'],
      };
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await updateMoviePreferences(prefs);
      setPrefs(updated);
      setStatusMessage('Preferences saved successfully!');
      onPreferencesSaved?.(updated);
      setTimeout(() => {
        onClose();
      }, 700);
    } catch (e) {
      console.error('Failed to save preferences:', e);
      setStatusMessage('Error saving preferences');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setSaving(true);
    try {
      const reset = await resetMoviePreferences();
      setPrefs(reset);
      setStatusMessage('Preferences reset to default values.');
      onPreferencesSaved?.(reset);
    } catch (e) {
      console.error('Failed to reset preferences:', e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="hub-pref-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="User Entertainment Preferences"
    >
      <div className="hub-pref-modal">
        {/* Header */}
        <div className="hub-pref-header">
          <div className="hub-pref-header-left">
            <SlidersHorizontal size={18} className="pref-icon" />
            <h3 className="hub-pref-title">Entertainment Preferences</h3>
          </div>
          <button
            type="button"
            className="hub-pref-close-btn"
            onClick={onClose}
            title="Close"
            aria-label="Close preferences"
          >
            <X size={16} />
          </button>
        </div>

        {/* Scroll Content */}
        <div className="hub-pref-body">
          {/* Section: Preferred Genres */}
          <section className="hub-pref-section">
            <div className="hub-pref-section-title">
              <Film size={15} />
              <h4>Preferred Genres</h4>
            </div>
            <p className="hub-pref-hint">
              Select your favorite genres. Titles matching these will be highlighted during discovery.
            </p>
            <div className="hub-pref-chips-grid">
              {AVAILABLE_GENRES.map((genre) => {
                const active = prefs.preferred_genres.includes(genre);
                return (
                  <button
                    key={genre}
                    type="button"
                    className={`hub-pref-chip ${active ? 'active' : ''}`}
                    onClick={() => toggleGenre(genre)}
                  >
                    {genre}
                    {active && <Check size={12} className="check-mark" />}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Section: Disliked Genres (Suppressed in recommendations) */}
          <section className="hub-pref-section">
            <div className="hub-pref-section-title">
              <ThumbsDown size={15} color="#FF453A" />
              <h4>Disliked Genres</h4>
            </div>
            <p className="hub-pref-hint">
              Genres you prefer not to see. Bond will penalize or avoid these unless you explicitly ask for them.
            </p>
            <div className="hub-pref-chips-grid">
              {AVAILABLE_GENRES.map((genre) => {
                const isDisliked = (prefs.disliked_genres || []).includes(genre);
                return (
                  <button
                    key={`disliked-${genre}`}
                    type="button"
                    className={`hub-pref-chip disliked ${isDisliked ? 'active-disliked' : ''}`}
                    onClick={() => toggleDislikedGenre(genre)}
                  >
                    {genre}
                    {isDisliked && <X size={12} className="check-mark" />}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Section: Recommendation Behavior & Taste Settings (Phase 8.2) */}
          <section className="hub-pref-section">
            <div className="hub-pref-section-title">
              <Sparkles size={15} />
              <h4>Discovery & Taste Preferences</h4>
            </div>
            <p className="hub-pref-hint">
              Fine-tune Bond&apos;s ranking behavior to match your unique viewing style.
            </p>
            <div className="hub-pref-toggles-list" style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '10px' }}>
              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', background: 'rgba(255, 255, 255, 0.04)', borderRadius: '8px', cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <EyeOff size={16} color="#0A84FF" />
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>Exclude Watched Movies</div>
                    <div style={{ fontSize: '11px', color: '#8E8E93' }}>Automatically filter out films you have already marked as watched</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!prefs.exclude_watched}
                  onChange={() => toggleSetting('exclude_watched')}
                  style={{ width: '16px', height: '16px', accentColor: '#0A84FF', cursor: 'pointer' }}
                />
              </label>

              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', background: 'rgba(255, 255, 255, 0.04)', borderRadius: '8px', cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Sparkles size={16} color="#FF9F0A" />
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>Prefer Underrated / Hidden Gems</div>
                    <div style={{ fontSize: '11px', color: '#8E8E93' }}>Boost high-rated films that fly under the mainstream radar</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!prefs.prefer_underrated}
                  onChange={() => toggleSetting('prefer_underrated')}
                  style={{ width: '16px', height: '16px', accentColor: '#FF9F0A', cursor: 'pointer' }}
                />
              </label>

              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', background: 'rgba(255, 255, 255, 0.04)', borderRadius: '8px', cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Award size={16} color="#30D158" />
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>Prefer Critically Acclaimed (7.8+)</div>
                    <div style={{ fontSize: '11px', color: '#8E8E93' }}>Prioritize universally acclaimed masterpieces with high review scores</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!prefs.prefer_highly_rated}
                  onChange={() => toggleSetting('prefer_highly_rated')}
                  style={{ width: '16px', height: '16px', accentColor: '#30D158', cursor: 'pointer' }}
                />
              </label>

              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', background: 'rgba(255, 255, 255, 0.04)', borderRadius: '8px', cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Clock size={16} color="#BF5AF2" />
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>Prefer Newer Releases (2020+)</div>
                    <div style={{ fontSize: '11px', color: '#8E8E93' }}>Favor modern contemporary cinema released in recent years</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!prefs.prefer_newer}
                  onChange={() => toggleSetting('prefer_newer')}
                  style={{ width: '16px', height: '16px', accentColor: '#BF5AF2', cursor: 'pointer' }}
                />
              </label>

              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', background: 'rgba(255, 255, 255, 0.04)', borderRadius: '8px', cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Film size={16} color="#64D2FF" />
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>Prefer Classic Era Films (Pre-1990)</div>
                    <div style={{ fontSize: '11px', color: '#8E8E93' }}>Boost timeless vintage classics from the golden eras of film</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!prefs.prefer_classic}
                  onChange={() => toggleSetting('prefer_classic')}
                  style={{ width: '16px', height: '16px', accentColor: '#64D2FF', cursor: 'pointer' }}
                />
              </label>
            </div>
          </section>

          {/* Section: Preferred Languages */}
          <section className="hub-pref-section">
            <div className="hub-pref-section-title">
              <Languages size={15} />
              <h4>Preferred Languages</h4>
            </div>
            <p className="hub-pref-hint">
              Choose your comfortable viewing languages for discovery feeds.
            </p>
            <div className="hub-pref-chips-grid">
              {AVAILABLE_LANGUAGES.map((lang) => {
                const active = prefs.preferred_languages.includes(lang.code);
                return (
                  <button
                    key={lang.code}
                    type="button"
                    className={`hub-pref-chip ${active ? 'active' : ''}`}
                    onClick={() => toggleLanguage(lang.code)}
                  >
                    {lang.label}
                    {active && <Check size={12} className="check-mark" />}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Section: Preferred Cinema Regions */}
          <section className="hub-pref-section">
            <div className="hub-pref-section-title">
              <Globe size={15} />
              <h4>Regional Industries</h4>
            </div>
            <p className="hub-pref-hint">
              Prioritize content from specific cinema industries.
            </p>
            <div className="hub-pref-chips-grid">
              {AVAILABLE_REGIONS.map((r) => {
                const active = prefs.preferred_regions.includes(r.id);
                return (
                  <button
                    key={r.id}
                    type="button"
                    className={`hub-pref-chip ${active ? 'active' : ''}`}
                    onClick={() => toggleRegion(r.id)}
                  >
                    {r.label}
                    {active && <Check size={12} className="check-mark" />}
                  </button>
                );
              })}
            </div>
          </section>
        </div>

        {/* Footer Actions */}
        <div className="hub-pref-footer">
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              type="button"
              className="hub-pref-reset-btn"
              onClick={handleReset}
              disabled={saving}
              title="Reset preferences to defaults"
            >
              <RotateCcw size={13} />
              <span>Reset Defaults</span>
            </button>
            <button
              type="button"
              className="hub-pref-reset-btn"
              onClick={() => {
                onClose();
                openSettings('movie_hub');
              }}
              title="Open TMDB API Key settings in Settings"
            >
              <Key size={13} />
              <span>TMDB Key Settings</span>
            </button>
          </div>

          <div className="hub-pref-footer-right">
            {statusMessage && <span className="hub-pref-status">{statusMessage}</span>}
            <button
              type="button"
              className="hub-pref-save-btn"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Preferences'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PreferencesModal;
