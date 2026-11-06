import { create } from 'zustand';
import {
  Conversation,
  Message,
  ModelInfo,
  VoiceStatus,
  CompanionProfile,
  CompanionCharacterState,
  VoiceMode,
  DiagnosticStatus,
  NavigationTab,
  PerformanceRecord,
  TextPerformanceRecord,
  VoicePerformanceRecord,
  AppState,
  VoiceErrorInfo,
  ChatAttachment,
} from '../types';
import * as api from '../api/http';
import { wsClient } from '../api/websocket';

const defaultDiagnosticStatus: DiagnosticStatus = {
  enabled: false,
  microphone_status: 'idle',
  recording_status: 'idle',
  audio_duration_sec: 0,
  audio_sample_count: 0,
  transcription_status: 'idle',
  recognized_text_available: false,
  recognized_text_preview: '',
  user_message_submission_status: 'idle',
  backend_connection_status: 'connected',
  model_generation_status: 'idle',
  assistant_response_status: 'idle',
  tts_generation_status: 'idle',
  audio_playback_status: 'idle',
  last_error: null,
  speech_recognition_latency_ms: 0,
  backend_request_latency_ms: 0,
  model_time_to_first_output_ms: 0,
  total_model_generation_ms: 0,
  tts_generation_time_ms: 0,
  time_to_first_audible_response_ms: 0,
};

let wsUnsubscribe: (() => void) | null = null;
let isStoreInitialized = false;
let generationWatchdogTimer: any = null;

function resetWatchdog(timeoutMs = 30000, onTimeout?: () => void) {
  if (generationWatchdogTimer) {
    clearTimeout(generationWatchdogTimer);
    generationWatchdogTimer = null;
  }
  if (timeoutMs > 0 && onTimeout) {
    generationWatchdogTimer = setTimeout(onTimeout, timeoutMs);
  }
}

function clearWatchdog() {
  if (generationWatchdogTimer) {
    clearTimeout(generationWatchdogTimer);
    generationWatchdogTimer = null;
  }
}

interface PendingTextTiming {
  requestId: string;
  t_user_clicks_send: number;
  t_backend_received?: number;
  t_first_token_rendered?: number;
}

let pendingTextTiming: PendingTextTiming | null = null;

export function computeEffectiveAppState(state: {
  appState?: AppState;
  isThinking?: boolean;
  isStreaming?: boolean;
  streamingMessageId?: number | null;
  messages?: Message[];
  voiceStatus?: VoiceStatus;
  voiceError?: string | null;
  interimTranscript?: string;
  currentSubtitle?: string;
  diagnosticStatus?: DiagnosticStatus;
}): AppState {
  // 1. Explicit voice/system error takes top precedence
  if (state.voiceError) {
    return 'ERROR';
  }

  // 2. Active LLM thinking/generating
  const messages = state.messages || [];
  const activeStreamingMsg = messages.find(
    (m) => (state.streamingMessageId && m.id === state.streamingMessageId) || m.status === 'streaming'
  );

  const isActivelyGenerating = Boolean(
    (state.isThinking || state.isStreaming) && (activeStreamingMsg || state.streamingMessageId)
  );

  // 3. Audio / Speech Playback (TTS is speaking)
  const isSpeaking = Boolean(
    state.currentSubtitle ||
    state.diagnosticStatus?.audio_playback_status === 'playing' ||
    state.appState === 'SPEAKING'
  ) && !isActivelyGenerating;

  if (isSpeaking) {
    return 'SPEAKING';
  }

  if (isActivelyGenerating) {
    return 'THINKING';
  }

  // 4. Speech recognition running (Whisper STT is transcribing)
  const isTranscribing = Boolean(
    state.diagnosticStatus?.transcription_status === 'transcribing' ||
    state.voiceStatus?.mode === 'processing' ||
    state.appState === 'TRANSCRIBING'
  );
  if (isTranscribing) {
    return 'TRANSCRIBING';
  }

  // 5. User speaks / microphone is listening
  const isListening = Boolean(
    state.interimTranscript ||
    state.diagnosticStatus?.recording_status === 'recording' ||
    state.voiceStatus?.mode === 'listening' ||
    state.appState === 'LISTENING'
  );
  if (isListening) {
    return 'LISTENING';
  }

  if (state.appState === 'ERROR') {
    return 'ERROR';
  }

  // 6. Default to IDLE ("Ready")
  return 'IDLE';
}

export interface AppStateDisplayInfo {
  state: AppState;
  headline: string;
  badgeText: string;
  badgeColor: string;
  detail: string;
  dotClass: string;
}

export function getAppStateDisplayInfo(
  appState: AppState,
  companionName: string = 'Buddy',
  activeModel: string = 'llama3.2:latest',
  isSleeping: boolean = false,
  isMuted: boolean = false
): AppStateDisplayInfo {
  if (isSleeping) {
    return {
      state: 'IDLE',
      headline: 'Sleeping',
      badgeText: 'Standby',
      badgeColor: '#A08CFF',
      detail: `Say 'Hey ${companionName}' or click Wake`,
      dotClass: 'dot-sleeping',
    };
  }

  if (isMuted && appState === 'IDLE') {
    return {
      state: 'IDLE',
      headline: 'Audio Muted',
      badgeText: 'Muted',
      badgeColor: '#FF9F0A',
      detail: 'Audio suppressed • Click unmute',
      dotClass: 'dot-muted',
    };
  }

  switch (appState) {
    case 'LISTENING':
      return {
        state: 'LISTENING',
        headline: "I'm listening...",
        badgeText: 'Listening',
        badgeColor: '#00E5FF',
        detail: 'Microphone active • Speak naturally',
        dotClass: 'dot-listening',
      };
    case 'TRANSCRIBING':
      return {
        state: 'TRANSCRIBING',
        headline: 'Transcribing...',
        badgeText: 'Transcribing',
        badgeColor: '#BF5AF2',
        detail: 'Local Whisper speech recognition running',
        dotClass: 'dot-transcribing',
      };
    case 'THINKING':
      return {
        state: 'THINKING',
        headline: 'Thinking...',
        badgeText: 'Generating',
        badgeColor: '#FF9F0A',
        detail: `Generating response with ${activeModel}`,
        dotClass: 'dot-thinking',
      };
    case 'SPEAKING':
      return {
        state: 'SPEAKING',
        headline: 'Speaking aloud...',
        badgeText: 'Speaking',
        badgeColor: '#30D158',
        detail: 'Synthesizing voice with local neural TTS',
        dotClass: 'dot-speaking',
      };
    case 'ERROR':
      return {
        state: 'ERROR',
        headline: 'Error occurred',
        badgeText: 'Error',
        badgeColor: '#FF3B30',
        detail: 'Attention needed • Check message or connection',
        dotClass: 'dot-error',
      };
    case 'IDLE':
    default:
      return {
        state: 'IDLE',
        headline: 'Ready to chat',
        badgeText: 'Ready',
        badgeColor: '#30D158',
        detail: `${activeModel} • Ready`,
        dotClass: 'dot-ready',
      };
  }
}

