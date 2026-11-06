import React from 'react';
import { SlidersHorizontal, RotateCcw, ArrowUpDown, Calendar, Film } from 'lucide-react';

export interface FilterState {
  language: string;
  genre: string;
  releaseYear: string;
  sortBy: string;
}

interface FilterControlsProps {
  filters: FilterState;
  onChange: (updated: Partial<FilterState>) => void;
  onReset: () => void;
  isModified: boolean;
}

export const LANGUAGE_OPTIONS = [
  { value: 'all', label: 'All Languages' },
  { value: 'hi', label: 'Hindi (हिंदी)' },
  { value: 'te', label: 'Telugu (తెలుగు)' },
  { value: 'ta', label: 'Tamil (தமிழ்)' },
  { value: 'ml', label: 'Malayalam (മലയാളം)' },
  { value: 'kn', label: 'Kannada (ಕನ್ನಡ)' },
  { value: 'bn', label: 'Bengali (বাংলা)' },
  { value: 'mr', label: 'Marathi (मराठी)' },
  { value: 'pa', label: 'Punjabi (ਪੰਜਾਬੀ)' },
  { value: 'en', label: 'English' },
  { value: 'ko', label: 'Korean (한국어)' },
  { value: 'ja', label: 'Japanese (日本語)' },
  { value: 'es', label: 'Spanish (Español)' },
  { value: 'fr', label: 'French (Français)' },
  { value: 'de', label: 'German (Deutsch)' },
];

export const GENRE_OPTIONS = [
  { value: 'all', label: 'All Genres' },
  { value: '28', label: 'Action' },
  { value: '12', label: 'Adventure' },
  { value: '16', label: 'Animation' },
  { value: '35', label: 'Comedy' },
  { value: '80', label: 'Crime' },
  { value: '99', label: 'Documentary' },
  { value: '18', label: 'Drama' },
  { value: '14', label: 'Fantasy' },
  { value: '27', label: 'Horror' },
  { value: '9648', label: 'Mystery' },
  { value: '10749', label: 'Romance' },
  { value: '878', label: 'Sci-Fi' },
  { value: '53', label: 'Thriller' },
  { value: '28|878', label: 'Action & Sci-Fi' },
  { value: '80|53', label: 'Crime & Thriller' },
  { value: '35|10749', label: 'Rom-Com (Comedy & Romance)' },
];

export const YEAR_OPTIONS = [
  { value: 'all', label: 'All Years' },
  { value: '2025', label: '2025' },
  { value: '2024', label: '2024' },
  { value: '2023', label: '2023' },
  { value: '2022', label: '2022' },
  { value: '2020s', label: '2020s' },
  { value: '2010s', label: '2010s' },
  { value: '2000s', label: '2000s' },
  { value: 'classic', label: 'Classics (<2000)' },
];

export const SORT_OPTIONS = [
  { value: 'popularity.desc', label: 'Most Popular' },
  { value: 'vote_average.desc', label: 'Highest Rated' },
  { value: 'primary_release_date.desc', label: 'Release Date (Newest)' },
  { value: 'title.asc', label: 'Title (A–Z)' },
];

export const FilterControls: React.FC<FilterControlsProps> = ({
  filters,
  onChange,
  onReset,
  isModified,
}) => {
  return (
    <div className="hub-secondary-filters" role="group" aria-label="Secondary Catalog Filters">
      {/* Language Dropdown Selector */}
      <div className="hub-select-wrap">
        <select
          className="hub-native-select"
          value={filters.language}
          onChange={(e) => onChange({ language: e.target.value })}
          aria-label="Filter by Language"
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Genre Dropdown Selector */}
      <div className="hub-select-wrap">
        <select
          className="hub-native-select"
          value={filters.genre}
          onChange={(e) => onChange({ genre: e.target.value })}
          aria-label="Filter by Genre"
        >
          {GENRE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Release Year Selector */}
      <div className="hub-select-wrap">
        <select
          className="hub-native-select"
          value={filters.releaseYear}
          onChange={(e) => onChange({ releaseYear: e.target.value })}
          aria-label="Filter by Release Year"
        >
          {YEAR_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Sort By Selector */}
      <div className="hub-select-wrap">
        <select
          className="hub-native-select"
          value={filters.sortBy}
          onChange={(e) => onChange({ sortBy: e.target.value })}
          aria-label="Sort Catalog"
          title="Provider-side sorting for catalog discovery (Popularity, Rating, Release Date); Local sorting for Title (A–Z) and search results."
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Clear / Reset Action Button */}
      {isModified && (
        <button
          type="button"
          className="hub-reset-filters-btn"
          onClick={onReset}
          title="Reset all filters to defaults"
        >
          <RotateCcw size={12} />
          <span>Reset</span>
        </button>
      )}
    </div>
  );
};

export default FilterControls;
