export type Role = 'user' | 'assistant' | 'system';

export type MessageStatus = 'pending' | 'streaming' | 'completed' | 'error' | 'cancelled';

export type AttachmentCategory = 'image' | 'document' | 'spreadsheet' | 'audio' | 'video';

export interface ChatAttachment {
  id: string;
  name: string;
  size: number;
  size_formatted?: string;
  type: string;
  extension: string;
  category: AttachmentCategory;
  dataUrl?: string;
  base64?: string;
  thumbnail_base64?: string;
  content?: string;
  path?: string;
  status?: 'pending' | 'uploading' | 'ready' | 'error';
  error?: string;
  metadata?: Record<string, any>;
}

export interface Message {
  id: number;
  conversation_id: string;
  role: Role;
  content: string;
  created_at: string;
  status: MessageStatus;
  feedback?: 'like' | 'dislike' | null;
  error_type?: string;
  recovery_action?: string;
  recovery_label?: string;
  truncated?: boolean;
  finish_reason?: string;
  routing?: ModelRoutingDecision | null;
  ui_badge?: string;
  attachments?: ChatAttachment[];
  images?: string[];
}

export interface VoiceErrorInfo {
  message: string;
  title?: string;
  error_type?: string;
  recovery_action?: string;
  recovery_label?: string;
  truncated?: boolean;
  finish_reason?: string;
  urgency?: 'info' | 'warning' | 'error';
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export type CompanionCharacterState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'happy' | 'sleeping';

export type AppState = 'IDLE' | 'LISTENING' | 'TRANSCRIBING' | 'THINKING' | 'SPEAKING' | 'ERROR';

export type VoiceMode = 'off' | 'continuous' | 'push_to_talk' | 'listening' | 'processing' | 'speaking';

export type OperationalState = 'active' | 'sleeping' | 'muted';

export interface CompanionProfile {
  name: string;
  personality: string;
  state: CompanionCharacterState;
  model: string;
  operational_state?: OperationalState;
}

export type ModelCapabilityType =
  | 'fast_response'
  | 'general_conversation'
  | 'reasoning'
  | 'coding'
  | 'long_context'
  | 'summarization'
  | 'structured_output'
  | 'vision'
  | 'multilingual';

export interface ModelProfileSummary {
  model_id: string;
  display_name: string;
  installed: boolean;
  size_bytes: number;
  size_formatted: string;
  quantization?: string | null;
  family: string;
  families: string[];
  parameter_size: string;
  context_capacity: number;
  estimated_vram_mb: number;
  capabilities: ModelCapabilityType[];
  is_online: boolean;
  is_local: boolean;
  last_used_timestamp?: number | null;
  benchmark_scores?: Record<string, any>;
  verification_details?: Record<string, any>;
}

export interface ModelInfo {
  active_model: string;
  available_models: string[];
  is_online: boolean;
  models?: ModelProfileSummary[];
}

export interface BenchmarkProgress {
  is_running: boolean;
  current_model: string;
  model_index: number;
  total_models: number;
  current_category: string;
  category_index: number;
  total_categories: number;
  percentage: number;
  message: string;
  cancelled: boolean;
  error?: string | null;
}

export interface BenchmarkRecordData {
  id?: number;
  model_id: string;
  digest?: string | null;
  category: string;
  run_type: 'cold' | 'warm';
  ttft_ms: number;
  tokens_per_sec: number;
  total_duration_ms: number;
  eval_count: number;
  model_load_ms: number;
  peak_ram_mb: number;
  peak_gpu_mb: number;
  context_capacity: number;
  quality_score: number;
  quality_details: Record<string, any>;
  raw_response: string;
  test_outcome: 'passed' | 'failed' | 'skipped';
  created_at: string;
}

export interface BenchmarkRecommendationItem {
  model_id: string;
  reason: string;
  quality_score?: number;
  avg_ttft_ms?: number;
  tokens_per_sec?: number;
  context_capacity?: number;
  composite_score?: number;
}

export interface BenchmarkRecommendations {
  models_tested: number;
  fastest_model?: BenchmarkRecommendationItem | null;
  best_conversational?: BenchmarkRecommendationItem | null;
  best_coding?: BenchmarkRecommendationItem | null;
  best_long_context?: BenchmarkRecommendationItem | null;
  best_vision?: BenchmarkRecommendationItem | null;
  best_balanced?: BenchmarkRecommendationItem | null;
}

export interface VoiceStatus {
  mode: VoiceMode;
  is_muted: boolean;
  tts_enabled: boolean;
  is_sleeping?: boolean;
  operational_state?: OperationalState;
  permission_granted?: boolean;
}

export interface DiagnosticStatus {
  enabled: boolean;
  microphone_status: string;
  recording_status: string;
  audio_duration_sec: number;
  audio_sample_count: number;
  transcription_status: string;
  recognized_text_available: boolean;
  recognized_text_preview?: string;
  user_message_submission_status: string;
  backend_connection_status: string;
  model_generation_status: string;
  assistant_response_status: string;
  tts_generation_status: string;
  audio_playback_status: string;
  last_error: string | null;
  speech_recognition_latency_ms?: number;
  backend_request_latency_ms?: number;
  model_time_to_first_output_ms?: number;
  total_model_generation_ms?: number;
  tts_generation_time_ms?: number;
  time_to_first_audible_response_ms?: number;
}

export interface MemoryItem {
  id: string;
  category: string;
  content: string;
  created_at: string;
}

export type NavigationTab = 'chat' | 'movies';

export interface TextPerformanceRecord {
  id: string;
  requestId: string;
  mode: 'text';
  timestamp: number; // Date.now() for display
  // 7 Monotonic Stage Milestones
  t_user_clicks_send: number;       // 1. performance.now()
  t_backend_received?: number;      // 2. time.perf_counter()
  t_llm_start?: number;             // 3. time.perf_counter()
  t_first_token_gen?: number;       // 4. time.perf_counter()
  t_first_token_rendered?: number;  // 5. performance.now()
  t_llm_completed?: number;         // 6. time.perf_counter()
  t_response_rendered: number;      // 7. performance.now()
  // Calculated Stage Deltas (ms)
  time_to_first_token_ui_ms: number;     // Milestone 1 -> 5
  time_to_first_token_backend_ms: number;// Milestone 3 -> 4
  backend_to_llm_start_ms: number;       // Milestone 2 -> 3
  model_generation_duration_ms: number;  // Milestone 4 -> 6
  render_completion_delay_ms: number;    // Milestone 6 -> 7
  total_roundtrip_ms: number;            // Milestone 1 -> 7
  response_length_chars?: number;
}

export interface VoicePerformanceRecord {
  id: string;
  requestId: string;
  mode: 'voice';
  timestamp: number; // Date.now() for display
  turn_id?: number;
  // 9 Monotonic Stage Milestones
  t_speech_start: number;           // 1. time.perf_counter()
  t_speech_end: number;             // 2. time.perf_counter()
  t_stt_start: number;              // 3. time.perf_counter()
  t_transcript_ready: number;       // 4. time.perf_counter()
  t_llm_start: number;              // 5. time.perf_counter()
  t_first_token_gen: number;        // 6. time.perf_counter()
  t_first_tts_audio: number;        // 7. time.perf_counter()
  t_audio_playback_start: number;   // 8. time.perf_counter()
  t_audio_playback_end: number;     // 9. time.perf_counter()
  // Calculated Stage Deltas (ms)
  user_speech_duration_ms: number;       // Milestone 1 -> 2
  vad_speech_end_to_stt_ms: number;      // Milestone 2 -> 3
  stt_duration_ms: number;               // Milestone 3 -> 4
  transcript_to_llm_ms: number;          // Milestone 4 -> 5
  llm_time_to_first_token_ms: number;    // Milestone 5 -> 6
  first_token_to_tts_chunk_ms: number;   // Milestone 6 -> 7
  tts_chunk_to_playback_ms: number;      // Milestone 7 -> 8
  time_to_first_audible_ms: number;      // Milestone 2 -> 8 (Speech End -> Playback Start)
  total_playback_duration_ms: number;    // Milestone 8 -> 9
  total_voice_turn_ms: number;           // Milestone 1 -> 9
}

export type PerformanceRecord = TextPerformanceRecord | VoicePerformanceRecord;

export interface ModelRoutingDecision {
  detected_task: string;
  selected_model: string;
  previous_model: string;
  switched: boolean;
  reason: string;
  fallback_used: boolean;
  ui_badge: string;
  required_capabilities: string[];
  resource_metrics?: Record<string, any>;
  research_limitation_noted?: boolean;
  material_change_note?: string | null;
  model_unavailable?: boolean;
  fallback_notification?: string | null;
}

export type ModelSelectionMode = 'auto' | 'manual';
export type ResponsePriority = 'fastest' | 'balanced' | 'quality';

export interface TaskPreferredModels {
  general_conversation?: string;
  complex_reasoning?: string;
  coding?: string;
  document_summarization?: string;
  vision?: string;
}

export interface ModelPreferences {
  status?: string;
  model_selection_mode: ModelSelectionMode;
  response_priority: ResponsePriority;
  task_preferred_models: TaskPreferredModels;
  manual_model?: string;
  compatible_models_by_task?: Record<string, string[]>;
  active_model?: string;
  is_manual_model_available?: boolean;
  available_models?: string[];
}

export interface ModelRouterStatus {
  status: string;
  auto_routing_enabled: boolean;
  router: {
    registered_models_count: number;
    installed_models: string[];
    supported_categories: string[];
    has_vision_model: boolean;
    has_reasoning_model: boolean;
    has_coding_model: boolean;
    last_decision?: ModelRoutingDecision | null;
  };
  last_decision?: ModelRoutingDecision | null;
}



