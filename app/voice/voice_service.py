"""Voice Service, Speech Recognition, and Speech Synthesis Coordinator.

Unifies MicrophoneManager, VADEngine, WhisperEngine, AudioPlayer, Piper TTS,
and Kokoro TTS into an end-to-end voice loop with real-time lip sync amplitude.
"""

from __future__ import annotations

from enum import Enum
import threading
import time
from typing import Any, Callable, List, Optional

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from app.core.signals import signals
from app.utils.logger import get_logger
from app.voice.audio_player import AudioPlayer
from app.voice.kokoro_engine import KokoroTTSEngine
from app.voice.conversation_state import VoiceActivationMode
from app.voice.microphone_manager import MicrophoneManager
from app.voice.piper_engine import PiperTTSEngine
from app.voice.sapi5_engine import Sapi5TTSEngine
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine

logger = get_logger(__name__)


class VoiceMode(Enum):
    OFF = "off"
    PUSH_TO_TALK = "push_to_talk"
    CONTINUOUS = "continuous"
    WAKE_WORD = "wake_word"


class _TTSSpeakWorker(QRunnable):
    """Background worker to synthesize and immediately trigger audio playback."""

    def __init__(
        self,
        tts_engine: BaseTTSEngine,
        audio_player: AudioPlayer,
        text: str,
        speak_id: int = 0,
        is_active_fn: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        voice_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.tts_engine = tts_engine
        self.audio_player = audio_player
        self.text = text
        self.speak_id = speak_id
        self.is_active_fn = is_active_fn
        self.on_error = on_error
        self.voice_kwargs = voice_kwargs or {}
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_tts("synthesizing")
        except Exception:
            pass

        try:
            if self.is_active_fn and not self.is_active_fn(self.speak_id):
                return
            start_time = time.perf_counter()
            audio = self.tts_engine.synthesize(self.text, **self.voice_kwargs)
            if self.is_active_fn and not self.is_active_fn(self.speak_id):
                return
            duration = time.perf_counter() - start_time
            try:
                from app.core.performance_monitor import get_performance_monitor
                get_performance_monitor().record_tts_duration(
                    type(self.tts_engine).__name__, duration, len(self.text)
                )
            except Exception:
                pass
            if not audio.is_empty:
                if self.is_active_fn and not self.is_active_fn(self.speak_id):
                    return
                try:
                    from app.core.diagnostic_mode import diagnostic_tracker
                    diagnostic_tracker.update_tts("synthesized")
                    diagnostic_tracker.update_playback("playing")
                except Exception:
                    pass
                signals.ai_speech_subtitle.emit(self.text)
                self.audio_player.play(audio.samples, audio.sample_rate)
        except RuntimeError as e:
            if "deleted" in str(e).lower():
                logger.debug("TTS worker aborted; parent QObject was deleted.")
                return
            logger.error("RuntimeError during TTS synthesis: %s", e)
            try:
                from app.core.diagnostic_mode import diagnostic_tracker, ERROR_TTS_FAILED
                diagnostic_tracker.update_tts("failed", error=ERROR_TTS_FAILED)
            except Exception:
                pass
            if self.on_error:
                try:
                    self.on_error(str(e))
                except Exception:
                    pass
        except Exception as e:
            logger.error("Error during TTS speech synthesis/playback: %s", e)
            try:
                from app.core.diagnostic_mode import diagnostic_tracker, ERROR_TTS_FAILED
                diagnostic_tracker.update_tts("failed", error=ERROR_TTS_FAILED)
            except Exception:
                pass
            if self.on_error:
                try:
                    self.on_error(str(e))
                except Exception:
                    pass


class VoiceService(QObject):
    """Central coordinator for microphone capture, VAD, Whisper STT, and TTS audio."""

    # UI and Controller Signals
    mode_changed = Signal(str)                  # "off", "push_to_talk", "continuous"
    listening_started = Signal()                # Mic is active and waiting/recording
    listening_stopped = Signal()
    speech_detected = Signal()                  # VAD speech onset confirmed
    transcription_started = Signal()            # Whisper inference in progress
    transcription_ready = Signal(str, str)      # (recognized_text, language_code)
    audio_level = Signal(float)                 # Normalized 0.0 - 1.0 for mic visualizers
    error_occurred = Signal(str)

    # Text-to-Speech & Lip Sync Signals (Phase 7)
    speaking_started = Signal()                 # AI began speaking
    speaking_finished = Signal()                # AI finished speaking
    lip_sync_amplitude = Signal(float)          # Mouth openness (0.0 to 1.0)
    playback_progress = Signal(float, float)    # current_sec, total_sec

    def __init__(
        self,
        mic_manager: Optional[MicrophoneManager] = None,
        vad_engine: Optional[VADEngine] = None,
        whisper_engine: Optional[WhisperEngine] = None,
        audio_player: Optional[AudioPlayer] = None,
        default_language: Optional[str] = None,   # None = auto-detect, 'en', 'hi', 'gu'
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.mic_manager = mic_manager or MicrophoneManager()
        self.vad_engine = vad_engine or VADEngine()

        # Load user configuration from persistent settings
        try:
            from app.settings.config_manager import get_config_manager
            self._config_manager = get_config_manager()
            cfg = self._config_manager.get_category("voice")
        except Exception:
            self._config_manager = None
            cfg = {}

        if whisper_engine is None:
            model_size = cfg.get("whisper_model", "base")
            self.whisper_engine = WhisperEngine(model_size=model_size)
        else:
            self.whisper_engine = whisper_engine

        self.audio_player = audio_player or AudioPlayer()

        # Speech synthesis engines with chained fallback resilience
        self.sapi_engine = Sapi5TTSEngine(parent=self)
        self.piper_engine = PiperTTSEngine(parent=self, fallback_engine=self.sapi_engine)
        self.kokoro_engine = KokoroTTSEngine(parent=self, fallback_engine=self.piper_engine)

        self.active_tts_engine: BaseTTSEngine = self.sapi_engine if self.sapi_engine.is_available() else self.piper_engine
        configured_engine = cfg.get("tts_engine") or cfg.get("engine")
        if configured_engine:
            self.set_tts_engine(str(configured_engine))
        else:
            if self.kokoro_engine.is_available():
                self.active_tts_engine = self.kokoro_engine
            elif self.piper_engine.is_available():
                self.active_tts_engine = self.piper_engine
            elif self.sapi_engine.is_available():
                self.active_tts_engine = self.sapi_engine
        self.tts_enabled: bool = True

        # Apply voice speed & TTS voice from config
        if "voice_speed" in cfg:
            try:
                self.set_tts_speed(float(cfg["voice_speed"]))
            except (ValueError, TypeError):
                pass
        if "tts_voice" in cfg:
            self.set_voice(str(cfg["tts_voice"]))

        if default_language is None:
            configured_lang = cfg.get("language", "auto")
            self.language = None if configured_lang in ("auto", "", None) else configured_lang
        else:
            self.language = default_language

        if "silence_threshold_ms" in cfg:
            try:
                self.vad_engine.silence_threshold_ms = int(cfg["silence_threshold_ms"])
            except (ValueError, TypeError):
                self.vad_engine.silence_threshold_ms = 400
        else:
            self.vad_engine.silence_threshold_ms = 400

        # Selected Voice Profile (Phase 1)
        self.selected_voice_profile: str = cfg.get("selected_profile", "arjun")
        signals.voice_profile_changed.connect(self.set_voice_profile)

        if self._config_manager is not None:
            try:
                self._config_manager.setting_changed.connect(self._on_setting_changed)
                if hasattr(self._config_manager, "config_reloaded"):
                    self._config_manager.config_reloaded.connect(self.reload_from_config)
            except Exception:
                pass

        self._mode = VoiceMode.OFF
        self._is_push_to_talking = False
        self._is_dictating: bool = False
        self._is_shutdown: bool = False
        self._ptt_chunks: List[np.ndarray] = []
        self._dictation_chunks: List[np.ndarray] = []
        self._ptt_lock = threading.Lock()
        self._dictation_lock = threading.Lock()
        self._current_speak_id: int = 0
        self._thread_pool = QThreadPool.globalInstance()

        # Asynchronously preload Whisper model to eliminate first-utterance cold start latency
        if hasattr(self.whisper_engine, "preload_async"):
            self.whisper_engine.preload_async()

        # Connect STT & Microphone signals
        self.mic_manager.audio_level.connect(self.audio_level.emit)
        self.mic_manager.error_occurred.connect(self.error_occurred.emit)
        self.whisper_engine.error_occurred.connect(self.error_occurred.emit)

        # Connect VAD signals
        self.vad_engine.speech_started.connect(self._on_vad_speech_started)
        self.vad_engine.speech_ended.connect(self._on_vad_speech_ended)

        # Connect Audio Player & Lip Sync signals (Phase 7)
        self.audio_player.playback_started.connect(self.speaking_started.emit)
        self.audio_player.playback_finished.connect(self.speaking_finished.emit)
        self.audio_player.playback_stopped.connect(self.speaking_finished.emit)
        self.audio_player.amplitude_updated.connect(self.lip_sync_amplitude.emit)
        self.audio_player.playback_progress.connect(self.playback_progress.emit)
        self.audio_player.error_occurred.connect(self.error_occurred.emit)

        # Voice Conversation Controller (Phase 8 Continuous Hands-Free Dialogue)
        from app.voice.voice_conversation_controller import VoiceConversationController
        self.conversation_controller = VoiceConversationController(
            mic_manager=self.mic_manager,
            vad_engine=self.vad_engine,
            whisper_engine=self.whisper_engine,
            audio_player=self.audio_player,
            tts_engine=self.active_tts_engine,
            ai_service=None,
            language=self.language,
            parent=self,
        )
        self.conversation_controller.transcription_ready.connect(self.transcription_ready.emit)
        self.conversation_controller.speech_started.connect(self.speech_detected.emit)
        self.conversation_controller.error_occurred.connect(self.error_occurred.emit)

        # Voice Command & Intent Dispatcher
        from app.voice.command_dispatcher import VoiceCommandDispatcher
        self.command_dispatcher = VoiceCommandDispatcher(
            voice_service=self,
            parent=self,
        )
        self.conversation_controller.command_dispatcher = self.command_dispatcher

        # Wire mic audio frames to processing pipelines
        self.mic_manager.subscribe(self._on_audio_frame_received)

        from app.core.buddy_state_manager import get_buddy_state_manager
        self.buddy_state_manager = get_buddy_state_manager()
        if hasattr(self.buddy_state_manager, "set_audio_player"):
            self.buddy_state_manager.set_audio_player(self.audio_player)
        else:
            self.buddy_state_manager.audio_player = self.audio_player

    @property
    def mode(self) -> VoiceMode:
        return self._mode

    @property
    def tts_engine(self) -> BaseTTSEngine:
        """Active text-to-speech engine instance."""
        return self.active_tts_engine

    @tts_engine.setter
    def tts_engine(self, engine: BaseTTSEngine) -> None:
        self.active_tts_engine = engine
        if hasattr(self, "conversation_controller"):
            self.conversation_controller.tts_engine = self.active_tts_engine
            if hasattr(self.conversation_controller, "audio_queue"):
                self.conversation_controller.audio_queue.tts_engine = self.active_tts_engine

    def set_language(self, language_code: Optional[str]) -> None:
        """Set recognition language ('en', 'hi', 'gu', or None for auto-detect)."""
        self.language = language_code if language_code else None
        if hasattr(self, "conversation_controller"):
            self.conversation_controller.language = self.language
        logger.info("Voice recognition language set to: %s", self.language or "auto-detect")

    def attach_ai_service(self, ai_service: object) -> None:
        """Attach local AI service for continuous conversation orchestration."""
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            self.conversation_controller.ai_service = ai_service  # type: ignore[assignment]
        if hasattr(self, "command_dispatcher") and self.command_dispatcher:
            self.command_dispatcher.ai_service = ai_service

    @Slot(str, object)
    def _on_setting_changed(self, key_path: str, new_value: Any) -> None:
        """Dynamically update runtime voice parameters when configuration settings change."""
        if key_path.startswith("language."):
            param = key_path.split(".", 1)[1]
            if param == "stt_language":
                self.set_language(None if new_value in ("auto", "", None) else str(new_value))
            return

        if not key_path.startswith("voice."):
            return

        param = key_path.split(".", 1)[1]
        logger.info("Voice configuration setting updated: %s = %s", param, new_value)

        if param == "language":
            self.set_language(None if new_value in ("auto", "", None) else str(new_value))
        elif param == "mode":
            self.set_mode(str(new_value))
        elif param == "whisper_model":
            if hasattr(self.whisper_engine, "model_size"):
                self.whisper_engine.model_size = str(new_value)
        elif param in ("tts_engine", "engine"):
            self.set_tts_engine(str(new_value))
        elif param in ("selected_profile", "voice_profile"):
            self.set_voice_profile(str(new_value))
        elif param == "tts_voice":
            self.set_voice(str(new_value))
        elif param in ("voice_speed", "speed"):
            try:
                self.set_tts_speed(float(new_value))
            except (ValueError, TypeError):
                pass
        elif param in ("volume", "voice_volume"):
            try:
                vol = float(new_value)
                if vol > 1.0:
                    vol = vol / 100.0
                self.set_volume(max(0.0, min(1.0, vol)))
            except (ValueError, TypeError):
                pass
        elif param == "silence_threshold_ms":
            try:
                self.vad_engine.set_silence_threshold(int(new_value))
                if hasattr(self, "conversation_controller") and self.conversation_controller:
                    self.conversation_controller.set_silence_threshold_ms(int(new_value))
            except (ValueError, TypeError):
                pass
        elif param in ("echo_mode", "echo_cancellation_mode"):
            self.set_echo_mode(str(new_value))
        elif param == "wake_word":
            if self.wake_word_engine:
                self.wake_word_engine.set_activation_phrase(str(new_value))
        elif param == "enabled":
            if not new_value:
                self.set_mode(VoiceMode.OFF)

    @property
    def is_shutdown(self) -> bool:
        """Return True if VoiceService has initiated or completed shutdown."""
        return self._is_shutdown

    @property
    def is_muted(self) -> bool:
        """Return True if VoiceService is currently muted."""
        return getattr(self, "_is_muted", False)

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute microphone input and conversation processing (Phase 8.4)."""
        self._is_muted = muted
        if hasattr(self, "mic_manager") and self.mic_manager:
            self.mic_manager.set_muted(muted)
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            self.conversation_controller.set_muted(muted)
        if muted:
            signals.voice_state_changed.emit("muted")

    @property
    def interruption_manager(self):
        """InterruptionManager component (Phase 9.2)."""
        return getattr(self.conversation_controller, "interruption_manager", None)

    @property
    def wake_word_engine(self):
        """WakeWordEngine component (Phase 9.5)."""
        return getattr(self.conversation_controller, "wake_word_engine", None)

    def set_echo_mode(self, mode: str) -> None:
        """Set acoustic echo handling mode ('headset' or 'speaker') (Phase 9.4)."""
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            self.conversation_controller.interruption_manager.set_echo_mode(mode)

    def emergency_stop(self) -> None:
        """Immediately halt all audio streams, TTS workers, and microphone listeners (Phase 9.9)."""
        logger.warning("VoiceService emergency stop triggered.")
        self._current_speak_id += 1
        self.set_mode(VoiceMode.OFF)
        self.audio_player.emergency_stop()
        self.mic_manager.emergency_stop()
        if hasattr(self, "sapi_engine") and hasattr(self.sapi_engine, "emergency_stop"):
            try:
                self.sapi_engine.emergency_stop()
            except Exception:
                pass
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            try:
                self.conversation_controller.emergency_stop()
            except Exception:
                pass
        if hasattr(self, "_thread_pool") and self._thread_pool:
            try:
                self._thread_pool.clear()
            except Exception:
                pass

    def shutdown(self) -> None:
        """Permanently shut down VoiceService and release all audio/system resources."""
        if self._is_shutdown:
            return
        self._is_shutdown = True
        logger.info("VoiceService shutting down cleanly...")
        self.emergency_stop()
        self.stop()
        self.mic_manager.shutdown()
        self.audio_player.shutdown()
        if hasattr(self, "sapi_engine") and hasattr(self.sapi_engine, "shutdown"):
            try:
                self.sapi_engine.shutdown()
            except Exception:
                pass
        self.unload_models()
        logger.info("VoiceService shutdown complete.")

    def set_mode(self, mode: VoiceMode | str) -> None:
        """Set the active voice mode ('off', 'push_to_talk', 'continuous', 'wake_word')."""
        if isinstance(mode, str):
            try:
                mode = VoiceMode(mode.lower().strip())
            except ValueError:
                mode = VoiceMode.OFF

        if self._is_shutdown and mode != VoiceMode.OFF:
            logger.debug("VoiceService set_mode rejected: service is shut down.")
            return

        if self._mode == mode:
            return

        prev_mode = self._mode
        self._mode = mode
        logger.info("Voice mode transition: %s -> %s", prev_mode.value, mode.value)

        # Handle transitions
        if prev_mode == VoiceMode.PUSH_TO_TALK and self._is_push_to_talking:
            self.stop_push_to_talk()

        if mode == VoiceMode.CONTINUOUS:
            if hasattr(self, "conversation_controller"):
                self.conversation_controller.set_activation_mode(VoiceActivationMode.CONTINUOUS)
                started = self.conversation_controller.enable()
            else:
                self.vad_engine.reset_states()
                started = self.mic_manager.start_recording()

            if not started:
                logger.error("[DIAGNOSTIC] Microphone unavailable: Failed to activate continuous voice listening.")
                self._mode = VoiceMode.OFF
                self.mode_changed.emit(VoiceMode.OFF.value)
                self.listening_stopped.emit()
                from app.core.signals import signals
                signals.voice_state_changed.emit("off")
                return

            self.listening_started.emit()
        elif mode == VoiceMode.WAKE_WORD:
            if hasattr(self, "conversation_controller"):
                self.conversation_controller.set_activation_mode(VoiceActivationMode.WAKE_WORD)
                started = self.conversation_controller.enable()
            else:
                started = self.mic_manager.start_recording()

            if not started:
                logger.error("[DIAGNOSTIC] Microphone unavailable: Failed to activate wake-word voice listening.")
                self._mode = VoiceMode.OFF
                self.mode_changed.emit(VoiceMode.OFF.value)
                self.listening_stopped.emit()
                from app.core.signals import signals
                signals.voice_state_changed.emit("off")
                return

            self.listening_started.emit()
        elif mode == VoiceMode.PUSH_TO_TALK:
            if hasattr(self, "conversation_controller"):
                self.conversation_controller.set_activation_mode(VoiceActivationMode.PUSH_TO_TALK)
                self.conversation_controller.disable()
            if prev_mode in (VoiceMode.CONTINUOUS, VoiceMode.WAKE_WORD):
                self.mic_manager.stop_recording()
                self.listening_stopped.emit()
        elif mode == VoiceMode.OFF:
            if hasattr(self, "conversation_controller"):
                self.conversation_controller.set_activation_mode(VoiceActivationMode.OFF)
                self.conversation_controller.disable()
            self.mic_manager.stop_recording()
            self.listening_stopped.emit()

        self.mode_changed.emit(mode.value)

    # -------------------------------------------------------------------------
    # Text-To-Speech Playback & Controls (7.4, 7.5, 7.7)
    # -------------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Synthesize and speak text out loud with lip sync."""
        if self._is_shutdown:
            logger.debug("VoiceService.speak rejected: service is shut down.")
            return

        if hasattr(self, "buddy_state_manager") and self.buddy_state_manager:
            if not self.buddy_state_manager.can_speak:
                logger.debug("VoiceService.speak suppressed: Buddy is in state '%s'.", self.buddy_state_manager.state_name)
                return

        if not self.tts_enabled:
            logger.debug("TTS is disabled; skipping spoken response.")
            return

        cleaned = text.strip()
        if not cleaned:
            return

        # Reject duplicate identical speech within short window (2.5s)
        now = time.time()
        if cleaned == getattr(self, "_last_spoken_text", "") and (now - getattr(self, "_last_spoken_time", 0.0)) < 2.5:
            logger.warning("[DIAGNOSTIC] Duplicate request rejected: duplicate speech synthesis request '%s'.", cleaned)
            return

        self._last_spoken_text = cleaned
        self._last_spoken_time = now
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            if hasattr(self.conversation_controller, "echo_suppressor"):
                self.conversation_controller.echo_suppressor.record_assistant_speech(cleaned)

        # Invalidate any ongoing or queued synthesis workers and stop current playback
        self._current_speak_id += 1
        speak_id = self._current_speak_id
        self.audio_player.stop()

        voice_kwargs = {}
        if hasattr(self, "selected_voice_profile") and self.selected_voice_profile:
            from app.voice.voice_registry import get_voice_profile
            p = get_voice_profile(self.selected_voice_profile)
            voice_kwargs["voice"] = p.primary_voice_id
            voice_kwargs["voice_name"] = p.primary_voice_id
            voice_kwargs["speed"] = p.speaking_rate

        worker = _TTSSpeakWorker(
            tts_engine=self.active_tts_engine,
            audio_player=self.audio_player,
            text=cleaned,
            speak_id=speak_id,
            is_active_fn=lambda sid: sid == self._current_speak_id,
            on_error=lambda err: self.error_occurred.emit(err),
            voice_kwargs=voice_kwargs,
        )
        self._thread_pool.start(worker)

    def stop_speaking(self) -> None:
        """Interrupt and stop current speech playback immediately (Phase 6)."""
        self._current_speak_id += 1
        self.audio_player.stop()
        if hasattr(self, "sapi_engine") and hasattr(self.sapi_engine, "stop"):
            try:
                self.sapi_engine.stop()
            except Exception:
                pass
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            if hasattr(self.conversation_controller, "audio_queue") and self.conversation_controller.audio_queue:
                self.conversation_controller.audio_queue.clear()
            if hasattr(self.conversation_controller, "interruption_manager") and self.conversation_controller.interruption_manager:
                try:
                    self.conversation_controller.interruption_manager.handle_user_interruption()
                except Exception:
                    pass
        signals.ai_speech_finished.emit()

    def stop(self) -> None:
        """Stop voice capture, speech playback, and wait for any ongoing TTS tasks."""
        self.set_mode(VoiceMode.OFF)
        self.stop_speaking()
        try:
            self.mic_manager.unsubscribe(self._on_audio_frame_received)
        except Exception:
            pass
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            self.conversation_controller.cleanup()
        if hasattr(self, "_thread_pool") and self._thread_pool:
            self._thread_pool.waitForDone(500)

    def unload_models(self, keep_wake_detector: bool = False) -> None:
        """Unload Piper, Kokoro, SAPI5, and Whisper model weights from memory (Phase 11.2, 11.8).
        
        Args:
            keep_wake_detector: If True, keep Whisper model loaded so wake-word detection
                                remains active during low-power sleep mode (Phase 4).
        """
        logger.info("Unloading voice models from memory (keep_wake_detector=%s)...", keep_wake_detector)
        if self.piper_engine and hasattr(self.piper_engine, "unload_model"):
            try:
                self.piper_engine.unload_model()
            except Exception as e:
                logger.debug("Error unloading Piper model: %s", e)
        if self.kokoro_engine and hasattr(self.kokoro_engine, "unload_model"):
            try:
                self.kokoro_engine.unload_model()
            except Exception as e:
                logger.debug("Error unloading Kokoro model: %s", e)
        if hasattr(self, "sapi_engine") and self.sapi_engine and hasattr(self.sapi_engine, "unload_model"):
            try:
                self.sapi_engine.unload_model()
            except Exception as e:
                logger.debug("Error unloading SAPI5 model: %s", e)
        if not keep_wake_detector and self.whisper_engine and hasattr(self.whisper_engine, "unload_model"):
            try:
                self.whisper_engine.unload_model()
            except Exception as e:
                logger.debug("Error unloading Whisper model: %s", e)

    def set_tts_enabled(self, enabled: bool) -> None:
        """Enable or disable spoken responses."""
        self.tts_enabled = enabled
        if not self.tts_enabled:
            self.stop_speaking()

    def set_tts_engine(self, engine_name: str) -> None:
        """Switch active TTS engine ('piper', 'kokoro', or 'system'/'sapi5')."""
        engine_key = engine_name.lower().strip()
        if "kokoro" in engine_key:
            self.active_tts_engine = self.kokoro_engine
            logger.info("Active TTS engine switched to Kokoro-82M.")
        elif any(k in engine_key for k in ("system", "sapi", "sapi5", "windows")):
            self.active_tts_engine = self.sapi_engine
            logger.info("Active TTS engine switched to Windows SAPI5 Voice.")
        elif "piper" in engine_key:
            self.active_tts_engine = self.piper_engine
            logger.info("Active TTS engine switched to Piper TTS.")
        else:
            # For unrecognized engine names, choose best working available engine
            if self.sapi_engine.is_available():
                self.active_tts_engine = self.sapi_engine
            else:
                self.active_tts_engine = self.piper_engine

        if hasattr(self, "conversation_controller"):
            if hasattr(self.conversation_controller, "set_tts_engine"):
                self.conversation_controller.set_tts_engine(self.active_tts_engine)
            else:
                self.conversation_controller.tts_engine = self.active_tts_engine
                if hasattr(self.conversation_controller, "audio_queue"):
                    self.conversation_controller.audio_queue.tts_engine = self.active_tts_engine

    def get_available_tts_engines(self) -> List[str]:
        """Return identifiers of available TTS engines."""
        engines = ["piper"]
        if hasattr(self.kokoro_engine, "is_available") and self.kokoro_engine.is_available():
            engines.append("kokoro")
        if hasattr(self, "sapi_engine") and hasattr(self.sapi_engine, "is_available") and self.sapi_engine.is_available():
            engines.append("system")
        return engines

    def get_available_voices(self) -> List[str]:
        """Return list of voice names available in the active or installed TTS engines."""
        if hasattr(self.active_tts_engine, "get_available_voices"):
            try:
                v = self.active_tts_engine.get_available_voices()
                if v:
                    return v
            except Exception:
                pass
        if hasattr(self, "sapi_engine") and hasattr(self.sapi_engine, "get_available_voices"):
            try:
                return self.sapi_engine.get_available_voices()
            except Exception:
                pass
        return []

    def is_tts_available(self) -> bool:
        """Check whether speech synthesis is operational directly or via fallback engine."""
        if hasattr(self.active_tts_engine, "is_available") and self.active_tts_engine.is_available():
            return True
        fb = getattr(self.active_tts_engine, "fallback_engine", None)
        if fb and hasattr(fb, "is_available") and fb.is_available():
            return True
        if hasattr(self, "sapi_engine") and hasattr(self.sapi_engine, "is_available") and self.sapi_engine.is_available():
            return True
        return getattr(self.active_tts_engine, "is_loaded", False)

    def set_voice(self, voice_name: str) -> None:
        """Set voice model for the active TTS engine."""
        self.active_tts_engine.load_model(voice_name)

    def set_voice_profile(self, profile_id: str) -> None:
        """Switch active companion voice profile dynamically without restarting (Phase 1.3)."""
        from app.voice.voice_registry import get_voice_profile
        profile = get_voice_profile(profile_id)
        if getattr(self, "selected_voice_profile", None) == profile.profile_id:
            return
        self.selected_voice_profile = profile.profile_id
        logger.info(
            "VoiceService: Switched voice profile to '%s' (%s, engine=%s, voice=%s)",
            profile.name,
            profile.gender,
            profile.primary_engine,
            profile.primary_voice_id,
        )
        # Ensure compatible TTS engine is selected
        if profile.primary_engine in ("kokoro", "piper", "sapi5"):
            self.set_tts_engine(profile.primary_engine)
        if hasattr(self.active_tts_engine, "load_model"):
            try:
                self.active_tts_engine.load_model(profile.primary_voice_id)
            except Exception as e:
                logger.debug("Active TTS load_model note: %s", e)
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            if getattr(self.conversation_controller, "selected_voice_profile", None) != profile.profile_id:
                self.conversation_controller.set_voice_profile(profile.profile_id)

    def play_voice_preview(self, profile_id: str, language: str = "en", text: Optional[str] = None) -> None:
        """Synthesize and play an instant preview sample for the given voice profile (Phase 1.4)."""
        from app.voice.voice_registry import get_voice_profile, get_preview_sample_text
        from app.ai.multilingual_engine import MultilingualEngine

        profile = get_voice_profile(profile_id)
        sample_text = text.strip() if (text and text.strip()) else get_preview_sample_text(language)
        logger.info("Playing voice preview for '%s' in [%s]: '%s'", profile.name, language.upper(), sample_text)

        # Unmute audio player if user explicitly clicked test/preview
        if hasattr(self.audio_player, "is_muted") and self.audio_player.is_muted:
            logger.info("Temporarily unmuting AudioPlayer for explicit voice preview request.")
            self.audio_player.set_muted(False)

        # Ensure volume is audible
        if hasattr(self.audio_player, "volume"):
            if self.audio_player.volume <= 0.05:
                cfg_vol = 0.8
                if self._config_manager:
                    try:
                        cfg_vol = float(self._config_manager.get("voice.volume", 0.8))
                    except Exception:
                        cfg_vol = 0.8
                self.audio_player.set_volume(max(0.5, cfg_vol))

        # Determine engine and matching voice ID
        if profile.primary_engine == "kokoro" and self.kokoro_engine.is_available():
            engine = self.kokoro_engine
            preferred_id = profile.primary_voice_id
        elif hasattr(self, "piper_engine") and self.piper_engine.is_available():
            engine = self.piper_engine
            preferred_id = profile.primary_voice_id
        else:
            engine = self.sapi_engine
            preferred_id = profile.fallback_voice_id or "david"

        engine_name = type(engine).__name__
        installed_voices = engine.get_available_voices() if hasattr(engine, "get_available_voices") else []

        spoken_text, voice_hint = MultilingualEngine.prepare_text_for_tts(
            text=sample_text,
            target_language=language,
            engine_name=engine_name,
            installed_voices=installed_voices,
            preferred_voice_id=preferred_id,
            preferred_gender=profile.gender,
        )

        effective_speed = profile.speaking_rate
        if self._config_manager:
            cfg_speed = self._config_manager.get("voice.voice_speed") or self._config_manager.get("voice.speed")
            if cfg_speed is not None:
                try:
                    effective_speed = float(cfg_speed) * profile.speaking_rate
                except Exception:
                    pass

        # Invalidate current speak ID and stop current playback
        self._current_speak_id += 1
        speak_id = self._current_speak_id
        self.audio_player.stop()

        signals.ai_speech_subtitle.emit(f"[{profile.name} - {profile.gender.title()}] {sample_text}")
        self.speaking_started.emit()

        final_voice = voice_hint or preferred_id

        worker = _TTSSpeakWorker(
            tts_engine=engine,
            audio_player=self.audio_player,
            text=spoken_text,
            speak_id=speak_id,
            is_active_fn=lambda sid: sid == self._current_speak_id,
            on_error=lambda err: self.error_occurred.emit(err),
            voice_kwargs={
                "voice": final_voice,
                "voice_name": final_voice,
                "speed": effective_speed,
            },
        )
        self._thread_pool.start(worker)

    def get_recent_timing_logs(self) -> list[dict[str, Any]]:
        """Return structured timing logs recorded for recent voice interactions (Phase 3)."""
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            return self.conversation_controller.get_recent_timing_logs()
        return []

    def set_tts_speed(self, speed: float) -> None:
        """Set speech playback speed (0.5 to 2.0)."""
        clamped = max(0.5, min(2.0, float(speed)))
        if hasattr(self, "active_tts_engine") and self.active_tts_engine:
            self.active_tts_engine.speed = clamped
        if hasattr(self, "kokoro_engine") and self.kokoro_engine:
            self.kokoro_engine.speed = clamped
        if hasattr(self, "piper_engine") and self.piper_engine:
            self.piper_engine.speed = clamped
        if hasattr(self, "sapi_engine") and self.sapi_engine:
            self.sapi_engine.speed = clamped

    def reload_from_config(self) -> None:
        """Reload all voice parameters from configuration after reset or reload."""
        if not self._config_manager:
            return
        cfg = self._config_manager.get_category("voice") or self._config_manager.get("voice", {})

        # Voice speed
        speed = float(cfg.get("voice_speed", 1.0))
        self.set_tts_speed(speed)

        # TTS engine
        configured_engine = cfg.get("tts_engine") or cfg.get("engine")
        if configured_engine:
            self.set_tts_engine(str(configured_engine))

        # TTS voice
        if "tts_voice" in cfg:
            self.set_voice(str(cfg["tts_voice"]))

        # Mode
        if "mode" in cfg:
            self.set_mode(str(cfg["mode"]))

        # Language
        configured_lang = cfg.get("language", "auto")
        self.language = None if configured_lang in ("auto", "", None) else configured_lang

        # Silence threshold
        if "silence_threshold_ms" in cfg:
            try:
                self.vad_engine.silence_threshold_ms = int(cfg["silence_threshold_ms"])
            except (ValueError, TypeError):
                self.vad_engine.silence_threshold_ms = 400

    def set_volume(self, volume: float) -> None:
        """Set output speaker volume (0.0 to 1.0)."""
        self.audio_player.set_volume(volume)

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute speaker playback."""
        self.audio_player.set_muted(muted)
        if hasattr(self, "buddy_state_manager") and self.buddy_state_manager:
            if muted and not self.buddy_state_manager.is_sleeping:
                self.buddy_state_manager.set_muted(True, reason="voice_service_set_muted")
            elif not muted and self.buddy_state_manager.is_muted:
                self.buddy_state_manager.set_muted(False, reason="voice_service_set_unmuted")

    # -------------------------------------------------------------------------
    # Push-to-Talk Flow (6.4)
    # -------------------------------------------------------------------------

    def start_push_to_talk(self) -> bool:
        """User pressed Push-to-Talk button. Begin recording audio."""
        if self._is_shutdown:
            logger.debug("Push-to-Talk rejected: VoiceService is shut down.")
            return False

        with self._ptt_lock:
            if self._is_push_to_talking:
                logger.warning("[DIAGNOSTIC] Duplicate request rejected: Push-to-talk already active.")
                return True

        # Stop speaking if AI was speaking so user can talk without feedback
        self.stop_speaking()

        ok = self.mic_manager.start_recording()
        if not ok:
            logger.error("[DIAGNOSTIC] Microphone unavailable: Push-to-Talk failed to open audio stream.")
            self.error_occurred.emit("Microphone unavailable or permission denied.")
            return False

        if self._mode == VoiceMode.OFF:
            self._mode = VoiceMode.PUSH_TO_TALK
            self.mode_changed.emit(VoiceMode.PUSH_TO_TALK.value)

        with self._ptt_lock:
            self._ptt_chunks.clear()
            self._is_push_to_talking = True

        logger.info("[DIAGNOSTIC] Recording started: Push-to-Talk active, recording user speech...")
        self.speech_detected.emit()
        self.listening_started.emit()
        return True

    def stop_push_to_talk(self) -> None:
        """User released Push-to-Talk button. Stop recording and transcribe."""
        with self._ptt_lock:
            if not self._is_push_to_talking:
                return
            self._is_push_to_talking = False
            chunks = list(self._ptt_chunks)
            self._ptt_chunks.clear()

        if self._mode == VoiceMode.PUSH_TO_TALK:
            self.mic_manager.stop_recording()
            logger.info("[DIAGNOSTIC] Microphone stopped.")
            self.listening_stopped.emit()

        if not chunks:
            logger.info("[DIAGNOSTIC] No speech detected: Push-to-Talk finished with no audio captured.")
            return

        combined_audio = np.concatenate(chunks)
        duration_sec = len(combined_audio) / self.mic_manager.sample_rate

        if duration_sec < 0.20:
            logger.info("[DIAGNOSTIC] No speech detected: Push-to-Talk audio click < 0.20s discarded.")
            return

        logger.info("[DIAGNOSTIC] Recording completed: Push-to-Talk captured %.2fs of audio.", duration_sec)
        logger.info("[DIAGNOSTIC] Transcription in progress: submitting Push-to-Talk audio to Whisper...")
        self._submit_to_whisper(combined_audio)

    # -------------------------------------------------------------------------
    # Search & Input Dictation (isolated non-conversational speech transcription)
    # -------------------------------------------------------------------------

    @property
    def is_dictating(self) -> bool:
        with self._dictation_lock:
            return self._is_dictating

    def start_dictation(self) -> bool:
        """Begin recording audio specifically for UI text dictation (e.g. Movie Hub search)."""
        if self._is_shutdown:
            logger.debug("Dictation rejected: VoiceService is shut down.")
            return False

        with self._dictation_lock:
            if self._is_dictating:
                logger.warning("Duplicate request: Dictation already active.")
                return True

        # Stop assistant speech if playing so there is no feedback
        self.stop_speaking()

        ok = self.mic_manager.start_recording()
        if not ok:
            logger.error("Microphone unavailable for dictation.")
            return False

        with self._dictation_lock:
            self._dictation_chunks.clear()
            self._is_dictating = True

        logger.info("Dictation started: capturing microphone audio for search/text input...")
        return True

    def stop_dictation(self) -> str:
        """Stop dictation recording, transcribe audio using local Whisper, and return recognized text."""
        with self._dictation_lock:
            if not self._is_dictating:
                return ""
            self._is_dictating = False
            chunks = list(self._dictation_chunks)
            self._dictation_chunks.clear()

        # If voice mode was off and not in push-to-talk, stop microphone stream
        if self._mode == VoiceMode.OFF and not self._is_push_to_talking:
            self.mic_manager.stop_recording()

        if not chunks:
            logger.info("Dictation finished with no audio chunks captured.")
            return ""

        combined_audio = np.concatenate(chunks)
        duration_sec = len(combined_audio) / self.mic_manager.sample_rate

        if duration_sec < 0.20:
            logger.info("Dictation discarded: audio duration < 0.20s.")
            return ""

        logger.info("Dictation transcribing %.2fs of audio with Whisper...", duration_sec)
        effective_lang = self.language if (self.language and self.language != "auto") else None

        try:
            result = self.whisper_engine.transcribe(
                audio_data=combined_audio,
                language=effective_lang,
                prompt="Search movies, TV shows, actors, directors",
            )
            text = (result.text or "").strip()
            # Clean common trailing punctuation from transcription (e.g. "Inception." -> "Inception")
            if text.endswith((".", ",", "!", "?")):
                text = text[:-1].strip()
            logger.info("Dictation transcribed successfully: '%s'", text)
            return text
        except Exception as e:
            logger.error("Error during dictation transcription: %s", e)
            return ""

    # -------------------------------------------------------------------------
    # Frame Processing & VAD Routing
    # -------------------------------------------------------------------------

    def _on_audio_frame_received(self, chunk: np.ndarray) -> None:
        """Callback invoked on every incoming audio frame from MicrophoneManager."""
        # Suppress incoming frames during active speaker output or acoustic cooldown
        if self.audio_player.is_in_cooldown(0.65) or self.audio_player.is_playing:
            if not self._is_push_to_talking and not self._is_dictating:
                return

        # Route to Dictation buffer if active (isolated UI search/dictation mode)
        if self._is_dictating:
            with self._dictation_lock:
                self._dictation_chunks.append(chunk)
            return

        # Route to Push-to-Talk buffer if active
        if self._is_push_to_talking:
            with self._ptt_lock:
                self._ptt_chunks.append(chunk)

        # Route to Continuous VAD engine only if conversation controller is not managing it
        if self._mode == VoiceMode.CONTINUOUS and not self._is_push_to_talking:
            if not (hasattr(self, "conversation_controller") and self.conversation_controller.is_enabled):
                self.vad_engine.process_frame(chunk)

    def _on_vad_speech_started(self) -> None:
        """Triggered by VADEngine when user starts speaking in Continuous mode."""
        if self._mode == VoiceMode.CONTINUOUS:
            # If AI was speaking, user speaking interrupts it!
            is_speaking = self.audio_player.is_playing or (
                hasattr(self, "conversation_controller")
                and hasattr(self.conversation_controller, "state")
                and getattr(self.conversation_controller.state, "value", "") in ("speaking", "ai_speaking")
            )
            if is_speaking:
                self.stop_speaking()
            logger.debug("Continuous VAD detected speech start.")
            self.speech_detected.emit()

    def _on_vad_speech_ended(self, utterance: np.ndarray) -> None:
        """Triggered by VADEngine when user completes utterance in Continuous mode."""
        if self._mode == VoiceMode.CONTINUOUS:
            if (
                hasattr(self, "conversation_controller")
                and self.conversation_controller.is_enabled
                and self.conversation_controller.ai_service is not None
            ):
                return
            duration_sec = len(utterance) / self.mic_manager.sample_rate
            logger.info("Continuous VAD speech segment completed: %.2fs", duration_sec)
            self._submit_to_whisper(utterance)

    # -------------------------------------------------------------------------
    # Whisper STT Dispatch & Callback
    # -------------------------------------------------------------------------

    def _submit_to_whisper(self, audio_data: np.ndarray) -> None:
        """Submit audio segment to background thread for Faster-Whisper transcription."""
        # Waveform-level AEC correlation check against assistant playback reference
        if hasattr(self, "conversation_controller") and self.conversation_controller:
            canceller = getattr(self.conversation_controller, "echo_canceller", None)
            if canceller and hasattr(canceller, "correlate_utterance_with_playback"):
                is_echo, corr, reason = canceller.correlate_utterance_with_playback(audio_data)
                if is_echo:
                    logger.warning(
                        "[DIAGNOSTIC] AEC: Discarded audio segment matching assistant playback (peak corr=%.3f, reason=%s).",
                        corr,
                        reason,
                    )
                    return

        self.transcription_started.emit()

        effective_lang = self.language if (self.language and self.language != "auto") else None
        prompt = None
        if effective_lang == "hi":
            prompt = "नमस्ते, आपका नाम क्या है? मैं आपकी कैसे मदद कर सकता हूँ?"
        elif effective_lang == "gu":
            prompt = "નમસ્તે, તમારું નામ શું છે? હું તમને કેવી રીતે મદદ કરી શકું?"
        elif effective_lang == "en":
            prompt = "Hello, how can I help you today?"
        else:
            prompt = "Hello, Namaste, Kem cho, Tamaru naam su che, Aapka naam kya hai, How are you?"

        def on_transcribed(result: TranscriptionResult) -> None:
            text = result.text.strip()
            if not text:
                logger.info("[DIAGNOSTIC] No speech detected: Transcription was empty/silence.")
                return

            # Echo cancellation check
            if hasattr(self, "conversation_controller") and self.conversation_controller:
                suppressor = getattr(self.conversation_controller, "echo_suppressor", None)
                if suppressor and hasattr(suppressor, "is_echo"):
                    is_echo, reason, conf = suppressor.is_echo(text)
                    if is_echo:
                        logger.warning("[DIAGNOSTIC] Unexpected audio capture detected: Discarding recognized text matching assistant response echo (%s, conf=%.2f): '%s'", reason, conf, text)
                        return

            logger.info("[DIAGNOSTIC] Transcription completed: '%s' [%s]", text, result.language)
            logger.info(
                "Recognized speech [%s (%.2f)]: '%s'",
                result.language,
                result.language_probability,
                text,
            )
            self.transcription_ready.emit(text, result.language)

        self.whisper_engine.transcribe_async(
            audio_data=audio_data,
            language=effective_lang,
            prompt=prompt,
            callback=on_transcribed,
        )
