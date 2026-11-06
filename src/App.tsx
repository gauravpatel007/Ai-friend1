import React, { useEffect } from 'react';
import { Header } from './components/Header/Header';
import { Sidebar } from './components/Sidebar/Sidebar';
import { ChatStream } from './components/ChatStream/ChatStream';
import { RightPanel } from './components/RightPanel/RightPanel';
import { MovieHubWorkspace } from './components/MovieHub/MovieHubWorkspace';
import { SettingsModal } from './components/SettingsModal/SettingsModal';
import { VoicePortal } from './components/VoicePortal/VoicePortal';
import { PerformancePanel } from './components/PerformancePanel/PerformancePanel';
import { useChatStore } from './store/useChatStore';
import './App.css';

declare global {
  interface Window {
    openChat?: () => void;
    openVoicePortal?: () => void;
    openSettings?: () => void;
    openMovieHub?: () => void;
  }
}

export const App: React.FC = () => {
  const {
    init,
    cleanup,
    activeTab,
    setActiveTab,
    isSettingsOpen,
    isVoicePortalOpen,
    setVoicePortalOpen,
    setSettingsOpen,
    isPerformancePanelOpen,
  } = useChatStore();

  useEffect(() => {
    init();

    // Register global bridge triggers for native desktop events
    window.openChat = () => {
      setActiveTab('chat');
      setVoicePortalOpen(false);
      setSettingsOpen(false);
    };

    window.openMovieHub = () => {
      setActiveTab('movies');
      setVoicePortalOpen(false);
      setSettingsOpen(false);
    };

    window.openVoicePortal = () => {
      setSettingsOpen(false);
      setVoicePortalOpen(true);
      const state = useChatStore.getState();
      if (state.voiceStatus.mode === 'off') {
        state.setVoiceMode('continuous');
      }
    };

    window.openSettings = () => {
      setVoicePortalOpen(false);
      setSettingsOpen(true);
    };

    const handleOpenChat = () => {
      setActiveTab('chat');
      setVoicePortalOpen(false);
      setSettingsOpen(false);
    };
    const handleOpenMovieHub = () => {
      setActiveTab('movies');
      setVoicePortalOpen(false);
      setSettingsOpen(false);
    };
    const handleOpenVoice = () => {
      setSettingsOpen(false);
      setVoicePortalOpen(true);
      const state = useChatStore.getState();
      if (state.voiceStatus.mode === 'off') {
        state.setVoiceMode('continuous');
      }
    };
    const handleOpenSettings = () => {
      setVoicePortalOpen(false);
      setSettingsOpen(true);
    };

    window.addEventListener('open-chat', handleOpenChat);
    window.addEventListener('open-movie-hub', handleOpenMovieHub);
    window.addEventListener('open-voice-portal', handleOpenVoice);
    window.addEventListener('open-settings', handleOpenSettings);

    return () => {
      cleanup();
      window.removeEventListener('open-chat', handleOpenChat);
      window.removeEventListener('open-movie-hub', handleOpenMovieHub);
      window.removeEventListener('open-voice-portal', handleOpenVoice);
      window.removeEventListener('open-settings', handleOpenSettings);
    };
  }, []);

  return (
    <div className="apple-window-frame">
      <Header />

      <main className="apple-main-viewport">
        {/* Destination 1: AI Companion Workspace (Sidebar, ChatStream, RightPanel) */}
        <div
          className={`companion-workspace-view ${activeTab === 'chat' ? 'workspace-active' : 'workspace-hidden'}`}
          aria-hidden={activeTab !== 'chat'}
        >
          <Sidebar />
          <ChatStream />
          <RightPanel />
        </div>

        {/* Destination 2: Movie Hub Workspace (Full-Screen Dedicated Tab) */}
        <div
          className={`movie-hub-workspace-view ${activeTab === 'movies' ? 'workspace-active' : 'workspace-hidden'}`}
          aria-hidden={activeTab !== 'movies'}
        >
          <MovieHubWorkspace />
        </div>
      </main>

      {/* Modern Apple System Settings Modal */}
      {isSettingsOpen && <SettingsModal />}

      {/* Modern Apple Voice Portal Overlay */}
      {isVoicePortalOpen && <VoicePortal />}

      {/* Developer Response-Time Monitoring Panel */}
      {isPerformancePanelOpen && <PerformancePanel />}
    </div>
  );
};

export default App;
