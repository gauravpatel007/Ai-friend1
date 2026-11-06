"""Voice Conversation Controller — Real-Time Voice Orchestrator with Interruption & Wake Word.

Implements Phase 8 & Phase 9 of the AI Desktop Friend roadmap:
- End-to-end continuous hands-free dialogue lifecycle.
- Real-time speech detection and user interruption handling during AI playback (Phase 9.1 - 9.4).
- OpenWakeWord integration, low-power standby mode, and inactivity countdown (Phase 9.5 - 9.7).
- Configurable activation modes (Push-to-Talk, Wake Word, Continuous, Off) without restart (Phase 9.8).
- Immediate emergency stop for listening and processing (Phase 9.9).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, QTimer

from app.ai.ai_service import AIService
from app.ai.cancellation import CancellationToken
from app.ai.thinking_filter import ThinkingFilter
from app.character.states import CharacterState
from app.core.signals import signals
from app.utils.logger import get_logger
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import (
    ConversationLatencyMetrics,
    ConversationState,
    VoiceActivationMode,
)
from app.voice.echo_suppressor import AcousticEchoSuppressor
from app.voice.interruption_manager import InterruptionConfig, InterruptionManager
from app.voice.microphone_manager import MicrophoneManager
from app.voice.sentence_chunker import SentenceChunker
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine
from app.voice.vad_engine import VADEngine, VADState
from app.voice.wake_word_engine import WakeWordConfig, WakeWordEngine
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine

logger = get_logger(__name__)


# ─── Phase 9 & Strict State Machine: Valid Conversation State Transitions ────
VALID_TRANSITIONS: Dict[ConversationState, Set[ConversationState]] = {
    ConversationState.SLEEPING: {
        ConversationState.WAKE_WORD_DETECTED,
        ConversationState.MUTED,
        ConversationState.MICROPHONE_UNAVAILABLE,
        ConversationState.IDLE,
        ConversationState.ERROR,
    },
    ConversationState.WAKE_WORD_STANDBY: {
        ConversationState.WAKE_WORD_DETECTED,
        ConversationState.LISTENING,
        ConversationState.MUTED,
        ConversationState.MICROPHONE_UNAVAILABLE,
        ConversationState.IDLE,
        ConversationState.ERROR,
    },
    ConversationState.WAKE_WORD_DETECTED: {
        ConversationState.LISTENING,
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.ERROR,
    },
    ConversationState.LISTENING: {
        ConversationState.USER_SPEAKING,
        ConversationState.TRANSCRIBING,
        ConversationState.PROCESSING,
        ConversationState.SPEAKING,
        ConversationState.INTERRUPTED,
        ConversationState.MUTED,
        ConversationState.MICROPHONE_UNAVAILABLE,
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.CANCELED,
        ConversationState.ERROR,
        ConversationState.IDLE,
    },
    ConversationState.USER_SPEAKING: {
        ConversationState.TRANSCRIBING,
        ConversationState.PROCESSING,
        ConversationState.LISTENING,
        ConversationState.INTERRUPTED,
        ConversationState.MUTED,
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.CANCELED,
        ConversationState.ERROR,
    },
    ConversationState.TRANSCRIBING: {
        ConversationState.SUBMITTING_USER_MESSAGE,
        ConversationState.GENERATING_RESPONSE,
        ConversationState.PROCESSING,
        ConversationState.SPEAKING,
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.CANCELED,
        ConversationState.ERROR,
        ConversationState.LISTENING,
        ConversationState.IDLE,
    },
    ConversationState.PROCESSING: {
        ConversationState.SUBMITTING_USER_MESSAGE,
        ConversationState.GENERATING_RESPONSE,
        ConversationState.SPEAKING,
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.CANCELED,
        ConversationState.ERROR,
    },
    ConversationState.SUBMITTING_USER_MESSAGE: {
        ConversationState.GENERATING_RESPONSE,
        ConversationState.PROCESSING,
        ConversationState.SPEAKING,
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.CANCELED,
        ConversationState.ERROR,
        ConversationState.LISTENING,
        ConversationState.IDLE,
    },
    ConversationState.GENERATING_RESPONSE: {
        ConversationState.SPEAKING,
        ConversationState.USER_SPEAKING,
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.CANCELED,
        ConversationState.ERROR,
    },
    ConversationState.SPEAKING: {
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.USER_SPEAKING,
        ConversationState.INTERRUPTED,
        ConversationState.CANCELED,
        ConversationState.ERROR,
        ConversationState.LISTENING,
    },
    ConversationState.INTERRUPTED: {
        ConversationState.USER_SPEAKING,
        ConversationState.LISTENING,
        ConversationState.PROCESSING,
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.IDLE,
        ConversationState.ERROR,
    },
    ConversationState.MUTED: {
        ConversationState.LISTENING,
        ConversationState.SLEEPING,
        ConversationState.IDLE,
        ConversationState.ERROR,
    },
    ConversationState.MICROPHONE_UNAVAILABLE: {
        ConversationState.IDLE,
        ConversationState.ERROR,
        ConversationState.LISTENING,
    },
    ConversationState.RETURNING_TO_SLEEP: {
        ConversationState.SLEEPING,
        ConversationState.WAKE_WORD_DETECTED,
        ConversationState.IDLE,
        ConversationState.ERROR,
    },
    ConversationState.CANCELED: {
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.LISTENING,
        ConversationState.IDLE,
        ConversationState.ERROR,
    },
    ConversationState.ERROR: {
        ConversationState.RETURNING_TO_SLEEP,
        ConversationState.SLEEPING,
        ConversationState.IDLE,
    },
    ConversationState.IDLE: {
        ConversationState.SLEEPING,
        ConversationState.WAKE_WORD_DETECTED,
        ConversationState.LISTENING,
        ConversationState.SPEAKING,
        ConversationState.USER_SPEAKING,
        ConversationState.MUTED,
        ConversationState.MICROPHONE_UNAVAILABLE,
        ConversationState.ERROR,
    },
}


class VoiceConversationController(QObject):
    """Central orchestrator for real-time continuous voice conversations, interruptions, and wake-word control."""

    # State Machine and Lifecycle Signals (Phase 8.2 & 9.7)
    state_changed = Signal(object)                  # ConversationState
    activation_mode_changed = Signal(str)           # "push_to_talk", "wake_word", "continuous", "off"
    speech_started = Signal()                       # User speech onset detected
    speech_ended = Signal(float)                    # Utterance completed (duration in seconds)
    transcription_ready = Signal(str, str)          # (recognized_text, language_code)
    interim_transcription_ready = Signal(str)       # Progressive interim recognized user text
    turn_started = Signal(int)                      # turn_id
    turn_completed = Signal(int)                    # turn_id
    sentence_chunk_produced = Signal(int, int, str) # (turn_id, chunk_index, sentence_text)
    latency_measured = Signal(dict)                 # ConversationLatencyMetrics as dict (Phase 8.9)
    interruption_triggered = Signal(int)            # turn_id that was interrupted
    wake_word_triggered = Signal(str, float)        # (phrase, score)
    emergency_stopped = Signal()                    # Emergency stop fired
    error_occurred = Signal(str)

    def __init__(
        self,
        mic_manager: Optional[MicrophoneManager] = None,
        vad_engine: Optional[VADEngine] = None,
        whisper_engine: Optional[WhisperEngine] = None,
        audio_player: Optional[AudioPlayer] = None,
        tts_engine: Optional[BaseTTSEngine] = None,
        ai_service: Optional[Any] = None,
        interruption_manager: Optional[InterruptionManager] = None,
        wake_word_engine: Optional[WakeWordEngine] = None,
        language: Optional[str] = None,
        activation_mode: VoiceActivationMode = VoiceActivationMode.CONTINUOUS,
        parent: Optional[QObject] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)
        self.mic_manager = mic_manager if mic_manager is not None else MicrophoneManager(parent=self)
        self.vad_engine = vad_engine if vad_engine is not None else VADEngine(parent=self)
        self.whisper_engine = whisper_engine if whisper_engine is not None else WhisperEngine(parent=self)
        self.audio_player = audio_player if audio_player is not None else AudioPlayer(parent=self)

        if tts_engine is not None:
            self.tts_engine = tts_engine
        else:
            try:
                from app.voice.sapi5_engine import Sapi5TTSEngine
                from app.voice.piper_engine import PiperTTSEngine
                sapi = Sapi5TTSEngine(parent=self)
                piper = PiperTTSEngine(fallback_engine=sapi, parent=self)
                if piper.is_available():
                    self.tts_engine = piper
                elif sapi.is_available():
                    self.tts_engine = sapi
                else:
                    self.tts_engine = piper
            except Exception as e:
                logger.warning("Could not initialize default TTS engine fallback: %s", e)
                from app.voice.tts_base import BaseTTSEngine as _BaseTTS, SynthesizedAudio as _SynAudio

                class _StubTTSEngine(_BaseTTS):
                    def synthesize(self, text: str, **kw: Any) -> _SynAudio:
                        return _SynAudio(
                            samples=np.zeros(1600, dtype=np.float32),
                            sample_rate=16000,
                            duration_seconds=0.1,
                            text=text,
                            voice_name="stub",
                        )

                    def is_available(self) -> bool:
                        return False

                self.tts_engine = _StubTTSEngine(parent=self)

        self.ai_service = ai_service
        self.language = language

        # State machine & activation mode (Phase 9.8)
        self._state = ConversationState.DISABLED
        if isinstance(activation_mode, str):
            try:
                self._activation_mode = VoiceActivationMode(activation_mode.lower().strip())
            except ValueError:
                self._activation_mode = VoiceActivationMode.WAKE_WORD
        else:
            self._activation_mode = activation_mode or VoiceActivationMode.WAKE_WORD

        self.auto_return_to_sleep: bool = kwargs.get("auto_return_to_sleep", (self._activation_mode == VoiceActivationMode.WAKE_WORD))
        self.wake_timeout_sec: float = float(kwargs.get("wake_timeout_sec", 6.0))
        self._turn_id: int = 0
        self._lock = threading.Lock()
        self.enable_direct_ai_dispatch: bool = True

        # Structured Session Tracking (Phase 3)
        self.session_id: str = kwargs.get("session_id") or f"vsession_{int(time.time())}"
        self._recent_timing_logs: list[dict[str, Any]] = []

        # Selected Voice Profile (Phase 1)
        self.selected_voice_profile: str = kwargs.get("selected_voice_profile", "arjun")
        if hasattr(self, "ai_service") and self.ai_service and getattr(self.ai_service, "config_manager", None):
            self.selected_voice_profile = self.ai_service.config_manager.get("voice.selected_profile", "arjun")
        signals.voice_profile_changed.connect(self.set_voice_profile)

        # Sentence chunking and audio pipelining (Phase 8.5, 8.6)
        self.sentence_chunker = SentenceChunker()
        self.thinking_filter = ThinkingFilter()
        self.audio_queue = StreamingAudioQueue(
            audio_player=self.audio_player,
            tts_engine=self.tts_engine,
            parent=self,
        )

        # Interruption Management (Phase 9.1 - 9.4)
        self.interruption_manager = interruption_manager or InterruptionManager(
            audio_player=self.audio_player,
            vad_engine=self.vad_engine,
            parent=self,
        )

        # Wake-Word Detection & Standby Lifecycle (Phase 9.5 - 9.7)
        if wake_word_engine is None:
            self.wake_word_engine = WakeWordEngine(
                whisper_engine=self.whisper_engine,
                vad_engine=self.vad_engine,
                parent=self,
            )
        else:
            self.wake_word_engine = wake_word_engine
            if getattr(self.wake_word_engine, "whisper_engine", None) is None and self.whisper_engine:
                self.wake_word_engine.whisper_engine = self.whisper_engine
            if getattr(self.wake_word_engine, "vad_engine", None) is None and self.vad_engine:
                self.wake_word_engine.vad_engine = self.vad_engine

        # Voice Command & Intent Dispatcher (Phase 8 Voice Commands)
        from app.voice.command_dispatcher import VoiceCommandDispatcher
        self.command_dispatcher: VoiceCommandDispatcher = VoiceCommandDispatcher(
            ai_service=self.ai_service,
            parent=self,
        )

        # Active turn tracking and latency metrics (Phase 8.8, 8.9)
        self._active_metrics: Optional[ConversationLatencyMetrics] = None
        self._accumulated_ai_response: list[str] = []
        self._active_cancellation_token: Optional[CancellationToken] = None
        self._last_user_transcript: str = ""
        self._last_user_transcript_time: float = 0.0
        self._last_assistant_response: str = ""
        self._processed_turn_ids: set[int] = set()
        self._is_shutdown: bool = False

        # Real-time Progressive Interim Transcription (Phase 1)
        self._interim_generation_id: int = 0
        self._is_interim_transcribing: bool = False
        self._last_interim_dispatch_time: float = 0.0
        self._interim_frame_count: int = 0
        self._frames_since_last_interim: int = 0
        self._last_interim_text: str = ""

        # Acoustic Feedback Echo Suppressor (Phase 8 & 9 Echo Suppression)
        self.echo_suppressor = AcousticEchoSuppressor()

        # Acoustic Echo Canceller & Reference Signal Tracker (Phase 9 AEC)
        from app.voice.acoustic_echo_canceller import AcousticEchoCanceller
        self.echo_canceller = AcousticEchoCanceller(parent=self)
        self.enable_barge_in: bool = True
        self.enable_direct_ai_dispatch: bool = (ai_service is not None)

        # Context-Aware Interruption Tracking (Phase 4)
        self._active_interruption_snapshot: Optional[Any] = None
        self._interrupted_user_query: str = ""
        self._current_turn_user_prompt: str = ""
        self._interrupted_turn_id: Optional[int] = None

        # Phase 9 State Machine Watchdogs & Bounded Retry Tracking
        self._consecutive_error_count: int = 0
        self._utterance_timer: Optional[QTimer] = None
        self._generation_watchdog_timer: Optional[QTimer] = None
        self._stt_watchdog_timer: Optional[QTimer] = None
        self._error_recovery_timer: Optional[QTimer] = None

        # Return-to-sleep silence countdown timer
        self._wake_silence_timer = QTimer(self)
        self._wake_silence_timer.setSingleShot(True)
        self._wake_silence_timer.timeout.connect(self._on_wake_silence_timeout)

        # Wire VAD, Interruption, Wake-Word, Audio Queue, and Playback signals
        self._internal_connections: list = []
        self._global_connections: list = []
        self._wire_signals()

        # Subscribe to microphone stream for continuous & interruption frame routing
        self.mic_manager.subscribe(self.process_mic_frame)

    # ─── Initialization and Wiring ──────────────────────────────────────

    def _wire_signals(self) -> None:
        """Connect internal pipelines and event handlers."""
        self._internal_connections = [
            # VAD hooks
            self.vad_engine.speech_started.connect(self._on_vad_speech_started),
            self.vad_engine.speech_ended.connect(self._on_vad_speech_ended),

            # STT & Player error hooks
            self.whisper_engine.error_occurred.connect(lambda err: self._on_pipeline_error(err, stage="stt")),
            self.audio_player.error_occurred.connect(lambda err: self._on_pipeline_error(err, stage="tts")),

            # Audio Player hooks (ensures controller is in AI_SPEAKING during all playback)
            self.audio_player.playback_started.connect(self._on_audio_player_started),
            self.audio_player.playback_finished.connect(self._on_audio_player_finished),
            self.audio_player.playback_stopped.connect(self._on_audio_player_finished),

            # Echo suppressor & AEC playback tracking
            self.audio_player.playback_started.connect(self.echo_suppressor.mark_playback_started),
            self.audio_player.playback_finished.connect(self.echo_suppressor.mark_playback_ended),
            self.audio_player.playback_stopped.connect(self.echo_suppressor.mark_playback_ended),
            self.audio_player.playback_started.connect(self.echo_canceller.mark_playback_started),
            self.audio_player.playback_finished.connect(self.echo_canceller.mark_playback_stopped),
            self.audio_player.playback_stopped.connect(self.echo_canceller.mark_playback_stopped),
            self.audio_player.playback_reference_ready.connect(self.echo_canceller.feed_reference_audio),
            self.audio_player.device_changed.connect(lambda dev: self.echo_canceller.detect_device_mode(dev)),

            # Audio Queue hooks
            self.audio_queue.chunk_synthesized.connect(self._on_chunk_synthesized),
            self.audio_queue.chunk_playback_started.connect(self._on_chunk_playback_started),
            self.audio_queue.all_chunks_played.connect(self._on_all_speech_played),
            self.audio_queue.error_occurred.connect(self.error_occurred.emit),

            # Phase 9: Interruption & Wake-Word hooks
            self.interruption_manager.interruption_detected.connect(self._on_interruption_detected),
            self.wake_word_engine.wake_word_detected.connect(self._on_wake_word_detected),
            self.wake_word_engine.inactivity_timeout.connect(self._on_wake_word_inactivity_timeout),
            self.vad_engine.no_speech_detected.connect(self._on_vad_no_speech_detected),
        ]

    def __del__(self) -> None:
        try:
            self.cleanup()
        except Exception:
            pass

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    @property
    def state(self) -> ConversationState:
        return self._state

    @property
    def activation_mode(self) -> VoiceActivationMode:
        return self._activation_mode

    @property
    def is_enabled(self) -> bool:
        return self._state != ConversationState.DISABLED

    @property
    def current_turn_id(self) -> int:
        return self._turn_id

    def set_tts_engine(self, engine: BaseTTSEngine) -> None:
        """Update active TTS synthesis engine and synchronize with audio queue."""
        if engine is not None:
            self.tts_engine = engine
            if hasattr(self, "audio_queue") and self.audio_queue is not None:
                self.audio_queue.tts_engine = engine

    def set_echo_mode(self, mode: str) -> None:
        """Set acoustic echo handling profile ('speaker', 'headset', 'auto')."""
        if hasattr(self, "echo_canceller") and self.echo_canceller:
            self.echo_canceller.set_echo_mode(mode)
        if hasattr(self, "interruption_manager") and self.interruption_manager:
            self.interruption_manager.set_echo_mode(mode)

    def set_silence_threshold_ms(self, threshold_ms: int) -> None:
        """Configure VAD end-of-speech silence detection timeout in milliseconds."""
        if hasattr(self, "vad_engine") and self.vad_engine:
            self.vad_engine.set_silence_threshold(threshold_ms)

    # ─── Configurable Activation Modes (Phase 9.8) ──────────────────────

    def set_activation_mode(self, mode: VoiceActivationMode | str) -> None:
        """Switch between activation modes ('push_to_talk', 'wake_word', 'continuous', 'off') dynamically."""
        if isinstance(mode, str):
            try:
                mode = VoiceActivationMode(mode.lower().strip())
            except ValueError:
                mode = VoiceActivationMode.OFF

        if self._activation_mode == mode and self.is_enabled:
            return

        prev_str = self._activation_mode.value if hasattr(self._activation_mode, "value") else str(self._activation_mode)
        new_str = mode.value if hasattr(mode, "value") else str(mode)
        logger.info("Switching voice activation mode: %s -> %s", prev_str, new_str)
        self._activation_mode = mode
        self.activation_mode_changed.emit(mode.value)
        signals.activation_mode_changed.emit(mode.value)

        if mode == VoiceActivationMode.OFF:
            self.emergency_stop()
        elif mode == VoiceActivationMode.WAKE_WORD:
            self.auto_return_to_sleep = True
            self.enable()
            self.wake_word_engine.enable()
            self._transition_to(ConversationState.SLEEPING)
        elif mode == VoiceActivationMode.CONTINUOUS:
            self.auto_return_to_sleep = False
            self.wake_word_engine.disable()
            self.enable()
            self._transition_to(ConversationState.LISTENING)
        elif mode == VoiceActivationMode.PUSH_TO_TALK:
            self.wake_word_engine.disable()
            self.disable()

    # ─── Lifecycle: Enable / Disable (Phase 8.3 & 9.6) ───────────────────

    def enable(self) -> bool:
        """Activate hands-free voice conversation mode."""
        if self._is_shutdown:
            logger.debug("VoiceConversationController enable rejected: controller is shut down.")
            return False

        if self._activation_mode == VoiceActivationMode.WAKE_WORD:
            self.wake_word_engine.enable()

        if self._state not in (ConversationState.DISABLED, ConversationState.IDLE):
            return True

        logger.info("Enabling voice conversation orchestrator in '%s' mode...", self._activation_mode.value)
        self.vad_engine.reset_states()
        ok = self.mic_manager.start_recording()
        if not ok:
            status = getattr(self.mic_manager, "last_status", "unavailable")
            if status == "permission_denied":
                err_msg = "Microphone permission denied. Please allow microphone access in Windows Settings > Privacy & security > Microphone."
            else:
                err_msg = "Microphone unavailable: No active audio input device detected."
            logger.error("[DIAGNOSTIC] %s", err_msg)
            self._transition_to(ConversationState.MICROPHONE_UNAVAILABLE)
            self.error_occurred.emit(err_msg)
            return False

        # Connect global AI streaming and bus signals
        try:
            self._global_connections = [
                signals.ai_response_chunk.connect(self._on_ai_stream_chunk),
                signals.ai_response_complete.connect(self._on_ai_stream_complete),
                signals.ai_cancel_requested.connect(self.cancel_current_turn),
                signals.emergency_stop_requested.connect(self.emergency_stop),
                signals.ai_error_occurred.connect(lambda err: self._on_pipeline_error(err, stage="llm")),
            ]
        except Exception:
            pass

        if self._activation_mode == VoiceActivationMode.WAKE_WORD:
            self.wake_word_engine.enable()
            self._transition_to(ConversationState.WAKE_WORD_STANDBY)
        else:
            self._transition_to(ConversationState.LISTENING)

        return True

    def disable(self) -> None:
        """Deactivate hands-free voice conversation mode and release resources."""
        if self._state == ConversationState.DISABLED:
            return

        logger.info("Disabling voice conversation orchestrator...")
        self.cancel_current_turn()
        self.mic_manager.stop_recording()
        self.audio_player.stop()
        self.audio_queue.clear()
        self.wake_word_engine.disable()

        # Disconnect global signals cleanly
        if hasattr(self, "_global_connections"):
            for conn in self._global_connections:
                try:
                    QObject.disconnect(conn)
                except Exception:
                    pass
            self._global_connections.clear()

        self._transition_to(ConversationState.DISABLED)

    def cleanup(self) -> None:
        """Fully detach controller and release internal and global signal connections."""
        self._is_shutdown = True
        self.emergency_stop()
        self.disable()
        try:
            self.mic_manager.unsubscribe(self.process_mic_frame)
        except Exception:
            pass
        self.audio_queue.shutdown()

        if hasattr(self, "_internal_connections"):
            for conn in self._internal_connections:
                try:
                    QObject.disconnect(conn)
                except Exception:
                    pass
            self._internal_connections.clear()

    @Slot(str)
    def set_voice_profile(self, profile_id: str) -> None:
        """Switch active voice profile dynamically without restarting Bond (Phase 1.3)."""
        from app.voice.voice_registry import get_voice_profile
        profile = get_voice_profile(profile_id)
        if getattr(self, "selected_voice_profile", None) == profile.profile_id:
            return
        self.selected_voice_profile = profile.profile_id
        logger.info(
            "VoiceConversationController: Switched voice profile to '%s' (%s, engine=%s, voice=%s)",
            profile.name,
            profile.gender,
            profile.primary_engine,
            profile.primary_voice_id,
        )
        if self.tts_engine and hasattr(self.tts_engine, "load_model"):
            try:
                self.tts_engine.load_model(profile.primary_voice_id)
            except Exception as e:
                logger.debug("TTS engine load_model note on voice profile switch: %s", e)

    def set_tts_engine(self, engine: BaseTTSEngine) -> None:
        """Dynamically update active TTS engine."""
        self.tts_engine = engine
        if hasattr(self, "audio_queue") and self.audio_queue:
            self.audio_queue.tts_engine = engine
        if hasattr(self, "selected_voice_profile") and self.selected_voice_profile:
            self.set_voice_profile(self.selected_voice_profile)

    def get_recent_timing_logs(self) -> list[dict[str, Any]]:
        """Return structured timing logs recorded for recent voice interactions (Phase 3)."""
        return list(self._recent_timing_logs)

    # ─── Emergency Stop (Phase 9.9) ─────────────────────────────────────

    def emergency_stop(self) -> None:
        """Provide an immediate, guaranteed stop for microphone capture, audio, and active turns."""
        logger.warning("[DIAGNOSTIC] Errors and cancellations: Emergency stop triggered.")
        logger.warning("[EMERGENCY STOP ACTIVATED] Halting all voice capture, playback, and inference.")
        self.cancel_current_turn()
        self._stop_utterance_watchdog()
        self._stop_generation_watchdog()
        self._stop_stt_watchdog()
        if hasattr(self, "_error_recovery_timer") and self._error_recovery_timer:
            try:
                self._error_recovery_timer.stop()
            except Exception:
                pass
        self.audio_queue.emergency_stop()
        self.audio_player.emergency_stop()
        self.mic_manager.emergency_stop()
        if hasattr(self, "echo_canceller"):
            self.echo_canceller.reset()
        self.wake_word_engine.disable()
        self.vad_engine.reset_states()
        self._consecutive_error_count = 0
        self._transition_to(ConversationState.IDLE)

        # Reset UI and character indicators immediately
        signals.character_state_changed.emit(CharacterState.IDLE.name.lower())
        signals.voice_state_changed.emit("off")
        self.emergency_stopped.emit()
        signals.ai_speech_finished.emit()

    @Slot()
    def _on_audio_player_started(self) -> None:
        """Invoked when AudioPlayer begins output playback (e.g. TTS speech or test audio)."""
        self._stop_generation_watchdog()
        if hasattr(self, "wake_word_engine") and self.wake_word_engine:
            self.wake_word_engine.is_speaking = True
            self.wake_word_engine.audio_player_is_playing = True
        if self._state not in (ConversationState.IDLE, ConversationState.DISABLED, ConversationState.SPEAKING):
            self._transition_to(ConversationState.SPEAKING)

    @Slot()
    def _on_audio_player_finished(self) -> None:
        """Invoked when AudioPlayer stops or finishes playing output audio."""
        if hasattr(self, "wake_word_engine") and self.wake_word_engine:
            self.wake_word_engine.is_speaking = False
            self.wake_word_engine.audio_player_is_playing = False

        if self._state in (ConversationState.INTERRUPTED, ConversationState.USER_SPEAKING):
            return

        if self._state in (ConversationState.SPEAKING, ConversationState.AI_SPEAKING):
            # If the streaming audio queue is active with pending or currently synthesizing chunks,
            # let the queue and `_on_all_speech_played` handle completion!
            if (
                not self.audio_queue.is_empty
                or getattr(self.audio_queue, "_is_playing_chunk", False)
                or getattr(self.audio_queue, "_is_synthesizing", False)
            ):
                return

            decay_delay_ms = 200 if getattr(getattr(self, "echo_canceller", None), "echo_mode", "speaker") == "headset" else 350
            def resume_listening() -> None:
                if self._state not in (ConversationState.DISABLED, ConversationState.IDLE, ConversationState.USER_SPEAKING):
                    self.vad_engine.reset_states()
                    if self._activation_mode == VoiceActivationMode.CONTINUOUS and not getattr(self, "auto_return_to_sleep", True):
                        self._transition_to(ConversationState.LISTENING)
                    else:
                        self._return_to_sleep(reason="audio_player_finished")

            QTimer.singleShot(decay_delay_ms, resume_listening)

    # ─── Frame Routing: VAD, Wake Word & Interruption (Phase 9.1) ──────

    def set_muted(self, muted: bool) -> None:
        """Set software mute state (Phase 8.4)."""
        self._is_muted = muted
        if muted:
            self.vad_engine.reset_states()
            self._transition_to(ConversationState.MUTED)
        else:
            if self._activation_mode == VoiceActivationMode.WAKE_WORD:
                self._transition_to(ConversationState.SLEEPING)
            else:
                self._transition_to(ConversationState.LISTENING)

    def process_mic_frame(self, chunk: np.ndarray) -> None:
        """Route incoming microphone frame according to active state and mode."""
        if (
            self._is_shutdown
            or getattr(self, "_is_muted", False)
            or self._state in (
                ConversationState.DISABLED,
                ConversationState.IDLE,
                ConversationState.MUTED,
                ConversationState.MICROPHONE_UNAVAILABLE,
            )
        ):
            return

        effective_echo_mode = getattr(self.echo_canceller, "echo_mode", "speaker") if hasattr(self, "echo_canceller") else "speaker"
        cooldown_limit = 0.20 if effective_echo_mode == "headset" else 0.35

        # Check central AEC and playback tracking
        is_playing = (
            self.audio_player.is_playing
            or (hasattr(self, "echo_canceller") and self.echo_canceller.is_playing)
        )
        is_cooldown = (
            self.audio_player.is_in_cooldown(cooldown_limit)
            or self.echo_suppressor.is_in_decay_window
            or (hasattr(self, "echo_canceller") and self.echo_canceller.is_in_cooldown(cooldown_limit))
        )
        is_speaking_state = self._state in (ConversationState.SPEAKING, ConversationState.AI_SPEAKING)
        is_thinking_state = self._state in (
            ConversationState.GENERATING_RESPONSE,
            ConversationState.AI_THINKING,
            ConversationState.TRANSCRIBING,
            ConversationState.SUBMITTING_USER_MESSAGE,
        )
        is_queue_active = (
            getattr(self.audio_queue, "_is_playing_chunk", False)
            or getattr(self.audio_queue, "_is_synthesizing", False)
            or not self.audio_queue.is_empty
        )

        # 1. Microphone Gating during TTS playback and acoustic decay cooldown:
        # Prevents microphone input from capturing the AI's own speech and causing feedback loops!
        if is_playing or is_cooldown or (is_speaking_state and is_queue_active):
            if not is_playing and self._state == ConversationState.USER_SPEAKING:
                # Do not discard active user speech if playback is not active
                pass
            else:
                self.vad_engine.reset_states()
                # Barge-in support: verified sustained user speech interruption
                if is_speaking_state and getattr(self, "enable_barge_in", True):
                    if hasattr(self, "echo_canceller") and self.echo_canceller:
                        analysis = self.echo_canceller.analyze_mic_frame(chunk)
                        if not analysis.is_echo:
                            self.interruption_manager.process_mic_frame(chunk, self._turn_id)
                    else:
                        self.interruption_manager.process_mic_frame(chunk, self._turn_id)
                return

        # 2. Gate mic frames during speech recognition, submission, and model generation
        if is_thinking_state:
            self.vad_engine.reset_states()
            return

        # Strict Wake-Word Standby / Sleep Mode (ultra-low CPU keyword detection)
        if (
            self._activation_mode == VoiceActivationMode.WAKE_WORD
            and self._state in (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY)
        ):
            self.wake_word_engine.process_frame(chunk)
            return

        # Normal active listening & utterance recording: route to VAD engine
        if self._state == ConversationState.USER_SPEAKING:
            self.vad_engine.process_frame(chunk)
            self._interim_frame_count += 1
            self._frames_since_last_interim += 1

            # Auto-recovery watchdog: release interim lock if in-flight pass took > 1.5 seconds
            if self._is_interim_transcribing and (time.monotonic() - getattr(self, "_last_interim_dispatch_time", 0.0) > 1.5):
                logger.warning("Interim transcription pass exceeded 1.5s timeout; resetting lock.")
                self._is_interim_transcribing = False

            # Real-time word-by-word streaming: trigger interim Whisper pass every ~96-128ms (>=3 frames)
            # or on frame cadence, as soon as the previous greedy pass completes
            if (self._frames_since_last_interim >= 3 or self._interim_frame_count % 12 == 0) and not self._is_interim_transcribing:
                buf = self.vad_engine.get_current_speech_buffer()
                if buf is not None and len(buf) >= 2048:
                    self._is_interim_transcribing = True
                    self._last_interim_dispatch_time = time.monotonic()
                    self._frames_since_last_interim = 0
                    gen_id = self._interim_generation_id
                    effective_lang = self.language if (self.language and self.language != "auto") else None
                    self.whisper_engine.transcribe_interim_async(
                        audio_data=buf,
                        generation_id=gen_id,
                        language=effective_lang,
                        callback=self._on_interim_transcription_ready,
                    )
        elif self._state == ConversationState.LISTENING:
            self.vad_engine.process_frame(chunk)

    # ─── State Machine Transitions (Phase 8.2 & 9.7) ────────────────────

    def _transition_to(self, new_state: ConversationState) -> bool:
        """Execute state transition with desktop companion character animation sync."""
        with self._lock:
            prev_state = self._state
            if prev_state == new_state:
                return True

            valid_targets = VALID_TRANSITIONS.get(prev_state, set())
            if (
                valid_targets
                and new_state not in valid_targets
                and new_state not in (ConversationState.ERROR, ConversationState.CANCELED, ConversationState.IDLE)
            ):
                logger.warning(
                    "[STATE_MACHINE] Blocked unauthorized transition from %s to %s: not permitted in strict state flow. Permitted targets: %s",
                    prev_state.value,
                    new_state.value,
                    [s.value for s in valid_targets],
                )
                return False

            self._state = new_state

        logger.info("[STATE_MACHINE] Conversation state transition: %s -> %s", prev_state.value, new_state.value)
        self.state_changed.emit(new_state)
        signals.voice_state_changed.emit(new_state.value)

        # Inactivity timer management during active wake-word conversation
        if self._activation_mode == VoiceActivationMode.WAKE_WORD:
            if new_state in (ConversationState.GENERATING_RESPONSE, ConversationState.SPEAKING):
                self.wake_word_engine.pause_inactivity_timer()
            elif new_state == ConversationState.LISTENING:
                self.wake_word_engine.reset_inactivity_timer()
            elif new_state == ConversationState.USER_SPEAKING:
                self.wake_word_engine.reset_inactivity_timer()

        # Synchronize desktop companion character visual state
        if new_state in (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY, ConversationState.RETURNING_TO_SLEEP):
            signals.character_state_changed.emit(CharacterState.SLEEPING.name.lower())
            signals.app_mode_changed.emit("sleeping")
        elif new_state in (ConversationState.LISTENING, ConversationState.WAKE_WORD_DETECTED):
            signals.character_state_changed.emit(CharacterState.LISTENING.name.lower())
        elif new_state in (ConversationState.USER_SPEAKING, ConversationState.INTERRUPTED):
            signals.character_state_changed.emit(CharacterState.LISTENING.name.lower())
        elif new_state in (ConversationState.TRANSCRIBING, ConversationState.PROCESSING, ConversationState.SUBMITTING_USER_MESSAGE, ConversationState.GENERATING_RESPONSE):
            signals.character_state_changed.emit(CharacterState.THINKING.name.lower())
        elif new_state == ConversationState.SPEAKING:
            signals.character_state_changed.emit(CharacterState.SPEAKING.name.lower())
        elif new_state in (ConversationState.ERROR, ConversationState.MICROPHONE_UNAVAILABLE):
            signals.character_state_changed.emit(CharacterState.ERROR.name.lower())
        elif new_state in (ConversationState.IDLE, ConversationState.CANCELED, ConversationState.MUTED):
            signals.character_state_changed.emit(CharacterState.IDLE.name.lower())
        return True

    # ─── Strict Return-to-Sleep Helper ─────────────────────────────────

    def _return_to_sleep(self, reason: str = "normal") -> None:
        """Safely transition through RETURNING_TO_SLEEP back to resting SLEEP MODE."""
        if hasattr(self, "_wake_silence_timer") and self._wake_silence_timer:
            self._wake_silence_timer.stop()

        with self._lock:
            if self._state in (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY):
                return

        logger.info("[LIFECYCLE] Returning to SLEEP MODE (reason: '%s')", reason)
        self._transition_to(ConversationState.RETURNING_TO_SLEEP)
        self._transition_to(ConversationState.SLEEPING)

        if hasattr(self, "wake_word_engine") and self.wake_word_engine:
            self.wake_word_engine.is_speaking = False
            self.wake_word_engine.enter_standby()

        if hasattr(self, "vad_engine") and self.vad_engine:
            self.vad_engine.reset_states()

        signals.character_state_changed.emit(CharacterState.SLEEPING.name.lower())
        signals.app_mode_changed.emit("sleeping")

        try:
            from app.core.buddy_state_manager import get_buddy_state_manager
            get_buddy_state_manager().enter_sleep(reason=reason)
        except Exception:
            pass

    # ─── Phase 9 & Strict Wake-Word Standby Lifecycle ──────────────────

    def _on_wake_word_detected(self, phrase: str, score: float) -> None:
        """Invoked when user utters the activation phrase ('Hey Bond')."""
        if self._state in (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY):
            logger.info("🎯 [WAKE_WORD] Verified wake word '%s' confirmed (score=%.2f). Transitioning SLEEPING -> WAKE_WORD_DETECTED -> LISTENING.", phrase, score)
            self.wake_word_triggered.emit(phrase, score)
            signals.wake_word_detected.emit(phrase, score)
            self._transition_to(ConversationState.WAKE_WORD_DETECTED)
            if hasattr(self, "wake_word_engine") and self.wake_word_engine:
                self.wake_word_engine.exit_standby()
            self.vad_engine.reset_states()
            self._transition_to(ConversationState.LISTENING)
            signals.character_state_changed.emit(CharacterState.LISTENING.name.lower())
            try:
                from app.core.buddy_state_manager import get_buddy_state_manager
                get_buddy_state_manager().wake_up(reason="wake_word_detected")
            except Exception:
                pass

            # Start return-to-sleep silence timer
            if getattr(self, "auto_return_to_sleep", True) and hasattr(self, "_wake_silence_timer") and self._wake_silence_timer:
                timeout_ms = int(getattr(self, "wake_timeout_sec", 6.0) * 1000)
                self._wake_silence_timer.start(timeout_ms)

    @Slot()
    def _on_wake_silence_timeout(self) -> None:
        """Silence timeout: user did not speak after wake word was detected."""
        if self._state == ConversationState.LISTENING:
            logger.info(
                "[LIFECYCLE] Return-to-sleep: No user speech detected within %.1fs of wake word. Returning to SLEEP MODE.",
                getattr(self, "wake_timeout_sec", 6.0),
            )
            self._return_to_sleep(reason="wake_silence_timeout")

    def _on_wake_word_inactivity_timeout(self) -> None:
        """Return to sleep mode when user stops speaking for timeout period."""
        if self._state in (ConversationState.LISTENING, ConversationState.USER_SPEAKING):
            logger.info("[LIFECYCLE] Inactivity timeout reached. Returning to SLEEP MODE.")
            self._return_to_sleep(reason="inactivity_timeout")

    # ─── Phase 9: Interruption Handling (9.2) ───────────────────────────

    def _on_interruption_detected(self, turn_id: int, speech_samples: np.ndarray) -> None:
        """Handle verified user speech interruption while AI was speaking (Phase 3 9. Barge-in & 10. Cancellation)."""
        if self._state not in (ConversationState.AI_SPEAKING, ConversationState.SPEAKING):
            return

        t_cancel_start = time.perf_counter()
        logger.info(
            "💥 USER INTERRUPTION CONFIRMED in turn #%d! Halting speech and listening...",
            turn_id,
        )
        self.interruption_triggered.emit(turn_id)

        # 1. Stop audio playback and capture rich interruption state (Phase 4 Context-Aware Interruption)
        snapshot = self.audio_queue.stop_and_capture_interruption()
        self._active_interruption_snapshot = snapshot
        self._interrupted_user_query = getattr(self, "_current_turn_user_prompt", "") or self._last_user_transcript
        self._interrupted_turn_id = turn_id

        # 2. Discard stale turn & increment turn ID (Phase 8.8 & 9.2)
        with self._lock:
            self._turn_id += 1
            new_turn_id = self._turn_id

        # 3. Cancel ongoing AI generation
        if self.ai_service:
            self.ai_service.cancel_generation()

        # Emit interrupted voice state for real-time visualization (Phase 8.5)
        self._transition_to(ConversationState.INTERRUPTED)

        t_cancel_end = time.perf_counter()
        cancellation_ms = max(0.1, (t_cancel_end - t_cancel_start) * 1000.0)

        # Calculate barge-in detection time from interruption manager
        barge_in_ms = 400.0
        if hasattr(self, "interruption_manager") and self.interruption_manager:
            onset_t = getattr(self.interruption_manager, "_interruption_onset_time", 0.0)
            if onset_t > 0.0:
                barge_in_ms = max(50.0, (time.time() - onset_t) * 1000.0)
            elif hasattr(self.interruption_manager, "config"):
                barge_in_ms = float(self.interruption_manager.config.min_speech_duration_sec * 1000.0)

        if self._active_metrics:
            self._active_metrics.record_interruption(
                barge_in_ms=barge_in_ms,
                cancellation_ms=cancellation_ms,
                reason="user_speech_barge_in",
            )
            logger.info(
                "[STRUCTURED_TIMING] Interruption confirmed in turn #%d: BargeIn=%.1fms | Cancellation=%.1fms",
                turn_id,
                barge_in_ms,
                cancellation_ms,
            )

        # 5. Switch character animation to LISTENING
        signals.character_state_changed.emit(CharacterState.LISTENING.name.lower())

        # 6. Immediately transition to USER_SPEAKING and seed VAD buffer with user's speech
        self._transition_to(ConversationState.USER_SPEAKING)
        self.speech_started.emit()

        # Seed VAD engine with the captured speech so user doesn't lose their opening words!
        self.vad_engine.reset_states()
        if hasattr(self.vad_engine, "_active_utterance_frames") and speech_samples is not None and len(speech_samples) > 0:
            self.vad_engine._active_utterance_frames.append(speech_samples)
            self.vad_engine._state = VADState.SPEAKING

    # ─── Step 1: User Speech Detection & Recording ─────────────────────

    def _on_vad_speech_started(self) -> None:
        """VAD confirmed speech onset while listening."""
        if hasattr(self, "_wake_silence_timer") and self._wake_silence_timer:
            self._wake_silence_timer.stop()

        if self._state != ConversationState.LISTENING:
            return

        logger.info("[DIAGNOSTIC] Actual speech detected.")
        logger.debug("User began speaking.")
        self._transition_to(ConversationState.USER_SPEAKING)
        self.speech_started.emit()
        self._start_utterance_watchdog()

        # Initialize latency metrics at the exact speech onset (monotonic t0)
        with self._lock:
            turn_preview = self._turn_id + 1
        req_id = f"vreq_{int(time.time() * 1000)}_{turn_preview}"
        from app.voice.conversation_state import ConversationLatencyMetrics
        self._active_metrics = ConversationLatencyMetrics(
            turn_id=turn_preview,
            request_id=req_id,
            session_id=self.session_id,
            input_language=self.language or "auto",
        )
        self._active_metrics.mark_speech_start()
        onset_ms = getattr(self.vad_engine, "min_speech_frames", 3) * (getattr(self.vad_engine, "frame_size", 512) / float(getattr(self.vad_engine, "sample_rate", 16000))) * 1000.0
        self._active_metrics.speech_detection_latency_ms = float(onset_ms)

        # Reset interim progressive speech tracking
        self._interim_generation_id += 1
        self._is_interim_transcribing = False
        self._interim_frame_count = 0
        self._frames_since_last_interim = 0
        self._last_interim_text = ""
        signals.user_speech_interim.emit("")

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.reset_turn()
            diagnostic_tracker.update_recording("recording")
        except Exception:
            pass

    def _on_interim_transcription_ready(self, gen_id: int, text: str) -> None:
        """Callback from background interim Whisper pass (Phase 1)."""
        self._is_interim_transcribing = False
        if gen_id != self._interim_generation_id or self._state != ConversationState.USER_SPEAKING:
            return

        cleaned = text.strip()
        if cleaned and cleaned != self._last_interim_text:
            self._last_interim_text = cleaned
            self.interim_transcription_ready.emit(cleaned)
            signals.user_speech_interim.emit(cleaned)

            # Phase 6: Mid-sentence hesitation & connector pause adaptation (6.1)
            try:
                from app.ai.turn_taking_manager import TurnTakingManager
                has_connector = TurnTakingManager.has_trailing_connector(cleaned)
                if hasattr(self, "vad_engine") and self.vad_engine:
                    self.vad_engine.set_trailing_connector(has_connector)
            except Exception:
                pass

    def _on_vad_speech_ended(self, utterance: np.ndarray) -> None:
        """VAD confirmed end of user utterance."""
        self._stop_utterance_watchdog()
        self._interim_generation_id += 1
        self._is_interim_transcribing = False
        self._frames_since_last_interim = 0
        if self._state != ConversationState.USER_SPEAKING:
            return

        duration_sec = len(utterance) / float(self.mic_manager.sample_rate)
        logger.info("[DIAGNOSTIC] Recording completed: %.2fs utterance captured.", duration_sec)
        self.speech_ended.emit(duration_sec)
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_recording("stopped", duration_sec=duration_sec, sample_count=len(utterance))
        except Exception:
            pass

        # Phase 6.4: Audio segment deduplication check (prevent reprocessing identical audio buffer)
        rms = float(np.sqrt(np.mean(np.square(utterance)))) if utterance.size > 0 else 0.0
        sample_hash = hash(utterance[:min(1000, len(utterance))].tobytes())
        audio_fp = (round(duration_sec, 2), round(rms, 4), sample_hash)
        now_mono = time.monotonic()
        if not hasattr(self, "_recent_audio_fingerprints"):
            self._recent_audio_fingerprints = []
        for fp, t_rec in self._recent_audio_fingerprints:
            if fp == audio_fp and (now_mono - t_rec) < 2.0:
                logger.warning("[DIAGNOSTIC] Duplicate request rejected: Reprocessed audio segment discarded.")
                self.vad_engine.reset_states()
                return
        self._recent_audio_fingerprints.append((audio_fp, now_mono))
        if len(self._recent_audio_fingerprints) > 10:
            self._recent_audio_fingerprints = self._recent_audio_fingerprints[-5:]

        # Waveform-level AEC correlation check (pre-STT defense against speaker feedback)
        if hasattr(self, "echo_canceller"):
            is_echo, peak_corr, reason = self.echo_canceller.correlate_utterance_with_playback(utterance)
            if is_echo:
                logger.warning(
                    "[DIAGNOSTIC] AEC: Discarded captured utterance matching assistant playback (peak corr=%.3f, reason=%s).",
                    peak_corr,
                    reason,
                )
                self.vad_engine.reset_states()
                if self._activation_mode == VoiceActivationMode.CONTINUOUS:
                    self._transition_to(ConversationState.LISTENING)
                elif self._activation_mode == VoiceActivationMode.WAKE_WORD:
                    self._transition_to(ConversationState.WAKE_WORD_STANDBY)
                else:
                    self._transition_to(ConversationState.IDLE)
                return

        # Start new turn & initialize latency metrics
        with self._lock:
            self._turn_id += 1
            turn_id = self._turn_id

        if not self._active_metrics or self._active_metrics.turn_id != turn_id:
            req_id = f"vreq_{int(time.time() * 1000)}_{turn_id}"
            from app.voice.conversation_state import ConversationLatencyMetrics
            self._active_metrics = ConversationLatencyMetrics(
                turn_id=turn_id,
                request_id=req_id,
                session_id=self.session_id,
                input_language=self.language or "auto",
            )
        self._active_metrics.turn_id = turn_id
        self._active_metrics.mark_speech_end(duration_sec)
        endpoint_ms = getattr(self.vad_engine, "silence_threshold_ms", 400)
        self._active_metrics.vad_endpoint_latency_ms = float(endpoint_ms)
        self.turn_started.emit(turn_id)

        # Transition to TRANSCRIBING
        self._transition_to(ConversationState.TRANSCRIBING)
        logger.info("[DIAGNOSTIC] Transcription in progress: submitting turn #%d to Faster-Whisper...", turn_id)
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_transcription("in_progress")
        except Exception:
            pass

        # Step 2: Transcribe via Faster-Whisper
        self._active_metrics.mark_stt_start()
        effective_lang = self.language if (self.language and self.language != "auto") else None
        prompt = None
        if effective_lang == "hi":
            prompt = "नमस्ते, आपका नाम क्या है? मैं आपकी कैसे मदद कर सकता हूँ?"
        elif effective_lang == "gu":
            prompt = "નમસ્તે, તમારું નામ શું છે? હું તમને કેવી રીતે મદદ કરી શકું?"
        elif effective_lang == "en":
            prompt = "Hello, how can I help you today?"
        else:
            # Multilingual initial prompt priming for auto-detect mode & code-switching
            prompt = "Hello, Namaste, Kem cho, Tamaru naam su che, Aapka naam kya hai, How are you?"

        self._start_stt_watchdog(turn_id, timeout_sec=12.0)
        self.whisper_engine.transcribe_async(
            audio_data=utterance,
            language=effective_lang,
            prompt=prompt,
            callback=lambda res: self._on_transcription_completed(res, turn_id),
        )

    @Slot(str)
    def _on_vad_no_speech_detected(self, reason: str) -> None:
        """Handle VAD utterance rejected as lacking genuine speech."""
        self._stop_utterance_watchdog()
        self._is_interim_transcribing = False
        self._interim_generation_id += 1
        logger.info("[DIAGNOSTIC] No speech detected in utterance: %s. Returning to LISTENING.", reason)
        try:
            from app.core.diagnostic_mode import diagnostic_tracker, ERROR_NO_SPEECH
            diagnostic_tracker.update_transcription("no_speech", error=ERROR_NO_SPEECH)
        except Exception:
            pass
        if self._state == ConversationState.USER_SPEAKING:
            if self._activation_mode == VoiceActivationMode.CONTINUOUS and not getattr(self, "auto_return_to_sleep", True):
                self._transition_to(ConversationState.LISTENING)
            else:
                self._return_to_sleep(reason="vad_no_speech")

    # ─── Step 2: Speech Recognition (STT) ──────────────────────────────

    def _on_transcription_completed(self, result: TranscriptionResult, turn_id: int) -> None:
        """Callback from background Whisper engine when audio is transcribed."""
        self._stop_stt_watchdog()
        if turn_id in self._processed_turn_ids:
            logger.warning("[DIAGNOSTIC] Duplicate request rejected: Turn #%d has already been processed.", turn_id)
            return

        if turn_id != self._turn_id or self._state in (ConversationState.IDLE, ConversationState.DISABLED, ConversationState.CANCELED):
            logger.debug("Discarding STT result for stale/superseded turn #%d", turn_id)
            return

        text = result.text.strip()
        if not text:
            logger.info("[DIAGNOSTIC] No speech detected: Transcription was empty/silence. Returning to SLEEP MODE.")
            try:
                from app.core.diagnostic_mode import diagnostic_tracker, ERROR_NO_SPEECH
                diagnostic_tracker.update_transcription("no_speech", error=ERROR_NO_SPEECH)
            except Exception:
                pass
            signals.user_speech_interim.emit("")
            if self._activation_mode == VoiceActivationMode.WAKE_WORD or getattr(self, "auto_return_to_sleep", True):
                self._return_to_sleep(reason="empty_transcription")
            else:
                self._transition_to(ConversationState.LISTENING)
            return

        # Multi-algorithm acoustic feedback echo suppression
        is_echo, reason, conf = self.echo_suppressor.is_echo(text)
        if is_echo:
            logger.warning(
                "[DIAGNOSTIC] Unexpected audio capture detected: Discarded acoustic echo of assistant speech (%s, conf=%.2f): '%s'",
                reason,
                conf,
                text,
            )
            logger.info("Discarded acoustic echo of assistant speech: '%s'", text)
            if self._activation_mode == VoiceActivationMode.WAKE_WORD or getattr(self, "auto_return_to_sleep", True):
                self._return_to_sleep(reason="acoustic_echo")
            else:
                self._transition_to(ConversationState.LISTENING)
            return

        # Exact match check against self._last_assistant_response only for immediate duplicate
        import re
        norm_text = re.sub(r'[^\w\s]', '', text.lower()).strip()
        norm_assistant = re.sub(r'[^\w\s]', '', self._last_assistant_response.lower()).strip()
        if norm_assistant and norm_text == norm_assistant:
            logger.warning("[DIAGNOSTIC] Unexpected audio capture detected: Discarded exact acoustic echo of assistant speech: '%s'", text)
            logger.info("Discarded acoustic echo of assistant speech: '%s'", text)
            self._transition_to(ConversationState.LISTENING if self._activation_mode == VoiceActivationMode.CONTINUOUS else ConversationState.IDLE)
            return

        # Reject duplicate transcript within short window (2.0s)
        if self.echo_suppressor.is_recent_duplicate_user(text, window_sec=2.0):
            logger.warning("[DIAGNOSTIC] Duplicate request rejected: Discarded duplicate repeated user transcript: '%s'", text)
            logger.info("Discarded duplicate repeated user transcript: '%s'", text)
            self._transition_to(ConversationState.LISTENING if self._activation_mode == VoiceActivationMode.CONTINUOUS else ConversationState.IDLE)
            return

        now = time.time()
        if norm_text == self._last_user_transcript and (now - self._last_user_transcript_time) < 2.0:
            logger.warning("[DIAGNOSTIC] Duplicate request rejected: Discarded duplicate repeated user transcript: '%s'", text)
            logger.info("Discarded duplicate repeated user transcript: '%s'", text)
            self._transition_to(ConversationState.LISTENING if self._activation_mode == VoiceActivationMode.CONTINUOUS else ConversationState.IDLE)
            return

        self._processed_turn_ids.add(turn_id)
        if len(self._processed_turn_ids) > 100:
            self._processed_turn_ids = set(list(self._processed_turn_ids)[-50:])

        self._last_user_transcript = norm_text
        self._last_user_transcript_time = now
        self._last_detected_input_lang = result.language or "en"
        self.echo_suppressor.record_user_speech(text)

        logger.info("[DIAGNOSTIC] Transcription completed: '%s' [%s]", text, result.language)
        logger.info("Recognized user speech [turn #%d, lang=%s]: '%s'", turn_id, result.language, text)
        if self._active_metrics:
            self._active_metrics.input_language = result.language or "en"
            self._active_metrics.mark_stt_done(text)
            logger.info(
                "[LATENCY_PROFILE] Turn #%d: STT completed in %.1f ms | Recognized: '%s'",
                turn_id,
                self._active_metrics.stt_latency_ms,
                text,
            )

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_transcription("completed", text=text)
        except Exception:
            pass

        # Transition to SUBMITTING_USER_MESSAGE (Phase 9 flow)
        self._transition_to(ConversationState.SUBMITTING_USER_MESSAGE)

        self.transcription_ready.emit(text, result.language)
        signals.user_speech_final.emit(text)
        signals.voice_transcription_ready.emit(text)

        # Step 2.5: Phase 4 Context-Aware Interruption Handling (takes precedence during interruptions)
        interruption_ctx = None
        if hasattr(self, "_active_interruption_snapshot") and self._active_interruption_snapshot:
            snapshot = self._active_interruption_snapshot
            self._active_interruption_snapshot = None
            orig_prompt = getattr(self, "_interrupted_user_query", "") or getattr(self, "_current_turn_user_prompt", "")

            # Classify interruption
            from app.ai.interruption_classifier import InterruptionClassifier, InterruptionType
            duration_s = self._active_metrics.user_speech_duration_s if self._active_metrics else 0.0
            classification = InterruptionClassifier.classify(
                interruption_text=text,
                speech_duration_sec=duration_s,
            )
            logger.info(
                "[INTERRUPTION_2.0] Interruption classified: type=%s, conf=%.2f, reason='%s'",
                classification.interruption_type.value,
                classification.confidence,
                classification.reason,
            )

            # Handle Type D: Brief Acknowledgement (Backchanneling)
            if classification.interruption_type == InterruptionType.ACKNOWLEDGEMENT:
                if snapshot.unspoken_sentences:
                    logger.info(
                        "[INTERRUPTION_2.0] Type D Acknowledgement during speech. Resuming %d remaining unspoken sentences.",
                        len(snapshot.unspoken_sentences),
                    )
                    self._transition_to(ConversationState.SPEAKING)
                    self.audio_queue.start_new_turn(turn_id)
                    for s in snapshot.unspoken_sentences:
                        self.audio_queue.enqueue_sentence(s, turn_id=turn_id)
                    return
                else:
                    logger.info("[INTERRUPTION_2.0] Type D Acknowledgement at end of turn. Returning to LISTENING.")
                    self._transition_to(
                        ConversationState.LISTENING if self._activation_mode == VoiceActivationMode.CONTINUOUS else ConversationState.IDLE
                    )
                    self.turn_completed.emit(turn_id)
                    return

            interruption_ctx = {
                "type": classification.interruption_type.value,
                "original_query": orig_prompt,
                "actually_spoken": snapshot.actually_spoken_text,
                "interruption_text": text,
                "interrupted_turn_id": snapshot.turn_id,
            }

            # Dispatch directly with interruption context
            self._dispatch_to_ai(text, turn_id, interruption_context=interruption_ctx)
            return

        # Step 2.6: Voice Command & Intent Interception (for regular non-interrupted turns)
        if hasattr(self, "command_dispatcher") and self.command_dispatcher:
            if self.command_dispatcher.dispatch(text, language=result.language):
                logger.info("Voice command processed for turn #%d: '%s'. Skipping AI dispatch.", turn_id, text)
                self._transition_to(
                    ConversationState.LISTENING if self._activation_mode == VoiceActivationMode.CONTINUOUS else ConversationState.IDLE
                )
                self.turn_completed.emit(turn_id)
                return

        # Step 3: Dispatch to AI Engine (regular conversational turns)
        self._dispatch_to_ai(text, turn_id)

    # ─── Step 3: AI Inference & Streaming (Phase 8.4) ───────────────────

    def _dispatch_to_ai(
        self,
        user_text: str,
        turn_id: int,
        interruption_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send recognized user text to the local LLM runtime."""
        self._current_turn_user_prompt = user_text
        self._transition_to(ConversationState.GENERATING_RESPONSE)

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_submission("submitting")
            diagnostic_tracker.update_model_generation("thinking")
            diagnostic_tracker.update_assistant_response("receiving")
        except Exception:
            pass

        # Prepare sentence chunker and audio queue for this turn
        self.sentence_chunker.reset()
        self.thinking_filter.reset()
        self._accumulated_ai_response.clear()
        self.audio_queue.start_new_turn(turn_id)

        # Start watchdog to prevent hanging on model failures
        self._start_generation_watchdog(turn_id)

        if self._active_metrics:
            self._active_metrics.mark_backend_sent()
            self._active_metrics.mark_llm_start()

        # Trigger AI Service request if available and direct dispatch is enabled
        if self.ai_service and getattr(self, "enable_direct_ai_dispatch", True):
            req_id = self._active_metrics.request_id if self._active_metrics else None
            try:
                self.ai_service.ask(
                    user_prompt=user_text,
                    is_voice=True,
                    request_id=req_id,
                    interruption_context=interruption_context,
                )
            except TypeError:
                self.ai_service.ask(user_prompt=user_text, is_voice=True)

    # ─── Step 4: Token Streaming & Sentence Chunking (Phase 8.5) ───────

    def _on_ai_stream_chunk(self, raw_token: str) -> None:
        """Receive incremental token chunks from LLM and feed to SentenceChunker."""
        if self._state not in (ConversationState.AI_THINKING, ConversationState.AI_SPEAKING, ConversationState.GENERATING_RESPONSE, ConversationState.SPEAKING):
            return

        # Ensure we only process stream chunks if the current AI generation is for voice (not typed text chat!)
        if hasattr(self.ai_service, "is_current_generation_voice") and not self.ai_service.is_current_generation_voice:
            return

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_model_generation("generating")
        except Exception:
            pass

        # Filter out <think> tags
        filtered = self.thinking_filter.process_chunk(raw_token)
        if not filtered:
            return

        if self._active_metrics:
            if self._active_metrics.t_backend_request_received == 0.0:
                self._active_metrics.mark_backend_received()
            self._active_metrics.mark_first_token()

        self._accumulated_ai_response.append(filtered)

        # Chunk into natural sentences
        sentences = self.sentence_chunker.add_chunk(filtered)
        for sentence in sentences:
            self._on_sentence_extracted(sentence)

    def _on_ai_stream_complete(self, full_text: str) -> None:
        """LLM finished response generation; flush remaining sentence text."""
        if self._state not in (ConversationState.AI_THINKING, ConversationState.AI_SPEAKING, ConversationState.GENERATING_RESPONSE, ConversationState.SPEAKING):
            return

        # Ensure we only process stream completion if the current AI generation is for voice (not typed text chat!)
        if hasattr(self.ai_service, "is_current_generation_voice") and not self.ai_service.is_current_generation_voice:
            return

        self._last_assistant_response = full_text.strip()
        self.echo_suppressor.record_assistant_speech(full_text)

        if self._active_metrics:
            self._active_metrics.mark_llm_done()

        # Flush any tail tokens in the filter & chunker
        remaining_filter = self.thinking_filter.flush()
        if remaining_filter:
            tail_sentences = self.sentence_chunker.add_chunk(remaining_filter)
            for s in tail_sentences:
                self._on_sentence_extracted(s)

        final_chunks = self.sentence_chunker.flush()
        for idx, s in enumerate(final_chunks):
            is_final = (idx == len(final_chunks) - 1)
            self._on_sentence_extracted(s, is_final=is_final)

        # Mark stream finished in audio queue
        self.audio_queue.mark_stream_finished(self._turn_id)

    def _on_sentence_extracted(self, sentence: str, is_final: bool = False) -> None:
        """Route extracted sentence to StreamingAudioQueue for TTS synthesis."""
        turn_id = self._turn_id
        if self._active_metrics:
            self._active_metrics.mark_first_sentence()

        # Phase 6.4: Strip robotic canned questions from synthesized speech
        try:
            from app.ai.turn_taking_manager import TurnTakingManager
            sentence_cleaned = TurnTakingManager.strip_canned_closing_questions(sentence)
            if not sentence_cleaned:
                logger.info("[TURN_TAKING] Filtered robotic canned closing question: '%s'", sentence)
                return

            # Phase 6.4: Repetition prevention against immediate prior assistant response
            if getattr(self, "_last_assistant_response", None):
                if TurnTakingManager.is_duplicate_response(sentence_cleaned, self._last_assistant_response, threshold=0.95):
                    logger.warning("[TURN_TAKING] Avoided repeating previous assistant response sentence: '%s'", sentence_cleaned)
                    return
            sentence = sentence_cleaned
        except Exception:
            pass

        chunk_idx = self.audio_queue._next_chunk_index
        logger.debug("Sentence chunk #%d extracted: '%s'", chunk_idx, sentence)
        self.echo_suppressor.record_assistant_speech(sentence)
        self.sentence_chunk_produced.emit(turn_id, chunk_idx, sentence)

        # Multilingual voice compatibility validation
        from app.ai.multilingual_engine import MultilingualEngine
        cfg_voice_mode = "follow_response"
        specific_lang = "en"
        if hasattr(self, "ai_service") and self.ai_service and hasattr(self.ai_service, "config_manager") and self.ai_service.config_manager:
            cfg_voice_mode = self.ai_service.config_manager.get("language.voice_output_language", "follow_response")
            specific_lang = self.ai_service.config_manager.get("language.specific_voice_language", "en")

        target_voice_lang = "en"
        if cfg_voice_mode in ("en", "gu", "hi"):
            target_voice_lang = cfg_voice_mode
        elif cfg_voice_mode == "specific":
            target_voice_lang = specific_lang if specific_lang in ("en", "gu", "hi") else "en"
        elif cfg_voice_mode == "follow_input":
            target_voice_lang = getattr(self, "_last_detected_input_lang", "en")
        else:  # follow_response
            configured_resp_lang = "en"
            if hasattr(self, "ai_service") and self.ai_service and getattr(self.ai_service, "config_manager", None):
                configured_resp_lang = self.ai_service.config_manager.get("language.response_language", "en")
            if configured_resp_lang in ("en", "gu", "hi"):
                target_voice_lang = configured_resp_lang
            else:
                det = MultilingualEngine.detect_language(sentence)
                target_voice_lang = det.code if det.code in ("en", "gu", "hi") else "en"

        engine_name = type(self.tts_engine).__name__
        installed_voices = None
        if hasattr(self.tts_engine, "get_available_voices"):
            try:
                installed_voices = self.tts_engine.get_available_voices()
            except Exception:
                pass

        check = MultilingualEngine.check_tts_capability(
            engine_name=engine_name,
            target_language=target_voice_lang,
            installed_voices=installed_voices,
        )

        if not check["supported"]:
            logger.warning(
                "[TTS_LIMITATION] Speech synthesis for language '%s' is not supported by active engine '%s'. "
                "Safely skipping audio playback to prevent phonetic distortion. Text displayed in chat.",
                target_voice_lang, engine_name,
            )
            signals.ai_speech_subtitle.emit(f"[{check['status_badge']}: {check['language_name']} voice not installed]")
            return

        # Resolve active voice profile
        from app.voice.voice_registry import get_voice_profile
        selected_prof_id = getattr(self, "selected_voice_profile", "arjun")
        profile = get_voice_profile(selected_prof_id)

        # Prepare spoken text (transliterating native script for TTS if needed) and resolve voice hint
        spoken_text, voice_hint = MultilingualEngine.prepare_text_for_tts(
            text=sentence,
            target_language=target_voice_lang,
            engine_name=engine_name,
            installed_voices=installed_voices,
            preferred_voice_id=profile.primary_voice_id,
            preferred_gender=profile.gender,
        )

        # Phase 7: Retrieve speaking style for the active persona
        persona_style = None
        if hasattr(self, "ai_service") and self.ai_service and getattr(self.ai_service, "personality_manager", None):
            try:
                persona_style = self.ai_service.personality_manager.get_speaking_style_for_persona()
            except Exception:
                persona_style = None

        base_rate = persona_style.speaking_rate if persona_style else profile.speaking_rate
        effective_speed = base_rate
        if hasattr(self, "ai_service") and self.ai_service and getattr(self.ai_service, "config_manager", None):
            cfg_speed = self.ai_service.config_manager.get("voice.voice_speed")
            if cfg_speed is not None:
                try:
                    effective_speed = float(cfg_speed) * base_rate
                except (ValueError, TypeError):
                    pass

        # Enqueue sentence for background TTS synthesis
        self.audio_queue.enqueue_sentence(
            sentence=spoken_text,
            turn_id=turn_id,
            is_final=is_final,
            display_text=sentence,
            voice_hint=voice_hint or profile.primary_voice_id,
            speed=effective_speed,
            speaking_style=persona_style,
        )

    # ─── Step 5: Audio Playback & Loop Completion ──────────────────────

    def _on_chunk_synthesized(self, turn_id: int, chunk_index: int, text: str) -> None:
        """Callback when TTS worker finishes synthesizing an audio segment."""
        if turn_id == self._turn_id and self._active_metrics:
            self._active_metrics.mark_first_tts_audio()
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_tts("synthesized")
        except Exception:
            pass

    def _on_chunk_playback_started(self, turn_id: int, chunk_index: int, text: str) -> None:
        """Callback when AudioPlayer begins playing a speech chunk."""
        if turn_id != self._turn_id:
            return

        self._stop_generation_watchdog()

        if self._active_metrics:
            self._active_metrics.mark_playback_started()
            logger.info(
                "[LATENCY_PROFILE] Turn #%d Time-To-First-Playback: %.1f ms (Speech End -> First Sound Heard)",
                turn_id,
                self._active_metrics.time_to_first_playback_ms,
            )

        self.echo_suppressor.record_assistant_speech(text)

        # Transition to SPEAKING when sound output starts
        if self._state not in (ConversationState.SPEAKING, ConversationState.AI_SPEAKING):
            self._transition_to(ConversationState.SPEAKING)

        # Emit synchronized sentence subtitle to central signal bus (Phase 2)
        signals.ai_speech_subtitle.emit(text)

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_playback("playing")
        except Exception:
            pass

    def _on_all_speech_played(self, turn_id: int) -> None:
        """Callback when all queued speech chunks have finished playing."""
        if turn_id != self._turn_id:
            return

        self._stop_generation_watchdog()
        self._consecutive_error_count = 0

        # Signal that all speech sentences for this turn have finished playing (Phase 2)
        signals.ai_speech_finished.emit()

        logger.info("[DIAGNOSTIC] TTS playback completed.")
        logger.info("All speech playback finished for turn #%d. Returning to LISTENING.", turn_id)

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_playback("completed")
            diagnostic_tracker.update_model_generation("completed")
            diagnostic_tracker.update_assistant_response("received")
        except Exception:
            pass

        # Finish latency metrics
        if self._active_metrics:
            self._active_metrics.mark_tts_done()
            self._active_metrics.mark_playback_ended()
            full_response = "".join(self._accumulated_ai_response)
            self._active_metrics.finish_turn(full_response)
            metrics_dict = self._active_metrics.to_dict()
            telemetry_dict = self._active_metrics.to_telemetry_dict()
            structured_log = self._active_metrics.to_structured_log()

            # Store in structured timing buffer (Phase 3)
            self._recent_timing_logs.append(structured_log)
            if len(self._recent_timing_logs) > 50:
                self._recent_timing_logs = self._recent_timing_logs[-50:]

            import json
            logger.info("[STRUCTURED_TIMING] %s", json.dumps(structured_log))

            try:
                from app.api.websocket import ws_manager
                ws_manager.broadcast_sync("performance_telemetry", telemetry_dict)
                ws_manager.broadcast_sync("structured_timing", structured_log)
            except Exception as broadcast_err:
                logger.debug("Failed to broadcast performance telemetry: %s", broadcast_err)
            logger.info(
                "[LATENCY_PROFILE] ─── Turn #%d Latency Profile Summary ───\n"
                "  • Speech Capture:            %.2f s\n"
                "  • STT (Whisper) Latency:     %.1f ms\n"
                "  • Backend Dispatch Latency:  %.1f ms\n"
                "  • Model Time to First Token: %.1f ms\n"
                "  • Total Model Gen Time:      %.1f ms\n"
                "  • TTS Synthesis Latency:     %.1f ms\n"
                "  • Time to First Playback:    %.1f ms\n"
                "  • Total Turn Duration:       %.1f ms",
                turn_id,
                metrics_dict["user_speech_duration_s"],
                metrics_dict["stt_latency_ms"],
                metrics_dict["backend_request_latency_ms"],
                metrics_dict["llm_first_token_latency_ms"],
                metrics_dict["total_model_generation_ms"],
                metrics_dict["tts_first_audio_latency_ms"],
                metrics_dict["time_to_first_playback_ms"],
                metrics_dict["total_turn_duration_ms"],
            )
            logger.info("Conversation Turn #%d Latencies: %s", turn_id, metrics_dict)
            self.latency_measured.emit(metrics_dict)
            try:
                from app.core.diagnostic_mode import diagnostic_tracker
                diagnostic_tracker.update_stage_latencies(metrics_dict)
            except Exception:
                pass

        self.turn_completed.emit(turn_id)

        # Return to SLEEP after acoustic echo decay delay,
        # but resume LISTENING ONLY if the user has explicitly enabled continuous conversation mode!
        if self._state not in (ConversationState.IDLE, ConversationState.DISABLED):
            self.vad_engine.reset_states()
            def resume_listening() -> None:
                if self._state not in (ConversationState.IDLE, ConversationState.DISABLED, ConversationState.USER_SPEAKING):
                    # Purge any residual audio captured during decay
                    self.vad_engine.reset_states()
                    if self._activation_mode == VoiceActivationMode.CONTINUOUS and not getattr(self, "auto_return_to_sleep", True):
                        self._transition_to(ConversationState.LISTENING)
                    else:
                        self._return_to_sleep(reason="response_completed")
            decay_delay_ms = 200 if getattr(getattr(self, "echo_canceller", None), "echo_mode", "speaker") == "headset" else 350
            QTimer.singleShot(decay_delay_ms, resume_listening)

    # ─── Turn Cancellation Management ───────────────────────────────────

    def cancel_current_turn(self) -> None:
        """Cancel ongoing turn immediately and discard pending audio/text."""
        if self._is_shutdown or self._state in (ConversationState.DISABLED, ConversationState.INTERRUPTED, ConversationState.USER_SPEAKING):
            return

        with self._lock:
            turn_id = self._turn_id
            self._turn_id += 1  # Invalidate active turn ID

        logger.info("[DIAGNOSTIC] Errors and cancellations: Turn #%d cancelled.", turn_id)
        logger.info("Canceling voice conversation turn #%d.", turn_id)
        self._stop_utterance_watchdog()
        self._stop_stt_watchdog()
        self._stop_generation_watchdog()
        self._is_interim_transcribing = False
        self._interim_generation_id += 1
        self.audio_player.stop()
        self.audio_queue.clear()
        self.sentence_chunker.reset()
        self.thinking_filter.reset()
        self._accumulated_ai_response.clear()

        if self.ai_service:
            self.ai_service.cancel_generation()

        self._transition_to(ConversationState.CANCELED)
        signals.ai_speech_finished.emit()

        if self._state not in (ConversationState.IDLE, ConversationState.DISABLED):
            self.vad_engine.reset_states()
            if self._activation_mode == VoiceActivationMode.CONTINUOUS and not getattr(self, "auto_return_to_sleep", True):
                self._transition_to(ConversationState.LISTENING)
            else:
                self._return_to_sleep(reason="turn_cancelled")

    # ─── Phase 9: Watchdog Timers & Error Recovery ───────────────────────

    def _start_utterance_watchdog(self, timeout_sec: float = 15.0) -> None:
        """Start watchdog to prevent endless listening when background noise keeps VAD triggered."""
        self._stop_utterance_watchdog()
        self._utterance_timer = QTimer(self)
        self._utterance_timer.setSingleShot(True)
        self._utterance_timer.timeout.connect(self._on_utterance_timeout)
        self._utterance_timer.start(int(timeout_sec * 1000))

    def _stop_utterance_watchdog(self) -> None:
        """Stop active utterance watchdog."""
        if hasattr(self, "_utterance_timer") and self._utterance_timer is not None:
            try:
                self._utterance_timer.stop()
                self._utterance_timer.deleteLater()
            except Exception:
                pass
            self._utterance_timer = None

    def _on_utterance_timeout(self) -> None:
        """Utterance watchdog fired: force-finalize active speech segment."""
        if self._state == ConversationState.USER_SPEAKING:
            logger.warning("[DIAGNOSTIC] Utterance watchdog: max speech duration exceeded (15s). Force finalizing.")
            res = None
            if hasattr(self.vad_engine, "force_finalize_utterance"):
                res = self.vad_engine.force_finalize_utterance()
            if res is not None and len(res) > 0:
                logger.info("[DIAGNOSTIC] Utterance watchdog: Successfully force-finalized %d samples.", len(res))
                if self._state == ConversationState.USER_SPEAKING:
                    self._on_vad_speech_ended(res)
            else:
                logger.info("[DIAGNOSTIC] Utterance watchdog: No valid speech frames collected in 15s window. Returning to LISTENING.")
                self.vad_engine.reset_states()
                self._transition_to(ConversationState.LISTENING)

    def _start_generation_watchdog(self, turn_id: int, timeout_sec: float = 30.0) -> None:
        """Watchdog to ensure AI response generation does not leave interface permanently busy."""
        self._stop_generation_watchdog()
        self._generation_watchdog_timer = QTimer(self)
        self._generation_watchdog_timer.setSingleShot(True)
        self._generation_watchdog_timer.timeout.connect(lambda: self._on_generation_timeout(turn_id))
        self._generation_watchdog_timer.start(int(timeout_sec * 1000))

    def _stop_generation_watchdog(self) -> None:
        """Stop active generation watchdog."""
        if hasattr(self, "_generation_watchdog_timer") and self._generation_watchdog_timer is not None:
            try:
                self._generation_watchdog_timer.stop()
                self._generation_watchdog_timer.deleteLater()
            except Exception:
                pass
            self._generation_watchdog_timer = None

    def _on_generation_timeout(self, turn_id: int) -> None:
        """Generation watchdog fired: AI response did not arrive within timeout."""
        if turn_id == self._turn_id and self._state in (
            ConversationState.SUBMITTING_USER_MESSAGE,
            ConversationState.GENERATING_RESPONSE,
            ConversationState.AI_THINKING,
        ):
            logger.warning("[DIAGNOSTIC] Generation watchdog: Turn #%d response timed out after 30s.", turn_id)
            self._on_pipeline_error(f"AI response generation timed out for turn #{turn_id}.", stage="llm")

    def _start_stt_watchdog(self, turn_id: int, timeout_sec: float = 12.0) -> None:
        """Watchdog to ensure Faster-Whisper does not hang permanently in TRANSCRIBING state."""
        self._stop_stt_watchdog()
        self._stt_watchdog_timer = QTimer(self)
        self._stt_watchdog_timer.setSingleShot(True)
        self._stt_watchdog_timer.timeout.connect(lambda: self._on_stt_timeout(turn_id))
        self._stt_watchdog_timer.start(int(timeout_sec * 1000))

    def _stop_stt_watchdog(self) -> None:
        """Stop active STT watchdog."""
        if hasattr(self, "_stt_watchdog_timer") and self._stt_watchdog_timer is not None:
            try:
                self._stt_watchdog_timer.stop()
                self._stt_watchdog_timer.deleteLater()
            except Exception:
                pass
            self._stt_watchdog_timer = None

    def _on_stt_timeout(self, turn_id: int) -> None:
        """STT watchdog fired: speech recognition took too long."""
        if self._state == ConversationState.TRANSCRIBING and turn_id == self._turn_id:
            logger.warning("[DIAGNOSTIC] STT watchdog: Turn #%d Faster-Whisper transcription timed out after 12s.", turn_id)
            self._stop_stt_watchdog()
            self._stop_utterance_watchdog()
            self.vad_engine.reset_states()
            signals.user_speech_interim.emit("")
            self.error_occurred.emit("Speech transcription timed out. Audio buffer was reset.")
            if self._activation_mode == VoiceActivationMode.CONTINUOUS and not getattr(self, "auto_return_to_sleep", True):
                self._transition_to(ConversationState.LISTENING)
            else:
                self._return_to_sleep(reason="stt_timeout")

    def _on_pipeline_error(self, error_msg: str, stage: str = "general") -> None:
        """Handle errors cleanly with bounded retry auto-recovery to prevent infinite loops."""
        logger.error("[DIAGNOSTIC] Pipeline error in stage '%s': %s", stage, error_msg)
        self._consecutive_error_count += 1

        self._stop_utterance_watchdog()
        self._stop_stt_watchdog()
        self._stop_generation_watchdog()
        self.audio_player.stop()
        self.audio_queue.clear()

        self._transition_to(ConversationState.ERROR)
        signals.ai_speech_finished.emit()
        self.error_occurred.emit(error_msg)

        # Cancel any pending recovery timer
        if hasattr(self, "_error_recovery_timer") and self._error_recovery_timer is not None:
            try:
                self._error_recovery_timer.stop()
                self._error_recovery_timer.deleteLater()
            except Exception:
                pass
            self._error_recovery_timer = None

        if self._consecutive_error_count <= 3:
            logger.info("Scheduling automatic recovery from error in 2.5s (attempt %d/3)...", self._consecutive_error_count)
            self._error_recovery_timer = QTimer(self)
            self._error_recovery_timer.setSingleShot(True)
            self._error_recovery_timer.timeout.connect(self._recover_from_error)
            self._error_recovery_timer.start(2500)
        else:
            logger.error(
                "Repeated pipeline failures (%d consecutive errors). Pausing voice loop to prevent infinite retry loop.",
                self._consecutive_error_count,
            )
            self._consecutive_error_count = 0
            self._transition_to(ConversationState.IDLE)
            self.error_occurred.emit("Voice conversation paused after repeated errors. Please check microphone/model.")

    def _recover_from_error(self) -> None:
        """Auto-recover from error state to listening or sleep mode."""
        if self._state == ConversationState.ERROR:
            logger.info("Auto-recovering from ERROR state.")
            self.vad_engine.reset_states()
            if self._activation_mode == VoiceActivationMode.CONTINUOUS and not getattr(self, "auto_return_to_sleep", True):
                self._transition_to(ConversationState.LISTENING)
            else:
                self._return_to_sleep(reason="error_recovery")
