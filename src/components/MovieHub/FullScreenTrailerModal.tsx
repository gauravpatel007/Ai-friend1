import React, { useEffect, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X, Maximize2, Minimize2, ExternalLink, Play } from 'lucide-react';
import { VideoModel } from '../../api/movieApi';
import './FullScreenTrailerModal.css';

interface FullScreenTrailerModalProps {
  isOpen: boolean;
  trailer: VideoModel | null;
  movieTitle: string;
  releaseYear?: string | number | null;
  onClose: () => void;
}

export const FullScreenTrailerModal: React.FC<FullScreenTrailerModalProps> = ({
  isOpen,
  trailer,
  movieTitle,
  releaseYear,
  onClose,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isNativeFs, setIsNativeFs] = useState<boolean>(() => {
    return typeof document !== 'undefined' ? !!document.fullscreenElement : false;
  });

  // Track native browser fullscreen changes
  useEffect(() => {
    const handleFsChange = () => {
      setIsNativeFs(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFsChange);
    return () => document.removeEventListener('fullscreenchange', handleFsChange);
  }, []);

  // Attempt browser OS fullscreen on trailer launch
  useEffect(() => {
    if (!isOpen) return;

    // Prevent background scrolling while trailer modal is active
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Auto-request fullscreen if supported and permitted
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {
        // Ignored if browser gesture policy blocks automatic fullscreen
      });
    }

    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [isOpen]);

  // Clean exit handler (exits native fullscreen and closes trailer)
  const handleExitFullScreen = () => {
    if (document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch(() => { });
    }
    onClose();
  };

  // Keyboard shortcut handler (Escape to exit)
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        handleExitFullScreen();
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => window.removeEventListener('keydown', handleKeyDown, true);
  }, [isOpen]);

  const toggleNativeFs = async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (containerRef.current?.requestFullscreen) {
        await containerRef.current.requestFullscreen();
      } else if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
    } catch {
      // Ignored if browser policy denies
    }
  };

  if (!isOpen || !trailer || !trailer.key) return null;

  const trailerUrl = trailer.url || `https://www.youtube.com/watch?v=${trailer.key}`;
  const iframeSrc = `https://www.youtube-nocookie.com/embed/${trailer.key}?autoplay=1&rel=0&modestbranding=1&fs=1`;

  const modalContent = (
    <div
      ref={containerRef}
      className="fullscreen-trailer-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={`Full-screen trailer: ${movieTitle}`}
    >
      {/* Top Floating Controls Bar */}
      <div className="fullscreen-trailer-topbar">
        <div className="fullscreen-trailer-info">
          <span className="fullscreen-trailer-tag">
            <Play size={10} fill="currentColor" />
            <span>Trailer</span>
          </span>
          <div className="fullscreen-trailer-title-group">
            <h2 className="fullscreen-trailer-title">{movieTitle}</h2>
            {releaseYear && <span className="fullscreen-trailer-year">({releaseYear})</span>}
          </div>
          {trailer.name && (
            <span className="fullscreen-trailer-name" title={trailer.name}>
              • {trailer.name}
            </span>
          )}
        </div>

        <div className="fullscreen-trailer-actions">
          {trailerUrl && (
            <a
              href={trailerUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="fullscreen-trailer-btn-icon"
              title="Open video on YouTube in new tab"
              aria-label="Open on YouTube"
            >
              <ExternalLink size={16} />
            </a>
          )}

          <button
            type="button"
            className="fullscreen-trailer-btn-icon"
            onClick={toggleNativeFs}
            title={isNativeFs ? 'Exit OS Fullscreen' : 'Enter OS Fullscreen'}
            aria-label="Toggle Fullscreen"
          >
            {isNativeFs ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>

          {/* Primary Always-Available Exit button */}
          <button
            type="button"
            className="fullscreen-trailer-exit-btn"
            onClick={handleExitFullScreen}
            title="Exit"
            aria-label="Exit"
          >
            <Minimize2 size={15} />
            <span>Exit</span>
          </button>
        </div>
      </div>

      {/* Full-Screen Video Stage */}
      <div className="fullscreen-trailer-stage">
        <iframe
          src={iframeSrc}
          title={trailer.name || `${movieTitle} Official Trailer`}
          className="fullscreen-trailer-iframe"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
          allowFullScreen
        />
      </div>
    </div>
  );

  return typeof document !== 'undefined' ? createPortal(modalContent, document.body) : modalContent;
};

export default FullScreenTrailerModal;
