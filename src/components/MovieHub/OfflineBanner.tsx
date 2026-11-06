import React, { useState } from 'react';
import { WifiOff, RefreshCw, CheckCircle2, Database } from 'lucide-react';
import './OfflineBanner.css';

interface OfflineBannerProps {
  isOffline: boolean;
  onRetry: () => Promise<void>;
  cachedCount?: number;
}

export const OfflineBanner: React.FC<OfflineBannerProps> = ({
  isOffline,
  onRetry,
  cachedCount = 0,
}) => {
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);

  if (!isOffline) return null;

  const handleRetryClick = async () => {
    setIsRetrying(true);
    setRetryMessage(null);
    try {
      await onRetry();
    } catch {
      setRetryMessage('Still offline. Check your internet connection.');
    } finally {
      setIsRetrying(false);
    }
  };

  return (
    <aside className="hub-offline-banner" role="status" aria-live="polite">
      <div className="hub-offline-content">
        <div className="hub-offline-icon-frame" aria-hidden="true">
          <WifiOff size={18} className="hub-offline-glyph" />
        </div>

        <div className="hub-offline-text-block">
          <div className="hub-offline-headline-row">
            <h4 className="hub-offline-title">Offline Mode</h4>
            <span className="hub-offline-pill">Local Storage Active</span>
          </div>
          <p className="hub-offline-desc">
            You are currently offline or TMDB is unreachable. Showing locally cached titles and your personal library.
            {cachedCount > 0 && ` (${cachedCount} titles cached)`} Live catalog searches require an internet connection.
          </p>
          {retryMessage && <span className="hub-offline-retry-hint">{retryMessage}</span>}
        </div>
      </div>

      <div className="hub-offline-actions">
        <button
          type="button"
          className="hub-offline-retry-btn"
          onClick={handleRetryClick}
          disabled={isRetrying}
          aria-label="Retry network connection"
        >
          <RefreshCw size={13} className={isRetrying ? 'hub-spin' : ''} />
          <span>{isRetrying ? 'Checking...' : 'Retry Connection'}</span>
        </button>
      </div>
    </aside>
  );
};
