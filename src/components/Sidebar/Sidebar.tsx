import React, { useState } from 'react';
import { Search, Plus, Trash2, Edit2, Check, MessageSquare, Database, Settings, X } from 'lucide-react';
import { useChatStore, getAppStateDisplayInfo } from '../../store/useChatStore';
import './Sidebar.css';

export const Sidebar: React.FC = () => {
  const {
    conversations,
    activeConvId,
    selectConversation,
    createConversation,
    deleteConversation,
    renameConversation,
    searchQuery,
    setSearchQuery,
    setSettingsOpen,
    isSidebarOpen,
    companionProfile,
    voiceStatus,
    modelInfo,
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

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  if (!isSidebarOpen) {
    return null;
  }

  const startRename = (id: string, currentTitle: string) => {
    setEditingId(id);
    setEditTitle(currentTitle);
  };

  const cancelRename = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const handleSaveRename = async (id: string) => {
    const trimmed = editTitle.trim();
    if (trimmed) {
      await renameConversation(id, trimmed);
    }
    setEditingId(null);
  };

  const filtered = (conversations || []).filter((c) =>
    (c?.title || 'New Chat').toLowerCase().includes((searchQuery || '').toLowerCase())
  );

  const formatTimestamp = (iso: string) => {
    if (!iso) return '';
    try {
      const date = new Date(iso);
      const now = new Date();
      if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  return (
    <aside className="apple-sidebar">
      {/* Top: Search & New Chat */}
      <div className="sidebar-header-section">
        {/* Spotlight-style Search Input */}
        <div className="spotlight-search-box">
          <Search size={14} className="search-glyph" />
          <input
            type="text"
            className="search-input-field"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              className="search-clear-btn"
              onClick={() => setSearchQuery('')}
              title="Clear search"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* Apple Primary Action Button */}
        <button
          className="btn-apple-new-chat"
          onClick={() => createConversation('New Chat')}
          title="Create New Conversation"
        >
          <Plus size={16} />
          <span>New Chat</span>
        </button>
      </div>

      {/* Middle: Conversation List (macOS Notes Style) */}
      <div className="conversation-scroll-viewport">
        {filtered.length === 0 ? (
          <div className="empty-conversations-state">
            <div className="empty-icon-frame">
              <MessageSquare size={20} />
            </div>
            <span className="empty-text">No conversations</span>
            <span className="empty-subtext">Click 'New Chat' to start one</span>
          </div>
        ) : (
          <div className="conversations-stack">
            {filtered.map((conv) => {
              const isActive = conv.id === activeConvId;
              const isEditing = editingId === conv.id;

              if (isEditing) {
                return (
                  <div
                    key={conv.id}
                    className={`conversation-row-item ${isActive ? 'row-active' : ''} row-editing`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="conv-icon-frame">
                      <MessageSquare size={15} />
                    </div>
                    <form
                      className="conv-rename-form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        handleSaveRename(conv.id);
                      }}
                    >
                      <input
                        type="text"
                        className="conv-rename-input"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') cancelRename();
                        }}
                        autoFocus
                        maxLength={60}
                        placeholder="Rename chat..."
                      />
                      <div className="conv-rename-actions">
                        <button
                          type="submit"
                          className="conv-action-btn conv-save-btn"
                          title="Save title"
                          aria-label="Save title"
                        >
                          <Check size={12} />
                        </button>
                        <button
                          type="button"
                          className="conv-action-btn conv-cancel-btn"
                          onClick={cancelRename}
                          title="Cancel"
                          aria-label="Cancel"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    </form>
                  </div>
                );
              }

              return (
                <div
                  key={conv.id}
                  className={`conversation-row-item ${isActive ? 'row-active' : ''}`}
                  onClick={() => selectConversation(conv.id)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') selectConversation(conv.id);
                  }}
                >
                  <div className="conv-icon-frame">
                    <MessageSquare size={15} />
                  </div>

                  <div
                    className="conv-details-col"
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      startRename(conv.id, conv.title);
                    }}
                  >
                    <div className="conv-title-bar">
                      <span className="conv-item-title" title={`${conv.title} (Double-click to rename)`}>
                        {conv.title}
                      </span>
                      <span className="conv-time-caption">
                        {formatTimestamp(conv.updated_at)}
                      </span>
                    </div>

                    <div className="conv-sub-bar">
                      <span className="conv-meta-badge">
                        {conv.message_count > 0
                          ? `${conv.message_count} messages`
                          : 'New conversation'}
                      </span>
                    </div>
                  </div>

                  {/* Contextual Action Buttons */}
                  <div className="conv-row-actions">
                    <button
                      className="conv-action-btn conv-edit-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        startRename(conv.id, conv.title);
                      }}
                      title="Rename conversation"
                      aria-label="Rename conversation"
                    >
                      <Edit2 size={12} />
                    </button>
                    <button
                      className="conv-action-btn conv-trash-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteConversation(conv.id);
                      }}
                      title="Delete conversation"
                      aria-label="Delete conversation"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Bottom Footer: Minimalist macOS Status Bar */}
      <div className="sidebar-bottom-bar">
        <div className="sidebar-status-chip" title={`${displayInfo.headline} (${displayInfo.badgeText})`}>
          <span className={`status-apple-dot ${displayInfo.dotClass}`} />
          <span className="sidebar-status-text">{displayInfo.badgeText}</span>
        </div>

        <div className="bottom-meta-chip">
          <Database size={13} className="chip-icon" />
          <span>{conversations.length} {conversations.length === 1 ? 'chat' : 'chats'}</span>
        </div>

        <button
          className="bottom-settings-trigger"
          onClick={() => setSettingsOpen(true)}
          title="Application Settings"
          aria-label="Application Settings"
        >
          <Settings size={14} />
        </button>
      </div>
    </aside>
  );
};
