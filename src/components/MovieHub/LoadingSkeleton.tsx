import React from 'react';

interface LoadingSkeletonProps {
  count?: number;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({ count = 8 }) => {
  const skeletons = Array.from({ length: count });

  return (
    <div className="hub-skeleton-grid" role="status" aria-label="Loading movies and series">
      {skeletons.map((_, i) => (
        <div key={i} className="hub-skeleton-card">
          <div className="hub-skeleton-poster shimmer-animation" />
          <div className="hub-skeleton-text-block">
            <div className="hub-skeleton-line hub-skeleton-title shimmer-animation" />
            <div className="hub-skeleton-line hub-skeleton-sub shimmer-animation" />
          </div>
        </div>
      ))}
    </div>
  );
};

export default LoadingSkeleton;