interface ChatStore {
  // State
  conversations: Conversation[];
  activeConvId: string | null;
  messages: Message[];
  appState: AppState;
  isStreaming: boolean;
  isThinking: boolean;
  streamingMessageId: number | null;
  streamingText: string;
  voiceStatus: VoiceStatus;
  companionProfile: CompanionProfile;
  modelInfo: ModelInfo;
  searchQuery: string;
  isSettingsOpen: boolean;
  settingsInitialCategory?: string;
  isVoicePortalOpen: boolean;
  isSidebarOpen: boolean;
  isRightPanelOpen: boolean;
  activeTab: NavigationTab;
  voiceError: string | null;
  voiceErrorInfo: VoiceErrorInfo | null;
  lastUserPrompt: string | null;
  interimTranscript: string;
  currentSubtitle: string;
  isPerformancePanelOpen: boolean;
  performanceHistory: PerformanceRecord[];
  latestPerformanceRecord: PerformanceRecord | null;

  // Actions
  setAppState: (state: AppState) => void;
  getEffectiveAppState: () => AppState;
  setActiveTab: (tab: NavigationTab) => void;
  toggleSidebar: () => void;
  toggleRightPanel: () => void;
  setVoicePortalOpen: (open: boolean) => void;
  toggleVoicePortal: () => void;
  togglePerformancePanel: () => void;
  setPerformancePanelOpen: (open: boolean) => void;
  clearPerformanceHistory: () => void;
  clearVoiceError: () => void;
  executeRecoveryAction: (action: string, payload?: any) => Promise<void>;
  init: () => Promise<void>;
  cleanup: () => void;
  selectConversation: (id: string) => Promise<void>;
  createConversation: (title?: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  sendMessage: (content: string, isVoice?: boolean, attachments?: ChatAttachment[]) => Promise<void>;
  cancelGeneration: () => Promise<void>;
  clearCurrentChat: () => Promise<void>;
  toggleVoice: () => Promise<void>;
  setVoiceMode: (mode: VoiceMode) => Promise<void>;
  startPushToTalk: () => Promise<void>;
  stopPushToTalk: () => Promise<void>;
  stopVoice: () => Promise<void>;
  muteVoice: (muted: boolean) => Promise<void>;
  testVoice: (text?: string, profileId?: string, language?: string) => Promise<void>;
  previewVoice: (profileId: string, language?: string, text?: string) => Promise<void>;
  selectModel: (model: string) => Promise<void>;
  setVoiceEngine: (engine: string) => Promise<void>;
  setVoiceSpeed: (speed: number) => Promise<void>;
  setVoiceVolume: (volume: number) => Promise<void>;
  setSearchQuery: (q: string) => void;
  setSettingsOpen: (open: boolean, category?: string) => void;
  openSettings: (category?: string) => void;
  setPetAlwaysOnTop: (alwaysOnTop: boolean) => Promise<void>;
  togglePetVisible: (visible: boolean) => Promise<void>;
  resetPetPosition: () => Promise<void>;
  petAlwaysOnTop: boolean;
  petVisible: boolean;
  diagnosticMode: boolean;
  diagnosticStatus: DiagnosticStatus;
  setDiagnosticMode: (enabled: boolean) => Promise<void>;
  setMessageFeedback: (messageId: number, feedback: 'like' | 'dislike' | null) => Promise<void>;
  deleteMessage: (messageId: number, pair?: boolean) => Promise<void>;
  editMessage: (messageId: number, content: string) => Promise<void>;
  retryMessage: (messageId: number, prompt?: string) => Promise<void>;
  sleep: () => Promise<void>;
  wake: () => Promise<void>;
  mute: () => Promise<void>;
  unmute: () => Promise<void>;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  conversations: [],
  activeConvId: null,
  messages: [],
  appState: 'IDLE',
  isStreaming: false,
  isThinking: false,
  streamingMessageId: null,
  streamingText: '',
  voiceStatus: { mode: 'off', is_muted: false, tts_enabled: true },
  companionProfile: {
    name: (typeof window !== 'undefined' && (window as any).__INITIAL_COMPANION_NAME__) || 'Buddy',
    personality: 'friendly',
    state: 'idle',
    model: 'llama3.2:latest',
  },
  modelInfo: {
    active_model: 'llama3.2:latest',
    available_models: ['llama3.2:latest'],
    is_online: true,
  },
  petAlwaysOnTop: true,
  petVisible: true,
  searchQuery: '',
  isSettingsOpen: false,
  settingsInitialCategory: undefined,
  isVoicePortalOpen: false,
  isSidebarOpen: true,
  isRightPanelOpen: true,
  activeTab: 'chat',
  voiceError: null,
  voiceErrorInfo: null,
  lastUserPrompt: null,
  interimTranscript: '',
  currentSubtitle: '',
  diagnosticMode: false,
  diagnosticStatus: defaultDiagnosticStatus,
  isPerformancePanelOpen: false,
  performanceHistory: [],
  latestPerformanceRecord: null,

  setAppState: (state: AppState) => set({ appState: state }),
  getEffectiveAppState: () => computeEffectiveAppState(get()),
  setActiveTab: (tab: NavigationTab) => set({ activeTab: tab }),
  toggleSidebar: () => set((s) => ({ isSidebarOpen: !s.isSidebarOpen })),
  toggleRightPanel: () => set((s) => ({ isRightPanelOpen: !s.isRightPanelOpen })),
  setVoicePortalOpen: (open: boolean) => set({ isVoicePortalOpen: open }),
  toggleVoicePortal: () => set((s) => ({ isVoicePortalOpen: !s.isVoicePortalOpen })),
  togglePerformancePanel: () => set((s) => ({ isPerformancePanelOpen: !s.isPerformancePanelOpen })),
  setPerformancePanelOpen: (open: boolean) => set({ isPerformancePanelOpen: open }),
  clearPerformanceHistory: () => set({ performanceHistory: [], latestPerformanceRecord: null }),
  clearVoiceError: () => set((s) => ({
    voiceError: null,
    voiceErrorInfo: null,
    appState: s.appState === 'ERROR' ? 'IDLE' : s.appState,
  })),
  executeRecoveryAction: async (action: string, payload?: any) => {
    try {
      console.log('[Recovery] Executing recovery action:', action, payload);
      if (action === 'open_settings' || action === 'open_privacy_settings') {
        get().openSettings('voice');
      } else if (action === 'retry_voice' || action === 'retry_device') {
        await api.executeRecoveryAction('retry_voice', payload);
        get().clearVoiceError();
      } else if (action === 'start_ollama') {
        await api.executeRecoveryAction('start_ollama', payload);
      } else if (action === 'listen_again') {
        await api.executeRecoveryAction('listen_again', payload);
        get().clearVoiceError();
      } else if (action === 'select_model') {
        get().openSettings('ai');
        await api.executeRecoveryAction('select_model', payload);
      } else if (action === 'retry_playback' || action === 'retry_speaker') {
        await api.executeRecoveryAction(action, payload);
        get().clearVoiceError();
      } else if (action === 'fallback_tts' || action === 'default_voice') {
        await api.executeRecoveryAction(action, payload);
        get().clearVoiceError();
      } else if (action === 'retry_request' || action === 'retry') {
        if (payload?.messageId) {
          await get().retryMessage(payload.messageId, payload?.prompt);
        }
      } else {
        await api.executeRecoveryAction(action, payload);
      }
    } catch (err) {
      console.error('[Recovery] Action execution failed:', err);
    }
  },
  setDiagnosticMode: async (enabled: boolean) => {
    try {
      const res = await api.toggleDiagnosticMode(enabled);
      set({ diagnosticMode: res.enabled, diagnosticStatus: res.diagnostic });
    } catch (e) {
      console.error('Failed to toggle diagnostic mode', e);
      set({ diagnosticMode: enabled });
    }
  },

  cleanup: () => {
    clearWatchdog();
    if (wsUnsubscribe) {
      wsUnsubscribe();
      wsUnsubscribe = null;
    }
    isStoreInitialized = false;
  },

  init: async () => {
    // Unsubscribe any prior listener before attaching a new one
    if (wsUnsubscribe) {
      wsUnsubscribe();
      wsUnsubscribe = null;
    }

    // 1. Connect WebSocket
    wsClient.connect();

    wsUnsubscribe = wsClient.subscribe((type, data) => {
      switch (type) {
        case 'app_state': {
          const rawState = data?.state;
          if (rawState && ['IDLE', 'LISTENING', 'TRANSCRIBING', 'THINKING', 'SPEAKING', 'ERROR'].includes(rawState)) {
            set({ appState: rawState as AppState });
          }
          break;
        }

        case 'ai_chunk': {
          const chunk = data.chunk || '';
          if (!chunk) break;

          // If event has conversation_id, guard against messages from other conversations
          if (data.conversation_id && get().activeConvId && data.conversation_id !== get().activeConvId) {
            break;
          }

          if (pendingTextTiming && !pendingTextTiming.t_first_token_rendered) {
            pendingTextTiming.t_first_token_rendered = performance.now();
          }

          if (!get().streamingText) {
            console.log('[BOUNDARY] First model output received by frontend.');
          }

          resetWatchdog(35000, () => {
            console.warn('[Watchdog] Streaming stalled after 35s without new tokens.');
            set((s) => ({
              isStreaming: false,
              isThinking: false,
              appState: 'IDLE',
              messages: s.messages.map((m) =>
                m.status === 'streaming'
                  ? { ...m, status: 'completed' as const }
                  : m
              ),
            }));
          });

          set((s) => {
            const newText = s.streamingText + chunk;
            const targetId = data.message_id || s.streamingMessageId;
            const exists = s.messages.some((m) => (targetId ? m.id === targetId : m.role === 'assistant' && m.status === 'streaming'));
            let updatedMessages: Message[];

            if (exists) {
              updatedMessages = s.messages.map((m) => {
                if (targetId && m.id === targetId) {
                  return { ...m, content: newText, status: 'streaming' as const };
                }
                if (!targetId && m.role === 'assistant' && m.status === 'streaming') {
                  return { ...m, content: newText };
                }
                return m;
              });
            } else {
              // Ensure streaming chunk renders immediately even if message_added placeholder was delayed
              const newAssistantMsg: Message = {
                id: targetId || Date.now(),
                conversation_id: s.activeConvId || 'default',
                role: 'assistant',
                content: newText,
                status: 'streaming',
                created_at: new Date().toISOString(),
              };
              updatedMessages = [...s.messages, newAssistantMsg];
            }

            return {
              streamingText: newText,
              streamingMessageId: targetId || s.streamingMessageId,
              isStreaming: true,
              isThinking: false,
              appState: 'THINKING',
              messages: updatedMessages,
            };
          });
          break;
        }

        case 'ai_complete': {
          clearWatchdog();
          const t_responseRendered = performance.now();
          console.log('[BOUNDARY] Response received by frontend.');

          // If event has conversation_id, guard against messages from other conversations
          if (data.conversation_id && get().activeConvId && data.conversation_id !== get().activeConvId) {
            break;
          }

          const rawBackendText = typeof data.text === 'string' ? data.text.trim() : '';
          const targetId = data.message_id || get().streamingMessageId;

          // Response-Time Monitoring: Record 7-stage Text telemetry
          if (pendingTextTiming) {
            const timings = data.timings || {};
            const t_send = pendingTextTiming.t_user_clicks_send;
            const t_backend_recv = timings.t_backend_received || pendingTextTiming.t_backend_received;
            const t_llm_start = timings.t_llm_start;
            const t_first_token_gen = timings.t_first_token;
            const t_first_rendered = pendingTextTiming.t_first_token_rendered || t_responseRendered;
            const t_llm_completed = timings.t_llm_completed;
            const t_rendered = t_responseRendered;

            const textRecord: TextPerformanceRecord = {
              id: 'tperf_' + Date.now(),
              requestId: data.request_id || pendingTextTiming.requestId,
              mode: 'text',
              timestamp: Date.now(),
              t_user_clicks_send: t_send,
              t_backend_received: t_backend_recv,
              t_llm_start,
              t_first_token_gen,
              t_first_token_rendered: t_first_rendered,
              t_llm_completed,
              t_response_rendered: t_rendered,
              time_to_first_token_ui_ms: Math.max(0, t_first_rendered - t_send),
              time_to_first_token_backend_ms: timings.llm_time_to_first_token_ms || (t_first_token_gen && t_llm_start ? Math.max(0, (t_first_token_gen - t_llm_start) * 1000) : 0),
              backend_to_llm_start_ms: timings.backend_to_llm_start_ms || (t_llm_start && t_backend_recv ? Math.max(0, (t_llm_start - t_backend_recv) * 1000) : 0),
              model_generation_duration_ms: timings.llm_generation_duration_ms || (t_llm_completed && t_first_token_gen ? Math.max(0, (t_llm_completed - t_first_token_gen) * 1000) : 0),
              render_completion_delay_ms: Math.max(0, t_rendered - t_first_rendered),
              total_roundtrip_ms: Math.max(0, t_rendered - t_send),
              response_length_chars: rawBackendText.length || get().streamingText.length,
            };
            set((s) => ({
              latestPerformanceRecord: textRecord,
              performanceHistory: [textRecord, ...s.performanceHistory].slice(0, 50),
            }));
            pendingTextTiming = null;
          }

          set((s) => {
            const finalContent = rawBackendText || s.streamingText;
            if (!finalContent) {
              return {
                isStreaming: false,
                isThinking: false,
                streamingText: '',
                streamingMessageId: null,
                appState: 'IDLE',
              };
            }

            const isTruncated = Boolean(data.truncated || data.finish_reason === 'length');
            const finishReason = data.finish_reason || (isTruncated ? 'length' : 'stop');

            const exists = s.messages.some((m) => (targetId ? m.id === targetId : m.role === 'assistant' && m.status === 'streaming'));
            let updatedMessages: Message[];

            if (exists) {
              updatedMessages = s.messages.map((m) => {
                if (targetId && m.id === targetId) {
                  return {
                    ...m,
                    content: finalContent,
                    status: 'completed' as const,
                    truncated: isTruncated,
                    finish_reason: finishReason,
                  };
                }
                if (m.role === 'assistant' && m.status === 'streaming') {
                  return {
                    ...m,
                    id: targetId || m.id,
                    content: finalContent,
                    status: 'completed' as const,
                    truncated: isTruncated,
                    finish_reason: finishReason,
                  };
                }
                return m;
              });
            } else {
              const completedMsg: Message = {
                id: targetId || Date.now(),
                conversation_id: s.activeConvId || 'default',
                role: 'assistant',
                content: finalContent,
                status: 'completed',
                created_at: new Date().toISOString(),
                truncated: isTruncated,
                finish_reason: finishReason,
              };
              updatedMessages = [...s.messages, completedMsg];
            }

            return {
              isStreaming: false,
              isThinking: false,
              streamingText: '',
              streamingMessageId: null,
              appState: s.currentSubtitle ? 'SPEAKING' : 'IDLE',
              messages: updatedMessages,
            };
          });
          break;
        }

        case 'ai_error': {
          clearWatchdog();
          console.warn('[BOUNDARY] AI generation error received by frontend:', data.message);
          const targetId = data.message_id || get().streamingMessageId;
          const rawErr = data.message || '';
          const lower = rawErr.toLowerCase();
          let errMsg = rawErr || 'Error occurred while generating response.';
          if (lower.includes('connection') || lower.includes('unreachable') || lower.includes('not running') || lower.includes('offline') || lower.includes('model unavailable')) {
            errMsg = 'The AI model is unavailable. Check that the local model service is running.';
          }
          const errorType = data.error_type || (lower.includes('connection') ? 'llm_unavailable' : 'llm_error');
          const recoveryAction = data.recovery_action || (lower.includes('connection') ? 'start_ollama' : 'retry_request');
          const recoveryLabel = data.recovery_label || (lower.includes('connection') ? 'Start Ollama' : 'Retry');

          set((s) => {
            const exists = s.messages.some((m) => (targetId ? m.id === targetId : m.role === 'assistant' && m.status === 'streaming'));
            let updatedMessages: Message[];

            if (exists) {
              updatedMessages = s.messages.map((m) =>
                (targetId && m.id === targetId) || (m.role === 'assistant' && m.status === 'streaming')
                  ? {
                      ...m,
                      content: errMsg,
                      status: 'error' as const,
                      error_type: errorType,
                      recovery_action: recoveryAction,
                      recovery_label: recoveryLabel,
                    }
                  : m
              );
            } else {
              const errorMsg: Message = {
                id: targetId || Date.now(),
                conversation_id: s.activeConvId || 'default',
                role: 'assistant',
                content: errMsg,
                status: 'error',
                created_at: new Date().toISOString(),
                error_type: errorType,
                recovery_action: recoveryAction,
                recovery_label: recoveryLabel,
              };
              updatedMessages = [...s.messages, errorMsg];
            }

            return {
              isStreaming: false,
              isThinking: false,
              streamingText: '',
              streamingMessageId: null,
              appState: 'ERROR',
              messages: updatedMessages,
            };
          });
          break;
        }

        case 'ai_cancelled': {
          clearWatchdog();
          console.log('[BOUNDARY] AI generation cancelled.');
          const targetId = data.message_id || get().streamingMessageId;
          set((s) => ({
            isStreaming: false,
            isThinking: false,
            streamingText: '',
            streamingMessageId: null,
            appState: 'IDLE',
            messages: s.messages.map((m) =>
              (targetId && m.id === targetId) || m.status === 'streaming'
                ? { ...m, status: 'cancelled' as const }
                : m
            ),
          }));
          break;
        }

        case 'char_state': {
          const charState = (data.state as CompanionCharacterState) || 'idle';
          let mappedAppState: AppState | null = null;
          const lower = String(charState).toLowerCase();
          if (lower === 'listening') mappedAppState = 'LISTENING';
          else if (lower === 'transcribing') mappedAppState = 'TRANSCRIBING';
          else if (lower === 'thinking') mappedAppState = 'THINKING';
          else if (lower === 'speaking') mappedAppState = 'SPEAKING';
          else if (lower === 'error') mappedAppState = 'ERROR';
          else if (lower === 'idle' || lower === 'sleeping') mappedAppState = 'IDLE';

          set((s) => ({
            companionProfile: { ...s.companionProfile, state: charState },
            ...(mappedAppState ? { appState: mappedAppState } : {}),
          }));
          break;
        }

        case 'voice_state': {
          const vMode = (data.state as VoiceMode) || 'off';
          set((s) => ({
            voiceStatus: { ...s.voiceStatus, mode: vMode },
          }));
          break;
        }

        case 'message_added': {
          const incoming = data.message as Message;
          if (incoming) {
            if (!get().activeConvId) {
              set({ activeConvId: incoming.conversation_id });
            }
            if (incoming.conversation_id === get().activeConvId) {
              set((s) => {
                // If message already exists by ID, do not duplicate
                const existingIdx = s.messages.findIndex((m) => m.id === incoming.id);
                if (existingIdx !== -1) {
                  // Only update if incoming has completed content and existing was empty
                  if (incoming.content && !s.messages[existingIdx].content) {
                    const updated = [...s.messages];
                    updated[existingIdx] = { ...updated[existingIdx], content: incoming.content, status: incoming.status };
                    return { messages: updated };
                  }
                  return s;
                }

                // Reconcile optimistic user message if matching content
                if (incoming.role === 'user') {
                  const optIdx = s.messages.findIndex(
                    (m) =>
                      m.role === 'user' &&
                      m.content === incoming.content &&
                      typeof m.id === 'number' &&
                      m.id > 1000000000000
                  );
                  if (optIdx !== -1) {
                    const updated = [...s.messages];
                    updated[optIdx] = incoming;
                    return { messages: updated };
                  }
                }

                // If assistant placeholder arrives, track as streamingMessageId if not already set
                if (incoming.role === 'assistant' && incoming.status === 'streaming') {
                  return {
                    streamingMessageId: incoming.id,
                    isStreaming: true,
                    isThinking: true,
                    streamingText: '',
                    messages: [...s.messages, incoming],
                  };
                }

                return { messages: [...s.messages, incoming] };
              });
            }
          }
          break;
        }

        case 'message_deleted': {
          const deletedIds = new Set((data.message_ids as number[]) || []);
          if (data.message_id) {
            deletedIds.add(data.message_id);
          }
          set((s) => ({
            messages: s.messages.filter((m) => !deletedIds.has(m.id)),
          }));
          break;
        }

        case 'message_updated': {
          const updatedId = data.message_id;
          const newContent = data.content;
          const newStatus = data.status;

          set((s) => ({
            messages: s.messages.map((m) =>
              m.id === updatedId
                ? {
                    ...m,
                    content: newContent !== undefined ? newContent : m.content,
                    status: newStatus || m.status,
                  }
                : m
            ),
            streamingText: newStatus === 'streaming' ? '' : s.streamingText,
            streamingMessageId: newStatus === 'streaming' ? updatedId : s.streamingMessageId,
            isStreaming: newStatus === 'streaming' ? true : s.isStreaming,
            isThinking: newStatus === 'streaming' ? true : s.isThinking,
          }));
          break;
        }

        case 'voice_mute_changed': {
          set((s) => ({
            voiceStatus: { ...s.voiceStatus, is_muted: Boolean(data.muted) },
          }));
          break;
        }

        case 'transcription': {
          const rawText = data?.text || '';
          const trimmed = typeof rawText === 'string' ? rawText.trim() : '';
          const isDispatched = Boolean(data?.dispatched);
          if (trimmed) {
            console.log('[BOUNDARY] Transcription finalized:', trimmed, 'dispatched:', isDispatched);
            set((s) => ({
              voiceError: null,
              interimTranscript: '',
              appState: isDispatched ? 'THINKING' : 'TRANSCRIBING',
              diagnosticStatus: {
                ...s.diagnosticStatus,
                transcription_status: 'completed',
                recognized_text_available: true,
                recognized_text_preview: trimmed,
              },
            }));
            if (!isDispatched) {
              set({ isThinking: true, appState: 'THINKING' });
              get().sendMessage(trimmed, true);
            }
          } else {
            console.warn('[BOUNDARY] Empty transcription rejected by frontend.');
            set({
              isThinking: false,
              interimTranscript: '',
              appState: 'ERROR',
              voiceError: 'No speech was detected. Please try again.',
            });
            setTimeout(() => {
              if (get().voiceError) {
                set((s) => ({
                  voiceError: null,
                  appState: s.appState === 'ERROR' ? 'IDLE' : s.appState,
                }));
              }
            }, 6000);
          }
          break;
        }

        case 'user_speech_interim': {
          const interim = typeof data?.text === 'string' ? data.text : '';
          set((s) => ({
            interimTranscript: interim,
            appState: interim ? 'LISTENING' : s.appState,
            diagnosticStatus: {
              ...s.diagnosticStatus,
              transcription_status: interim ? 'interim' : s.diagnosticStatus.transcription_status,
              recognized_text_preview: interim || s.diagnosticStatus.recognized_text_preview,
            },
          }));
          break;
        }

        case 'speech_subtitle': {
          const subtitle = typeof data?.text === 'string' ? data.text : '';
          set((s) => ({
            currentSubtitle: subtitle,
            appState: subtitle ? 'SPEAKING' : s.appState === 'SPEAKING' ? 'IDLE' : s.appState,
          }));
          break;
        }

        case 'speech_finished': {
          set((s) => ({
            currentSubtitle: '',
            interimTranscript: '',
            appState: s.appState === 'SPEAKING' ? 'IDLE' : s.appState,
          }));
          break;
        }

        case 'voice_error': {
          let errMsg = data?.message || 'Voice error occurred. Please try speaking again.';
          const lower = errMsg.toLowerCase();
          let recAction = data?.recovery_action || 'listen_again';
          let recLabel = data?.recovery_label || 'Try Again';
          let errType = data?.error_type || 'general_voice_error';

          if (lower.includes('permission') || lower.includes('access denied')) {
            errMsg = 'Microphone permission denied. Please allow microphone access in Windows Settings.';
            recAction = 'open_settings';
            recLabel = 'Open Windows Settings';
            errType = 'mic_permission_denied';
          } else if (lower.includes('unavailable') && lower.includes('mic')) {
            errMsg = 'Microphone unavailable. No input audio device detected.';
            recAction = 'retry_device';
            recLabel = 'Retry Microphone';
            errType = 'mic_unavailable';
          } else if (lower.includes('no speech') || lower.includes('no clear speech') || lower.includes('silence')) {
            errMsg = 'No speech was detected. Please try again.';
            recAction = 'listen_again';
            recLabel = 'Try Again';
            errType = 'empty_transcription';
          } else if (lower.includes('timed out') || lower.includes('timeout')) {
            errMsg = 'Speech transcription timed out. Audio buffer was reset.';
            recAction = 'listen_again';
            recLabel = 'Try Again';
            errType = 'stt_timeout';
          } else if (lower.includes('send') || lower.includes('submission') || lower.includes('could not be sent')) {
            errMsg = 'Speech was recognized, but the message could not be sent.';
            recAction = 'retry';
            recLabel = 'Retry';
            errType = 'submission_failure';
          } else if (lower.includes('ollama') || lower.includes('offline') || lower.includes('model unavailable') || lower.includes('service')) {
            errMsg = 'The AI model is unavailable. Check that the local model service is running.';
            recAction = 'start_ollama';
            recLabel = 'Start Ollama';
            errType = 'llm_unavailable';
          } else if (lower.includes('tts') || lower.includes('text-to-speech') || lower.includes('audio player') || lower.includes('playback')) {
            errMsg = 'The AI replied, but text-to-speech failed.';
            recAction = 'retry_playback';
            recLabel = 'Retry Speaker';
            errType = 'tts_failure';
          }

          const info: VoiceErrorInfo = {
            message: errMsg,
            title: data?.title || 'Voice Alert',
            error_type: errType,
            recovery_action: recAction,
            recovery_label: recLabel,
            urgency: data?.urgency || 'warning',
          };

          set({
            isThinking: false,
            voiceError: errMsg,
            voiceErrorInfo: info,
            appState: info.urgency === 'info' ? get().appState : 'ERROR',
          });
          setTimeout(() => {
            if (get().voiceError === errMsg) {
              set((s) => ({
                voiceError: null,
                voiceErrorInfo: null,
                appState: s.appState === 'ERROR' ? 'IDLE' : s.appState,
              }));
            }
          }, 7000);
          break;
        }

        case 'diagnostic_update': {
          if (data) {
            set((s) => ({
              diagnosticStatus: { ...s.diagnosticStatus, ...data },
              diagnosticMode: typeof data.enabled === 'boolean' ? data.enabled : s.diagnosticMode,
            }));
          }
          break;
        }

        case 'ws_connection_status': {
          const status = data?.status || 'disconnected';
          set((s) => ({
            diagnosticStatus: {
              ...s.diagnosticStatus,
              backend_connection_status: status,
            },
          }));
          break;
        }

        case 'model_changed': {
          if (data.model) {
            set((s) => ({
              modelInfo: { ...s.modelInfo, active_model: data.model },
              companionProfile: { ...s.companionProfile, model: data.model },
            }));
          }
          break;
        }

        case 'companion_name_changed':
        case 'companion_profile_updated': {
          if (data && data.name) {
            const cleanName = String(data.name).trim();
            set((s) => ({
              companionProfile: {
                ...s.companionProfile,
                name: cleanName,
                ...(data.personality ? { personality: data.personality } : {}),
              },
            }));
            document.title = `AI Desktop Friend — Desktop Companion - ${cleanName}`;
          }
          break;
        }

        case 'config_updated': {
          if (data && (data.key === 'ai.companion_name' || data.key === 'companion.name' || data.key === 'character.name')) {
            const cleanName = String(data.value).trim();
            set((s) => ({
              companionProfile: { ...s.companionProfile, name: cleanName },
            }));
            document.title = `AI Desktop Friend — Desktop Companion - ${cleanName}`;
          }
          break;
        }

        case 'config_batch_updated': {
          if (data && data.settings) {
            const name = data.settings['ai.companion_name'] || data.settings['companion.name'] || data.settings['character.name'];
            if (name) {
              const cleanName = String(name).trim();
              set((s) => ({
                companionProfile: { ...s.companionProfile, name: cleanName },
              }));
              document.title = `AI Desktop Friend — Desktop Companion - ${cleanName}`;
            }
          }
          break;
        }

        case 'pet_topmost_changed': {
          set({ petAlwaysOnTop: Boolean(data.always_on_top) });
          break;
        }

        case 'pet_visibility_changed': {
          set({ petVisible: Boolean(data.visible) });
          break;
        }

        case 'pet_position_reset': {
          set({ petVisible: true });
          break;
        }

        case 'buddy_state_changed': {
          const state = data?.state;
          if (state) {
            set((s) => ({
              companionProfile: {
                ...s.companionProfile,
                state: state === 'sleeping' ? 'sleeping' : s.companionProfile.state === 'sleeping' ? 'idle' : s.companionProfile.state,
                operational_state: state,
              },
              voiceStatus: {
                ...s.voiceStatus,
                is_sleeping: state === 'sleeping',
                operational_state: state,
                is_muted: state === 'muted' ? true : s.voiceStatus.is_muted,
              },
            }));
          }
          break;
        }

        case 'message_feedback_updated': {
          if (data && typeof data.message_id === 'number') {
            set((s) => ({
              messages: s.messages.map((m) =>
                m.id === data.message_id ? { ...m, feedback: data.feedback } : m
              ),
            }));
          }
          break;
        }

        case 'performance_telemetry': {
          if (data && data.metrics) {
            const m = data.metrics;
            const voiceRecord: VoicePerformanceRecord = {
              id: 'vperf_' + Date.now(),
              requestId: m.request_id || data.request_id || ('vreq_' + Date.now()),
              mode: 'voice',
              timestamp: Date.now(),
              turn_id: m.turn_id,
              t_speech_start: m.t_speech_start || 0,
              t_speech_end: m.t_speech_end || 0,
              t_stt_start: m.t_stt_start || 0,
              t_transcript_ready: m.t_transcript_ready || 0,
              t_llm_start: m.t_llm_start || 0,
              t_first_token_gen: m.t_first_token_gen || 0,
              t_first_tts_audio: m.t_first_tts_audio || 0,
              t_audio_playback_start: m.t_audio_playback_start || 0,
              t_audio_playback_end: m.t_audio_playback_end || 0,
              user_speech_duration_ms: m.user_speech_duration_ms || 0,
              vad_speech_end_to_stt_ms: m.vad_speech_end_to_stt_ms || 0,
              stt_duration_ms: m.stt_duration_ms || 0,
              transcript_to_llm_ms: m.transcript_to_llm_ms || 0,
              llm_time_to_first_token_ms: m.llm_time_to_first_token_ms || 0,
              first_token_to_tts_chunk_ms: m.first_token_to_tts_chunk_ms || 0,
              tts_chunk_to_playback_ms: m.tts_chunk_to_playback_ms || 0,
              time_to_first_audible_ms: m.time_to_first_audible_ms || 0,
              total_playback_duration_ms: m.total_playback_duration_ms || 0,
              total_voice_turn_ms: m.total_voice_turn_ms || 0,
            };
            set((s) => ({
              latestPerformanceRecord: voiceRecord,
              performanceHistory: [voiceRecord, ...s.performanceHistory].slice(0, 50),
            }));
          }
          break;
        }
      }
    });

    if (isStoreInitialized) {
      return;
    }
    isStoreInitialized = true;

    // Listen for custom bridge event dispatched from Python ModernChatWindow
    window.addEventListener('companion-name-changed', (e: any) => {
      const newName = e.detail;
      if (newName) {
        const cleanName = String(newName).trim();
        set((s) => ({
          companionProfile: { ...s.companionProfile, name: cleanName },
        }));
        document.title = `AI Desktop Friend — Desktop Companion - ${cleanName}`;
      }
    });

    // 2. Load conversations, models, voice status, profile, pet status, and diagnostic status
    try {
      const [convs, models, voice, profile, petStatus, diagStatus] = await Promise.all([
        api.fetchConversations().catch(() => []),
        api.fetchModels().catch(() => ({ active_model: 'llama3.2:3b', available_models: [] })),
        api.fetchVoiceStatus().catch(() => ({ mode: 'off', is_muted: false, is_speaking: false, is_recording: false, device: null, tts_enabled: true })),
        api.fetchCompanionState().catch(() => null),
        api.fetchPetStatus().catch(() => ({ always_on_top: true, visible: true, character: 'robot' })),
        api.fetchDiagnosticStatus().catch(() => null),
      ]);

      const stateUpdates: any = {
        conversations: convs,
        modelInfo: models,
        voiceStatus: voice,
        petAlwaysOnTop: petStatus?.always_on_top ?? true,
        petVisible: petStatus?.visible ?? true,
        diagnosticMode: diagStatus ? Boolean(diagStatus.enabled) : false,
        diagnosticStatus: diagStatus ? { ...defaultDiagnosticStatus, ...diagStatus } : defaultDiagnosticStatus,
      };

      if (profile) {
        const cleanName = profile.name ? String(profile.name).trim() : '';
        const opState = profile.operational_state || (profile.state === 'sleeping' ? 'sleeping' : 'active');
        stateUpdates.companionProfile = {
          ...get().companionProfile,
          ...profile,
          ...(cleanName ? { name: cleanName } : {}),
          operational_state: opState,
        };
        stateUpdates.voiceStatus = {
          ...stateUpdates.voiceStatus,
          is_sleeping: profile.state === 'sleeping' || opState === 'sleeping',
          operational_state: opState,
        };
        if (cleanName) {
          document.title = `AI Desktop Friend — Desktop Companion - ${cleanName}`;
        }
      }

      set(stateUpdates);

      // Robust synchronization: Always verify config directly to ensure name matches latest user settings
      api.fetchConfig().then((cfg) => {
        const cfgName = cfg?.ai?.companion_name || cfg?.['ai.companion_name'] || cfg?.companion?.name || cfg?.['companion.name'] || cfg?.character?.name || cfg?.['character.name'];
        if (cfgName) {
          const cleanName = String(cfgName).trim();
          set((s) => ({
            companionProfile: { ...s.companionProfile, name: cleanName },
          }));
          document.title = `AI Desktop Friend — Desktop Companion - ${cleanName}`;
        }
        if (cfg?.pet) {
          if (typeof cfg.pet.always_on_top === 'boolean') {
            set({ petAlwaysOnTop: cfg.pet.always_on_top });
          }
          if (typeof cfg.pet.visible === 'boolean') {
            set({ petVisible: cfg.pet.visible });
          }
        }
      }).catch(() => {});

      if (convs.length > 0) {
        await get().selectConversation(convs[0].id);
      } else {
        await get().createConversation('New Chat');
      }
    } catch (e) {
      console.warn('Initial data fetch warning (API starting up?):', e);
    }
  },

  selectConversation: async (id: string) => {
    // Prevent stale generations from corrupting the newly selected conversation
    if (get().isStreaming || get().isThinking) {
      try {
        await api.cancelAi();
      } catch {
        // Ignored
      }
    }

    set({
      activeConvId: id,
      isStreaming: false,
      streamingText: '',
      isThinking: false,
      streamingMessageId: null,
    });

    try {
      const msgs = await api.fetchMessages(id);
      // Guard against race conditions when quickly switching conversations
      if (get().activeConvId === id) {
        set({ messages: msgs });
      }
    } catch (e) {
      console.error('Failed to load messages for conversation', id, e);
    }
  },

  createConversation: async (title = 'New Chat') => {
    try {
      const newConv = await api.createConversation(title);
      set((s) => ({
        conversations: [newConv, ...s.conversations],
        activeConvId: newConv.id,
        messages: [],
      }));
    } catch (e) {
      console.warn('Backend offline fallback for createConversation:', e);
      const localConv: Conversation = {
        id: 'conv-' + Date.now(),
        title,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 0,
      };
      set((s) => ({
        conversations: [localConv, ...s.conversations],
        activeConvId: localConv.id,
        messages: [],
      }));
    }
  },

  renameConversation: async (id: string, title: string) => {
    try {
      await api.renameConversation(id, title);
      set((s) => ({
        conversations: s.conversations.map((c) => (c.id === id ? { ...c, title } : c)),
      }));
    } catch (e) {
      console.error('Failed to rename conversation', e);
    }
  },

  deleteConversation: async (id: string) => {
    try {
      await api.deleteConversation(id);
      const remaining = get().conversations.filter((c) => c.id !== id);
      set({ conversations: remaining });
      if (get().activeConvId === id) {
        if (remaining.length > 0) {
          await get().selectConversation(remaining[0].id);
        } else {
          await get().createConversation('New Chat');
        }
      }
    } catch (e) {
      console.error('Failed to delete conversation', e);
    }
  },

  sendMessage: async (content: string, isVoice = false, attachments?: ChatAttachment[]) => {
    const trimmed = content.trim();
    const hasAttachments = Boolean(attachments && attachments.length > 0);
    if (!trimmed && !hasAttachments) return;

    // Prevent duplicate request if already generating for this exact prompt
    if ((get().isThinking || get().isStreaming) && trimmed && trimmed === get().lastUserPrompt) {
      console.warn('[Deduplication] Blocked duplicate message submission:', trimmed);
      return;
    }

    // Gracefully abort previous generation if one is active
    if (get().isThinking || get().isStreaming) {
      try {
        clearWatchdog();
        await api.cancelAi();
      } catch {}
    }

    let convId = get().activeConvId;
    if (!convId) {
      await get().createConversation('New Chat');
      convId = get().activeConvId;
      if (!convId) {
        convId = 'conv-' + Date.now();
        set((s) => ({
          activeConvId: convId,
          conversations: [
            {
              id: convId!,
              title: (trimmed || (hasAttachments ? attachments![0].name : 'New Chat')).slice(0, 24),
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              message_count: 1,
            },
            ...s.conversations,
          ],
        }));
      }
    }

    // Instant optimistic user message rendering with attached media chips/thumbnails
    const optimisticUserMsg: Message = {
      id: Date.now(),
      conversation_id: convId,
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
      status: 'completed',
      attachments: hasAttachments ? attachments : undefined,
    };

    console.log('[BOUNDARY] User message accepted by frontend:', { content: trimmed, convId, isVoice, attachmentsCount: attachments?.length || 0 });

    // Generation watchdog: ensure frontend does not wait forever if response event never arrives
    resetWatchdog(30000, () => {
      console.warn('[Watchdog] AI generation response timed out after 30s.');
      set((s) => {
        if (!s.isThinking && !s.isStreaming) return s;
        const targetId = s.streamingMessageId;
        return {
          isThinking: false,
          isStreaming: false,
          streamingText: '',
          streamingMessageId: null,
          appState: 'ERROR',
          messages: s.messages.map((m) =>
            (targetId && m.id === targetId) || (m.role === 'assistant' && m.status === 'streaming')
              ? {
                  ...m,
                  content: m.content || 'Local model response timed out. Please verify Ollama is active and try again.',
                  status: 'error' as const,
                }
              : m
          ),
        };
      });
    });

    // Response-Time Monitoring: Start monotonic timer & initialize pending text timing
    const t_userClicksSend = performance.now();
    const requestId = 'treq_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    pendingTextTiming = {
      requestId,
      t_user_clicks_send: t_userClicksSend,
    };

    set((s) => ({
      messages: [...s.messages, optimisticUserMsg],
      isThinking: true,
      isStreaming: false,
      streamingText: '',
      lastUserPrompt: trimmed || (hasAttachments ? `Attachment: ${attachments![0].name}` : ''),
      appState: 'THINKING',
    }));

    try {
      const images = attachments?.filter((a) => a.category === 'image' && a.base64).map((a) => a.base64!);
      const res = await api.sendMessage(convId, trimmed, isVoice, requestId, t_userClicksSend, attachments, images);
      if (res && res.status === 'duplicate_rejected') {
        console.warn('[Deduplication] Backend duplicate rejected smoothly:', res.message);
        clearWatchdog();
        set((s) => ({
          isThinking: false,
          isStreaming: false,
          streamingText: '',
          appState: 'IDLE',
          messages: s.messages.filter((m) => m.id !== optimisticUserMsg.id),
        }));
        return;
      }

      if (pendingTextTiming && res.backend_received_time) {
        pendingTextTiming.t_backend_received = res.backend_received_time;
      }
      set((s) => ({
        streamingMessageId: res.assistant_message_id,
        messages: s.messages.map((m) =>
          m.id === optimisticUserMsg.id ? { ...m, id: res.user_message_id } : m
        ),
      }));

      // Refresh conversation list to get updated timestamp / auto-title
      const convs = await api.fetchConversations();
      set({ conversations: convs });
    } catch (e: any) {
      console.warn('API sendMessage warning (backend offline fallback):', e);
      clearWatchdog();
      if (isVoice) {
        set({ voiceError: 'Speech was recognized, but the message could not be sent.' });
      }
      const errMsg = e?.message?.includes('timed out')
        ? 'Request timed out waiting for backend response. Please verify Ollama is active and click Retry.'
        : 'Backend communication error. Check that the local server is running.';

      set((s) => {
        if (!s.isThinking) return s;
        const targetId = s.streamingMessageId;
        const fallbackAssistantMsg: Message = {
          id: targetId || Date.now() + 1,
          conversation_id: convId!,
          role: 'assistant',
          content: errMsg,
          created_at: new Date().toISOString(),
          status: 'error',
          recovery_action: 'retry_request',
          recovery_label: 'Retry',
        };
        return {
          isThinking: false,
          isStreaming: false,
          streamingText: '',
          streamingMessageId: null,
          appState: 'ERROR',
          messages: s.messages.some((m) => m.id === targetId)
            ? s.messages.map((m) => (m.id === targetId ? fallbackAssistantMsg : m))
            : [...s.messages, fallbackAssistantMsg],
        };
      });
    }
  },

