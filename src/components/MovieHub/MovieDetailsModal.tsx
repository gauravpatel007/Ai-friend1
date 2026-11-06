import React, { useEffect, useState, useRef } from 'react';
import {
  X,
  Star,
  Play,
  Film,
  Tv,
  Calendar,
  Clock,
  User,
  Layers,
  Sparkles,
  ExternalLink,
  AlertCircle,
  Loader2,
  TvMinimal,
  Bookmark,
  Heart,
  CheckCircle2,
  Trash2,
  SlidersHorizontal,
  Maximize2,
} from 'lucide-react';
import { MovieItemModel } from './MovieCard';
import { FullScreenPosterModal } from './FullScreenPosterModal';
import { FullScreenTrailerModal } from './FullScreenTrailerModal';
import {
  fetchMediaDetails,
  fetchWatchProviders,
  WatchProvidersModel,
  MediaDetailsModel,
  CastMemberModel,
  VideoModel,
  MediaItemSummary,
  fetchEntryStatus,
  addToWatchlist,
  removeFromWatchlist,
  markAsWatched,
  updateEntryStatus,
  setFavorite,
  setLocalRating,
  UserMediaEntry,
  fetchHDHub4uStatus,
  resolveHdHub4uUrl,
  resolveWatchProviderUrl,
  fetchWatchProviderTemplates,
} from '../../api/movieApi';
import './MovieDetailsModal.css';

interface MovieDetailsModalProps {
  item: MovieItemModel | null;
  isOpen: boolean;
  onClose: () => void;
  onSelectRelated?: (item: MovieItemModel) => void;
  onTrackingChanged?: () => void;
  onStartCompare?: (item: MovieItemModel) => void;
}

/**
 * Generate HdHub4u search URL by replacing 'pixels' with movie/series title.
 * e.g. "Infinity war" -> "https://new10.hdhub4u.cl/search.html?q=infinity+war"
 */
export function getHdHub4uSearchUrl(title?: string | null, template?: string | null): string {
  if (!title) {
    return template || 'https://new10.hdhub4u.cl/search.html?q=';
  }
  // Compatible fallback formatting: title.replace(/\s+/g, '')
  const cleanTitle = title.replace(/\s+/g, '');
  return resolveHdHub4uUrl(template, title) || `https://new10.hdhub4u.cl/search.html?q=${encodeURIComponent(cleanTitle)}`;
}

/**
 * Generate YouTube search URL for movie or series trailer.
 * Matches exact format: https://www.youtube.com/results?search_query=jailer+2+(2026)+trailer
 */
export function getYouTubeTrailerSearchUrl(title?: string | null, releaseYear?: string | number | null): string {
  const cleanTitle = (title || '').trim();
  if (!cleanTitle) return 'https://www.youtube.com/results?search_query=trailer';
  const yearPart = releaseYear ? `(${releaseYear}) ` : '';
  const query = `${cleanTitle} ${yearPart}trailer`.replace(/\s+/g, ' ').trim();
  const encoded = encodeURIComponent(query).replace(/%20/g, '+');
  return `https://www.youtube.com/results?search_query=${encoded}`;
}

