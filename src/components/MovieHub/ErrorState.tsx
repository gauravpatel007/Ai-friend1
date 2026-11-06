import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Failed to Load Titles',
  message = 'An error occurred while connecting to the metadata service. Please check your network or try again.',
  onRetry,
}) => {
  return (
    <div className="hub-error-state-card" role="alert">
      <div className="hub-error-icon-bubble">
        <AlertCircle size={32} className="error-glyph" />
      </div>
      <h3 className="hub-error-title">{title}</h3>
      <p className="hub-error-desc">{message}</p>
      {onRetry && (
        <button
          type="button"
          className="hub-error-retry-btn"
          onClick={onRetry}
          title="Retry Operation"
        >
          <RefreshCw size={13} />
          <span>Try Again</span>
        </button>
      )}
    </div>
  );
};

export default ErrorState;