  cancelGeneration: async () => {
    clearWatchdog();
    try {
      await api.cancelAi();
    } catch (e) {
      console.error('Failed to cancel generation', e);
    } finally {
      set((s) => ({
        isStreaming: false,
        isThinking: false,
        streamingText: '',
        streamingMessageId: null,
        interimTranscript: '',
        currentSubtitle: '',
        appState: 'IDLE',
        messages: s.messages.map((m) =>
          (s.streamingMessageId && m.id === s.streamingMessageId) || m.status === 'streaming'
            ? { ...m, status: 'cancelled' as const }
            : m
        ),
      }));
    }
  },

  clearCurrentChat: async () => {
    const convId = get().activeConvId;
    if (!convId) return;
    try {
      await api.clearMessages(convId);
      set({ messages: [] });
    } catch (e) {
      console.error('Failed to clear messages', e);
    }
  },

  toggleVoice: async () => {
    try {
      const res = await api.toggleVoice();
      set((s) => ({
        voiceStatus: { ...s.voiceStatus, mode: (res.mode as VoiceMode) || 'off' },
      }));
    } catch (e) {
      console.error('Failed to toggle voice', e);
    }
  },

  setVoiceMode: async (mode: VoiceMode) => {
    try {
      const res = await api.setVoiceMode(mode);
      set((s) => ({
        voiceStatus: { ...s.voiceStatus, mode: (res.mode as VoiceMode) || mode },
      }));
    } catch (e) {
      console.error('Failed to set voice mode', e);
    }
  },