export const MovieDetailsModal: React.FC<MovieDetailsModalProps> = ({
  item,
  isOpen,
  onClose,
  onSelectRelated,
  onTrackingChanged,
  onStartCompare,
}) => {
  const [details, setDetails] = useState<MediaDetailsModel | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTrailer, setActiveTrailer] = useState<VideoModel | null>(null);
  const [posterError, setPosterError] = useState<boolean>(false);
  const [backdropError, setBackdropError] = useState<boolean>(false);
  const [isPosterFullScreen, setIsPosterFullScreen] = useState<boolean>(false);
  const [hdhubTemplate, setHdhubTemplate] = useState<string>('https://new10.hdhub4u.cl/search.html?q=pixels');
  const [customProviderTemplates, setCustomProviderTemplates] = useState<Record<string, string>>({});

  // Local persistent tracking states (Phase 8)
  const [storedEntry, setStoredEntry] = useState<UserMediaEntry | null>(null);
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [trackingBusy, setTrackingBusy] = useState<boolean>(false);

  // Streaming Availability State (Phase 11.6 - Official JustWatch via TMDB)
  const [providers, setProviders] = useState<WatchProvidersModel | null>(null);
  const [providersLoading, setProvidersLoading] = useState<boolean>(false);

  const modalRef = useRef<HTMLDivElement>(null);

  // Fetch tracking status from local SQLite storage
  const loadTrackingStatus = (mediaType: 'movie' | 'tv', id: string | number) => {
    fetchEntryStatus(mediaType, id)
      .then((entry) => setStoredEntry(entry))
      .catch(() => setStoredEntry(null));
  };

  // Load active HDHub4u template on modal open
  useEffect(() => {
    if (!isOpen) return;
    fetchWatchProviderTemplates()
      .then((res) => {
        const map: Record<string, string> = {};
        res.providers.forEach((p) => {
          if (p.is_custom) map[p.key] = p.template;
        });
        setCustomProviderTemplates(map);
      })
      .catch(() => {});

    fetchHDHub4uStatus()
      .then((status) => {
        if (status?.active_url) {
          setHdhubTemplate(status.active_url);
        }
      })
      .catch(() => {});
  }, [isOpen]);

  // Fetch comprehensive media details on item selection
  useEffect(() => {
    if (!isOpen || !item) {
      setDetails(null);
      setActiveTrailer(null);
      setError(null);
      setStoredEntry(null);
      setProviders(null);
      setProvidersLoading(false);
      return;
    }

    let isSubscribed = true;
    setLoading(true);
    setError(null);
    setPosterError(false);
    setBackdropError(false);

    const mediaType = item.mediaType === 'tv' ? 'tv' : 'movie';

    fetchMediaDetails(mediaType, item.id)
      .then((data) => {
        if (isSubscribed) {
          setDetails(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isSubscribed) {
          setError(err.message || 'Failed to load title details.');
          setLoading(false);
        }
      });

    // Phase 11.6: Fetch streaming watch providers
    setProvidersLoading(true);
    fetchWatchProviders(mediaType, item.id, 'IN')
      .then((provData) => {
        if (isSubscribed) {
          setProviders(provData);
        }
      })
      .catch(() => {
        if (isSubscribed) {
          setProviders(null);
        }
      })
      .finally(() => {
        if (isSubscribed) {
          setProvidersLoading(false);
        }
      });

    loadTrackingStatus(mediaType, item.id);

    return () => {
      isSubscribed = false;
    };
  }, [isOpen, item]);

  // Handle Watchlist Toggle
  const handleToggleWatchlist = async () => {
    if (!item || trackingBusy) return;
    setTrackingBusy(true);
    try {
      const mediaType = item.mediaType === 'tv' ? 'tv' : 'movie';
      const isCurrentlyWatchlisted = storedEntry?.status === 'watchlist';

      if (isCurrentlyWatchlisted) {
        await removeFromWatchlist(mediaType, item.id);
        const updated = await fetchEntryStatus(mediaType, item.id);
        setStoredEntry(updated);
      } else {
        const genresStr = details?.genres?.map((g) => g.name).join(', ') || item.genres || '';
        const saved = await addToWatchlist({
          tmdb_id: Number(item.id),
          title: item.title,
          media_type: mediaType,
          poster_path: item.posterPath,
          release_year: typeof item.releaseYear === 'number' ? item.releaseYear : undefined,
          original_language: item.originalLanguage,
          vote_average: item.voteAverage,
          overview: item.overview,
          status: 'watchlist',
          genres: genresStr,
        });
        setStoredEntry(saved);
      }
      onTrackingChanged?.();
    } catch (e) {
      console.error('Failed to toggle watchlist:', e);
    } finally {
      setTrackingBusy(false);
    }
  };

  // Handle Favorite Toggle
  const handleToggleFavorite = async () => {
    if (!item || trackingBusy) return;
    setTrackingBusy(true);
    try {
      const mediaType = item.mediaType === 'tv' ? 'tv' : 'movie';
      const newFavState = !storedEntry?.is_favorite;
      const parsedYear =
        typeof item.releaseYear === 'number'
          ? item.releaseYear
          : item.releaseYear
          ? parseInt(String(item.releaseYear), 10)
          : details?.release_year ?? undefined;

      const genresStr = details?.genres?.map((g) => g.name).join(', ') || item.genres || '';
      const saved = await setFavorite(mediaType, item.id, newFavState, {
        title: item.title || details?.title || '',
        poster_path: item.posterPath || details?.poster_url || undefined,
        backdrop_path: item.backdropPath || details?.backdrop_url || undefined,
        release_year: parsedYear,
        original_language: item.originalLanguage,
        vote_average: item.voteAverage ?? details?.vote_average ?? 0.0,
        overview: item.overview || details?.overview || '',
        genres: genresStr,
      });
      setStoredEntry(saved);
      onTrackingChanged?.();
    } catch (e) {
      console.error('Failed to toggle favorite:', e);
    } finally {
      setTrackingBusy(false);
    }
  };

  // Handle Watched Toggle
  const handleToggleWatched = async () => {
    if (!item || trackingBusy) return;
    setTrackingBusy(true);
    try {
      const mediaType = item.mediaType === 'tv' ? 'tv' : 'movie';
      const isCurrentlyWatched = storedEntry?.status === 'watched';

      if (isCurrentlyWatched) {
        const saved = await updateEntryStatus(mediaType, item.id, 'none');
        setStoredEntry(saved);
      } else {
        const parsedYear =
          typeof item.releaseYear === 'number'
            ? item.releaseYear
            : item.releaseYear
            ? parseInt(String(item.releaseYear), 10)
            : details?.release_year ?? undefined;

        const genresStr = details?.genres?.map((g) => g.name).join(', ') || item.genres || '';
        const saved = await markAsWatched(mediaType, item.id, {
          title: item.title || details?.title || '',
          poster_path: item.posterPath || details?.poster_url || undefined,
          backdrop_path: item.backdropPath || details?.backdrop_url || undefined,
          release_year: parsedYear,
          original_language: item.originalLanguage,
          vote_average: item.voteAverage ?? details?.vote_average ?? 0.0,
          overview: item.overview || details?.overview || '',
          genres: genresStr,
        });
        setStoredEntry(saved);
      }
      onTrackingChanged?.();
    } catch (e) {
      console.error('Failed to toggle watched status:', e);
    } finally {
      setTrackingBusy(false);
    }
  };

  // Handle Local Rating
  const handleSetRating = async (ratingVal: number | null) => {
    if (!item || trackingBusy) return;
    setTrackingBusy(true);
    try {
      const mediaType = item.mediaType === 'tv' ? 'tv' : 'movie';
      const saved = await setLocalRating(mediaType, item.id, ratingVal, {
        title: item.title,
        poster_path: item.posterPath,
        release_year: typeof item.releaseYear === 'number' ? item.releaseYear : undefined,
      });
      setStoredEntry(saved);
      onTrackingChanged?.();
    } catch (e) {
      console.error('Failed to set rating:', e);
    } finally {
      setTrackingBusy(false);
    }
  };

  // Handle ESC key to dismiss trailer or modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (activeTrailer) {
          setActiveTrailer(null);
        } else if (isOpen) {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, activeTrailer, onClose]);

  // Prevent background scrolling when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen || !item) return null;

  // Format runtime minutes into "2h 49m"
  const formatRuntime = (mins?: number | null) => {
    if (!mins || mins <= 0) return null;
    const hours = Math.floor(mins / 60);
    const remainder = mins % 60;
    if (hours > 0 && remainder > 0) return `${hours}h ${remainder}m`;
    if (hours > 0) return `${hours}h`;
    return `${remainder}m`;
  };

  const isMovie = item.mediaType === 'movie';
  const effectiveDetails = details;
  const ratingValue = effectiveDetails?.vote_average || item.voteAverage;
  const ratingFormatted = ratingValue ? ratingValue.toFixed(1) : null;
  const voteCount = effectiveDetails?.vote_count;
  const backdropUrl = effectiveDetails?.backdrop_url || item.backdropPath;

  // Official or best trailer
  const primaryTrailer = effectiveDetails?.trailers?.[0] || null;
  const movieTitle = effectiveDetails?.title || item.title || '';
  const movieYear = effectiveDetails?.release_year || item.releaseYear || null;
  const fallbackYouTubeSearchUrl = getYouTubeTrailerSearchUrl(movieTitle, movieYear);

  return (
    <div
      className="hub-details-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={`${item.title} Details`}
    >
      <div className="hub-details-modal" ref={modalRef}>
        {/* Close Button - Stays permanently accessible in top-right */}
        <button
          type="button"
          className="hub-details-close-btn"
          onClick={onClose}
          title="Close Details (Escape)"
          aria-label="Close details dialog"
        >
          <X size={16} />
        </button>

        {/* Ambient Backdrop Banner Frame (Behind scroll content, zero overlap clipping) */}
        <div className="hub-details-backdrop-frame" aria-hidden="true">
          {backdropUrl && !backdropError ? (
            <img
              src={backdropUrl}
              alt=""
              className="hub-details-backdrop-img"
              onError={() => setBackdropError(true)}
            />
          ) : (
            <div className="hub-details-backdrop-gradient" />
          )}
          <div className="hub-details-backdrop-overlay" />
        </div>

        {/* Modal Scrollable Body */}
        <div className="hub-details-body-scroll">
          {loading ? (
            <div className="hub-details-loading-state">
              <Loader2 size={32} className="spin-icon" />
              <span>Loading verified metadata...</span>
            </div>
          ) : error ? (
            <div className="hub-details-error-state">
              <AlertCircle size={28} className="error-glyph" />
              <p>{error}</p>
              <button
                type="button"
                className="hub-details-retry-btn"
                onClick={() => {
                  setLoading(true);
                  fetchMediaDetails(item.mediaType === 'tv' ? 'tv' : 'movie', item.id)
                    .then((data) => {
                      setDetails(data);
                      setLoading(false);
                    })
                    .catch((err) => {
                      setError(err.message);
                      setLoading(false);
                    });
                }}
              >
                Try Again
              </button>
            </div>
          ) : (
            <>
              {/* Primary Header Row: Poster + Main Metadata */}
              <div className="hub-details-hero-row">
                {/* Poster Frame */}
                <div
                  className="hub-details-poster-frame"
                  onClick={() => {
                    if (item.posterPath && !posterError) {
                      setIsPosterFullScreen(true);
                    }
                  }}
                  style={{ cursor: item.posterPath && !posterError ? 'zoom-in' : 'default' }}
                  title={item.posterPath && !posterError ? 'Click poster to view in full screen' : undefined}
                  role={item.posterPath && !posterError ? 'button' : undefined}
                  tabIndex={item.posterPath && !posterError ? 0 : undefined}
                  onKeyDown={(e) => {
                    if ((e.key === 'Enter' || e.key === ' ') && item.posterPath && !posterError) {
                      e.preventDefault();
                      setIsPosterFullScreen(true);
                    }
                  }}
                >
                  {item.posterPath && !posterError ? (
                    <>
                      <img
                        src={item.posterPath}
                        alt={item.title}
                        className="hub-details-poster-img"
                        onError={() => setPosterError(true)}
                      />
                      <div className="hub-poster-zoom-badge" aria-hidden="true">
                        <Maximize2 size={12} />
                        <span>Full Screen</span>
                      </div>
                    </>
                  ) : (
                    <div className="hub-details-poster-fallback">
                      {isMovie ? <Film size={44} /> : <Tv size={44} />}
                      <span className="hub-poster-fallback-title">{item.title}</span>
                    </div>
                  )}
                </div>

                {/* Meta Column */}
                <div className="hub-details-meta-column">
                  {/* Badges Bar */}
                  <div className="hub-details-badges-bar">
                    <span className={`hub-media-type-tag ${isMovie ? 'tag-movie' : 'tag-series'}`}>
                      {isMovie ? 'MOVIE' : 'SERIES'}
                    </span>

                    {ratingFormatted && (
                      <span className="hub-rating-pill" title={`Rating: ${ratingFormatted}/10`}>
                        <Star size={11} className="rating-star-icon" />
                        <span>{ratingFormatted}</span>
                        {voteCount ? (
                          <span className="hub-vote-count">({voteCount.toLocaleString()} votes)</span>
                        ) : null}
                      </span>
                    )}

                    {effectiveDetails?.status && (
                      <span className="hub-status-pill">{effectiveDetails.status}</span>
                    )}
                  </div>

                  {/* Title & Tagline */}
                  <h2 className="hub-details-title">{item.title}</h2>
                  {effectiveDetails?.tagline && (
                    <p className="hub-details-tagline">&ldquo;{effectiveDetails.tagline}&rdquo;</p>
                  )}

                  {/* Spec Row: Year, Runtime, Seasons, Language */}
                  <div className="hub-details-spec-row">
                    {item.releaseYear && (
                      <div className="hub-spec-item">
                        <Calendar size={13} />
                        <span>{item.releaseYear}</span>
                      </div>
                    )}

                    {effectiveDetails?.runtime_minutes && (
                      <div className="hub-spec-item">
                        <Clock size={13} />
                        <span>{formatRuntime(effectiveDetails.runtime_minutes)}</span>
                      </div>
                    )}

                    {!isMovie && effectiveDetails?.number_of_seasons && (
                      <div className="hub-spec-item">
                        <TvMinimal size={13} />
                        <span>
                          {effectiveDetails.number_of_seasons} Season
                          {effectiveDetails.number_of_seasons > 1 ? 's' : ''}
                          {effectiveDetails.number_of_episodes
                            ? ` • ${effectiveDetails.number_of_episodes} Episodes`
                            : ''}
                        </span>
                      </div>
                    )}

                    {item.originalLanguage && (
                      <span className="hub-card-lang-chip">
                        {item.originalLanguage.toUpperCase()}
                      </span>
                    )}
                  </div>

                  {/* Genre Pills */}
                  {effectiveDetails?.genres && effectiveDetails.genres.length > 0 && (
                    <div className="hub-details-genres-list">
                      {effectiveDetails.genres.map((g) => (
                        <span key={g.id} className="hub-genre-pill">
                          {g.name}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Action Row: Trailer + Watchlist + Favorites + Watched */}
                  <div className="hub-details-actions-bar">
                    {primaryTrailer && primaryTrailer.key ? (
                      <>
                        <button
                          type="button"
                          className="hub-trailer-action-btn"
                          onClick={() => {
                            try {
                              if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
                                document.documentElement.requestFullscreen().catch(() => {});
                              }
                            } catch {}
                            setActiveTrailer(primaryTrailer);
                          }}
                          title="Watch Official Trailer in Full Screen"
                        >
                          <Play size={14} className="play-icon" />
                          <span>Watch Trailer</span>
                        </button>

                        <a
                          href={primaryTrailer.url || fallbackYouTubeSearchUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hub-trailer-link-btn"
                          title="Open Trailer in YouTube (External)"
                        >
                          <ExternalLink size={13} />
                          <span>YouTube</span>
                        </a>
                      </>
                    ) : (
                      <>
                        <a
                          href={fallbackYouTubeSearchUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hub-trailer-action-btn"
                          title={`Search ${movieTitle} Trailer on YouTube`}
                        >
                          <Play size={14} className="play-icon" />
                          <span>Watch Trailer</span>
                        </a>

                        <a
                          href={fallbackYouTubeSearchUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hub-trailer-link-btn"
                          title={`Search ${movieTitle} Trailer on YouTube`}
                        >
                          <ExternalLink size={13} />
                          <span>YouTube</span>
                        </a>
                      </>
                    )}

                    {/* Phase 8: Persistent Watchlist Toggle */}
                    <button
                      type="button"
                      className={`hub-track-btn ${storedEntry?.status === 'watchlist' ? 'active-watchlist' : ''}`}
                      onClick={handleToggleWatchlist}
                      disabled={trackingBusy}
                      title={storedEntry?.status === 'watchlist' ? 'Remove from Watchlist' : 'Add to Watchlist'}
                    >
                      <Bookmark size={14} className={storedEntry?.status === 'watchlist' ? 'fill-icon' : ''} />
                      <span>{storedEntry?.status === 'watchlist' ? 'In Watchlist' : 'Add to Watchlist'}</span>
                    </button>

                    {/* Phase 8: Persistent Favorite Toggle */}
                    <button
                      type="button"
                      className={`hub-track-btn ${storedEntry?.is_favorite ? 'active-fav' : ''}`}
                      onClick={handleToggleFavorite}
                      disabled={trackingBusy}
                      title={storedEntry?.is_favorite ? 'Favorited' : 'Mark as Favorite'}
                    >
                      <Heart
                        size={14}
                        fill={storedEntry?.is_favorite ? '#FF375F' : 'none'}
                        color={storedEntry?.is_favorite ? '#FF375F' : 'currentColor'}
                      />
                      <span>{storedEntry?.is_favorite ? 'Favorited' : 'Favorite'}</span>
                    </button>

                    {/* Phase 8: Persistent Watched Toggle */}
                    <button
                      type="button"
                      className={`hub-track-btn ${storedEntry?.status === 'watched' ? 'active-watched' : ''}`}
                      onClick={handleToggleWatched}
                      disabled={trackingBusy}
                      title={storedEntry?.status === 'watched' ? 'Marked as Watched' : 'Mark as Watched'}
                    >
                      <CheckCircle2
                        size={14}
                        color={storedEntry?.status === 'watched' ? '#30D158' : 'currentColor'}
                      />
                      <span>{storedEntry?.status === 'watched' ? 'Watched' : 'Mark Watched'}</span>
                    </button>

                    {/* Phase 11.5: Movie Comparison Trigger */}
                    {onStartCompare && item && (
                      <button
                        type="button"
                        className="hub-track-btn hub-compare-trigger-btn"
                        onClick={() => {
                          onStartCompare(item);
                          onClose();
                        }}
                        title="Compare this title side-by-side with another"
                      >
                        <SlidersHorizontal size={14} />
                        <span>Compare</span>
                      </button>
                    )}
                  </div>

                  {/* Phase 8: Local User Rating Control (1-10 Stars, separate from provider) */}
                  <div className="hub-details-rating-bar">
                    <span className="hub-rating-bar-label">Personal Rating:</span>
                    <div className="hub-stars-interactive" role="radiogroup" aria-label="Rate this title from 1 to 10">
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((starNum) => {
                        const isFilled = (hoverRating ?? storedEntry?.user_rating ?? 0) >= starNum;
                        return (
                          <button
                            key={starNum}
                            type="button"
                            className="hub-star-rate-btn"
                            onMouseEnter={() => setHoverRating(starNum)}
                            onMouseLeave={() => setHoverRating(null)}
                            onClick={() => handleSetRating(starNum)}
                            title={`Rate ${starNum} out of 10`}
                            aria-label={`Rate ${starNum} of 10`}
                          >
                            <Star
                              size={14}
                              fill={isFilled ? '#FFD60A' : 'none'}
                              color={isFilled ? '#FFD60A' : 'rgba(255, 255, 255, 0.25)'}
                            />
                          </button>
                        );
                      })}
                    </div>
                    {storedEntry?.user_rating ? (
                      <div className="hub-rating-value-group">
                        <span className="hub-local-score">{storedEntry.user_rating}/10</span>
                        <button
                          type="button"
                          className="hub-clear-rating-btn"
                          onClick={() => handleSetRating(null)}
                          title="Clear your rating"
                        >
                          Clear
                        </button>
                      </div>
                    ) : (
                      <span className="hub-local-score-placeholder">Unrated</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Storyline / Overview */}
              <section className="hub-details-section" aria-label="Storyline">
                <h3 className="hub-section-heading">Overview</h3>
                <p className="hub-details-overview-text">
                  {effectiveDetails?.overview || item.overview || 'No synopsis is available for this title.'}
                </p>
              </section>

              {/* Middle Row: Directors / Creators & HdHub4u Download */}
              <div className="hub-details-middle-row">
                {effectiveDetails?.directors && effectiveDetails.directors.length > 0 && (
                  <section className="hub-details-section hub-directors-section" aria-label="Directing & Creators">
                    <h3 className="hub-section-heading">
                      {isMovie ? 'Directed by' : 'Created by'}
                    </h3>
                    <div className="hub-directors-row">
                      {effectiveDetails.directors.map((dir, idx) => (
                        <span key={idx} className="hub-director-chip">
                          <User size={12} />
                          <span>{dir}</span>
                        </span>
                      ))}
                    </div>
                  </section>
                )}

                {/* HdHub4u Download Action Button */}
                <section className="hub-details-section hub-hdhub4u-section" aria-label="HdHub4u Download">
                  <h3 className="hub-section-heading">Download here</h3>
                  <a
                    href={getHdHub4uSearchUrl(item.title || details?.title || '', hdhubTemplate)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hub-hdhub4u-btn"
                    title={`Download ${item.title || details?.title || 'movie'} on HdHub4u`}
                  >
                    <img
                      src="/assets/icons/hdhub4u_logo.png"
                      alt="HdHub4u"
                      className="hub-hdhub4u-logo"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                      }}
                    />
                    <span className="hub-hdhub4u-label">HdHub4u</span>
                    <ExternalLink size={13} className="hub-hdhub4u-icon" />
                  </a>
                </section>
              </div>

              {/* Cast & Characters */}
              {effectiveDetails?.cast && effectiveDetails.cast.length > 0 && (
                <section className="hub-details-section" aria-label="Cast">
                  <h3 className="hub-section-heading">Top Cast</h3>
                  <div className="hub-cast-scroll-grid">
                    {effectiveDetails.cast.map((actor: CastMemberModel) => (
                      <div key={actor.id} className="hub-cast-card">
                        <div className="hub-cast-avatar-frame">
                          {actor.profile_url ? (
                            <img
                              src={actor.profile_url}
                              alt={actor.name}
                              className="hub-cast-avatar-img"
                              loading="lazy"
                            />
                          ) : (
                            <div className="hub-cast-avatar-fallback">
                              <User size={20} />
                            </div>
                          )}
                        </div>
                        <div className="hub-cast-meta">
                          <span className="hub-cast-actor-name" title={actor.name}>
                            {actor.name}
                          </span>
                          {actor.character && (
                            <span className="hub-cast-character-name" title={actor.character}>
                              {actor.character}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Phase 11.6: Streaming Availability (Official JustWatch via TMDB) */}
              <section className="hub-details-section hub-providers-section" aria-label="Streaming Availability">
                <div className="hub-providers-header">
                  <div className="hub-providers-title-wrap">
                    <Tv size={16} className="hub-providers-icon" />
                    <h3 className="hub-section-heading">Where to Watch</h3>
                  </div>
                  {providers?.region && (
                    <span className="hub-providers-region-pill">Region: {providers.region}</span>
                  )}
                </div>

                {providersLoading ? (
                  <div className="hub-providers-loading">
                    <Loader2 size={16} className="hub-spinner" />
                    <span>Checking verified streaming options...</span>
                  </div>
                ) : (
                  <>
                    {!providers || (!providers.flatrate.length && !providers.rent.length && !providers.buy.length) ? (
                      <div className="hub-providers-empty">
                        <p>No verified streaming or digital rental options listed for this region.</p>
                      </div>
                    ) : (
                      <div className="hub-providers-groups">
                        {providers.flatrate.length > 0 && (
                          <div className="hub-provider-group">
                            <span className="hub-provider-group-label">Stream:</span>
                            <div className="hub-provider-chips-row">
                              {providers.flatrate.map((prov) => (
                                <a
                                  key={prov.provider_id}
                                  href={resolveWatchProviderUrl(prov.provider_name, movieTitle, customProviderTemplates)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="hub-provider-chip hub-provider-link"
                                  title={`Watch "${movieTitle}" on ${prov.provider_name} (opens in browser)`}
                                >
                                  {prov.logo_url && (
                                    <img src={prov.logo_url} alt={prov.provider_name} className="hub-provider-logo" />
                                  )}
                                  <span>{prov.provider_name}</span>
                                  <ExternalLink size={10} className="hub-provider-ext-icon" />
                                </a>
                              ))}
                            </div>
                          </div>
                        )}

                        {providers.rent.length > 0 && (
                          <div className="hub-provider-group">
                            <span className="hub-provider-group-label">Rent:</span>
                            <div className="hub-provider-chips-row">
                              {providers.rent.map((prov) => (
                                <a
                                  key={prov.provider_id}
                                  href={resolveWatchProviderUrl(prov.provider_name, movieTitle, customProviderTemplates)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="hub-provider-chip hub-provider-link"
                                  title={`Watch "${movieTitle}" on ${prov.provider_name} (opens in browser)`}
                                >
                                  {prov.logo_url && (
                                    <img src={prov.logo_url} alt={prov.provider_name} className="hub-provider-logo" />
                                  )}
                                  <span>{prov.provider_name}</span>
                                  <ExternalLink size={10} className="hub-provider-ext-icon" />
                                </a>
                              ))}
                            </div>
                          </div>
                        )}

                        {providers.buy.length > 0 && (
                          <div className="hub-provider-group">
                            <span className="hub-provider-group-label">Buy:</span>
                            <div className="hub-provider-chips-row">
                              {providers.buy.map((prov) => (
                                <a
                                  key={prov.provider_id}
                                  href={resolveWatchProviderUrl(prov.provider_name, movieTitle, customProviderTemplates)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="hub-provider-chip hub-provider-link"
                                  title={`Watch "${movieTitle}" on ${prov.provider_name} (opens in browser)`}
                                >
                                  {prov.logo_url && (
                                    <img src={prov.logo_url} alt={prov.provider_name} className="hub-provider-logo" />
                                  )}
                                  <span>{prov.provider_name}</span>
                                  <ExternalLink size={10} className="hub-provider-ext-icon" />
                                </a>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    <p className="hub-providers-attribution">
                      {providers?.attribution || 'Streaming availability data provided by JustWatch via TMDB.'}
                    </p>
                  </>
                )}
              </section>

              {/* Related / Similar Titles (Requirement 7.4) */}
              {effectiveDetails?.similar && effectiveDetails.similar.length > 0 && (
                <section className="hub-details-section" aria-label="Related Titles">
                  <h3 className="hub-section-heading">Related Titles</h3>
                  <div className="hub-similar-scroll-row">
                    {effectiveDetails.similar.map((sim: MediaItemSummary) => {
                      const simModel: MovieItemModel = {
                        id: sim.id,
                        title: sim.title,
                        mediaType: sim.media_type,
                        posterPath: sim.poster_url || (sim.poster_path ? `https://image.tmdb.org/t/p/w500${sim.poster_path}` : null),
                        backdropPath: sim.backdrop_url || (sim.backdrop_path ? `https://image.tmdb.org/t/p/w1280${sim.backdrop_path}` : null),
                        releaseYear: sim.release_year || (sim.release_date ? sim.release_date.slice(0, 4) : undefined),
                        voteAverage: sim.vote_average,
                        overview: sim.overview,
                        originalLanguage: sim.original_language || undefined,
                      };

                      return (
                        <div
                          key={`${sim.media_type}-${sim.id}`}
                          className="hub-similar-card"
                          onClick={() => onSelectRelated && onSelectRelated(simModel)}
                          title={`View ${sim.title}`}
                          tabIndex={0}
                          role="button"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && onSelectRelated) onSelectRelated(simModel);
                          }}
                        >
                          <div className="hub-similar-poster-frame">
                            {simModel.posterPath ? (
                              <img
                                src={simModel.posterPath}
                                alt={sim.title}
                                className="hub-similar-poster-img"
                                loading="lazy"
                              />
                            ) : (
                              <div className="hub-similar-fallback">
                                {sim.media_type === 'tv' ? <Tv size={20} /> : <Film size={20} />}
                              </div>
                            )}
                            {sim.vote_average > 0 && (
                              <span className="hub-similar-rating-badge">
                                <Star size={9} className="rating-star-icon" />
                                <span>{sim.vote_average.toFixed(1)}</span>
                              </span>
                            )}
                          </div>
                          <span className="hub-similar-title">{sim.title}</span>
                          {simModel.releaseYear && (
                            <span className="hub-similar-year">{simModel.releaseYear}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
            </>
          )}
        </div>

        {/* Full-Screen Immersive Trailer Player Lightbox */}
        <FullScreenTrailerModal
          isOpen={!!activeTrailer}
          trailer={activeTrailer}
          movieTitle={movieTitle}
          releaseYear={movieYear}
          onClose={() => setActiveTrailer(null)}
        />

        {/* Full-Screen High-Resolution Poster Viewer Lightbox */}
        <FullScreenPosterModal
          isOpen={isPosterFullScreen}
          posterUrl={item.posterPath || details?.poster_url || null}
          title={item.title || details?.title || ''}
          releaseYear={item.releaseYear || details?.release_year || null}
          mediaType={isMovie ? 'movie' : 'tv'}
          onClose={() => setIsPosterFullScreen(false)}
        />
      </div>
    </div>
  );
};

export default MovieDetailsModal;
