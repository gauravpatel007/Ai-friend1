import React, { useState } from 'react';
import {
  Mic,
  MicOff,
  Plus,
  Settings,
  PanelLeft,
  PanelRight,
  Radio,
  Edit2,
  Check,
  X,
  MessageSquare,
  Film,
  Moon,
  VolumeX,
  Loader2,
  Sun,
  Activity,
} from 'lucide-react';
import { useChatStore, getAppStateDisplayInfo } from '../../store/useChatStore';
import './Header.css';

export const Header: React.FC = () => {
  const {
    companionProfile,
    modelInfo,
    voiceStatus,
    toggleVoice,
    setVoicePortalOpen,
    createConversation,
    setSettingsOpen,
    isSidebarOpen,
    toggleSidebar,
    isRightPanelOpen,
    toggleRightPanel,
    conversations,
    activeConvId,
    renameConversation,
    activeTab,
    setActiveTab,
    wake,
    sleep,
    unmute,
    isPerformancePanelOpen,
    togglePerformancePanel,
  } = useChatStore();

  const effectiveAppState = useChatStore((s) => s.getEffectiveAppState());
  const isSleeping = Boolean(voiceStatus.is_sleeping || companionProfile.state === 'sleeping' || companionProfile.operational_state === 'sleeping');
  const isMuted = Boolean(voiceStatus.is_muted || companionProfile.operational_state === 'muted');
  const displayInfo = getAppStateDisplayInfo(
    effectiveAppState,
    companionProfile.name || 'Buddy',
    modelInfo.active_model,
    isSleeping,
    isMuted
  );

  const activeConv = (conversations || []).find((c) => c.id === activeConvId);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');

  const handleStartEditTitle = () => {
    if (!activeConv) return;
    setTitleDraft(activeConv.title || 'New Chat');
    setIsEditingTitle(true);
  };

  const handleSaveTitle = () => {
    if (!activeConv) return;
    const trimmed = titleDraft.trim();
    if (trimmed && trimmed !== activeConv.title) {
      renameConversation(activeConv.id, trimmed);
    }
    setIsEditingTitle(false);
  };

  const isVoiceActive = voiceStatus.mode !== 'off' && !isSleeping;
  const [isWaking, setIsWaking] = useState(false);

  const handleVoiceIslandClick = async () => {
    if (isSleeping) {
      if (isWaking) return;
      setIsWaking(true);
      try {
        await wake();
      } catch (err) {
        console.error('Failed to wake companion:', err);
      } finally {
        setTimeout(() => setIsWaking(false), 600);
      }
      return;
    }
    if (isMuted) {
      try {
        await unmute();
      } catch (err) {
        console.error('Failed to unmute companion:', err);
      }
      return;
    }
    if (!isVoiceActive) {
      try {
        await toggleVoice();
      } catch (err) {
        console.error('Failed to toggle voice:', err);
      }
    }
    setVoicePortalOpen(true);
  };

  return (
    <div className="app-toolbar">
      {/* Left: Sidebar Toggle, Avatar & Status */}
      <div className="toolbar-left">
        <button
          className={`toolbar-icon-btn ${isSidebarOpen ? 'active' : ''}`}
          onClick={toggleSidebar}
          title={isSidebarOpen ? 'Hide Sidebar' : 'Show Sidebar'}
          aria-label="Toggle Sidebar"
        >
          <PanelLeft size={16} />
        </button>

        <div className="toolbar-companion-chip">
          <div className="companion-avatar-frame">
            <img
              src={`/assets/characters/robot/${companionProfile.state || 'idle'}.png`}
              onError={(e) => {
                (e.target as HTMLImageElement).src = '/assets/characters/robot/idle.png';
              }}
              alt="AI Companion"
              className="companion-avatar-img"
            />
            <span className="avatar-live-indicator" />
          </div>

          <div className="companion-meta">
            <span className="companion-title">{companionProfile.name || 'Buddy'}</span>
            <div className="companion-status-row">
              <span className={`status-live-dot ${displayInfo.dotClass}`} />
              <span className="status-caption">
                {displayInfo.headline} • {displayInfo.badgeText}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Center: Destination Switcher, Dynamic Voice Island & Active Chat Title */}
      <div className="toolbar-center">
        {/* Apple macOS Segmented Workspace Switcher */}
        <div className="nav-segmented-control" role="tablist" aria-label="Main Workspaces">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'chat'}
            className={`nav-segment-btn ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
            title="Switch to AI Companion Chat"
          >
            <MessageSquare size={13} />
            <span>Companion</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'movies'}
            className={`nav-segment-btn ${activeTab === 'movies' ? 'active' : ''}`}
            onClick={() => setActiveTab('movies')}
            title="Switch to Movie Hub Discovery"
          >
            <Film size={13} />
            <span>Movie Hub</span>
          </button>
        </div>

        {/* Active Chat Title Chip with Inline Rename (Companion Tab) */}
        {activeTab === 'chat' && activeConv && (
          <div className="active-chat-title-chip">
            {isEditingTitle ? (
              <form
                className="title-edit-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSaveTitle();
                }}
              >
                <input
                  type="text"
                  className="title-edit-input"
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') setIsEditingTitle(false);
                  }}
                  autoFocus
                  maxLength={60}
                  placeholder="Chat title..."
                />
                <button type="submit" className="title-btn-save" title="Save Title">
                  <Check size={12} />
                </button>
                <button
                  type="button"
                  className="title-btn-cancel"
                  onClick={() => setIsEditingTitle(false)}
                  title="Cancel"
                >
                  <X size={12} />
                </button>
              </form>
            ) : (
              <div
                className="title-display-box"
                onClick={handleStartEditTitle}
                title="Click to rename chat title"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleStartEditTitle();
                }}
              >
                <span className="active-chat-title-text">{activeConv.title || 'New Chat'}</span>
                <span className="title-edit-icon-badge" title="Rename Title">
                  <Edit2 size={11} />
                </span>
              </div>
            )}
          </div>
        )}

        <button
          className={`voice-island-pill ${isSleeping ? 'island-sleeping' : isMuted ? 'island-muted' : isVoiceActive ? 'island-active' : ''} ${isWaking ? 'island-waking' : ''}`}
          onClick={handleVoiceIslandClick}
          disabled={isWaking}
          title={
            isWaking
              ? 'Waking up companion...'
              : isSleeping
              ? `Sleeping — Click to Wake ${companionProfile.name || 'Buddy'}`
              : isMuted
              ? 'Muted — Click to unmute'
              : isVoiceActive
              ? 'Voice Active — Click to expand Apple Voice Portal'
              : 'Voice Off — Click to start voice conversation'
          }
          aria-label={isSleeping ? 'Wake Companion' : isMuted ? 'Unmute' : 'Voice Mode'}
        >
          <div className="island-icon-col">
            {isWaking ? (
              <Loader2 size={13} className="mic-svg spinner-waking" />
            ) : isSleeping ? (
              <Moon size={14} className="mic-svg sleeping-icon" />
            ) : isMuted ? (
              <VolumeX size={14} className="mic-svg muted-icon" />
            ) : isVoiceActive ? (
              <Mic size={14} className="mic-svg active-pulse" />
            ) : (
              <MicOff size={14} className="mic-svg" />
            )}
          </div>

          <span className="island-label">
            {isWaking
              ? 'Waking Up...'
              : isSleeping
              ? 'Sleeping'
              : isMuted
              ? 'Muted'
              : isVoiceActive
              ? 'Voice Active'
              : 'Voice Off'}
          </span>

          {!isSleeping && !isMuted && isVoiceActive && !isWaking && (
            <div className="siri-audio-wave" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
            </div>
          )}
        </button>
      </div>

      {/* Right: Actions & Panel Toggle */}
      <div className="toolbar-right">
        <button
          className="toolbar-voice-btn"
          onClick={() => setVoicePortalOpen(true)}
          title="Open Voice Window (Dedicated Siri & Audio Experience)"
          aria-label="Open Voice Window"
        >
          <Radio size={13} className="voice-btn-pulse" />
          <span>Voice Window</span>
        </button>

        <button
          className="toolbar-pill-btn"
          onClick={() => createConversation('New Chat')}
          title="Start a new chat"
        >
          <Plus size={15} />
          <span>New Chat</span>
        </button>

        <button
          className={`toolbar-icon-btn ${isPerformancePanelOpen ? 'active' : ''}`}
          onClick={togglePerformancePanel}
          title="Developer Response-Time Monitoring Panel"
          aria-label="Toggle Performance Monitor"
        >
          <Activity size={16} />
        </button>

        <button
          className="toolbar-icon-btn"
          onClick={() => setSettingsOpen(true)}
          title="Application Settings"
          aria-label="Open Settings"
        >
          <Settings size={16} />
        </button>

        <button
          className={`toolbar-icon-btn ${isRightPanelOpen ? 'active' : ''}`}
          onClick={toggleRightPanel}
          title={isRightPanelOpen ? 'Hide Inspector' : 'Show Inspector'}
          aria-label="Toggle Inspector Panel"
        >
          <PanelRight size={16} />
        </button>
      </div>
    </div>
  );
};
