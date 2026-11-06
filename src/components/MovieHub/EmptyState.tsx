import React from 'react';
import { Film, RotateCcw } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  description?: string;
  onReset?: () => void;
  actionText?: string;
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No Titles Found',
  description = 'Try adjusting your search query, content format, or regional filters to explore titles.',
  onReset,
  actionText = 'Reset Filters',
  icon,
}) => {
  return (
    <div className="hub-empty-state-card" role="status">
      <div className="hub-empty-icon-bubble">
        {icon || <Film size={32} className="empty-glyph" />}
      </div>
      <h3 className="hub-empty-title">{title}</h3>
      <p className="hub-empty-desc">{description}</p>
      {onReset && (
        <button
          type="button"
          className="hub-empty-action-btn"
          onClick={onReset}
          title="Reset Active Filters"
        >
          <RotateCcw size={13} />
          <span>{actionText}</span>
        </button>
      )}
    </div>
  );
};

export default EmptyState;
