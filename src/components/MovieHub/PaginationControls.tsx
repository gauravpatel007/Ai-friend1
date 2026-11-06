import React from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

interface PaginationControlsProps {
  currentPage: number;
  totalPages: number;
  totalResults: number;
  onPageChange: (newPage: number) => void;
  isLoading?: boolean;
}

export const PaginationControls: React.FC<PaginationControlsProps> = ({
  currentPage,
  totalPages,
  totalResults,
  onPageChange,
  isLoading = false,
}) => {
  // TMDB caps maximum discover/search pages to 500
  const maxAllowedPages = Math.min(totalPages, 500);

  if (maxAllowedPages <= 1) {
    return null;
  }

  const handlePrev = () => {
    if (currentPage > 1 && !isLoading) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNext = () => {
    if (currentPage < maxAllowedPages && !isLoading) {
      onPageChange(currentPage + 1);
    }
  };

  const handleFirst = () => {
    if (currentPage !== 1 && !isLoading) {
      onPageChange(1);
    }
  };

  const handleLast = () => {
    if (currentPage !== maxAllowedPages && !isLoading) {
      onPageChange(maxAllowedPages);
    }
  };

  // Generate a compact list of visible page buttons around currentPage
  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    const delta = 1; // Show current - 1, current, current + 1

    const left = Math.max(2, currentPage - delta);
    const right = Math.min(maxAllowedPages - 1, currentPage + delta);

    pages.push(1);

    if (left > 2) {
      pages.push('...');
    }

    for (let i = left; i <= right; i++) {
      pages.push(i);
    }

    if (right < maxAllowedPages - 1) {
      pages.push('...');
    }

    if (maxAllowedPages > 1) {
      pages.push(maxAllowedPages);
    }

    return pages;
  };

  return (
    <nav className="hub-pagination-bar" aria-label="Catalog Pagination">
      <div className="hub-pagination-meta">
        <span className="hub-pagination-count">
          Showing page <strong>{currentPage}</strong> of <strong>{maxAllowedPages}</strong>
          {totalResults > 0 && (
            <span className="hub-total-results">
              {' '}&bull; {totalResults.toLocaleString()} titles available
            </span>
          )}
        </span>
      </div>

      <div className="hub-pagination-actions">
        {/* Jump to First Page */}
        <button
          type="button"
          className="hub-page-nav-btn"
          onClick={handleFirst}
          disabled={currentPage <= 1 || isLoading}
          title="First Page"
          aria-label="Go to first page"
        >
          <ChevronsLeft size={14} />
        </button>

        {/* Previous Page */}
        <button
          type="button"
          className="hub-page-nav-btn"
          onClick={handlePrev}
          disabled={currentPage <= 1 || isLoading}
          title="Previous Page"
          aria-label="Go to previous page"
        >
          <ChevronLeft size={14} />
          <span className="hub-page-btn-text">Prev</span>
        </button>

        {/* Numbered Page Buttons */}
        <div className="hub-page-numbers-group">
          {getPageNumbers().map((p, idx) => {
            if (typeof p === 'string') {
              return (
                <span key={`ellipsis-${idx}`} className="hub-page-ellipsis" aria-hidden="true">
                  &hellip;
                </span>
              );
            }
            const isActive = p === currentPage;
            return (
              <button
                key={`page-${p}`}
                type="button"
                className={`hub-page-number-btn ${isActive ? 'active' : ''}`}
                onClick={() => !isActive && !isLoading && onPageChange(p)}
                disabled={isLoading}
                aria-current={isActive ? 'page' : undefined}
                aria-label={`Go to page ${p}`}
              >
                {p}
              </button>
            );
          })}
        </div>

        {/* Next Page */}
        <button
          type="button"
          className="hub-page-nav-btn"
          onClick={handleNext}
          disabled={currentPage >= maxAllowedPages || isLoading}
          title="Next Page"
          aria-label="Go to next page"
        >
          <span className="hub-page-btn-text">Next</span>
          <ChevronRight size={14} />
        </button>

        {/* Jump to Last Page */}
        <button
          type="button"
          className="hub-page-nav-btn"
          onClick={handleLast}
          disabled={currentPage >= maxAllowedPages || isLoading}
          title="Last Page"
          aria-label="Go to last page"
        >
          <ChevronsRight size={14} />
        </button>
      </div>
    </nav>
  );
};
