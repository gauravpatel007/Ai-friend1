import React from 'react';
import { Clapperboard, Film, Tv } from 'lucide-react';

export type ContentType = 'all' | 'movies' | 'series';

interface ContentTypeSelectorProps {
  value: ContentType;
  onChange: (val: ContentType) => void;
}

export const ContentTypeSelector: React.FC<ContentTypeSelectorProps> = ({
  value,
  onChange,
}) => {
  return (
    <div className="hub-segmented-selector" role="radiogroup" aria-label="Content Type Format">
      <button
        type="button"
        role="radio"
        aria-checked={value === 'all'}
        className={`hub-seg-btn ${value === 'all' ? 'active' : ''}`}
        onClick={() => onChange('all')}
        title="Show All Movies and Series"
      >
        <Clapperboard size={13} />
        <span>ALL</span>
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={value === 'movies'}
        className={`hub-seg-btn ${value === 'movies' ? 'active' : ''}`}
        onClick={() => onChange('movies')}
        title="Show Only Movies"
      >
        <Film size={13} />
        <span>ONLY MOVIES</span>
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={value === 'series'}
        className={`hub-seg-btn ${value === 'series' ? 'active' : ''}`}
        onClick={() => onChange('series')}
        title="Show Only Television Series"
      >
        <Tv size={13} />
        <span>ONLY SERIES</span>
      </button>
    </div>
  );
};

export default ContentTypeSelector;
