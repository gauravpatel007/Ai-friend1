import React, { useState } from 'react';
import {
  Activity,
  X,
  Copy,
  Check,
  Trash2,
  Clock,
  Zap,
  Mic,
  MessageSquare,
  ShieldCheck,
  Layers,
  ChevronDown,
} from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { PerformanceRecord, TextPerformanceRecord, VoicePerformanceRecord } from '../../types';
import './PerformancePanel.css';

export const PerformancePanel: React.FC = () => {
  const {
    isPerformancePanelOpen,
    togglePerformancePanel,
    performanceHistory,
    latestPerformanceRecord,
    clearPerformanceHistory,
  } = useChatStore();

  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  if (!isPerformancePanelOpen) {
    return null;
  }

  // Active record to display: either selected from history or latest
  const activeRecord: PerformanceRecord | undefined = selectedRecordId
    ? performanceHistory.find((r) => r.id === selectedRecordId) || latestPerformanceRecord || undefined
    : latestPerformanceRecord || performanceHistory[0] || undefined;

  const handleCopyRequestId = () => {
    if (!activeRecord) return;
    navigator.clipboard.writeText(activeRecord.requestId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatMs = (val?: number): string => {
    if (val === undefined || val === null || isNaN(val)) return '—';
    return `${val.toFixed(1)} ms`;
  };

  const formatTimestamp = (ts?: number): string => {
    if (!ts) return '—';
    return ts.toFixed(4) + 's';
  };

  return (
    <div className="perf-panel-overlay" onClick={togglePerformancePanel}>
      <div
        className="perf-panel-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="perf-panel-title"
      >
        {/* Header Bar */}
        <div className="perf-panel-header">
          <div className="perf-header-left">
            <div className="perf-icon-badge">
              <Activity size={18} className="perf-activity-glyph" />
            </div>
            <div>
              <h2 id="perf-panel-title" className="perf-title">
                Response-Time Monitoring
              </h2>
              <p className="perf-subtitle">
                Monotonic stage latency &amp; pipeline telemetry
              </p>
            </div>
          </div>

          <div className="perf-header-right">
            <div className="perf-privacy-badge" title="No audio recordings or message texts are stored for telemetry">
              <ShieldCheck size={14} className="privacy-lock-icon" />
              <span>Zero-Storage Telemetry</span>
            </div>

            <button
              className="perf-close-btn"
              onClick={togglePerformancePanel}
              title="Close Performance Panel"
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Toolbar & History Selector */}
        <div className="perf-toolbar">
          <div className="perf-history-picker">
            <span className="perf-history-label">Turn History:</span>
            {performanceHistory.length > 0 ? (
              <div className="perf-select-wrapper">
                <select
                  value={activeRecord?.id || ''}
                  onChange={(e) => setSelectedRecordId(e.target.value)}
                  className="perf-select"
                >
                  {performanceHistory.map((rec, idx) => {
                    const dur =
                      rec.mode === 'text'
                        ? rec.total_roundtrip_ms.toFixed(0) + 'ms'
                        : rec.total_voice_turn_ms.toFixed(0) + 'ms';
                    return (
                      <option key={rec.id} value={rec.id}>
                        #{idx + 1} [{rec.mode.toUpperCase()}] {rec.requestId.slice(0, 16)}... ({dur})
                      </option>
                    );
                  })}
                </select>
                <ChevronDown size={14} className="perf-select-arrow" />
              </div>
            ) : (
              <span className="perf-no-history">No conversation turns recorded yet</span>
            )}
          </div>

          {performanceHistory.length > 0 && (
            <button
              className="perf-clear-btn"
              onClick={clearPerformanceHistory}
              title="Clear all performance logs"
            >
              <Trash2 size={13} />
              <span>Clear History</span>
            </button>
          )}
        </div>

        {/* Main Content Area */}
        {activeRecord ? (
          <div className="perf-content-scroll">
            {/* Correlation ID & Mode Bar */}
            <div className="perf-meta-card">
              <div className="perf-mode-indicator">
                <span className={`perf-mode-pill mode-${activeRecord.mode}`}>
                  {activeRecord.mode === 'text' ? (
                    <>
                      <MessageSquare size={13} />
                      <span>TEXT MODE</span>
                    </>
                  ) : (
                    <>
                      <Mic size={13} />
                      <span>VOICE MODE</span>
                    </>
                  )}
                </span>
                <span className="perf-timestamp">
                  {new Date(activeRecord.timestamp).toLocaleTimeString()}
                </span>
              </div>

              <div className="perf-reqid-group">
                <span className="perf-reqid-label">Request ID:</span>
                <code className="perf-reqid-value">{activeRecord.requestId}</code>
                <button
                  className="perf-copy-btn"
                  onClick={handleCopyRequestId}
                  title="Copy Request ID"
                >
                  {copied ? <Check size={13} className="text-success" /> : <Copy size={13} />}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>

            {/* Mode-Specific KPI Cards */}
            {activeRecord.mode === 'text' ? (
              <TextKpiGrid record={activeRecord as TextPerformanceRecord} formatMs={formatMs} />
            ) : (
              <VoiceKpiGrid record={activeRecord as VoicePerformanceRecord} formatMs={formatMs} />
            )}

            {/* Waterfall Visualization */}
            <div className="perf-section-title-row">
              <Layers size={14} />
              <span>Pipeline Stage Waterfall</span>
            </div>
            {activeRecord.mode === 'text' ? (
              <TextWaterfall record={activeRecord as TextPerformanceRecord} />
            ) : (
              <VoiceWaterfall record={activeRecord as VoicePerformanceRecord} />
            )}

            {/* Monotonic Milestone Timeline Table */}
            <div className="perf-section-title-row">
              <Clock size={14} />
              <span>
                {activeRecord.mode === 'text'
                  ? 'Text Mode Milestones (7 Stages)'
                  : 'Voice Mode Milestones (9 Stages)'}
              </span>
            </div>
            {activeRecord.mode === 'text' ? (
              <TextMilestonesTable
                record={activeRecord as TextPerformanceRecord}
                formatMs={formatMs}
                formatTimestamp={formatTimestamp}
              />
            ) : (
              <VoiceMilestonesTable
                record={activeRecord as VoicePerformanceRecord}
                formatMs={formatMs}
                formatTimestamp={formatTimestamp}
              />
            )}
          </div>
        ) : (
          <div className="perf-empty-state">
            <div className="perf-empty-icon-wrap">
              <Zap size={32} />
            </div>
            <h3>No Latency Data Available</h3>
            <p>
              Send a typed chat message or speak in voice mode to record monotonic timing metrics
              across all processing stages.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── TEXT MODE KPI GRID ──────────────────────────────────────────────────────

interface TextKpiProps {
  record: TextPerformanceRecord;
  formatMs: (val?: number) => string;
}

const TextKpiGrid: React.FC<TextKpiProps> = ({ record, formatMs }) => (
  <div className="perf-kpi-grid">
    <div className="perf-kpi-card highlight-green">
      <span className="perf-kpi-label">UI Time To First Token (TTFT)</span>
      <span className="perf-kpi-value">{formatMs(record.time_to_first_token_ui_ms)}</span>
      <span className="perf-kpi-hint">User Send → First Character Rendered</span>
    </div>

    <div className="perf-kpi-card">
      <span className="perf-kpi-label">Model Engine TTFT</span>
      <span className="perf-kpi-value">{formatMs(record.time_to_first_token_backend_ms)}</span>
      <span className="perf-kpi-hint">LLM Start → Token 0 Emitted</span>
    </div>

    <div className="perf-kpi-card">
      <span className="perf-kpi-label">Generation Duration</span>
      <span className="perf-kpi-value">{formatMs(record.model_generation_duration_ms)}</span>
      <span className="perf-kpi-hint">Token 0 → LLM Completion</span>
    </div>

    <div className="perf-kpi-card">
      <span className="perf-kpi-label">Total Roundtrip</span>
      <span className="perf-kpi-value">{formatMs(record.total_roundtrip_ms)}</span>
      <span className="perf-kpi-hint">End-to-End User Turn Latency</span>
    </div>
  </div>
);

// ─── VOICE MODE KPI GRID ─────────────────────────────────────────────────────

interface VoiceKpiProps {
  record: VoicePerformanceRecord;
  formatMs: (val?: number) => string;
}

const VoiceKpiGrid: React.FC<VoiceKpiProps> = ({ record, formatMs }) => (
  <div className="perf-kpi-grid">
    <div className="perf-kpi-card highlight-purple">
      <span className="perf-kpi-label">Time To First Audible (TTFA)</span>
      <span className="perf-kpi-value">{formatMs(record.time_to_first_audible_ms)}</span>
      <span className="perf-kpi-hint">Speech End → First Audio Heard</span>
    </div>

    <div className="perf-kpi-card">
      <span className="perf-kpi-label">Speech Recognition (STT)</span>
      <span className="perf-kpi-value">{formatMs(record.stt_duration_ms)}</span>
      <span className="perf-kpi-hint">Whisper Audio Transcription</span>
    </div>

    <div className="perf-kpi-card">
      <span className="perf-kpi-label">LLM First Token (TTFT)</span>
      <span className="perf-kpi-value">{formatMs(record.llm_time_to_first_token_ms)}</span>
      <span className="perf-kpi-hint">Dispatch → First Token</span>
    </div>

    <div className="perf-kpi-card">
      <span className="perf-kpi-label">Total Turn Duration</span>
      <span className="perf-kpi-value">{formatMs(record.total_voice_turn_ms)}</span>
      <span className="perf-kpi-hint">Speech Start → Playback End</span>
    </div>
  </div>
);

// ─── TEXT WATERFALL ──────────────────────────────────────────────────────────

const TextWaterfall: React.FC<{ record: TextPerformanceRecord }> = ({ record }) => {
  const total = Math.max(record.total_roundtrip_ms, 1);
  const pBackendDispatch = (record.backend_to_llm_start_ms / total) * 100;
  const pModelTTFT = (record.time_to_first_token_backend_ms / total) * 100;
  const pGen = (record.model_generation_duration_ms / total) * 100;
  const pRenderDelay = (record.render_completion_delay_ms / total) * 100;

  return (
    <div className="perf-waterfall-card">
      <div className="perf-waterfall-bar">
        <div
          className="waterfall-segment seg-dispatch"
          style={{ width: `${Math.max(pBackendDispatch, 2)}%` }}
          title={`Backend Dispatch: ${record.backend_to_llm_start_ms.toFixed(1)}ms`}
        />
        <div
          className="waterfall-segment seg-ttft"
          style={{ width: `${Math.max(pModelTTFT, 2)}%` }}
          title={`Model TTFT: ${record.time_to_first_token_backend_ms.toFixed(1)}ms`}
        />
        <div
          className="waterfall-segment seg-gen"
          style={{ width: `${Math.max(pGen, 4)}%` }}
          title={`Streaming Generation: ${record.model_generation_duration_ms.toFixed(1)}ms`}
        />
        <div
          className="waterfall-segment seg-render"
          style={{ width: `${Math.max(pRenderDelay, 2)}%` }}
          title={`Render & Flush: ${record.render_completion_delay_ms.toFixed(1)}ms`}
        />
      </div>

      <div className="waterfall-legend">
        <span className="legend-item"><span className="legend-dot seg-dispatch" /> Dispatch ({record.backend_to_llm_start_ms.toFixed(0)}ms)</span>
        <span className="legend-item"><span className="legend-dot seg-ttft" /> Model TTFT ({record.time_to_first_token_backend_ms.toFixed(0)}ms)</span>
        <span className="legend-item"><span className="legend-dot seg-gen" /> Generation ({record.model_generation_duration_ms.toFixed(0)}ms)</span>
        <span className="legend-item"><span className="legend-dot seg-render" /> Render ({record.render_completion_delay_ms.toFixed(0)}ms)</span>
      </div>
    </div>
  );
};

// ─── VOICE WATERFALL ─────────────────────────────────────────────────────────

const VoiceWaterfall: React.FC<{ record: VoicePerformanceRecord }> = ({ record }) => {
  const total = Math.max(record.total_voice_turn_ms, 1);
  const pSpeech = (record.user_speech_duration_ms / total) * 100;
  const pStt = (record.stt_duration_ms / total) * 100;
  const pLlm = (record.llm_time_to_first_token_ms / total) * 100;
  const pTts = (record.first_token_to_tts_chunk_ms / total) * 100;
  const pPlay = (record.total_playback_duration_ms / total) * 100;

  return (
    <div className="perf-waterfall-card">
      <div className="perf-waterfall-bar">
        <div
          className="waterfall-segment seg-speech"
          style={{ width: `${Math.max(pSpeech, 2)}%` }}
          title={`User Speech: ${record.user_speech_duration_ms.toFixed(1)}ms`}
        />
        <div
          className="waterfall-segment seg-stt"
          style={{ width: `${Math.max(pStt, 2)}%` }}
          title={`STT Whisper: ${record.stt_duration_ms.toFixed(1)}ms`}
        />
        <div
          className="waterfall-segment seg-llm"
          style={{ width: `${Math.max(pLlm, 2)}%` }}
          title={`LLM TTFT: ${record.llm_time_to_first_token_ms.toFixed(1)}ms`}
        />
        <div
          className="waterfall-segment seg-tts"
          style={{ width: `${Math.max(pTts, 2)}%` }}
          title={`TTS Synthesize: ${record.first_token_to_tts_chunk_ms.toFixed(1)}ms`}
        />
        <div
          className="waterfall-segment seg-play"
          style={{ width: `${Math.max(pPlay, 4)}%` }}
          title={`Audio Playback: ${record.total_playback_duration_ms.toFixed(1)}ms`}
        />
      </div>

      <div className="waterfall-legend">
        <span className="legend-item"><span className="legend-dot seg-speech" /> User Speech</span>
        <span className="legend-item"><span className="legend-dot seg-stt" /> STT ({record.stt_duration_ms.toFixed(0)}ms)</span>
        <span className="legend-item"><span className="legend-dot seg-llm" /> LLM ({record.llm_time_to_first_token_ms.toFixed(0)}ms)</span>
        <span className="legend-item"><span className="legend-dot seg-tts" /> TTS ({record.first_token_to_tts_chunk_ms.toFixed(0)}ms)</span>
        <span className="legend-item"><span className="legend-dot seg-play" /> Playback ({record.total_playback_duration_ms.toFixed(0)}ms)</span>
      </div>
    </div>
  );
};

// ─── TEXT MILESTONES TABLE ───────────────────────────────────────────────────

interface TextTableProps {
  record: TextPerformanceRecord;
  formatMs: (val?: number) => string;
  formatTimestamp: (ts?: number) => string;
}

const TextMilestonesTable: React.FC<TextTableProps> = ({ record, formatMs, formatTimestamp }) => {
  const rows = [
    {
      num: 1,
      stage: 'User clicks Send',
      clock: 'Frontend (performance.now)',
      ts: formatTimestamp(record.t_user_clicks_send),
      delta: '— (Origin)',
      notes: 'User interaction event in chat UI',
    },
    {
      num: 2,
      stage: 'Backend receives request',
      clock: 'Backend (perf_counter)',
      ts: formatTimestamp(record.t_backend_received),
      delta: formatMs(record.backend_to_llm_start_ms),
      notes: 'FastAPI HTTP route receives payload',
    },
    {
      num: 3,
      stage: 'LLM starts processing',
      clock: 'Backend (perf_counter)',
      ts: formatTimestamp(record.t_llm_start),
      delta: formatMs(record.backend_to_llm_start_ms),
      notes: 'AIService dispatches worker to Ollama client',
    },
    {
      num: 4,
      stage: 'First token generated',
      clock: 'Backend (perf_counter)',
      ts: formatTimestamp(record.t_first_token_gen),
      delta: formatMs(record.time_to_first_token_backend_ms),
      notes: 'Ollama streaming worker yields chunk 0',
    },
    {
      num: 5,
      stage: 'First token rendered in UI',
      clock: 'Frontend (performance.now)',
      ts: formatTimestamp(record.t_first_token_rendered),
      delta: formatMs(record.time_to_first_token_ui_ms),
      notes: 'WebSocket chunk received & message rendered in DOM',
    },
    {
      num: 6,
      stage: 'Complete response generated',
      clock: 'Backend (perf_counter)',
      ts: formatTimestamp(record.t_llm_completed),
      delta: formatMs(record.model_generation_duration_ms),
      notes: 'LLM worker emits full completion signal',
    },
    {
      num: 7,
      stage: 'Response rendering completed',
      clock: 'Frontend (performance.now)',
      ts: formatTimestamp(record.t_response_rendered),
      delta: formatMs(record.total_roundtrip_ms),
      notes: 'Full response finalized & streaming state cleared',
    },
  ];

  return (
    <div className="perf-table-wrap">
      <table className="perf-table">
        <thead>
          <tr>
            <th className="col-num">#</th>
            <th className="col-stage">Pipeline Stage</th>
            <th className="col-clock">Clock Domain</th>
            <th className="col-delta">Stage Delta</th>
            <th className="col-notes">Technical Details</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.num}>
              <td className="col-num"><span className="stage-num-badge">{row.num}</span></td>
              <td className="col-stage"><strong>{row.stage}</strong></td>
              <td className="col-clock"><span className="clock-badge">{row.clock}</span></td>
              <td className="col-delta"><span className="delta-value">{row.delta}</span></td>
              <td className="col-notes">{row.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// ─── VOICE MILESTONES TABLE ──────────────────────────────────────────────────

interface VoiceTableProps {
  record: VoicePerformanceRecord;
  formatMs: (val?: number) => string;
  formatTimestamp: (ts?: number) => string;
}

const VoiceMilestonesTable: React.FC<VoiceTableProps> = ({ record, formatMs, formatTimestamp }) => {
  const rows = [
    {
      num: 1,
      stage: 'User starts speaking',
      ts: formatTimestamp(record.t_speech_start),
      delta: '— (Origin)',
      notes: 'Silero VAD speech onset detected',
    },
    {
      num: 2,
      stage: 'Speech ends',
      ts: formatTimestamp(record.t_speech_end),
      delta: formatMs(record.user_speech_duration_ms),
      notes: 'Silero VAD speech offset triggered',
    },
    {
      num: 3,
      stage: 'Speech recognition starts',
      ts: formatTimestamp(record.t_stt_start),
      delta: formatMs(record.vad_speech_end_to_stt_ms),
      notes: 'Faster-Whisper inference invoked',
    },
    {
      num: 4,
      stage: 'Final transcript becomes available',
      ts: formatTimestamp(record.t_transcript_ready),
      delta: formatMs(record.stt_duration_ms),
      notes: 'Whisper completes transcript beam search',
    },
    {
      num: 5,
      stage: 'LLM starts generating',
      ts: formatTimestamp(record.t_llm_start),
      delta: formatMs(record.transcript_to_llm_ms),
      notes: 'VoiceConversationController calls AIService.ask',
    },
    {
      num: 6,
      stage: 'First LLM token generated',
      ts: formatTimestamp(record.t_first_token_gen),
      delta: formatMs(record.llm_time_to_first_token_ms),
      notes: 'First LLM token chunk received by controller',
    },
    {
      num: 7,
      stage: 'First TTS audio chunk generated',
      ts: formatTimestamp(record.t_first_tts_audio),
      delta: formatMs(record.first_token_to_tts_chunk_ms),
      notes: 'SentenceChunker synthesizes audio segment 0',
    },
    {
      num: 8,
      stage: 'Audio playback begins',
      ts: formatTimestamp(record.t_audio_playback_start),
      delta: formatMs(record.time_to_first_audible_ms),
      notes: 'Sounddevice AudioPlayer starts playing audio segment 0',
    },
    {
      num: 9,
      stage: 'Complete response finishes playing',
      ts: formatTimestamp(record.t_audio_playback_end),
      delta: formatMs(record.total_playback_duration_ms),
      notes: 'All queued sentence audio chunks completed',
    },
  ];

  return (
    <div className="perf-table-wrap">
      <table className="perf-table">
        <thead>
          <tr>
            <th className="col-num">#</th>
            <th className="col-stage">Pipeline Stage</th>
            <th className="col-clock">Clock Domain</th>
            <th className="col-delta">Stage Delta</th>
            <th className="col-notes">Technical Details</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.num}>
              <td className="col-num"><span className="stage-num-badge">{row.num}</span></td>
              <td className="col-stage"><strong>{row.stage}</strong></td>
              <td className="col-clock"><span className="clock-badge">Backend (perf_counter)</span></td>
              <td className="col-delta"><span className="delta-value">{row.delta}</span></td>
              <td className="col-notes">{row.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
