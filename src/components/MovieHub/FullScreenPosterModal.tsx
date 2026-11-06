import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Maximize2, ExternalLink, Film, Tv } from 'lucide-react';
import './FullScreenPosterModal.css';

interface FullScreenPosterModalProps {
  isOpen: boolean;
  posterUrl: string | null;
  title: string;
  releaseYear?: string | number | null;
  mediaType?: 'movie' | 'tv' | string;
  onClose: () => void;
}

/**
 * Convert TMDB thumbnail or w500 URL to highest original resolution for crisp full-screen display.
 */
function getHighResPosterUrl(url: string | null): string | null {
  if (!url) return null;
  if (url.includes('image.tmdb.org/t/p/w500/')) {
    return url.replace('/w500/', '/original/');
  }
  if (url.includes('image.tmdb.org/t/p/w342/')) {
    return url.replace('/w342/', '/original/');
  }
  if (url.includes('image.tmdb.org/t/p/w780/')) {
    return url.replace('/w780/', '/original/');
  }
  return url;
}

export const FullScreenPosterModal: React.FC<FullScreenPosterModalProps> = ({
  isOpen,
  posterUrl,
  title,
  releaseYear,
  mediaType,
  onClose,
}) => {
  const highResUrl = getHighResPosterUrl(posterUrl);
  const [activeUrl, setActiveUrl] = useState<string | null>(highResUrl || posterUrl);
  const [hasError, setHasError] = useState<boolean>(false);
  const [isLoaded, setIsLoaded] = useState<boolean>(false);

  // Sync state when posterUrl changes
  useEffect(() => {
    setActiveUrl(getHighResPosterUrl(posterUrl) || posterUrl);
    setHasError(false);
    setIsLoaded(false);
  }, [posterUrl]);

  // Handle ESC key press
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => window.removeEventListener('keydown', handleKeyDown, true);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const content = (
    <div
      className="fullscreen-poster-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Full-screen poster: ${title}`}
    >
      {/* Top action controls */}
      <div className="fullscreen-poster-topbar" onClick={(e) => e.stopPropagation()}>
        <div className="fullscreen-poster-tag">
          {mediaType === 'tv' ? <Tv size={13} /> : <Film size={13} />}
          <span>{mediaType === 'tv' ? 'SERIES' : 'MOVIE'}</span>
          {releaseYear && <span className="fullscreen-poster-year">• {releaseYear}</span>}
        </div>

        <div className="fullscreen-poster-actions">
          {activeUrl && (
            <a
              href={activeUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="fullscreen-poster-btn-icon"
              title="Open full resolution in new tab"
              aria-label="Open high-resolution poster in new tab"
            >
              <ExternalLink size={16} />
            </a>
          )}
          <button
            type="button"
            className="fullscreen-poster-btn-close"
            onClick={onClose}
            title="Close full-screen poster (Esc)"
            aria-label="Close full-screen poster"
          >
            <X size={18} />
            <span className="fullscreen-esc-badge">ESC</span>
          </button>
        </div>
      </div>

      {/* Main poster image container */}
      <div
        className="fullscreen-poster-stage"
        onClick={(e) => e.stopPropagation()}
      >
        {activeUrl && !hasError ? (
          <div className="fullscreen-poster-frame">
            <img
              src={activeUrl}
              alt={`Full-screen poster for ${title}`}
              className={`fullscreen-poster-img ${isLoaded ? 'loaded' : 'loading'}`}
              onLoad={() => setIsLoaded(true)}
              onError={() => {
                // If /original/ failed, fallback to original provided url before error state
                if (posterUrl && activeUrl !== posterUrl) {
                  setActiveUrl(posterUrl);
                } else {
                  setHasError(true);
                }
              }}
            />
          </div>
        ) : (
          <div className="fullscreen-poster-fallback">
            <Film size={48} />
            <span className="fullscreen-fallback-text">{title}</span>
            <span className="fullscreen-fallback-sub">Poster image unavailable</span>
          </div>
        )}

        {/* Bottom caption */}
        <div className="fullscreen-poster-caption">
          <h2 className="fullscreen-caption-title">{title}</h2>
          {releaseYear && <span className="fullscreen-caption-year">({releaseYear})</span>}
        </div>
      </div>
    </div>
  );

  return typeof document !== 'undefined' ? createPortal(content, document.body) : content;
};

export default FullScreenPosterModal;
