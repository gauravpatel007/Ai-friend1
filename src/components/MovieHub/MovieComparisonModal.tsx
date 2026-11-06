import React, { useState, useEffect } from 'react';
import {
  X,
  Star,
  Film,
  Tv,
  Calendar,
  Clock,
  User,
  SlidersHorizontal,
  Search,
  Loader2,
  ExternalLink,
  Bookmark,
  CheckCircle2,
} from 'lucide-react';
import { MovieItemModel } from './MovieCard';
import {
  fetchMediaDetails,
  searchMedia,
  fetchEntryStatus,
  MediaDetailsModel,
  UserMediaEntry,
} from '../../api/movieApi';
import './MovieComparisonModal.css';

interface MovieComparisonModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTitleA: MovieItemModel | null;
  initialTitleB?: MovieItemModel | null;
  onOpenDetails?: (item: MovieItemModel) => void;
}

export const MovieComparisonModal: React.FC<MovieComparisonModalProps> = ({
  isOpen,
  onClose,
  initialTitleA,
  initialTitleB = null,
  onOpenDetails,
}) => {
  const [titleA, setTitleA] = useState<MovieItemModel | null>(initialTitleA);
  const [titleB, setTitleB] = useState<MovieItemModel | null>(initialTitleB);

  const [detailsA, setDetailsA] = useState<MediaDetailsModel | null>(null);
  const [detailsB, setDetailsB] = useState<MediaDetailsModel | null>(null);

  const [storedA, setStoredA] = useState<UserMediaEntry | null>(null);
  const [storedB, setStoredB] = useState<UserMediaEntry | null>(null);

  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);

  // Search state for picking comparison title B
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MovieItemModel[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (initialTitleA) setTitleA(initialTitleA);
      if (initialTitleB) setTitleB(initialTitleB);
    } else {
      setSearchQuery('');
      setSearchResults([]);
    }
  }, [isOpen, initialTitleA, initialTitleB]);

  // Load details for Title A
  useEffect(() => {
    if (!titleA) {
      setDetailsA(null);
      setStoredA(null);
      return;
    }
    let active = true;
    setLoadingA(true);
    const mediaType = titleA.mediaType === 'tv' ? 'tv' : 'movie';

    fetchMediaDetails(mediaType, titleA.id)
      .then((data) => {
        if (active) setDetailsA(data);
      })
      .catch((err) => console.debug('Failed loading title A details:', err))
      .finally(() => {
        if (active) setLoadingA(false);
      });

    fetchEntryStatus(mediaType, titleA.id)
      .then((entry) => {
        if (active) setStoredA(entry);
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, [titleA]);

  // Load details for Title B
  useEffect(() => {
    if (!titleB) {
      setDetailsB(null);
      setStoredB(null);
      return;
    }
    let active = true;
    setLoadingB(true);
    const mediaType = titleB.mediaType === 'tv' ? 'tv' : 'movie';

    fetchMediaDetails(mediaType, titleB.id)
      .then((data) => {
        if (active) setDetailsB(data);
      })
      .catch((err) => console.debug('Failed loading title B details:', err))
      .finally(() => {
        if (active) setLoadingB(false);
      });

    fetchEntryStatus(mediaType, titleB.id)
      .then((entry) => {
        if (active) setStoredB(entry);
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, [titleB]);

  // Search for second title to compare
  const handleSearchTitles = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;

    setIsSearching(true);
    try {
      const res = await searchMedia({ query: q, content_type: 'all' });
      const mapped: MovieItemModel[] = (res.results || []).map((item) => ({
        id: item.id,
        title: item.title,
        mediaType: item.media_type,
        posterPath: item.poster_url || (item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : null),
        backdropPath: item.backdrop_url || (item.backdrop_path ? `https://image.tmdb.org/t/p/w1280${item.backdrop_path}` : null),
        releaseYear: item.release_year ?? undefined,
        voteAverage: item.vote_average,
        overview: item.overview,
        originalLanguage: item.original_language ?? undefined,
      }));
      setSearchResults(mapped.slice(0, 6));
    } catch (err) {
      console.warn('Comparison search error:', err);
    } finally {
      setIsSearching(false);
    }
  };

  // Keyboard shortcut listener for Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const formatRuntime = (mins?: number | null) => {
    if (!mins) return 'N/A';
    const hrs = Math.floor(mins / 60);
    const m = mins % 60;
    return hrs > 0 ? `${hrs}h ${m}m` : `${m}m`;
  };

  return (
    <div
      className="hub-compare-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Title Comparison Modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="hub-compare-modal-window">
        {/* Header Bar */}
        <header className="hub-compare-header">
          <div className="hub-compare-header-title">
            <SlidersHorizontal size={18} className="hub-compare-header-glyph" />
            <h2>Side-by-Side Comparison</h2>
          </div>
          <button
            type="button"
            className="hub-compare-close-btn"
            onClick={onClose}
            title="Close comparison (Escape)"
            aria-label="Close comparison modal"
          >
            <X size={16} />
          </button>
        </header>

        {/* Comparison Content Viewport */}
        <div className="hub-compare-viewport">
          <div className="hub-compare-columns-grid">
            {/* Column 1: Title A */}
            <div className="hub-compare-column">
              <div className="hub-compare-col-header">
                <span className="hub-compare-col-label">Title 1</span>
              </div>

              {titleA ? (
                <div className="hub-compare-title-card">
                  <div className="hub-compare-poster-wrap">
                    {titleA.posterPath ? (
                      <img src={titleA.posterPath} alt={titleA.title} className="hub-compare-poster" />
                    ) : (
                      <div className="hub-compare-poster-fallback">
                        {titleA.mediaType === 'tv' ? <Tv size={32} /> : <Film size={32} />}
                      </div>
                    )}
                  </div>
                  <h3 className="hub-compare-title-name">{titleA.title}</h3>
                  <div className="hub-compare-tag-row">
                    <span className="hub-media-type-tag">
                      {titleA.mediaType === 'tv' ? 'SERIES' : 'MOVIE'}
                    </span>
                    {titleA.releaseYear && (
                      <span className="hub-compare-meta-pill">{titleA.releaseYear}</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="hub-compare-empty-col">No title selected.</div>
              )}
            </div>

            {/* Column 2: Title B (With Search Selector) */}
            <div className="hub-compare-column">
              <div className="hub-compare-col-header">
                <span className="hub-compare-col-label">Title 2</span>
                {titleB && (
                  <button
                    type="button"
                    className="hub-compare-change-btn"
                    onClick={() => {
                      setTitleB(null);
                      setSearchResults([]);
                    }}
                  >
                    Change
                  </button>
                )}
              </div>

              {titleB ? (
                <div className="hub-compare-title-card">
                  <div className="hub-compare-poster-wrap">
                    {titleB.posterPath ? (
                      <img src={titleB.posterPath} alt={titleB.title} className="hub-compare-poster" />
                    ) : (
                      <div className="hub-compare-poster-fallback">
                        {titleB.mediaType === 'tv' ? <Tv size={32} /> : <Film size={32} />}
                      </div>
                    )}
                  </div>
                  <h3 className="hub-compare-title-name">{titleB.title}</h3>
                  <div className="hub-compare-tag-row">
                    <span className="hub-media-type-tag">
                      {titleB.mediaType === 'tv' ? 'SERIES' : 'MOVIE'}
                    </span>
                    {titleB.releaseYear && (
                      <span className="hub-compare-meta-pill">{titleB.releaseYear}</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="hub-compare-select-panel">
                  <p className="hub-compare-select-hint">Search for a second title to compare:</p>
                  <form onSubmit={handleSearchTitles} className="hub-compare-search-form">
                    <div className="hub-compare-input-wrap">
                      <Search size={14} className="hub-compare-search-icon" />
                      <input
                        type="text"
                        placeholder="Search title by name..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="hub-compare-search-input"
                      />
                      {isSearching && <Loader2 size={14} className="hub-spinner" />}
                    </div>
                  </form>

                  {searchResults.length > 0 && (
                    <div className="hub-compare-results-list">
                      {searchResults.map((item) => (
                        <div
                          key={`${item.mediaType}-${item.id}`}
                          className="hub-compare-result-item"
                          onClick={() => {
                            setTitleB(item);
                            setSearchResults([]);
                          }}
                        >
                          <div className="hub-compare-result-thumb">
                            {item.posterPath ? (
                              <img src={item.posterPath} alt={item.title} />
                            ) : (
                              <Film size={16} />
                            )}
                          </div>
                          <div className="hub-compare-result-meta">
                            <span className="hub-compare-result-title">{item.title}</span>
                            <span className="hub-compare-result-sub">
                              {item.mediaType === 'tv' ? 'Series' : 'Movie'} &bull; {item.releaseYear || 'N/A'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Comparison Matrix Table */}
          {titleA && titleB && (
            <div className="hub-compare-matrix">
              <h4 className="hub-compare-section-title">Verified Specifications</h4>

              {/* Row 1: Ratings */}
              <div className="hub-compare-matrix-row">
                <div className="hub-matrix-label">TMDB Rating</div>
                <div className="hub-matrix-val-a">
                  <Star size={13} className="star-icon" />
                  <strong>{titleA.voteAverage ? titleA.voteAverage.toFixed(1) : 'Unrated'}</strong>
                  {detailsA?.vote_count ? (
                    <span className="hub-matrix-sub">({detailsA.vote_count.toLocaleString()} votes)</span>
                  ) : null}
                </div>
                <div className="hub-matrix-val-b">
                  <Star size={13} className="star-icon" />
                  <strong>{titleB.voteAverage ? titleB.voteAverage.toFixed(1) : 'Unrated'}</strong>
                  {detailsB?.vote_count ? (
                    <span className="hub-matrix-sub">({detailsB.vote_count.toLocaleString()} votes)</span>
                  ) : null}
                </div>
              </div>

              {/* Row 2: User Local Rating */}
              <div className="hub-compare-matrix-row">
                <div className="hub-matrix-label">Your Rating</div>
                <div className="hub-matrix-val-a">
                  {storedA?.user_rating ? (
                    <span className="hub-matrix-user-score">{storedA.user_rating} / 10</span>
                  ) : (
                    <span className="hub-matrix-muted">Unrated locally</span>
                  )}
                </div>
                <div className="hub-matrix-val-b">
                  {storedB?.user_rating ? (
                    <span className="hub-matrix-user-score">{storedB.user_rating} / 10</span>
                  ) : (
                    <span className="hub-matrix-muted">Unrated locally</span>
                  )}
                </div>
              </div>

              {/* Row 3: Runtime / Episodes */}
              <div className="hub-compare-matrix-row">
                <div className="hub-matrix-label">Format / Length</div>
                <div className="hub-matrix-val-a">
                  {titleA.mediaType === 'tv'
                    ? `${detailsA?.number_of_seasons || 1} Season(s), ${detailsA?.number_of_episodes || 'N/A'} Episodes`
                    : formatRuntime(detailsA?.runtime_minutes)}
                </div>
                <div className="hub-matrix-val-b">
                  {titleB.mediaType === 'tv'
                    ? `${detailsB?.number_of_seasons || 1} Season(s), ${detailsB?.number_of_episodes || 'N/A'} Episodes`
                    : formatRuntime(detailsB?.runtime_minutes)}
                </div>
              </div>

              {/* Row 4: Genres */}
              <div className="hub-compare-matrix-row">
                <div className="hub-matrix-label">Genres</div>
                <div className="hub-matrix-val-a hub-matrix-chips">
                  {detailsA?.genres?.map((g) => (
                    <span key={g.id} className="hub-matrix-genre-chip">
                      {g.name}
                    </span>
                  )) || 'N/A'}
                </div>
                <div className="hub-matrix-val-b hub-matrix-chips">
                  {detailsB?.genres?.map((g) => (
                    <span key={g.id} className="hub-matrix-genre-chip">
                      {g.name}
                    </span>
                  )) || 'N/A'}
                </div>
              </div>

              {/* Row 5: Directors / Creators */}
              <div className="hub-compare-matrix-row">
                <div className="hub-matrix-label">Direction</div>
                <div className="hub-matrix-val-a">
                  {detailsA?.directors?.join(', ') || 'N/A'}
                </div>
                <div className="hub-matrix-val-b">
                  {detailsB?.directors?.join(', ') || 'N/A'}
                </div>
              </div>

              {/* Row 6: Key Cast */}
              <div className="hub-compare-matrix-row">
                <div className="hub-matrix-label">Key Cast</div>
                <div className="hub-matrix-val-a">
                  {detailsA?.cast?.slice(0, 4).map((c) => c.name).join(', ') || 'N/A'}
                </div>
                <div className="hub-matrix-val-b">
                  {detailsB?.cast?.slice(0, 4).map((c) => c.name).join(', ') || 'N/A'}
                </div>
              </div>

              {/* Row 7: Overview / Synopsis */}
              <div className="hub-compare-matrix-row">
                <div className="hub-matrix-label">Synopsis</div>
                <div className="hub-matrix-val-a hub-matrix-overview">
                  {titleA.overview || 'No synopsis available.'}
                </div>
                <div className="hub-matrix-val-b hub-matrix-overview">
                  {titleB.overview || 'No synopsis available.'}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MovieComparisonModal;
