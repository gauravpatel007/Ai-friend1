import React, { useState, useEffect } from 'react';
import { Film, Tv, Star, Bookmark, Info, Clock, SlidersHorizontal, Heart, CheckCircle2 } from 'lucide-react';
import { getProxiedImageUrl, normalizePosterUrl } from '../../api/movieApi';

export interface MovieItemModel {
  id: string | number;
  title: string;
  mediaType: 'movie' | 'tv';
  posterPath?: string | null;
  backdropPath?: string | null;
  releaseYear?: string | number;
  voteAverage?: number;
  overview?: string;
  genreNames?: string[];
  originalLanguage?: string;
  isStale?: boolean;
  genres?: string | null;
}

interface MovieCardProps {
  item: MovieItemModel;
  onOpenDetails?: (item: MovieItemModel) => void;
  onOpenPoster?: (item: MovieItemModel) => void;
  onToggleWatchlist?: (item: MovieItemModel) => void;
  onToggleFavorite?: (item: MovieItemModel) => void;
  onToggleWatched?: (item: MovieItemModel) => void;
  onCompare?: (item: MovieItemModel) => void;
  isWatchlisted?: boolean;
  isFavorite?: boolean;
  isWatched?: boolean;
}

export const MovieCard: React.FC<MovieCardProps> = ({
  item,
  onOpenDetails,
  onOpenPoster,
  onToggleWatchlist,
  onToggleFavorite,
  onToggleWatched,
  onCompare,
  isWatchlisted = false,
  isFavorite = false,
  isWatched = false,
}) => {
  const rawPoster = normalizePosterUrl(item.posterPath, 'w500');
  const proxiedPoster = getProxiedImageUrl(rawPoster, 'w500');

  const [imgSrc, setImgSrc] = useState<string | null>(proxiedPoster || rawPoster);
  const [imageError, setImageError] = useState<boolean>(false);

  // Synchronize poster state if item changes
  useEffect(() => {
    const freshRaw = normalizePosterUrl(item.posterPath, 'w500');
    setImgSrc(getProxiedImageUrl(freshRaw, 'w500') || freshRaw);
    setImageError(false);
  }, [item.posterPath]);

  const isMovie = item.mediaType === 'movie';
  const ratingFormatted = item.voteAverage ? item.voteAverage.toFixed(1) : null;

  return (
    <article
      className="hub-media-card"
      tabIndex={0}
      aria-label={`${item.title} (${item.releaseYear || 'Unknown year'})`}
      onClick={() => onOpenDetails && onOpenDetails(item)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpenDetails && onOpenDetails(item);
        }
      }}
      style={{ cursor: 'pointer' }}
    >
      {/* Poster Media Frame */}
      <div className="hub-card-poster-frame">
        {imgSrc && !imageError ? (
          <img
            src={imgSrc}
            alt={item.title}
            className="hub-card-poster-img"
            loading="lazy"
            onError={() => {
              // If proxied route fails, try direct TMDB CDN url before showing fallback
              if (rawPoster && imgSrc !== rawPoster) {
                setImgSrc(rawPoster);
              } else {
                setImageError(true);
              }
            }}
          />
        ) : (
          <div className="hub-card-poster-fallback">
            {isMovie ? <Film size={32} /> : <Tv size={32} />}
            <span className="hub-fallback-title">{item.title}</span>
          </div>
        )}

        {/* Media Type, Rating & Stale Badges */}
        <div className="hub-card-top-badges">
          <span className={`hub-media-type-tag ${isMovie ? 'tag-movie' : 'tag-series'}`}>
            {isMovie ? 'MOVIE' : 'SERIES'}
          </span>
          {item.isStale && (
            <span className="hub-stale-pill" title="Cached offline copy">
              <Clock size={10} />
              <span>Cached</span>
            </span>
          )}
          {ratingFormatted && (
            <span className="hub-rating-pill" title={`Rating: ${ratingFormatted}/10`}>
              <Star size={11} className="rating-star-icon" />
              <span>{ratingFormatted}</span>
            </span>
          )}
          {isFavorite && (
            <span className="hub-fav-badge" title="Favorited">
              <Heart size={10} fill="#FF375F" color="#FF375F" />
            </span>
          )}
          {isWatched && (
            <span className="hub-watched-badge" title="Watched">
              <CheckCircle2 size={10} color="#30D158" />
            </span>
          )}
        </div>

        {/* Hover Action Overlay - Vertical Action Stack */}
        <div className="hub-card-hover-overlay">
          <button
            type="button"
            className="hub-card-action-btn action-details"
            onClick={(e) => {
              e.stopPropagation();
              onOpenDetails && onOpenDetails(item);
            }}
            title="View Details"
          >
            <Info size={14} />
            <span>Details</span>
          </button>
          <button
            type="button"
            className={`hub-card-action-btn action-bookmark ${isWatchlisted ? 'bookmarked' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              onToggleWatchlist && onToggleWatchlist(item);
            }}
            title={isWatchlisted ? 'Remove from Watchlist' : 'Add to Watchlist'}
          >
            <Bookmark size={14} />
            <span>{isWatchlisted ? 'Saved' : 'Watchlist'}</span>
          </button>
          {onToggleFavorite && (
            <button
              type="button"
              className={`hub-card-action-btn action-fav ${isFavorite ? 'active-fav' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                onToggleFavorite(item);
              }}
              title={isFavorite ? 'Remove from Favorites' : 'Add to Favorites'}
            >
              <Heart
                size={14}
                fill={isFavorite ? '#FF375F' : 'none'}
                color={isFavorite ? '#FF375F' : 'currentColor'}
              />
              <span>{isFavorite ? 'Favorited' : 'Favorite'}</span>
            </button>
          )}
          {onToggleWatched && (
            <button
              type="button"
              className={`hub-card-action-btn action-watched ${isWatched ? 'active-watched' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                onToggleWatched(item);
              }}
              title={isWatched ? 'Mark as Unwatched' : 'Mark as Watched'}
            >
              <CheckCircle2
                size={14}
                color={isWatched ? '#30D158' : 'currentColor'}
              />
              <span>{isWatched ? 'Watched' : 'Watch'}</span>
            </button>
          )}
          {onCompare && (
            <button
              type="button"
              className="hub-card-action-btn action-compare"
              onClick={(e) => {
                e.stopPropagation();
                onCompare(item);
              }}
              title="Compare title side-by-side"
              aria-label="Compare title"
            >
              <SlidersHorizontal size={14} />
              <span>Compare</span>
            </button>
          )}
        </div>
      </div>

      {/* Meta Content */}
      <div className="hub-card-body">
        <h4 className="hub-card-title" title={item.title}>
          {item.title}
        </h4>
        <div className="hub-card-meta-line">
          {item.releaseYear && <span className="hub-card-year">{item.releaseYear}</span>}
          {item.originalLanguage && (
            <span className="hub-card-lang-chip">{item.originalLanguage.toUpperCase()}</span>
          )}
        </div>
      </div>
    </article>
  );
};

export default MovieCard;
