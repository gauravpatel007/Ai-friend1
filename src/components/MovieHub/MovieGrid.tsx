import React from 'react';
import { MovieCard, MovieItemModel } from './MovieCard';
import { LoadingSkeleton } from './LoadingSkeleton';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';

export type GridViewStatus = 'loading' | 'empty' | 'error' | 'ready';

interface MovieGridProps {
  status: GridViewStatus;
  items?: MovieItemModel[];
  errorMessage?: string;
  onRetry?: () => void;
  onResetFilters?: () => void;
  onOpenDetails?: (item: MovieItemModel) => void;
  onOpenPoster?: (item: MovieItemModel) => void;
  onToggleWatchlist?: (item: MovieItemModel) => void;
  onToggleFavorite?: (item: MovieItemModel) => void;
  onToggleWatched?: (item: MovieItemModel) => void;
  onCompare?: (item: MovieItemModel) => void;
  watchlistIds?: Set<string | number>;
  favoriteIds?: Set<string | number>;
  watchedIds?: Set<string | number>;
  emptyTitle?: string;
  emptyDescription?: string;
}

export const MovieGrid: React.FC<MovieGridProps> = ({
  status,
  items = [],
  errorMessage,
  onRetry,
  onResetFilters,
  onOpenDetails,
  onOpenPoster,
  onToggleWatchlist,
  onToggleFavorite,
  onToggleWatched,
  onCompare,
  watchlistIds = new Set(),
  favoriteIds = new Set(),
  watchedIds = new Set(),
  emptyTitle,
  emptyDescription,
}) => {
  if (status === 'loading') {
    return <LoadingSkeleton count={10} />;
  }

  if (status === 'error') {
    return <ErrorState message={errorMessage} onRetry={onRetry} />;
  }

  if (status === 'empty' || items.length === 0) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        onReset={onResetFilters}
      />
    );
  }

  return (
    <div className="hub-media-grid" role="feed" aria-label="Media Results Grid">
      {items.map((item) => (
        <MovieCard
          key={`${item.mediaType}-${item.id}`}
          item={item}
          onOpenDetails={onOpenDetails}
          onOpenPoster={onOpenPoster}
          onToggleWatchlist={onToggleWatchlist}
          onToggleFavorite={onToggleFavorite}
          onToggleWatched={onToggleWatched}
          onCompare={onCompare}
          isWatchlisted={watchlistIds.has(item.id)}
          isFavorite={favoriteIds.has(item.id)}
          isWatched={watchedIds.has(item.id)}
        />
      ))}
    </div>
  );
};

export default MovieGrid;