  startPushToTalk: async () => {
    try {
      await api.startPushToTalk();
      set((s) => ({
        voiceStatus: { ...s.voiceStatus, mode: 'listening' },
      }));
    } catch (e) {
      console.error('Failed to start push to talk', e);
    }
  },

  stopPushToTalk: async () => {
    try {
      await api.stopPushToTalk();
      set((s) => ({
        voiceStatus: { ...s.voiceStatus, mode: 'processing' },
      }));
    } catch (e) {
      console.error('Failed to stop push to talk', e);
    }
  },

  stopVoice: async () => {
    try {
      await api.stopVoice();
      set((s) => ({
        voiceStatus: { ...s.voiceStatus, mode: 'off' },
        interimTranscript: '',
        currentSubtitle: '',
        appState: ['LISTENING', 'TRANSCRIBING', 'SPEAKING'].includes(s.appState) ? 'IDLE' : s.appState,
      }));
    } catch (e) {
      console.error('Failed to stop voice', e);
    }
  },

  muteVoice: async (muted: boolean) => {
    try {
      await api.muteVoice(muted);
      set((s) => ({
        voiceStatus: { ...s.voiceStatus, is_muted: muted },
      }));
    } catch (e) {
      console.error('Failed to mute voice', e);
    }
  },

  testVoice: async (text?: string, profileId?: string, language?: string) => {
    try {
      await api.testVoice(text, profileId, language);
    } catch (e) {
      console.error('Failed to test voice', e);
    }
  },

