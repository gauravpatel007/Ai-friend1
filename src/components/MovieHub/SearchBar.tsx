import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Search, X, Mic, MicOff, Loader2 } from 'lucide-react';
import { startVoiceDictation, stopVoiceDictation } from '../../api/movieApi';

interface SearchBarProps {
  value: string;
  onChange: (val: string) => void;
  onClear?: () => void;
  onSubmit?: (val: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

type DictationState = 'idle' | 'recording' | 'transcribing' | 'error';

export const SearchBar: React.FC<SearchBarProps> = ({
  value,
  onChange,
  onClear,
  onSubmit,
  placeholder = 'Search movies, series, directors, actors... (Ctrl+K)',
  disabled = false,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dictationState, setDictationState] = useState<DictationState>('idle');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const autoStopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isStoppingRef = useRef<boolean>(false);

  // Helper to show temporary feedback message
  const showFeedback = useCallback((msg: string, durationMs: number = 3200) => {
    setStatusMessage(msg);
    if (messageTimerRef.current) {
      clearTimeout(messageTimerRef.current);
    }
    messageTimerRef.current = setTimeout(() => {
      setStatusMessage(null);
    }, durationMs);
  }, []);

  // Clear timers on unmount
  useEffect(() => {
    return () => {
      if (autoStopTimeoutRef.current) clearTimeout(autoStopTimeoutRef.current);
      if (messageTimerRef.current) clearTimeout(messageTimerRef.current);
    };
  }, []);

  // Global keyboard shortcut to focus search: Ctrl+K or '/'
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      } else if (
        e.key === '/' &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  // Stop recording and transcribe audio using native Faster-Whisper
  const handleStopDictation = useCallback(async () => {
    if (isStoppingRef.current) return;
    isStoppingRef.current = true;

    if (autoStopTimeoutRef.current) {
      clearTimeout(autoStopTimeoutRef.current);
      autoStopTimeoutRef.current = null;
    }

    setDictationState('transcribing');
    setStatusMessage('Transcribing speech...');

    try {
      const res = await stopVoiceDictation();
      const recognized = (res.text || '').trim();

      if (recognized) {
        onChange(recognized);
        if (onSubmit) {
          onSubmit(recognized);
        }
        setStatusMessage(null);
      } else {
        showFeedback('No speech detected. Please speak clearly.');
      }
    } catch (err) {
      console.warn('Voice dictation error:', err);
      showFeedback('Voice recognition failed. Please try again.');
    } finally {
      setDictationState('idle');
      isStoppingRef.current = false;
    }
  }, [onChange, onSubmit, showFeedback]);

  // Start microphone dictation via backend
  const handleStartDictation = useCallback(async () => {
    if (disabled || isStoppingRef.current) return;

    if (dictationState === 'recording') {
      await handleStopDictation();
      return;
    }

    if (dictationState === 'transcribing') {
      return;
    }

    setDictationState('recording');
    setStatusMessage('Listening... Speak a movie or series title');

    try {
      const startRes = await startVoiceDictation();
      if (startRes.status !== 'ok') {
        throw new Error(startRes.message || 'Microphone unavailable');
      }

      // Automatically finalize recording after 6.5s if user does not press stop
      autoStopTimeoutRef.current = setTimeout(() => {
        handleStopDictation();
      }, 6500);
    } catch (err: any) {
      console.warn('Voice dictation start error:', err);
      setDictationState('error');
      showFeedback('Microphone unavailable or permission denied.', 3500);
      setTimeout(() => {
        setDictationState('idle');
      }, 2000);
    }
  }, [disabled, dictationState, handleStopDictation, showFeedback]);

  const handleClear = () => {
    onChange('');
    if (onClear) onClear();
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      if (dictationState === 'recording') {
        // Cancel recording without saving
        if (autoStopTimeoutRef.current) clearTimeout(autoStopTimeoutRef.current);
        stopVoiceDictation().catch(() => {});
        setDictationState('idle');
        setStatusMessage(null);
      } else {
        handleClear();
        inputRef.current?.blur();
      }
    } else if (e.key === 'Enter') {
      if (onSubmit) {
        onSubmit(value);
      }
    }
  };

  const inputPlaceholder =
    dictationState === 'recording'
      ? 'Listening... Speak title or actor now'
      : dictationState === 'transcribing'
        ? 'Transcribing speech with Whisper...'
        : placeholder;

  return (
    <div className="hub-searchbar-container" role="search">
      <div
        className={`hub-searchbar-frame ${
          dictationState === 'recording'
            ? 'listening'
            : dictationState === 'transcribing'
              ? 'transcribing'
              : dictationState === 'error'
                ? 'error'
                : ''
        }`}
      >
        <Search size={14} className="hub-searchbar-glyph" aria-hidden="true" />
        <input
          ref={inputRef}
          type="text"
          className="hub-searchbar-input"
          placeholder={inputPlaceholder}
          value={value}
          disabled={disabled || dictationState === 'transcribing'}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Search entertainment catalog"
        />

        {value && !disabled && dictationState === 'idle' && (
          <button
            type="button"
            className="hub-searchbar-clear"
            onClick={handleClear}
            title="Clear search (Escape)"
            aria-label="Clear search query"
          >
            <X size={13} />
          </button>
        )}

        <button
          type="button"
          className={`hub-searchbar-mic-btn ${dictationState === 'recording' ? 'active-recording' : ''}`}
          onClick={dictationState === 'recording' ? handleStopDictation : handleStartDictation}
          disabled={disabled || dictationState === 'transcribing'}
          title={
            dictationState === 'recording'
              ? 'Listening... Click to search'
              : dictationState === 'transcribing'
                ? 'Transcribing...'
                : 'Voice Search (Click to speak)'
          }
          aria-label={
            dictationState === 'recording'
              ? 'Listening to voice input. Click to finalize search.'
              : 'Start voice search'
          }
        >
          {dictationState === 'recording' ? (
            <MicOff size={14} className="hub-mic-icon recording" />
          ) : dictationState === 'transcribing' ? (
            <Loader2 size={14} className="hub-mic-icon spinning" />
          ) : (
            <Mic size={14} className="hub-mic-icon" />
          )}
        </button>

        {/* Dynamic status tooltip feedback */}
        {statusMessage && (
          <div
            className={`hub-searchbar-status-tip ${
              dictationState === 'recording'
                ? 'recording'
                : dictationState === 'transcribing'
                  ? 'transcribing'
                  : 'error'
            }`}
            role="status"
            aria-live="polite"
          >
            <span className="hub-status-dot" aria-hidden="true" />
            <span>{statusMessage}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default SearchBar;
