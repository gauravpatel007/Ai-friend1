"""Conversation States and Latency Tracking for Advanced Real-Time Voice Conversation.

Defines the state machine states, lifecycle transitions, and latency measurement data
structures for Phase 8 continuous hands-free voice conversations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional


class ConversationState(Enum):
    """Conversation state machine states for real-time voice interaction (Phases 8 & 9).
    
    Strict State Machine Flow:
    SLEEPING (default initial state)
      -> WAKE_WORD_DETECTED
      -> LISTENING
      -> PROCESSING (or TRANSCRIBING + GENERATING_RESPONSE)
      -> SPEAKING
      -> RETURNING_TO_SLEEP
      -> SLEEPING
    """

    SLEEPING = "sleeping"                    # Strict sleep mode: resting default state
    WAKE_WORD_STANDBY = "sleeping"           # Backward-compatible alias for SLEEPING
    WAKE_WORD_DETECTED = "wake_word_detected"# Verified wake word detected
    LISTENING = "listening"                  # Mic active, waiting for user speech
    USER_SPEAKING = "user_speaking"          # VAD detected speech onset, recording utterance
    TRANSCRIBING = "transcribing"            # Whisper STT decoding user speech to text
    PROCESSING = "processing"                # STT + LLM processing unified state
    SUBMITTING_USER_MESSAGE = "submitting_user_message"  # Handoff from STT to chat submission handler
    GENERATING_RESPONSE = "generating_response"  # LLM inference in progress, awaiting tokens
    AI_THINKING = "generating_response"      # Backward-compatible alias for GENERATING_RESPONSE
    SPEAKING = "speaking"                    # Synthesizing and streaming audio with lip sync
    AI_SPEAKING = "speaking"                 # Backward-compatible alias for SPEAKING
    RETURNING_TO_SLEEP = "returning_to_sleep"# Response finished, transitioning back to sleep
    INTERRUPTED = "interrupted"              # User barge-in detected during playback
    MUTED = "muted"                          # Microphone input hardware- or software-muted
    MICROPHONE_UNAVAILABLE = "microphone_unavailable" # Audio input device missing or inaccessible
    CANCELED = "canceled"                    # Ongoing turn canceled or interrupted
    ERROR = "error"                          # Error encountered during processing
    IDLE = "idle"                            # Companion idle / voice conversation inactive
    DISABLED = "idle"                        # Backward-compatible alias for IDLE

    @classmethod
    def _missing_(cls, value: object) -> Optional["ConversationState"]:
        if isinstance(value, str):
            val = value.lower().strip()
            if val in ("disabled", "off", "inactive"):
                return cls.IDLE
            if val in ("ai_thinking", "thinking"):
                return cls.GENERATING_RESPONSE
            if val in ("ai_speaking",):
                return cls.SPEAKING
            if val in ("sleeping", "sleep", "wake_word_standby", "standby"):
                return cls.SLEEPING
            if val in ("wake_word_detected", "wake_detected"):
                return cls.WAKE_WORD_DETECTED
            if val in ("processing",):
                return cls.PROCESSING
            if val in ("returning_to_sleep", "return_to_sleep"):
                return cls.RETURNING_TO_SLEEP
            if val in ("interrupted", "barge_in", "barged_in"):
                return cls.INTERRUPTED
            if val in ("muted", "mute"):
                return cls.MUTED
            if val in ("microphone_unavailable", "mic_unavailable", "no_mic"):
                return cls.MICROPHONE_UNAVAILABLE
        return None


class VoiceActivationMode(Enum):
    """Voice activation modes supported by the assistant (Phase 9.8)."""

    PUSH_TO_TALK = "push_to_talk"  # Manual microphone hold-to-talk activation
    WAKE_WORD = "wake_word"        # Standby -> activates on 'Hey Buddy' -> conversation -> standby
    CONTINUOUS = "continuous"      # Continuous hands-free dialogue while enabled
    OFF = "off"                    # Microphone completely disabled


@dataclass
class ConversationLatencyMetrics:
    """Monotonic latency metrics recorded for a single voice conversation turn.

    Measures all 9 voice stages required for response-time monitoring:
    1. User starts speaking (t_speech_start)
    2. Speech ends (t_speech_end)
    3. Speech recognition starts (t_stt_start)
    4. Final transcript becomes available (t_transcript_ready)
    5. LLM starts generating (t_llm_start)
    6. First LLM token generated (t_first_token_gen)
    7. First TTS audio chunk generated (t_first_tts_audio)
    8. Audio playback begins (t_audio_playback_start)
    9. Complete response finishes playing (t_audio_playback_end)
    """

    turn_id: int
    request_id: str = ""
    session_id: str = ""
    input_language: str = "en"
    user_text: str = ""
    ai_text: str = ""
    user_speech_duration_s: float = 0.0

    # Monotonic timestamps (time.perf_counter())
    t_turn_start: float = field(default_factory=time.perf_counter)
    epoch_timestamp: float = field(default_factory=time.time)
    t_speech_start: float = 0.0
    t_speech_end: float = 0.0
    t_stt_start: float = 0.0
    t_transcript_ready: float = 0.0
    t_stt_completed: float = 0.0  # Alias for backward-compat
    t_backend_request_sent: float = 0.0
    t_backend_request_received: float = 0.0
    t_llm_start: float = 0.0
    t_first_token_gen: float = 0.0
    t_first_llm_token: float = 0.0  # Alias for backward-compat
    t_llm_completed: float = 0.0
    t_first_sentence_chunk: float = 0.0
    t_first_tts_audio: float = 0.0
    t_tts_completed: float = 0.0
    t_audio_playback_start: float = 0.0
    t_first_playback_started: float = 0.0  # Alias for backward-compat
    t_audio_playback_end: float = 0.0
    t_turn_completed: float = 0.0

    # Computed latencies (milliseconds) (Phase 3 10-point measurement)
    speech_detection_latency_ms: float = 0.0      # 1. Physical speech onset -> VAD trigger
    vad_endpoint_latency_ms: float = 0.0          # 2. Silence hangover -> End of speech confirmed
    stt_latency_ms: float = 0.0                   # 3. Whisper speech recognition duration
    backend_request_latency_ms: float = 0.0       # Dispatch latency
    llm_first_token_latency_ms: float = 0.0       # 4. LLM time to first token (TTFT)
    total_model_generation_ms: float = 0.0        # 5. Full LLM response generation duration
    tts_first_audio_latency_ms: float = 0.0       # 6. Sentence chunk -> First synthesized audio
    total_tts_generation_ms: float = 0.0          # 7. Total speech synthesis duration
    audio_playback_completion_ms: float = 0.0     # 8. Audio playback duration
    time_to_first_playback_ms: float = 0.0        # Speech end -> First sound heard
    barge_in_detection_ms: float = 0.0            # 9. Barge-in interruption detection duration
    audio_cancellation_ms: float = 0.0            # 10. Playback abort & queue purge duration
    total_turn_duration_ms: float = 0.0

    # Interruption tracking and diagnostics (Phase 3)
    interruption_count: int = 0
    interruption_events: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def transcription(self) -> str:
        """Alias for user_text representing the transcribed utterance (Phase 3)."""
        return self.user_text

    @transcription.setter
    def transcription(self, val: str) -> None:
        self.user_text = val

    @property
    def stt_duration_ms(self) -> float:
        return self.stt_latency_ms

    @stt_duration_ms.setter
    def stt_duration_ms(self, val: float) -> None:
        self.stt_latency_ms = val

    @property
    def first_token_latency_ms(self) -> float:
        return self.llm_first_token_latency_ms

    @first_token_latency_ms.setter
    def first_token_latency_ms(self, val: float) -> None:
        self.llm_first_token_latency_ms = val

    @property
    def llm_duration_ms(self) -> float:
        return self.total_model_generation_ms

    @llm_duration_ms.setter
    def llm_duration_ms(self, val: float) -> None:
        self.total_model_generation_ms = val

    @property
    def first_audio_latency_ms(self) -> float:
        return self.tts_first_audio_latency_ms

    @first_audio_latency_ms.setter
    def first_audio_latency_ms(self, val: float) -> None:
        self.tts_first_audio_latency_ms = val

    @property
    def total_tts_duration_ms(self) -> float:
        return self.total_tts_generation_ms

    @total_tts_duration_ms.setter
    def total_tts_duration_ms(self, val: float) -> None:
        self.total_tts_generation_ms = val

    def mark_speech_start(self) -> None:
        self.t_speech_start = time.perf_counter()

    def mark_speech_end(self, speech_duration_s: float = 0.0) -> None:
        now = time.perf_counter()
        self.t_speech_end = now
        if speech_duration_s <= 0.0 and self.t_speech_start > 0.0:
            speech_duration_s = max(0.0, now - self.t_speech_start)
        if self.t_speech_start == 0.0:
            self.t_speech_start = max(0.0, now - speech_duration_s)
        self.user_speech_duration_s = speech_duration_s

    def mark_stt_start(self) -> None:
        self.t_stt_start = time.perf_counter()

    def mark_stt_done(self, recognized_text: str) -> None:
        now = time.perf_counter()
        self.t_transcript_ready = now
        self.t_stt_completed = now
        self.user_text = recognized_text
        ref = self.t_stt_start if self.t_stt_start > 0.0 else self.t_speech_end
        if ref > 0.0:
            self.stt_latency_ms = (now - ref) * 1000.0

    def mark_backend_sent(self) -> None:
        if self.t_backend_request_sent == 0.0:
            self.t_backend_request_sent = time.perf_counter()

    def mark_backend_received(self) -> None:
        if self.t_backend_request_received == 0.0:
            self.t_backend_request_received = time.perf_counter()
            if self.t_backend_request_sent > 0.0:
                self.backend_request_latency_ms = (self.t_backend_request_received - self.t_backend_request_sent) * 1000.0

    def mark_llm_start(self) -> None:
        if self.t_llm_start == 0.0:
            self.t_llm_start = time.perf_counter()

    def mark_first_token(self) -> None:
        now = time.perf_counter()
        if self.t_first_token_gen == 0.0:
            self.t_first_token_gen = now
            self.t_first_llm_token = now
            ref_time = self.t_llm_start if self.t_llm_start > 0.0 else (
                self.t_backend_request_sent if self.t_backend_request_sent > 0.0 else self.t_stt_completed
            )
            if ref_time > 0.0:
                self.llm_first_token_latency_ms = (now - ref_time) * 1000.0

    def mark_llm_done(self) -> None:
        now = time.perf_counter()
        if self.t_llm_completed == 0.0:
            self.t_llm_completed = now
            ref_start = self.t_llm_start if self.t_llm_start > 0.0 else (
                self.t_backend_request_received if self.t_backend_request_received > 0.0 else self.t_stt_completed
            )
            if ref_start > 0.0:
                self.total_model_generation_ms = (now - ref_start) * 1000.0

    def mark_first_sentence(self) -> None:
        if self.t_first_sentence_chunk == 0.0:
            self.t_first_sentence_chunk = time.perf_counter()

    def mark_first_tts_audio(self) -> None:
        now = time.perf_counter()
        if self.t_first_tts_audio == 0.0:
            self.t_first_tts_audio = now
            ref = self.t_first_token_gen if self.t_first_token_gen > 0.0 else self.t_first_sentence_chunk
            if ref > 0.0:
                self.tts_first_audio_latency_ms = (now - ref) * 1000.0

    def mark_tts_done(self) -> None:
        now = time.perf_counter()
        if self.t_tts_completed == 0.0:
            self.t_tts_completed = now
            if self.t_first_sentence_chunk > 0.0:
                self.total_tts_generation_ms = (now - self.t_first_sentence_chunk) * 1000.0

    def mark_playback_started(self) -> None:
        now = time.perf_counter()
        if self.t_audio_playback_start == 0.0:
            self.t_audio_playback_start = now
            self.t_first_playback_started = now
            if self.t_speech_end > 0.0:
                self.time_to_first_playback_ms = (now - self.t_speech_end) * 1000.0

    def mark_playback_ended(self) -> None:
        now = time.perf_counter()
        self.t_audio_playback_end = now
        self.t_turn_completed = now
        if self.t_audio_playback_start > 0.0:
            self.audio_playback_completion_ms = (now - self.t_audio_playback_start) * 1000.0
        t0 = self.t_speech_start if self.t_speech_start > 0.0 else self.t_turn_start
        self.total_turn_duration_ms = (now - t0) * 1000.0

    def finish_turn(self, full_ai_text: str = "", full_response: str = "") -> None:
        now = time.perf_counter()
        if self.t_audio_playback_end == 0.0:
            self.t_audio_playback_end = now
            if self.t_audio_playback_start > 0.0:
                self.audio_playback_completion_ms = (now - self.t_audio_playback_start) * 1000.0
        self.t_turn_completed = now
        text = full_ai_text or full_response
        if text:
            self.ai_text = text
        t0 = self.t_speech_start if self.t_speech_start > 0.0 else self.t_turn_start
        self.total_turn_duration_ms = (now - t0) * 1000.0

    def record_interruption(
        self,
        reason: str = "user_speech",
        barge_in_ms: float = 0.0,
        cancellation_ms: float = 0.0,
        **kwargs: Any,
    ) -> None:
        """Record a validated barge-in interruption event (Phase 3)."""
        if "barge_in_ms" in kwargs:
            barge_in_ms = kwargs["barge_in_ms"]
        if "cancellation_ms" in kwargs:
            cancellation_ms = kwargs["cancellation_ms"]
        if "reason" in kwargs:
            reason = kwargs["reason"]

        self.interruption_count += 1
        self.barge_in_detection_ms = max(self.barge_in_detection_ms, barge_in_ms)
        self.audio_cancellation_ms = max(self.audio_cancellation_ms, cancellation_ms)
        self.interruption_events.append({
            "event_index": self.interruption_count,
            "timestamp": time.time(),
            "barge_in_detection_ms": round(barge_in_ms, 1),
            "audio_cancellation_ms": round(cancellation_ms, 1),
            "barge_in_ms": round(barge_in_ms, 1),
            "cancellation_ms": round(cancellation_ms, 1),
            "reason": reason,
            "trigger": reason,
        })

    def to_structured_log(self) -> Dict[str, Any]:
        """Produce structured timing log for this voice interaction (Phase 3).
        
        Excludes raw PCM audio buffers, personal memory dumps, and sensitive telemetry.
        """
        trans_safe = self.user_text.strip()
        if len(trans_safe) > 120:
            trans_safe = trans_safe[:117] + "..."

        return {
            "session_id": self.session_id or f"session_{self.turn_id}",
            "turn_id": self.turn_id,
            "input_language": self.input_language or "en",
            "transcription": trans_safe,
            "stt_duration_ms": round(self.stt_latency_ms, 1),
            "llm_first_token_ms": round(self.llm_first_token_latency_ms, 1),
            "llm_duration_ms": round(self.total_model_generation_ms, 1),
            "tts_first_chunk_ms": round(self.tts_first_audio_latency_ms, 1),
            "tts_duration_ms": round(self.total_tts_generation_ms, 1),
            "first_audible_ms": round(self.time_to_first_playback_ms, 1),
            "playback_completion_ms": round(self.audio_playback_completion_ms, 1),
            "total_response_duration_ms": round(self.total_turn_duration_ms, 1),
            "speech_detection_ms": round(self.speech_detection_latency_ms, 1),
            "vad_endpoint_ms": round(self.vad_endpoint_latency_ms, 1),
            "barge_in_detection_ms": round(self.barge_in_detection_ms, 1),
            "audio_cancellation_ms": round(self.audio_cancellation_ms, 1),
            "interruption_events": list(self.interruption_events),
            "interruption_count": self.interruption_count,
            "errors": self.error,
        }

    def to_telemetry_dict(self) -> Dict[str, Any]:
        """Produce structured monotonic telemetry dict for developer performance monitoring.

        Does NOT store raw audio buffers, PCM recordings, or full sensitive prompt text.
        """
        t0 = self.t_speech_start if self.t_speech_start > 0.0 else self.t_turn_start

        def delta(t: float) -> float:
            if t <= 0.0 or t0 <= 0.0:
                return 0.0
            return max(0.0, round((t - t0) * 1000.0, 1))

        t_speech_end_delta = delta(self.t_speech_end)
        t_stt_start_delta = delta(self.t_stt_start)
        t_trans_ready_delta = delta(self.t_transcript_ready)
        t_llm_start_delta = delta(self.t_llm_start)
        t_token_delta = delta(self.t_first_token_gen)
        t_tts_delta = delta(self.t_first_tts_audio)
        t_playback_start_delta = delta(self.t_audio_playback_start)
        t_playback_end_delta = delta(self.t_audio_playback_end or self.t_turn_completed)

        return {
            "request_id": self.request_id or f"vreq_{self.turn_id}",
            "turn_id": self.turn_id,
            "mode": "voice",
            "timestamp": int(self.epoch_timestamp * 1000),
            # Monotonic absolute timestamps
            "t_speech_start": self.t_speech_start,
            "t_speech_end": self.t_speech_end,
            "t_stt_start": self.t_stt_start,
            "t_transcript_ready": self.t_transcript_ready,
            "t_llm_start": self.t_llm_start,
            "t_first_token_gen": self.t_first_token_gen,
            "t_first_tts_audio": self.t_first_tts_audio,
            "t_audio_playback_start": self.t_audio_playback_start,
            "t_audio_playback_end": self.t_audio_playback_end or self.t_turn_completed,
            # Calculated stage deltas (ms)
            "user_speech_duration_ms": round(self.user_speech_duration_s * 1000.0, 1),
            "vad_speech_end_to_stt_ms": round(max(0.0, (self.t_stt_start - self.t_speech_end) * 1000.0), 1) if self.t_stt_start > 0.0 and self.t_speech_end > 0.0 else 0.0,
            "stt_duration_ms": round(max(0.0, t_trans_ready_delta - t_stt_start_delta), 1),
            "transcript_to_llm_ms": round(max(0.0, t_llm_start_delta - t_trans_ready_delta), 1),
            "llm_time_to_first_token_ms": round(max(0.0, t_token_delta - t_llm_start_delta), 1),
            "first_token_to_tts_chunk_ms": round(max(0.0, t_tts_delta - t_token_delta), 1),
            "tts_chunk_to_playback_ms": round(max(0.0, t_playback_start_delta - t_tts_delta), 1),
            "time_to_first_audible_ms": round(max(0.0, t_playback_start_delta - t_speech_end_delta), 1),
            "total_playback_duration_ms": round(max(0.0, t_playback_end_delta - t_playback_start_delta), 1),
            "total_voice_turn_ms": t_playback_end_delta,
            "timings": {
                "userStartsSpeaking": 0.0,
                "speechEnds": t_speech_end_delta,
                "speechRecognitionStarts": t_stt_start_delta,
                "finalTranscriptAvailable": t_trans_ready_delta,
                "llmStartsGenerating": t_llm_start_delta,
                "firstLlmTokenGenerated": t_token_delta,
                "firstTtsAudioGenerated": t_tts_delta,
                "audioPlaybackBegins": t_playback_start_delta,
                "completeResponseFinishesPlaying": t_playback_end_delta,
            },
            "metrics": {
                "speechDurationMs": round(self.user_speech_duration_s * 1000.0, 1),
                "sttRecognitionMs": round(max(0.0, t_trans_ready_delta - t_stt_start_delta), 1),
                "dispatchToLlmMs": round(max(0.0, t_llm_start_delta - t_trans_ready_delta), 1),
                "timeToFirstTokenMs": round(max(0.0, t_token_delta - t_llm_start_delta), 1),
                "ttsFirstChunkMs": round(max(0.0, t_tts_delta - t_token_delta), 1),
                "timeToFirstAudibleMs": round(max(0.0, t_playback_start_delta - t_speech_end_delta), 1),
                "totalPlaybackDurationMs": round(max(0.0, t_playback_end_delta - t_playback_start_delta), 1),
                "totalTurnDurationMs": t_playback_end_delta,
                "promptChars": len(self.user_text),
                "responseChars": len(self.ai_text),
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to legacy dictionary for logging and analytics."""
        return {
            "session_id": self.session_id or f"session_{self.turn_id}",
            "turn_id": self.turn_id,
            "request_id": self.request_id,
            "input_language": self.input_language,
            "transcription": self.user_text,
            "audio_capture_duration_s": round(self.user_speech_duration_s, 2),
            "user_speech_duration_s": round(self.user_speech_duration_s, 2),
            "speech_detection_latency_ms": round(self.speech_detection_latency_ms, 1),
            "vad_endpoint_latency_ms": round(self.vad_endpoint_latency_ms, 1),
            "speech_recognition_latency_ms": round(self.stt_latency_ms, 1),
            "stt_latency_ms": round(self.stt_latency_ms, 1),
            "stt_duration_ms": round(self.stt_latency_ms, 1),
            "backend_request_latency_ms": round(self.backend_request_latency_ms, 1),
            "model_time_to_first_output_ms": round(self.llm_first_token_latency_ms, 1),
            "llm_first_token_latency_ms": round(self.llm_first_token_latency_ms, 1),
            "first_token_latency_ms": round(self.llm_first_token_latency_ms, 1),
            "total_model_generation_ms": round(self.total_model_generation_ms, 1),
            "llm_duration_ms": round(self.total_model_generation_ms, 1),
            "tts_generation_time_ms": round(self.tts_first_audio_latency_ms, 1),
            "tts_first_audio_latency_ms": round(self.tts_first_audio_latency_ms, 1),
            "first_audio_latency_ms": round(self.tts_first_audio_latency_ms, 1),
            "total_tts_generation_ms": round(self.total_tts_generation_ms, 1),
            "total_tts_duration_ms": round(self.total_tts_generation_ms, 1),
            "time_to_first_audible_response_ms": round(self.time_to_first_playback_ms, 1),
            "time_to_first_playback_ms": round(self.time_to_first_playback_ms, 1),
            "audio_playback_completion_ms": round(self.audio_playback_completion_ms, 1),
            "barge_in_detection_ms": round(self.barge_in_detection_ms, 1),
            "audio_cancellation_ms": round(self.audio_cancellation_ms, 1),
            "interruption_count": self.interruption_count,
            "total_turn_duration_ms": round(self.total_turn_duration_ms, 1),
            "user_text": self.user_text,
            "ai_text": self.ai_text,
            "errors": self.error,
        }