  previewVoice: async (profileId: string, language: string = 'en', text?: string) => {
    try {
      await api.previewVoice(profileId, language, text);
    } catch (e) {
      console.error('Failed to preview voice', e);
    }
  },

  selectModel: async (model: string) => {
    try {
      await api.selectModel(model);
      set((s) => ({
        modelInfo: { ...s.modelInfo, active_model: model },
        companionProfile: { ...s.companionProfile, model },
      }));
    } catch (e) {
      console.error('Failed to select model', e);
    }
  },

  setVoiceEngine: async (engine: string) => {
    try {
      await api.setVoiceEngine(engine);
    } catch (e) {
      console.error('Failed to set voice engine', e);
    }
  },

  setVoiceSpeed: async (speed: number) => {
    try {
      await api.setVoiceSpeed(speed);
    } catch (e) {
      console.error('Failed to set voice speed', e);
    }
  },

  setVoiceVolume: async (volume: number) => {
    try {
      await api.setVoiceVolume(volume);
    } catch (e) {
      console.error('Failed to set voice volume', e);
    }
  },

  setSearchQuery: (q: string) => set({ searchQuery: q }),
  setSettingsOpen: (open: boolean, category?: string) =>
    set({ isSettingsOpen: open, settingsInitialCategory: category }),
  openSettings: (category?: string) =>
    set({ isSettingsOpen: true, settingsInitialCategory: category }),

