import React from 'react';
import { Globe } from 'lucide-react';

export type RegionalCategory =
  | 'all'
  | 'indian'
  | 'bollywood'
  | 'south_indian'
  | 'hollywood'
  | 'international';

interface RegionFilterProps {
  value: RegionalCategory;
  onChange: (val: RegionalCategory) => void;
}

const REGION_OPTIONS: { id: RegionalCategory; label: string; title: string }[] = [
  { id: 'all', label: 'All Regions', title: 'Global Cinema' },
  { id: 'indian', label: 'Indian Cinema', title: 'All Indian Regional Film Industries' },
  { id: 'bollywood', label: 'Bollywood', title: 'Hindi Cinema' },
  { id: 'south_indian', label: 'South Indian', title: 'Telugu, Tamil, Malayalam & Kannada Cinema' },
  { id: 'hollywood', label: 'Hollywood', title: 'US & Western Blockbusters' },
  { id: 'international', label: 'International', title: 'World Cinema & Foreign Language' },
];

export const RegionFilter: React.FC<RegionFilterProps> = ({ value, onChange }) => {
  return (
    <div className="hub-filter-cluster regional-filter-cluster" role="radiogroup" aria-label="Regional Cinema">
      <div className="hub-cluster-label">
        <Globe size={13} />
        <span>Region:</span>
      </div>
      <div className="hub-pill-segmented-scroll">
        {REGION_OPTIONS.map((opt) => {
          const isActive = value === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={isActive}
              className={`hub-region-pill ${isActive ? 'active' : ''}`}
              onClick={() => onChange(opt.id)}
              title={opt.title}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default RegionFilter;
