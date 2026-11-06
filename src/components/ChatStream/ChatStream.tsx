import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Square,
  Plus,
  Smile,
  Copy,
  Check,
  RotateCcw,
  ThumbsUp,
  ThumbsDown,
  Sparkles,
  Mic,
  MicOff,
  AlertCircle,
  Moon,
  Pencil,
  Trash2,
  FileText,
  FileSpreadsheet,
  Music,
  Film,
  File as FileIcon,
  X,
  Image as ImageIcon,
  Loader2,
} from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { ChatAttachment, AttachmentCategory } from '../../types';
import * as api from '../../api/http';
import { EmojiPicker } from './EmojiPicker';
import './ChatStream.css';

export const ChatStream: React.FC = () => {
  const {
    messages,
    sendMessage,
    cancelGeneration,
    deleteMessage,
    editMessage,
    retryMessage,
    isThinking,
    isStreaming,
    companionProfile,
    voiceStatus,
    voiceError,
    voiceErrorInfo,
    clearVoiceError,
    executeRecoveryAction,
    toggleVoice,
    startPushToTalk,
    stopPushToTalk,
    setVoicePortalOpen,
    lastUserPrompt,
    diagnosticMode,
    diagnosticStatus,
    interimTranscript,
    setMessageFeedback,
    wake,
  } = useChatStore();

  const effectiveAppState = useChatStore((s) => s.getEffectiveAppState());
  const streamingMessageId = useChatStore((s) => s.streamingMessageId);

  const isSleeping = Boolean(voiceStatus.is_sleeping || companionProfile.state === 'sleeping' || companionProfile.operational_state === 'sleeping');
  const isListening = voiceStatus.mode !== 'off' && !voiceStatus.is_muted && !isSleeping;
  const isPtt = voiceStatus.mode === 'push_to_talk';
  const companionDisplayName = companionProfile.name || 'Buddy';

  const getPlaceholder = () => {
    if (isSleeping) return `Sleeping — say 'Hey ${companionDisplayName}' or type to chat...`;
    if (interimTranscript) return `Hearing you: "${interimTranscript}..."`;
    if (voiceStatus.mode === 'continuous') return 'Listening continuously... Speak aloud or type...';
    if (voiceStatus.mode === 'push_to_talk') return 'Hold mic to speak, or type a message...';
    if (voiceStatus.mode === 'listening') return 'Listening to you speak...';
    if (voiceStatus.mode === 'processing') return 'Processing speech...';
    return `Type a message to ${companionDisplayName}...`;
  };

  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [copiedId, setCopiedId] = useState<number | string | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');
  const [isEmojiPickerOpen, setIsEmojiPickerOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const emojiBtnRef = useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const getAttachmentCategoryIcon = (category: AttachmentCategory) => {
    switch (category) {
      case 'image':
        return <ImageIcon size={15} />;
      case 'document':
        return <FileText size={15} />;
      case 'spreadsheet':
        return <FileSpreadsheet size={15} />;
      case 'audio':
        return <Music size={15} />;
      case 'video':
        return <Film size={15} />;
      default:
        return <FileIcon size={15} />;
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (!bytes || bytes <= 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFilesSelect = async (files: FileList | File[]) => {
    const fileList = Array.from(files);
    if (fileList.length === 0) return;

    setUploadError(null);

    // Limit check: maximum 10 attachments total
    if (attachments.length + fileList.length > 10) {
      setUploadError('Maximum 10 attachments allowed at a time.');
      setTimeout(() => setUploadError(null), 4000);
      return;
    }

    // Size limit check: 25MB per file, 100MB total
    const MAX_PER_FILE = 25 * 1024 * 1024;
    const MAX_TOTAL = 100 * 1024 * 1024;

    let currentTotal = attachments.reduce((sum, a) => sum + (a.size || 0), 0);
    for (const file of fileList) {
      if (file.size > MAX_PER_FILE) {
        setUploadError(`"${file.name}" exceeds the 25MB limit.`);
        setTimeout(() => setUploadError(null), 4000);
        return;
      }
      currentTotal += file.size;
      if (currentTotal > MAX_TOTAL) {
        setUploadError('Total attachment size exceeds the 100MB limit.');
        setTimeout(() => setUploadError(null), 4000);
        return;
      }
    }

    setIsUploading(true);

    // Optimistic previews for immediate visual confirmation
    const optimisticList: ChatAttachment[] = fileList.map((file) => {
      const ext = (file.name.split('.').pop() || '').toLowerCase();
      let cat: AttachmentCategory = 'document';
      if (['png', 'jpg', 'jpeg', 'webp'].includes(ext) || file.type.startsWith('image/')) cat = 'image';
      else if (['csv', 'xlsx'].includes(ext)) cat = 'spreadsheet';
      else if (['wav', 'mp3', 'm4a'].includes(ext) || file.type.startsWith('audio/')) cat = 'audio';
      else if (['mp4', 'mov'].includes(ext) || file.type.startsWith('video/')) cat = 'video';

      const tempAtt: ChatAttachment = {
        id: `temp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        name: file.name,
        size: file.size,
        size_formatted: formatFileSize(file.size),
        type: file.type || 'application/octet-stream',
        extension: ext,
        category: cat,
        status: 'uploading',
      };

      if (cat === 'image') {
        try {
          tempAtt.dataUrl = URL.createObjectURL(file);
        } catch {}
      }

      return tempAtt;
    });

    setAttachments((prev) => [...prev, ...optimisticList]);

    try {
      const res = await api.uploadMultipleFiles(fileList);
      if (res && res.attachments && res.attachments.length > 0) {
        setAttachments((prev) => {
          const kept = prev.filter((p) => !optimisticList.some((opt) => opt.id === p.id));
          return [...kept, ...res.attachments];
        });
      }
    } catch (err: any) {
      console.error('File upload error:', err);
      setUploadError(err.message || 'Failed to upload attachments.');
      setTimeout(() => setUploadError(null), 5000);
      setAttachments((prev) => prev.filter((p) => !optimisticList.some((opt) => opt.id === p.id)));
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleRemoveAttachment = (index: number) => {
    const target = attachments[index];
    if (target && target.id && !target.id.startsWith('temp_')) {
      api.deleteUpload(target.id).catch((e) => console.warn('Delete upload note:', e));
    }
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleClearAllAttachments = () => {
    for (const att of attachments) {
      if (att.id && !att.id.startsWith('temp_')) {
        api.deleteUpload(att.id).catch((e) => console.warn('Delete upload note:', e));
      }
    }
    setAttachments([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const hasActiveStreamingMessage = messages.some((m) => (streamingMessageId && m.id === streamingMessageId) || m.status === 'streaming');
  const showThinkingIndicator = effectiveAppState === 'THINKING' && (isThinking || hasActiveStreamingMessage);
  const isGenerating = effectiveAppState === 'THINKING' || isStreaming;

  const handleSelectEmoji = (emoji: string) => {
    const textarea = inputRef.current;
    if (!textarea) {
      setInput((prev) => prev + emoji);
      return;
    }

    const start = textarea.selectionStart ?? input.length;
    const end = textarea.selectionEnd ?? input.length;

    const before = input.slice(0, start);
    const after = input.slice(end);
    const nextVal = before + emoji + after;

    setInput(nextVal);

    requestAnimationFrame(() => {
      textarea.focus();
      const newPos = start + emoji.length;
      textarea.setSelectionRange(newPos, newPos);

      // Auto-grow height if needed
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    });
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, showThinkingIndicator, isStreaming]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = () => {
    const trimmed = input.trim();
    if ((!trimmed && attachments.length === 0) || isGenerating || isUploading) return;
    sendMessage(trimmed, false, attachments.length > 0 ? attachments : undefined);
    setInput('');
    setAttachments([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    setIsEmojiPickerOpen(false);
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape' && isGenerating) {
      e.preventDefault();
      cancelGeneration();
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCopy = (id: number | string, text: string) => {
    const textToCopy = (text || '').trim();
    if (!textToCopy) return;

    // 1. Synchronously execute execCommand('copy') while user click event is live (retaining active user gesture in Chromium)
    try {
      const textArea = document.createElement('textarea');
      textArea.value = textToCopy;
      textArea.setAttribute('readonly', '');
      textArea.style.position = 'fixed';
      textArea.style.top = '0';
      textArea.style.left = '0';
      textArea.style.width = '2em';
      textArea.style.height = '2em';
      textArea.style.padding = '0';
      textArea.style.border = 'none';
      textArea.style.outline = 'none';
      textArea.style.boxShadow = 'none';
      textArea.style.background = 'transparent';
      textArea.style.opacity = '0.001';
      textArea.style.zIndex = '-1';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      textArea.setSelectionRange(0, textToCopy.length);
      document.execCommand('copy');
      document.body.removeChild(textArea);
    } catch (e) {
      console.warn('execCommand copy note:', e);
    }

    // 2. Modern async Clipboard API
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(textToCopy).catch((e) => {
        console.debug('Clipboard writeText note:', e);
      });
    }

    // 3. Qt WebEngine custom URL pybridge (triggers on main Qt thread in CustomWebPage)
    try {
      const bridgeFrame = document.createElement('iframe');
      bridgeFrame.style.display = 'none';
      bridgeFrame.src = `pybridge://copy?text=${encodeURIComponent(textToCopy)}`;
      document.body.appendChild(bridgeFrame);
      setTimeout(() => {
        try {
          document.body.removeChild(bridgeFrame);
        } catch {}
      }, 300);
    } catch {}

    // 4. Native backend clipboard REST API (Windows ctypes 64-bit safe)
    api.copyToClipboard(textToCopy).catch(() => {});

    // Instant visual feedback with green checkmark
    setCopiedId(id);
    setTimeout(() => {
      setCopiedId((curr) => (curr === id || String(curr) === String(id) ? null : curr));
    }, 2000);
  };

  const handleFeedback = (
    id: number,
    currentFeedback: 'like' | 'dislike' | null | undefined,
    target: 'like' | 'dislike'
  ) => {
    const nextFeedback = currentFeedback === target ? null : target;
    setMessageFeedback(id, nextFeedback);
  };

  const startEditing = (msg: { id: number; content: string; role?: string }) => {
    if (msg.role === 'assistant') return;
    setEditingMessageId(msg.id);
    setEditContent(msg.content);
  };

  const cancelEditing = () => {
    setEditingMessageId(null);
    setEditContent('');
  };

  const handleSaveEdit = async (id: number) => {
    const trimmed = editContent.trim();
    if (!trimmed) return;
    await editMessage(id, trimmed);
    cancelEditing();
  };

  const handleSaveAndRetry = async (assistantMsgId: number) => {
    const trimmed = editContent.trim();
    if (trimmed) {
      await editMessage(assistantMsgId, trimmed);
    }
    cancelEditing();
    await retryMessage(assistantMsgId);
  };

  const handleSaveUserAndRetry = async (userMsgId: number) => {
    const trimmed = editContent.trim();
    if (trimmed) {
      await editMessage(userMsgId, trimmed);
    }
    cancelEditing();
    await retryMessage(userMsgId, trimmed);
  };

  const handleDelete = async (id: number) => {
    if (window.confirm('Delete this message and its response?')) {
      await deleteMessage(id, true);
    }
  };

  const formatMessageTime = (iso: string) => {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const todayDateStr = new Date().toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });

  const promptSuggestions = [
    'How do local AI models work?',
    'Brainstorm productivity habits',
    'Write a concise summary',
  ];

  return (
    <section className="apple-chat-stream">
      {/* Date Header Badge */}
      <div className="stream-date-header">
        <span className="apple-date-pill">{todayDateStr}</span>
      </div>

      {/* Messages Scroll Area */}
      <div className="stream-messages-viewport" ref={scrollRef}>
        <div className="stream-centered-column">
          {messages.length === 0 ? (
            /* Apple Intelligence Hero State */
            <div className="apple-hero-container">
              <div className="hero-avatar-ambient">
                <img
                  src="/assets/characters/robot/happy.png"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = '/assets/characters/robot/idle.png';
                  }}
                  alt={companionDisplayName}
                  className="hero-avatar-media"
                />
              </div>

              <h2 className="hero-display-title">How can I help you today?</h2>
              <p className="hero-description">
                Your private AI companion powered by local Ollama models.
                Fast, responsive, and completely offline.
              </p>

              {/* Prompt Suggestions */}
              <div className="hero-suggestions-row">
                {promptSuggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    className="suggestion-pill"
                    onClick={() => {
                      setInput(suggestion);
                      inputRef.current?.focus();
                    }}
                  >
                    <span>{suggestion}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => {
              const isAi = msg.role === 'assistant';
              const isEditing = editingMessageId === msg.id;
              return (
                <div
                  key={msg.id || `${msg.role}-${msg.created_at}`}
                  className={`message-thread-item ${isAi ? 'thread-ai' : 'thread-user'}`}
                >
                  {isAi && (
                    <div className="message-avatar-wrap">
                      <img
                        src={`/assets/characters/robot/${companionProfile.state || 'idle'}.png`}
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = '/assets/characters/robot/idle.png';
                        }}
                        alt={companionDisplayName}
                        className="msg-avatar-media"
                      />
                    </div>
                  )}

                  <div className="message-body-wrap">
                    <div className="message-meta-row">
                      <span className="msg-sender-name">{isAi ? companionDisplayName : 'You'}</span>
                      <span className="msg-timestamp">{formatMessageTime(msg.created_at)}</span>
                    </div>

                    <div className={`apple-bubble ${isAi ? 'bubble-assistant' : 'bubble-user'} ${msg.status === 'error' ? 'bubble-error' : ''} ${isEditing ? 'bubble-editing' : ''}`}>
                      {isEditing ? (
                        <div className="message-edit-box">
                          <textarea
                            className="message-edit-textarea"
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Escape') {
                                cancelEditing();
                              } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                                e.preventDefault();
                                handleSaveEdit(msg.id);
                              }
                            }}
                            rows={Math.max(2, Math.min(8, editContent.split('\n').length + 1))}
                            autoFocus
                          />
                          <div className="message-edit-actions">
                            <button
                              type="button"
                              className="msg-edit-btn msg-edit-cancel"
                              onClick={cancelEditing}
                              title="Cancel editing (Esc)"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              className="msg-edit-btn msg-edit-save"
                              onClick={() => handleSaveEdit(msg.id)}
                              title="Save changes (Ctrl+Enter)"
                            >
                              Save
                            </button>
                            {isAi ? (
                              <button
                                type="button"
                                className="msg-edit-btn msg-edit-retry"
                                onClick={() => handleSaveAndRetry(msg.id)}
                                title="Save changes and re-generate only this response"
                              >
                                <RotateCcw size={11} /> Save &amp; Retry
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="msg-edit-btn msg-edit-retry"
                                onClick={() => handleSaveUserAndRetry(msg.id)}
                                title="Save prompt and re-generate response"
                              >
                                <RotateCcw size={11} /> Save &amp; Regenerate
                              </button>
                            )}
                          </div>
                        </div>
                      ) : msg.status === 'error' ? (
                        <div className="bubble-error-text">
                          <div className="bubble-error-header">
                            <AlertCircle size={14} className="bubble-error-icon" />
                            <span>Response Error</span>
                          </div>
                          <p className="bubble-error-message">{msg.content || 'An error occurred while generating response.'}</p>
                          <div className="bubble-error-actions-row" style={{ display: 'flex', gap: '8px', marginTop: '8px', flexWrap: 'wrap' }}>
                            <button
                              className="bubble-retry-btn"
                              onClick={() => {
                                if (msg.recovery_action && msg.recovery_action !== 'retry_request') {
                                  executeRecoveryAction(msg.recovery_action, { messageId: msg.id, prompt: lastUserPrompt });
                                } else {
                                  retryMessage(msg.id);
                                }
                              }}
                              title="Retry response generation"
                              aria-label="Retry generation"
                            >
                              <RotateCcw size={11} /> {msg.recovery_label || 'Retry'}
                            </button>
                            {msg.recovery_action === 'start_ollama' && (
                              <button
                                className="bubble-retry-btn"
                                style={{ background: 'rgba(255, 159, 10, 0.2)', borderColor: 'rgba(255, 159, 10, 0.4)', color: '#FF9F0A' }}
                                onClick={() => executeRecoveryAction('start_ollama')}
                              >
                                Start Ollama
                              </button>
                            )}
                          </div>
                        </div>
                      ) : (
                        <>
                          {msg.attachments && msg.attachments.length > 0 && (
                            <div className="bubble-attachments-container">
                              {msg.attachments.some((a) => a.category === 'image') && (
                                <div className="bubble-attachments-images">
                                  {msg.attachments
                                    .filter((a) => a.category === 'image')
                                    .map((att, i) => (
                                      <div key={att.id || i} className="bubble-attachment-image-card">
                                        <img
                                          src={
                                            att.dataUrl ||
                                            (att.thumbnail_base64
                                              ? `data:image/jpeg;base64,${att.thumbnail_base64}`
                                              : att.base64
                                              ? `data:image/png;base64,${att.base64}`
                                              : '')
                                          }
                                          alt={att.name}
                                          className="bubble-attachment-img"
                                        />
                                        <span className="bubble-attachment-img-name" title={att.name}>
                                          {att.name}
                                        </span>
                                      </div>
                                    ))}
                                </div>
                              )}
                              {msg.attachments.some((a) => a.category !== 'image') && (
                                <div className="bubble-attachments-files">
                                  {msg.attachments
                                    .filter((a) => a.category !== 'image')
                                    .map((att, i) => (
                                      <div key={att.id || i} className="bubble-attachment-file-chip">
                                        <span className={`file-chip-icon cat-${att.category}`}>
                                          {getAttachmentCategoryIcon(att.category)}
                                        </span>
                                        <div className="file-chip-info">
                                          <span className="file-chip-name" title={att.name}>
                                            {att.name}
                                          </span>
                                          <span className="file-chip-size">
                                            {att.size_formatted || formatFileSize(att.size)}
                                          </span>
                                        </div>
                                      </div>
                                    ))}
                                </div>
                              )}
                            </div>
                          )}

                          {msg.content ? (
                            <div className="bubble-markdown-text">
                              {msg.content}
                              {isAi && msg.status === 'streaming' && (
                                <span className="streaming-cursor" aria-hidden="true" />
                              )}
                              {isAi && msg.truncated && (
                                <div className="response-limit-notice" style={{ marginTop: '8px', paddingTop: '6px', borderTop: '1px solid rgba(255, 255, 255, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', fontSize: '11px', color: 'rgba(255, 255, 255, 0.55)' }}>
                                  <span>Output limit reached.</span>
                                  <button
                                    type="button"
                                    style={{ background: 'rgba(255, 255, 255, 0.08)', border: '1px solid rgba(255, 255, 255, 0.2)', borderRadius: '4px', padding: '2px 8px', color: '#E0E0FF', cursor: 'pointer', fontSize: '11px', transition: 'all 0.15s ease' }}
                                    onClick={() => sendMessage('Continue directly from where you left off. Do not repeat anything already written.')}
                                  >
                                    Continue
                                  </button>
                                </div>
                              )}
                            </div>
                          ) : isAi && msg.status === 'streaming' && !isThinking ? (
                            <div className="apple-typing-indicator" aria-label={`${companionDisplayName} is generating response...`}>
                              <span className="dot" />
                              <span className="dot" />
                              <span className="dot" />
                            </div>
                          ) : null}
                        </>
                      )}
                    </div>

                    {!isEditing && isAi && msg.content && (
                      <div className={`message-hover-toolbar ${msg.feedback ? 'has-active-feedback' : ''}`} aria-label="Message Actions">
                        <button
                          type="button"
                          className={`action-icon-pill ${copiedId === msg.id || (msg.id != null && String(copiedId) === String(msg.id)) ? 'copied-active' : ''}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(msg.id, msg.content);
                          }}
                          title={copiedId === msg.id || (msg.id != null && String(copiedId) === String(msg.id)) ? 'Copied to clipboard!' : 'Copy text'}
                          aria-label="Copy message"
                        >
                          {copiedId === msg.id || (msg.id != null && String(copiedId) === String(msg.id)) ? (
                            <Check size={12} className="copy-checked" />
                          ) : (
                            <Copy size={12} />
                          )}
                        </button>
                        <button
                          type="button"
                          className="action-icon-pill"
                          onClick={() => retryMessage(msg.id)}
                          title="Retry only this response"
                          aria-label="Retry response"
                        >
                          <RotateCcw size={12} />
                        </button>
                        <button
                          type="button"
                          className={`action-icon-pill ${msg.feedback === 'like' ? 'feedback-liked' : ''}`}
                          onClick={() => handleFeedback(msg.id, msg.feedback, 'like')}
                          title={
                            msg.feedback === 'like'
                              ? 'Liked (Click to undo)'
                              : 'Good response — AI will generate more answers like this'
                          }
                          aria-label="Thumbs Up"
                        >
                          <ThumbsUp size={12} />
                        </button>
                        <button
                          type="button"
                          className={`action-icon-pill ${msg.feedback === 'dislike' ? 'feedback-disliked' : ''}`}
                          onClick={() => handleFeedback(msg.id, msg.feedback, 'dislike')}
                          title={
                            msg.feedback === 'dislike'
                              ? 'Disliked (Click to undo)'
                              : 'Poor response — AI will avoid generating answers of this type'
                          }
                          aria-label="Thumbs Down"
                        >
                          <ThumbsDown size={12} />
                        </button>
                      </div>
                    )}

                    {!isEditing && !isAi && (
                      <div className="message-hover-toolbar user-toolbar" aria-label="Message Actions">
                        <button
                          type="button"
                          className={`action-icon-pill ${copiedId === msg.id || (msg.id != null && String(copiedId) === String(msg.id)) ? 'copied-active' : ''}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(msg.id, msg.content);
                          }}
                          title={copiedId === msg.id || (msg.id != null && String(copiedId) === String(msg.id)) ? 'Copied to clipboard!' : 'Copy text'}
                          aria-label="Copy message"
                        >
                          {copiedId === msg.id || (msg.id != null && String(copiedId) === String(msg.id)) ? (
                            <Check size={12} className="copy-checked" />
                          ) : (
                            <Copy size={12} />
                          )}
                        </button>
                        <button
                          type="button"
                          className="action-icon-pill"
                          onClick={() => startEditing(msg)}
                          title="Edit prompt"
                          aria-label="Edit prompt"
                        >
                          <Pencil size={12} />
                        </button>
                        <button
                          type="button"
                          className="action-icon-pill delete-pill"
                          onClick={() => handleDelete(msg.id)}
                          title="Delete prompt and response"
                          aria-label="Delete message"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {/* Apple Intelligence Thinking Indicator */}
          {showThinkingIndicator && (
            <div className="message-thread-item thread-ai thinking-thread-item">
              <div className="message-avatar-wrap">
                <img
                  src="/assets/characters/robot/thinking.png"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = '/assets/characters/robot/idle.png';
                  }}
                  alt="AI"
                  className="msg-avatar-media"
                />
              </div>

              <div className="message-body-wrap">
                <div className="apple-thinking-capsule">
                  <Sparkles size={14} className="thinking-sparkle" />
                  <span className="thinking-status-text">Thinking</span>
                  <div className="thinking-dots-wave">
                    <span className="wave-dot dot-1" />
                    <span className="wave-dot dot-2" />
                    <span className="wave-dot dot-3" />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Diagnostic Pipeline Ribbon (Phase 10) */}
      {diagnosticMode && (
        <div className="diagnostic-ribbon" role="status" title="Diagnostic Mode: Live voice pipeline telemetry">
          <span className="diagnostic-ribbon-tag">DIAGNOSTIC</span>
          <span className="diagnostic-ribbon-node">Mic: <strong>{diagnosticStatus.microphone_status}</strong></span>
          <span className="diagnostic-ribbon-dot">&bull;</span>
          <span className="diagnostic-ribbon-node">Rec: <strong>{diagnosticStatus.recording_status}</strong></span>
          {diagnosticStatus.audio_duration_sec > 0 && (
            <>
              <span className="diagnostic-ribbon-dot">&bull;</span>
              <span className="diagnostic-ribbon-node">{diagnosticStatus.audio_duration_sec.toFixed(1)}s</span>
            </>
          )}
          <span className="diagnostic-ribbon-dot">&bull;</span>
          <span className="diagnostic-ribbon-node">STT: <strong>{diagnosticStatus.transcription_status}</strong></span>
          <span className="diagnostic-ribbon-dot">&bull;</span>
          <span className="diagnostic-ribbon-node">Model: <strong>{diagnosticStatus.model_generation_status}</strong></span>
          <span className="diagnostic-ribbon-dot">&bull;</span>
          <span className="diagnostic-ribbon-node">TTS: <strong>{diagnosticStatus.tts_generation_status}</strong></span>
          <span className="diagnostic-ribbon-dot">&bull;</span>
          <span className="diagnostic-ribbon-node">Audio: <strong>{diagnosticStatus.audio_playback_status}</strong></span>
        </div>
      )}

      {/* Voice Error Notification Toast with Actionable Recovery */}
      {voiceError && (
        <div className="voice-error-toast" role="alert">
          <div className="voice-error-content">
            <MicOff size={13} className="voice-error-icon" />
            <span>{voiceError}</span>
          </div>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            {voiceErrorInfo?.recovery_action && voiceErrorInfo.recovery_action !== 'none' && (
              <button
                className="voice-error-recover-btn"
                style={{
                  background: '#007AFF',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '12px',
                  padding: '4px 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
                onClick={() => executeRecoveryAction(voiceErrorInfo.recovery_action!)}
              >
                {voiceErrorInfo.recovery_label || 'Retry'}
              </button>
            )}
            <button className="voice-error-dismiss" onClick={clearVoiceError}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Floating Apple-style Input Bar & Attachment Zone */}
      <div
        className={`stream-composer-dock ${isDragOver ? 'composer-drag-over' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragOver(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFilesSelect(e.dataTransfer.files);
          }
        }}
      >
        {/* Hidden multi-file input supporting all target categories */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          style={{ display: 'none' }}
          accept=".png,.jpg,.jpeg,.webp,.pdf,.docx,.txt,.md,.csv,.xlsx,.wav,.mp3,.m4a,.mp4,.mov,image/png,image/jpeg,image/webp,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,audio/wav,audio/mpeg,audio/mp4,audio/x-m4a,video/mp4,video/quicktime"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFilesSelect(e.target.files);
            }
          }}
        />

        {/* Attachment Error Banner */}
        {uploadError && (
          <div className="attachment-error-banner" role="alert">
            <AlertCircle size={13} className="attachment-error-icon" />
            <span>{uploadError}</span>
            <button
              type="button"
              className="attachment-error-close"
              onClick={() => setUploadError(null)}
              aria-label="Dismiss error"
            >
              <X size={12} />
            </button>
          </div>
        )}

        {/* Attachments Preview Strip */}
        {attachments.length > 0 && (
          <div className="attachments-preview-strip" aria-label="Attached files preview">
            <div className="attachments-preview-scroll">
              {attachments.map((att, idx) => (
                <div key={att.id || idx} className={`attachment-preview-card ${att.status === 'uploading' ? 'preview-uploading' : ''}`}>
                  {att.category === 'image' && (att.thumbnail_base64 || att.dataUrl) ? (
                    <div className="attachment-preview-thumbnail-wrap">
                      <img
                        src={att.thumbnail_base64 ? `data:image/jpeg;base64,${att.thumbnail_base64}` : att.dataUrl}
                        alt={att.name}
                        className="attachment-preview-thumbnail"
                      />
                    </div>
                  ) : (
                    <div className={`attachment-preview-icon-wrap cat-${att.category}`}>
                      {getAttachmentCategoryIcon(att.category)}
                    </div>
                  )}
                  <div className="attachment-preview-info">
                    <span className="attachment-preview-name" title={att.name}>
                      {att.name}
                    </span>
                    <span className="attachment-preview-size">
                      {att.size_formatted || formatFileSize(att.size)}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="attachment-preview-remove"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveAttachment(idx);
                    }}
                    title={`Remove ${att.name}`}
                    aria-label={`Remove ${att.name}`}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
              {isUploading && (
                <div className="attachment-uploading-pill">
                  <Loader2 size={13} className="spin-animation" />
                  <span>Processing...</span>
                </div>
              )}
            </div>
            {attachments.length > 1 && (
              <button
                type="button"
                className="attachment-clear-all-btn"
                onClick={handleClearAllAttachments}
                title="Clear all attachments"
              >
                Clear all
              </button>
            )}
          </div>
        )}

        {/* Apple Input Capsule */}
        <div
          className={`apple-input-capsule ${isListening ? 'capsule-listening' : ''}`}
          onClick={(e) => {
            if ((e.target as HTMLElement).tagName !== 'BUTTON' && (e.target as HTMLElement).tagName !== 'SVG') {
              inputRef.current?.focus();
            }
          }}
        >
          {/* Full Pipeline Emoji Picker Popover */}
          <EmojiPicker
            isOpen={isEmojiPickerOpen}
            onClose={() => setIsEmojiPickerOpen(false)}
            onSelectEmoji={handleSelectEmoji}
          />

          {/* '+' Add Media / Attachment Button */}
          <button
            type="button"
            className={`composer-action-btn ${attachments.length > 0 ? 'composer-action-btn-active' : ''}`}
            title="Attach media or documents (+)"
            aria-label="Add attachment"
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
          >
            <Plus size={16} />
          </button>

          <textarea
            ref={inputRef}
            className="composer-text-area"
            placeholder={getPlaceholder()}
            rows={1}
            value={input}
            autoFocus
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = 'auto';
              e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
            }}
            onKeyDown={handleKeyDown}
          />

          <button
            ref={emojiBtnRef}
            type="button"
            className={`composer-action-btn ${isEmojiPickerOpen ? 'composer-action-btn-active' : ''}`}
            title={isEmojiPickerOpen ? "Close emoji picker (Esc)" : "Insert emoji"}
            aria-label="Insert Emoji"
            aria-expanded={isEmojiPickerOpen}
            onClick={(e) => {
              e.stopPropagation();
              setIsEmojiPickerOpen((prev) => !prev);
            }}
          >
            <Smile size={16} />
          </button>

          <button
            className={`composer-action-btn ${isSleeping ? 'voice-btn-sleeping' : isListening ? 'voice-btn-active' : ''} ${isPtt ? 'voice-btn-ptt' : ''}`}
            onClick={isSleeping ? wake : isPtt ? undefined : toggleVoice}
            onMouseDown={!isSleeping && isPtt ? () => startPushToTalk() : undefined}
            onMouseUp={!isSleeping && isPtt ? () => stopPushToTalk() : undefined}
            onTouchStart={!isSleeping && isPtt ? () => startPushToTalk() : undefined}
            onTouchEnd={!isSleeping && isPtt ? () => stopPushToTalk() : undefined}
            title={
              isSleeping
                ? `Sleeping — Say 'Hey ${companionDisplayName}' or click to wake`
                : isPtt
                ? 'Push-to-Talk: Hold to speak, release to send'
                : isListening
                ? 'Voice Listening Active (Click to pause/disable)'
                : 'Turn on Voice Listening (Speak hands-free)'
            }
            aria-label="Toggle Voice Listening or Wake Companion"
          >
            {isSleeping ? <Moon size={16} /> : isListening ? <Mic size={16} /> : <MicOff size={16} />}
          </button>

          {isGenerating ? (
            <button
              className="composer-send-btn send-cancel-active"
              onClick={cancelGeneration}
              title="Stop generating (Esc)"
              aria-label="Stop generating"
            >
              <Square size={13} fill="currentColor" />
            </button>
          ) : (
            <button
              className={`composer-send-btn ${input.trim() || attachments.length > 0 ? 'send-enabled' : ''}`}
              onClick={handleSend}
              disabled={(!input.trim() && attachments.length === 0) || isUploading}
              title="Send Message (Enter)"
              aria-label="Send Message"
            >
              <Send size={15} />
            </button>
          )}
        </div>
      </div>
    </section>
  );
};
