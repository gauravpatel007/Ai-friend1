import React, { useEffect, useState, useMemo } from 'react';
import {
  Mic,
  MicOff,
  Square,
  Volume2,
  VolumeX,
  X,
  Radio,
  Sparkles,
  Sliders,
  CheckCircle2,
} from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import './VoicePortal.css';

export const VoicePortal: React.FC = () => {
  const {
    companionProfile,
    voiceStatus,
    setVoicePortalOpen,
    toggleVoice,
    setVoiceMode,
    stopVoice,
    muteVoice,
    diagnosticStatus,
    isStreaming,
    streamingText,
    interimTranscript,
    currentSubtitle,
    setSettingsOpen,
  } = useChatStore();

  const effectiveAppState = useChatStore((s) => s.getEffectiveAppState());
  const [wavePhase, setWavePhase] = useState(0);

  // Authoritative single-source conversational state from the store state machine
  const currentState = useMemo(() => {
    switch (effectiveAppState) {
      case 'LISTENING':
        return 'listening';
      case 'TRANSCRIBING':
        return 'transcribing';
      case 'THINKING':
        return 'thinking';
      case 'SPEAKING':
        return 'speaking';
      case 'ERROR':
        return 'error';
      case 'IDLE':
      default:
        return 'ready';
    }
  }, [effectiveAppState]);

  // Dynamic status text and colors
  const statusInfo = useMemo(() => {
    switch (currentState) {
      case 'listening':
        return {
          title: interimTranscript ? "Hearing you speak..." : "I'm listening...",
          subtitle: interimTranscript ? `"${interimTranscript}..."` : 'Speak naturally or tap stop when finished',
          badgeColor: '#00E5FF',
          badgeText: 'Listening',
        };
      case 'transcribing':
        return {
          title: 'Transcribing speech...',
          subtitle: 'Processing speech with local Whisper model',
          badgeColor: '#BF5AF2',
          badgeText: 'Processing',
        };
      case 'thinking':
        return {
          title: 'Thinking...',
          subtitle: streamingText ? `"${streamingText.slice(0, 75)}..."` : 'Generating response with local AI',
          badgeColor: '#FF9F0A',
          badgeText: 'Generating',
        };
      case 'speaking':
        return {
          title: 'Speaking aloud...',
          subtitle: currentSubtitle ? `"${currentSubtitle}"` : (streamingText ? `"${streamingText.slice(0, 80)}"` : 'Synthesizing voice with local neural TTS'),
          badgeColor: '#30D158',
          badgeText: 'Speaking',
        };
      case 'error':
        return {
          title: 'Voice error occurred',
          subtitle: 'Please check your microphone and try again',
          badgeColor: '#FF453A',
          badgeText: 'Error',
        };
      case 'ready':
      default:
        return {
          title: 'Ready to talk',
          subtitle: 'Tap microphone or speak naturally',
          badgeColor: '#30D158',
          badgeText: 'Ready',
        };
    }
  }, [currentState, streamingText, interimTranscript, currentSubtitle]);

  // Live waveform animation loop
  useEffect(() => {
    let animId: number;
    const updateAnimation = () => {
      setWavePhase((prev) => (prev + 0.12) % (Math.PI * 2));
      animId = requestAnimationFrame(updateAnimation);
    };
    animId = requestAnimationFrame(updateAnimation);
    return () => cancelAnimationFrame(animId);
  }, []);

  // Compute 28 responsive waveform bar heights
  const bars = useMemo(() => {
    const totalBars = 28;
    const isActive = currentState === 'listening' || currentState === 'speaking' || currentState === 'thinking';
    const baseEnergy = isActive ? 0.45 : 0.15;

    return Array.from({ length: totalBars }, (_, i) => {
      const distFromCenter = Math.abs(i - totalBars / 2) / (totalBars / 2);
      const envelope = Math.cos((distFromCenter * Math.PI) / 2) ** 1.3;
      const osc1 = Math.sin(wavePhase + i * 0.35) * 0.5 + 0.5;
      const osc2 = Math.cos(wavePhase * 1.4 - i * 0.25) * 0.3 + 0.3;
      const heightRatio = baseEnergy * envelope * (osc1 * 0.6 + osc2 * 0.4 + 0.2);
      const barHeight = Math.max(5, Math.min(34, heightRatio * 34));
      return { id: i, height: barHeight };
    });
  }, [wavePhase, currentState]);

  return (
    <div
      className="voice-portal-scrim"
      onClick={() => setVoicePortalOpen(false)}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="voice-portal-card"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Ambient Radial Portal Glow Background */}
        <div className={`portal-ambient-aura aura-${currentState}`} />

        {/* 1. Dynamic Island Top Header Pill */}
        <div className="portal-header-bar">
          <div className="portal-island-pill">
            <div className="island-avatar-mini">
              <img
                src={`/assets/characters/robot/${companionProfile.state || 'idle'}.png`}
                onError={(e) => {
                  (e.target as HTMLImageElement).src = '/assets/characters/robot/idle.png';
                }}
                alt={`${companionProfile.name || 'Buddy'} Avatar`}
              />
            </div>
            <span
              className="island-status-dot"
              style={{
                backgroundColor: statusInfo.badgeColor,
                boxShadow: `0 0 10px ${statusInfo.badgeColor}`,
              }}
            />
            <span className="island-title">
              {companionProfile.name || 'Buddy'} &bull; Voice Mode
            </span>
          </div>

          <button
            className="portal-close-btn"
            onClick={() => setVoicePortalOpen(false)}
            title="Close Voice Portal (Esc)"
            aria-label="Close"
          >
            <X size={15} />
          </button>
        </div>

        {/* 2. Siri-Inspired Luminous Acoustic Portal with Concentric Rings */}
        <div className="portal-visual-stage">
          <div className={`acoustic-ring ring-outer pulse-${currentState}`} />
          <div className={`acoustic-ring ring-middle pulse-${currentState}`} />
          <div className={`acoustic-ring ring-inner pulse-${currentState}`} />

          {/* Floating Character Avatar with 3D Bobbing */}
          <div className="portal-character-wrap">
            <div className="character-reflection" />
            <img
              src={`/assets/characters/robot/${companionProfile.state || 'idle'}.png`}
              onError={(e) => {
                (e.target as HTMLImageElement).src = '/assets/characters/robot/idle.png';
              }}
              alt="AI Companion"
              className="portal-character-img"
            />
          </div>
        </div>

        {/* 3. Status Text & Subtitle Guidance */}
        <div className="portal-text-section">
          <h2 className="portal-status-headline">{statusInfo.title}</h2>
          <p className="portal-status-subtitle">{statusInfo.subtitle}</p>
        </div>

        {/* 4. Organic Apple Equalizer Waveform */}
        <div className="portal-waveform-container" aria-label="Audio Visualizer">
          {bars.map((bar) => (
            <span
              key={bar.id}
              className="waveform-bar"
              style={{
                height: `${bar.height}px`,
                opacity: currentState === 'ready' ? 0.4 : 0.95,
              }}
            />
          ))}
        </div>

        {/* 5. Frosted Glass Action Dock */}
        <div className="portal-action-dock">
          {/* Left: Mode / Mute Toggle */}
          <button
            className={`dock-btn dock-btn-subtle ${voiceStatus.is_muted ? 'btn-active-danger' : ''}`}
            onClick={() => muteVoice(!voiceStatus.is_muted)}
            title={voiceStatus.is_muted ? 'Unmute microphone' : 'Mute microphone'}
            aria-label="Toggle Mute"
          >
            {voiceStatus.is_muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
          </button>

          {/* Center-Left: Mic Start / PTT */}
          <button
            className={`dock-btn dock-btn-mic ${currentState === 'listening' ? 'btn-listening-active' : ''}`}
            onClick={() => {
              if (voiceStatus.mode === 'off') {
                setVoiceMode('continuous');
              } else {
                toggleVoice();
              }
            }}
            title={voiceStatus.mode === 'off' ? 'Start listening' : 'Toggle listening'}
            aria-label="Toggle Microphone"
          >
            <Mic size={20} />
          </button>

          {/* Center-Right: Big Red Stop Button */}
          <button
            className="dock-btn dock-btn-stop"
            onClick={stopVoice}
            title="Stop voice and cancel current action"
            aria-label="Stop Voice"
          >
            <Square size={16} fill="white" />
          </button>

          {/* Right: Settings Sheet Shortcut */}
          <button
            className="dock-btn dock-btn-subtle"
            onClick={() => {
              setVoicePortalOpen(false);
              setSettingsOpen(true);
            }}
            title="Open Voice Settings"
            aria-label="Voice Settings"
          >
            <Sliders size={18} />
          </button>
        </div>

        {/* Footer Pill: Active Mode Indicator */}
        <div className="portal-footer-pill">
          <Radio size={11} className="pulse-icon" />
          <span>
            {voiceStatus.mode === 'continuous'
              ? 'Continuous Hands-Free Listening'
              : voiceStatus.mode === 'push_to_talk'
              ? 'Push-to-Talk (Hold Space or Mic)'
              : 'Voice Mode Active'}
          </span>
        </div>
      </div>
    </div>
  );
};
