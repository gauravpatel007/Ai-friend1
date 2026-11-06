import React, { useState } from 'react';
import {
  Mic,
  Square,
  Volume2,
  VolumeX,
  Plus,
  History,
  Trash2,
  Download,
  CheckCircle2,
  Layers,
  RotateCcw,
  Eye,
  EyeOff,
  Radio,
  Moon,
  Sun,
} from 'lucide-react';
import { useChatStore, getAppStateDisplayInfo } from '../../store/useChatStore';
import * as api from '../../api/http';
import './RightPanel.css';

export const RightPanel: React.FC = () => {
  const {
    companionProfile,
    voiceStatus,
    modelInfo,
    activeConvId,
    conversations,
    messages,
    petAlwaysOnTop,
    petVisible,
    setPetAlwaysOnTop,
    togglePetVisible,
    resetPetPosition,
    setVoiceMode,
    stopVoice,
    muteVoice,
    wake,
    sleep,
    createConversation,
    clearCurrentChat,
    toggleSidebar,
    isRightPanelOpen,
    setVoicePortalOpen,
  } = useChatStore();

  const effectiveAppState = useChatStore((s) => s.getEffectiveAppState());
  const clearVoiceError = useChatStore((s) => s.clearVoiceError);
  const cancelGeneration = useChatStore((s) => s.cancelGeneration);

  const [exportNotice, setExportNotice] = useState(false);
  const [exportLabel, setExportLabel] = useState('Exported');
  const [exportPath, setExportPath] = useState('');
  const [resetNotice, setResetNotice] = useState(false);

  if (!isRightPanelOpen) {
    return null;
  }

  const handleExport = async () => {
    const targetConvId = activeConvId || (conversations && conversations.length > 0 ? conversations[0].id : '');
    let markdownContent = '';
    let exportTitle = companionProfile.name ? `${companionProfile.name}_Chat` : 'Bond_Chat';
    let savedToDisk = false;

    try {
      const res = await api.exportChat(targetConvId);
      if (res && res.markdown) {
        markdownContent = res.markdown;
        if (res.title) exportTitle = res.title;
        if (res.file_path) {
          savedToDisk = true;
          setExportPath(res.file_path);
        }
      }
    } catch (e) {
      console.warn('Backend exportChat note, synthesizing from messages:', e);
    }

    // Fallback: Synthesize from active store messages if backend returned empty or was unavailable
    if (!markdownContent) {
      const companionName = companionProfile.name || 'Bond';
      const lines = [
        `# 💬 ${exportTitle}`,
        `*${companionName} Companion Chat • Exported on ${new Date().toLocaleString()}*`,
        '',
        '---',
        '',
      ];
      if (!messages || messages.length === 0) {
        lines.push('<div align="center" style="color: #888; font-style: italic;">No messages recorded in current chat session.</div>');
        lines.push('');
      } else {
        for (const m of messages) {
          const isUser = m.role === 'user';
          const speaker = isUser ? 'You' : companionName;
          const timeStr = m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
          const timePart = timeStr ? ` • ${timeStr}` : '';
          const escapedContent = (m.content || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br/>');

          if (isUser) {
            lines.push(
              `<div align="right" style="margin: 12px 0 12px auto; text-align: right;">\n` +
              `  <div style="display: inline-block; text-align: left; max-width: 78%; background-color: #2563eb; color: #ffffff; padding: 10px 16px; border-radius: 18px 18px 4px 18px; box-shadow: 0 2px 6px rgba(0,0,0,0.18); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">\n` +
              `    <div style="font-size: 11px; font-weight: 700; color: #bfdbfe; margin-bottom: 4px; text-align: right;">${speaker}${timePart}</div>\n` +
              `    <div style="font-size: 14px; line-height: 1.5; color: #ffffff;">${escapedContent}</div>\n` +
              `  </div>\n` +
              `</div>\n`
            );
          } else {
            lines.push(
              `<div align="left" style="margin: 12px auto 12px 0; text-align: left;">\n` +
              `  <div style="display: inline-block; text-align: left; max-width: 78%; background-color: #1e293b; color: #f8fafc; padding: 10px 16px; border-radius: 18px 18px 18px 4px; border: 1px solid #334155; box-shadow: 0 2px 6px rgba(0,0,0,0.18); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">\n` +
              `    <div style="font-size: 11px; font-weight: 700; color: #38bdf8; margin-bottom: 4px;">${speaker} 🤖${timePart}</div>\n` +
              `    <div style="font-size: 14px; line-height: 1.5; color: #f1f5f9;">${escapedContent}</div>\n` +
              `  </div>\n` +
              `</div>\n`
            );
          }
        }
      }
      markdownContent = lines.join('\n');
    }

    try {
      const cleanFileName = exportTitle.replace(/[^a-zA-Z0-9_\-\u0900-\u0DFF]/g, '_').replace(/_+/g, '_');
      const blob = new Blob([markdownContent], { type: 'text/markdown;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${cleanFileName || 'Chat'}_export.md`);
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      setTimeout(() => {
        try {
          if (link.parentNode) {
            link.parentNode.removeChild(link);
          }
          URL.revokeObjectURL(url);
        } catch (_) {}
      }, 500);

      // Safe clipboard copy (silent catch so it never halts export UI)
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(markdownContent).catch(() => {});
        }
      } catch (_) {}
    } catch (e) {
      console.error('Export download link note:', e);
    }

    setExportLabel(savedToDisk ? 'Saved!' : 'Exported');
    setExportNotice(true);
    setTimeout(() => {
      setExportNotice(false);
      setExportLabel('Export');
    }, 2500);
  };

  const handleResetPos = async () => {
    try {
      await resetPetPosition();
      setResetNotice(true);
      setTimeout(() => setResetNotice(false), 2000);
    } catch (e) {
      console.error('Reset pet position failed', e);
    }
  };

  const isVoiceOn = voiceStatus.mode !== 'off';

  return (
    <aside className="apple-inspector-panel">
      <div className="inspector-scroll-content">
        {/* 1. Companion Profile Card */}
        <div className="inspector-card companion-profile-card">
          <div className="profile-avatar-frame">
            <div className="avatar-ambient-glow" />
            <img
              src={`/assets/characters/robot/${companionProfile.state || 'idle'}.png`}
              onError={(e) => {
                (e.target as HTMLImageElement).src = '/assets/characters/robot/idle.png';
              }}
              alt={`${companionProfile.name || 'Buddy'} Avatar`}
              className="profile-avatar-media"
            />
          </div>
          <h2 className="companion-display-name">{companionProfile.name || 'Buddy'}</h2>
          <p className="companion-description-caption">
            Your Local AI Assistant &bull; Always ready to help
          </p>
        </div>

        {/* 2. Status Row Card */}
        {(() => {
          const isSleeping = Boolean(voiceStatus.is_sleeping || companionProfile.state === 'sleeping' || companionProfile.operational_state === 'sleeping');
          const isMuted = Boolean(voiceStatus.is_muted || companionProfile.operational_state === 'muted');
          const displayInfo = getAppStateDisplayInfo(
            effectiveAppState,
            companionProfile.name || 'Buddy',
            modelInfo.active_model,
            isSleeping,
            isMuted
          );

          return (
            <div className={`inspector-card system-status-row ${
              isSleeping
                ? 'card-sleeping'
                : isMuted && effectiveAppState === 'IDLE'
                ? 'card-muted'
                : effectiveAppState === 'ERROR'
                ? 'card-error'
                : effectiveAppState === 'THINKING'
                ? 'card-thinking'
                : effectiveAppState === 'LISTENING'
                ? 'card-listening'
                : effectiveAppState === 'TRANSCRIBING'
                ? 'card-transcribing'
                : effectiveAppState === 'SPEAKING'
                ? 'card-speaking'
                : ''
            }`}>
              <div className="status-dot-frame">
                <span className={`status-apple-dot ${displayInfo.dotClass}`} />
              </div>
              <div className="status-label-col">
                <span className="status-headline">
                  {displayInfo.headline}
                </span>
                <span className="status-detail">
                  {displayInfo.detail}
                </span>
              </div>
              <div className="status-actions-col">
                {isSleeping && (
                  <button
                    className="btn-inline-wake"
                    onClick={wake}
                    title="Wake companion up immediately"
                  >
                    <Sun size={12} />
                    <span>Wake</span>
                  </button>
                )}
                {effectiveAppState === 'ERROR' && (
                  <button
                    className="btn-inline-error-clear"
                    onClick={clearVoiceError}
                    title="Clear error"
                  >
                    <RotateCcw size={12} />
                    <span>Dismiss</span>
                  </button>
                )}
                {(effectiveAppState === 'THINKING' || effectiveAppState === 'SPEAKING') && (
                  <button
                    className="btn-inline-stop btn-inline-error-clear"
                    onClick={cancelGeneration}
                    title="Stop generating response"
                  >
                    <Square size={12} />
                    <span>Stop</span>
                  </button>
                )}
              </div>
            </div>
          );
        })()}

        {/* 3. Voice Controls (Segmented Control Style) */}
        <div className="inspector-card section-group-card">
          <div className="card-header-bar">
            <span className="card-section-title">Voice Mode</span>
            <span style={{ fontSize: '10px', color: 'var(--color-accent)', fontWeight: 600 }}>
              {voiceStatus.is_sleeping || companionProfile.state === 'sleeping'
                ? 'Sleeping (Standby)'
                : voiceStatus.mode === 'continuous'
                ? 'Hands-Free'
                : voiceStatus.mode === 'push_to_talk'
                ? 'PTT'
                : voiceStatus.mode === 'listening'
                ? 'Listening'
                : voiceStatus.mode === 'processing'
                ? 'Processing'
                : 'Text Only'}
            </span>
          </div>
          <div className="voice-segmented-grid">
            <button
              className={`segmented-btn ${voiceStatus.mode === 'off' ? 'btn-active-voice' : ''}`}
              onClick={() => setVoiceMode('off')}
              title="Text Mode: Voice capture disabled"
            >
              <span>Text</span>
            </button>

            <button
              className={`segmented-btn ${voiceStatus.mode === 'push_to_talk' ? 'btn-active-voice' : ''}`}
              onClick={() => setVoiceMode('push_to_talk')}
              title="Push-to-Talk Mode"
            >
              <Mic size={14} />
              <span>PTT</span>
            </button>

            <button
              className={`segmented-btn ${voiceStatus.mode === 'continuous' ? 'btn-active-voice' : ''}`}
              onClick={() => setVoiceMode('continuous')}
              title="Continuous Hands-Free Voice Mode"
            >
              <Volume2 size={14} />
              <span>Continuous</span>
            </button>
          </div>

          <div className="voice-segmented-grid voice-sub-grid" style={{ marginTop: '4px' }}>
            <button
              className="segmented-btn"
              onClick={stopVoice}
              title="Stop speaking and listening"
            >
              <Square size={13} />
              <span>Stop</span>
            </button>

            {(() => {
              const isSleeping = Boolean(voiceStatus.is_sleeping || companionProfile.state === 'sleeping' || companionProfile.operational_state === 'sleeping');
              return (
                <button
                  className={`segmented-btn ${isSleeping ? 'btn-active-sleep' : ''}`}
                  onClick={isSleeping ? wake : sleep}
                  title={isSleeping ? 'Wake companion up' : 'Put companion to sleep (wake word remains active)'}
                >
                  {isSleeping ? <Sun size={13} /> : <Moon size={13} />}
                  <span>{isSleeping ? 'Wake' : 'Sleep'}</span>
                </button>
              );
            })()}

            <button
              className={`segmented-btn ${voiceStatus.is_muted ? 'btn-active-mute' : ''}`}
              onClick={() => muteVoice(!voiceStatus.is_muted)}
              title="Mute/Unmute audio output"
            >
              {voiceStatus.is_muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
              <span>{voiceStatus.is_muted ? 'Muted' : 'Mute'}</span>
            </button>
          </div>

          <button
            className="btn-launch-voice-portal"
            onClick={() => setVoicePortalOpen(true)}
            title="Open Dedicated Apple Siri Voice Portal"
          >
            <Radio size={14} className="pulse-icon" />
            <span>Open Voice Portal</span>
          </button>
        </div>

        {/* 4. Quick Actions */}
        <div className="inspector-card section-group-card">
          <div className="card-header-bar">
            <span className="card-section-title">Quick Actions</span>
          </div>
          <div className="quick-action-tiles-grid">
            <button
              className="action-tile-btn"
              onClick={() => createConversation('New Chat')}
              title="Start a new chat"
            >
              <Plus size={15} />
              <span>New Chat</span>
            </button>

            <button
              className="action-tile-btn"
              onClick={toggleSidebar}
              title="Toggle Chat History Sidebar"
            >
              <History size={15} />
              <span>History</span>
            </button>

            <button
              className="action-tile-btn btn-action-danger"
              onClick={clearCurrentChat}
              title="Clear current messages"
            >
              <Trash2 size={15} />
              <span>Clear</span>
            </button>

            <button
              className={`action-tile-btn ${exportNotice ? 'btn-tile-highlight' : ''}`}
              onClick={handleExport}
              title={exportNotice ? `Saved: ${exportPath || 'Downloads'}` : "Export chat as Markdown to Downloads folder"}
            >
              {exportNotice ? (
                <>
                  <CheckCircle2 size={15} className="export-ok-icon" />
                  <span>{exportLabel}</span>
                </>
              ) : (
                <>
                  <Download size={15} />
                  <span>Export</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* 5. Desktop Pet Overlay Controls */}
        <div className="inspector-card section-group-card">
          <div className="card-header-bar">
            <span className="card-section-title">Desktop Pet Overlay</span>
            <Layers size={14} className="card-header-glyph" />
          </div>

          <div
            className="inspector-toggle-row"
            onClick={() => setPetAlwaysOnTop(!petAlwaysOnTop)}
            style={{ cursor: 'pointer' }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setPetAlwaysOnTop(!petAlwaysOnTop);
              }
            }}
          >
            <div className="toggle-label-group">
              <span className="toggle-headline">Always on Top</span>
              <span className="toggle-subcaption">Stay visible across all apps & windows</span>
            </div>
            <button
              type="button"
              className={`apple-switch-pill ${petAlwaysOnTop ? 'switch-active' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                setPetAlwaysOnTop(!petAlwaysOnTop);
              }}
              title="Toggle pet visibility above all applications"
              aria-label="Toggle pet always on top"
              aria-pressed={petAlwaysOnTop}
            >
              <div className="switch-thumb" />
            </button>
          </div>

          <div className="quick-action-tiles-grid" style={{ marginTop: '2px' }}>
            <button
              className="action-tile-btn"
              onClick={() => togglePetVisible(!petVisible)}
              title={petVisible ? 'Hide pet avatar from screen' : 'Show pet avatar on screen'}
            >
              {petVisible ? <EyeOff size={14} /> : <Eye size={14} />}
              <span>{petVisible ? 'Hide Pet' : 'Show Pet'}</span>
            </button>

            <button
              className="action-tile-btn"
              onClick={handleResetPos}
              title="Reset pet to default bottom-right position"
            >
              {resetNotice ? (
                <>
                  <CheckCircle2 size={14} className="export-ok-icon" />
                  <span>Reset!</span>
                </>
              ) : (
                <>
                  <RotateCcw size={14} />
                  <span>Reset Pos</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
};