  setPetAlwaysOnTop: async (alwaysOnTop: boolean) => {
    // Instant optimistic UI update
    set({ petAlwaysOnTop: alwaysOnTop });
    try {
      await api.setPetTopmost(alwaysOnTop);
    } catch (e) {
      console.error('Failed to set pet always on top', e);
      set({ petAlwaysOnTop: !alwaysOnTop });
    }
  },

  togglePetVisible: async (visible: boolean) => {
    // Instant optimistic UI update
    set({ petVisible: visible });
    try {
      await api.togglePetVisible(visible);
    } catch (e) {
      console.error('Failed to toggle pet visibility', e);
      set({ petVisible: !visible });
    }
  },

  resetPetPosition: async () => {
    // Resetting position ensures the pet is visible
    set({ petVisible: true });
    try {
      await api.resetPetPosition();
    } catch (e) {
      console.error('Failed to reset pet position', e);
    }
  },

  setMessageFeedback: async (messageId: number, feedback: 'like' | 'dislike' | null) => {
    // 1. Optimistic UI update
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === messageId ? { ...m, feedback } : m
      ),
    }));

    // 2. Persist to API
    try {
      await api.setMessageFeedback(messageId, feedback, get().activeConvId);
    } catch (e) {
      console.error('Failed to persist message feedback:', e);
    }
  },

  deleteMessage: async (messageId: number, pair = true) => {
    const currentMessages = get().messages;
    const targetIdx = currentMessages.findIndex((m) => m.id === messageId);
    const idsToRemove = new Set<number>([messageId]);

    // If deleting with paired turn, find the linked user/assistant message
    if (pair && targetIdx !== -1) {
      const target = currentMessages[targetIdx];
      if (target.role === 'user') {
        // Automatically delete the following assistant message(s) for this turn
        for (let i = targetIdx + 1; i < currentMessages.length; i++) {
          if (currentMessages[i].role === 'assistant') {
            idsToRemove.add(currentMessages[i].id);
          } else {
            break;
          }
        }
      } else if (target.role === 'assistant') {
        if (targetIdx - 1 >= 0 && currentMessages[targetIdx - 1].role === 'user') {
          idsToRemove.add(currentMessages[targetIdx - 1].id);
        }
      }
    }

    // Optimistic removal from store
    set((s) => ({
      messages: s.messages.filter((m) => !idsToRemove.has(m.id)),
    }));

    try {
      const res = await api.deleteMessage(messageId, pair);
      if (res && res.message_ids) {
        const confirmedIds = new Set(res.message_ids);
        set((s) => ({
          messages: s.messages.filter((m) => !confirmedIds.has(m.id)),
        }));
      }
    } catch (e) {
      console.error('Failed to delete message:', e);
      // Revert if API fails
      set({ messages: currentMessages });
    }
  },

  editMessage: async (messageId: number, content: string) => {
    const trimmed = content.trim();
    if (!trimmed) return;

    // Optimistic update
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === messageId ? { ...m, content: trimmed } : m
      ),
    }));

    try {
      await api.editMessage(messageId, trimmed);
    } catch (e) {
      console.error('Failed to update message content:', e);
    }
  },

  retryMessage: async (messageId: number, prompt?: string) => {
    const currentMessages = get().messages;
    const target = currentMessages.find((m) => m.id === messageId);
    if (!target) return;

    let targetAssistantId = messageId;
    let promptToRun = prompt?.trim() || '';

    if (target.role === 'assistant') {
      targetAssistantId = target.id;
      if (!promptToRun) {
        const idx = currentMessages.findIndex((m) => m.id === messageId);
        if (idx > 0 && currentMessages[idx - 1].role === 'user') {
          promptToRun = currentMessages[idx - 1].content;
        }
      }
    } else {
      promptToRun = promptToRun || target.content;
      const idx = currentMessages.findIndex((m) => m.id === messageId);
      if (idx + 1 < currentMessages.length && currentMessages[idx + 1].role === 'assistant') {
        targetAssistantId = currentMessages[idx + 1].id;
      }
    }

    // Reset ONLY the target assistant message to streaming & empty, keeping all other messages intact!
    set((s) => ({
      isThinking: true,
      isStreaming: true,
      streamingText: '',
      streamingMessageId: targetAssistantId,
      messages: s.messages.map((m) =>
        m.id === targetAssistantId
          ? { ...m, content: '', status: 'streaming' as const }
          : m
      ),
    }));

    try {
      await api.retryMessage(messageId, promptToRun);
    } catch (e) {
      console.error('Failed to retry message:', e);
      set({ isThinking: false, isStreaming: false });
    }
  },

  sleep: async () => {
    try {
      set((s) => ({
        companionProfile: { ...s.companionProfile, state: 'sleeping', operational_state: 'sleeping' },
        voiceStatus: { ...s.voiceStatus, is_sleeping: true, operational_state: 'sleeping' },
      }));
      await api.sleepCompanion();
    } catch (e) {
      console.error('Failed to put companion to sleep:', e);
    }
  },

  wake: async () => {
    try {
      set((s) => ({
        companionProfile: { ...s.companionProfile, state: 'idle', operational_state: 'active' },
        voiceStatus: { ...s.voiceStatus, is_sleeping: false, operational_state: 'active' },
      }));
      await api.wakeCompanion();
    } catch (e) {
      console.error('Failed to wake companion:', e);
    }
  },

  mute: async () => {
    try {
      set((s) => ({
        voiceStatus: { ...s.voiceStatus, is_muted: true, operational_state: 'muted' },
        companionProfile: { ...s.companionProfile, operational_state: 'muted' },
      }));
      await api.muteCompanion();
    } catch (e) {
      console.error('Failed to mute companion:', e);
    }
  },

  unmute: async () => {
    try {
      set((s) => ({
        voiceStatus: { ...s.voiceStatus, is_muted: false, operational_state: 'active' },
        companionProfile: { ...s.companionProfile, operational_state: 'active' },
      }));
      await api.unmuteCompanion();
    } catch (e) {
      console.error('Failed to unmute companion:', e);
    }
  },
}));
