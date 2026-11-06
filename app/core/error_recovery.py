"""Robust Error Recovery Coordinator (Phase 11.6).

Provides centralized recovery policies and user-facing notifications for:
- Ollama daemon offline / stopping.
- Missing AI model.
- Microphone disconnection.
- Speaker disconnection.
- TTS synthesis failure.
- STT speech recognition timeout.
- Background worker crash.
- Post-sleep / resume subsystem revalidation.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ErrorDescriptor:
    """Structured descriptor for categorized application errors."""
    error_type: str
    title: str
    message: str
    recovery_action: str = "none"
    recovery_label: str = ""
    urgency: str = "warning"  # "info", "warning", "error"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "title": self.title,
            "message": self.message,
            "recovery_action": self.recovery_action,
            "recovery_label": self.recovery_label,
            "urgency": self.urgency,
        }


class ErrorRecoveryCoordinator(QObject):
    """Coordinates error recovery strategies and user-facing notifications."""

    # Emitted to display a user-friendly error notification toast / message: (title, message, urgency)
    user_alert_requested = Signal(str, str, str)  # (title, message, "info"|"warning"|"error")
    # Emitted with structured ErrorDescriptor for modern UI consumption
    structured_error_emitted = Signal(object)     # ErrorDescriptor
    # Emitted when a subsystem successfully auto-recovers: subsystem_name
    subsystem_recovered = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._ollama_probe_timer = QTimer(self)
        self._ollama_probe_timer.setInterval(5000)
        self._ollama_probe_timer.timeout.connect(self._probe_ollama_recovery)
        self._probing_ollama = False
        self._target_ollama_client = None

        self._recent_errors: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _should_suppress_duplicate_alert(self, error_key: str, cooldown_sec: float = 10.0) -> bool:
        """Rate limit repeated alerts for the same underlying issue."""
        now = time.time()
        with self._lock:
            last_time = self._recent_errors.get(error_key, 0.0)
            if now - last_time < cooldown_sec:
                return True
            self._recent_errors[error_key] = now
            return False

    # -------------------------------------------------------------------------
    # AI & Ollama Error Recovery
    # -------------------------------------------------------------------------

    def handle_ollama_error(self, exc: Exception, model_name: str, client: Optional[Any] = None) -> None:
        """Handle Ollama server offline, timeout, or missing model."""
        from app.ai.ollama_client import (
            OllamaCancelledError,
            OllamaConnectionError,
            OllamaModelNotFoundError,
            OllamaTimeoutError,
        )

        if isinstance(exc, OllamaCancelledError):
            logger.debug("Ollama inference was deliberately cancelled by user.")
            self.handle_interrupted_request()
            return

        if isinstance(exc, OllamaModelNotFoundError):
            self.handle_model_loading_failure(model_name, str(exc))
            return

        if isinstance(exc, (OllamaConnectionError, ConnectionRefusedError)):
            self.handle_llm_unavailable(model_name, client)
            return

        if isinstance(exc, (OllamaTimeoutError, TimeoutError)):
            self.handle_backend_timeout()
            return

        # Generic AI exception
        err_str = str(exc)
        if not self._should_suppress_duplicate_alert(f"ai_generic_{err_str[:20]}"):
            desc = ErrorDescriptor(
                error_type="llm_error",
                title="AI Inference Error",
                message=f"Encountered: {err_str}",
                recovery_action="retry_request",
                recovery_label="Retry",
                urgency="warning",
            )
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
            self.structured_error_emitted.emit(desc)

    def _probe_ollama_recovery(self) -> None:
        """Periodically check if Ollama has returned online."""
        if not self._target_ollama_client:
            self._ollama_probe_timer.stop()
            self._probing_ollama = False
            return

        try:
            if self._target_ollama_client.is_server_reachable():
                logger.info("ErrorRecovery: Ollama service restored and reachable!")
                self._ollama_probe_timer.stop()
                self._probing_ollama = False
                self.subsystem_recovered.emit("ollama")
                self.user_alert_requested.emit(
                    "Ollama Connected",
                    "Local AI engine is back online and ready.",
                    "info",
                )
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Audio & Voice Hardware Disconnection
    # -------------------------------------------------------------------------

    def handle_microphone_disconnection(self, error_msg: str, voice_service: Optional[Any] = None) -> None:
        """Handle physical or driver disconnection of input microphone."""
        logger.error("ErrorRecovery: Microphone disconnection detected: %s", error_msg)
        if not self._should_suppress_duplicate_alert("mic_disconnect"):
            title = "Audio Device Issue"
            msg = "Microphone or speaker connection issue detected. Voice listening has been paused."
            self.user_alert_requested.emit(title, msg, "warning")

        if voice_service:
            try:
                voice_service.set_mode("off")
            except Exception as e:
                logger.error("Error setting voice mode to off on mic disconnect: %s", e)

    def handle_audio_device_error(self, error_msg: str, voice_service: Optional[Any] = None) -> None:
        """Alias for handle_microphone_disconnection or general audio device error."""
        self.handle_microphone_disconnection(error_msg, voice_service)

    def handle_speaker_disconnection(self, error_msg: str, audio_player: Optional[Any] = None) -> None:
        """Handle output audio playback device disconnection."""
        logger.error("ErrorRecovery: Speaker disconnection detected: %s", error_msg)
        if not self._should_suppress_duplicate_alert("speaker_disconnect"):
            title = "Audio Output Disconnected"
            msg = "Playback device unavailable. Spoken audio paused."
            self.user_alert_requested.emit(title, msg, "warning")

        if audio_player:
            try:
                audio_player.stop()
            except Exception as e:
                logger.error("Error stopping audio player on speaker disconnect: %s", e)

    # -------------------------------------------------------------------------
    # TTS & STT Failures
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Comprehensive Error Handlers (Task 7)
    # -------------------------------------------------------------------------

    def handle_microphone_permission_denied(self) -> ErrorDescriptor:
        """1. Handle microphone access denied by operating system or privacy settings."""
        desc = ErrorDescriptor(
            error_type="mic_permission_denied",
            title="Microphone Access Denied",
            message="Microphone permission was denied by Windows privacy settings. Please allow microphone access in Windows Settings.",
            recovery_action="open_privacy_settings",
            recovery_label="Open Windows Settings",
            urgency="error",
        )
        logger.error("ErrorRecovery: %s - %s", desc.title, desc.message)
        if not self._should_suppress_duplicate_alert("mic_permission_denied"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        return desc

    def handle_microphone_unavailable(self, error_msg: str = "", voice_service: Optional[Any] = None) -> ErrorDescriptor:
        """2. Handle microphone missing, disconnected, or failed to open stream."""
        desc = ErrorDescriptor(
            error_type="mic_unavailable",
            title="Microphone Unavailable",
            message="No active microphone detected. Please plug in a microphone or select an input device in Settings.",
            recovery_action="retry_device",
            recovery_label="Retry Microphone",
            urgency="warning",
        )
        logger.warning("ErrorRecovery: %s - %s (%s)", desc.title, desc.message, error_msg)
        if not self._should_suppress_duplicate_alert("mic_unavailable"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        if voice_service:
            try:
                voice_service.set_mode("off")
            except Exception as e:
                logger.debug("Error pausing voice on mic unavailable: %s", e)
        return desc

    def handle_empty_transcription(self, voice_controller: Optional[Any] = None, notify_user: bool = False) -> ErrorDescriptor:
        """3. Handle VAD speech completed but Whisper transcribed empty text or pure silence."""
        desc = ErrorDescriptor(
            error_type="empty_transcription",
            title="No Speech Heard",
            message="I couldn't hear any speech. Please speak a little louder or closer to the microphone.",
            recovery_action="listen_again",
            recovery_label="Try Speaking Again",
            urgency="info",
        )
        logger.info("ErrorRecovery: %s - %s", desc.title, desc.message)
        # Empty speech/ambient silence is routine: do not pop intrusive OS toast banners unless requested
        if notify_user and not self._should_suppress_duplicate_alert("empty_transcription", cooldown_sec=10.0):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        if voice_controller and hasattr(voice_controller, "vad_engine"):
            voice_controller.vad_engine.reset_states()
        return desc

    def handle_stt_timeout(self, voice_controller: Optional[Any] = None) -> ErrorDescriptor:
        """4. Handle speech recognition timeout or silence hang."""
        desc = ErrorDescriptor(
            error_type="stt_timeout",
            title="Speech Transcription Timed Out",
            message="Speech recognition took too long to respond. The audio buffer has been reset.",
            recovery_action="retry",
            recovery_label="Try Speaking Again",
            urgency="warning",
        )
        logger.warning("ErrorRecovery: %s - %s", desc.title, desc.message)
        if not self._should_suppress_duplicate_alert("stt_timeout"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        if voice_controller:
            try:
                if hasattr(voice_controller, "vad_engine"):
                    voice_controller.vad_engine.reset_states()
            except Exception:
                pass
        return desc

    def handle_llm_unavailable(self, model_name: str = "", client: Optional[Any] = None) -> ErrorDescriptor:
        """5. Handle Ollama offline, unreachable, or crashed."""
        desc = ErrorDescriptor(
            error_type="llm_unavailable",
            title="AI Engine Disconnected (Ollama Offline)",
            message="Could not connect to Ollama. The Ollama service is not running or unreachable on http://127.0.0.1:11434.",
            recovery_action="start_ollama",
            recovery_label="Start Ollama",
            urgency="error",
        )
        logger.error("ErrorRecovery: %s - %s", desc.title, desc.message)
        if not self._should_suppress_duplicate_alert("ollama_offline"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)

        # Start background probing to notify user when Ollama comes back
        if not self._probing_ollama:
            self._target_ollama_client = client
            self._probing_ollama = True
            self._ollama_probe_timer.start()
        return desc

    def handle_model_loading_failure(self, model_name: str, error_msg: str = "") -> ErrorDescriptor:
        """6. Handle model not found in Ollama, GPU OOM, or model corrupted."""
        is_missing = "not found" in error_msg.lower() or "missing" in error_msg.lower() or not error_msg
        title = "AI Model Not Found" if is_missing else "AI Model Loading Failed"
        msg = (
            f"Model '{model_name}' is not installed in Ollama.\n"
            f"Run 'ollama pull {model_name}' in your terminal, or pick an installed model in Settings."
        ) if is_missing else (
            f"Model '{model_name}' could not be loaded into memory. It may not be installed or system memory is low. "
            f"Run 'ollama pull {model_name}' or select another model in Settings."
        )
        desc = ErrorDescriptor(
            error_type="model_not_found" if is_missing else "model_loading_failure",
            title=title,
            message=msg,
            recovery_action="select_model",
            recovery_label="Select Model",
            urgency="warning",
        )
        logger.warning("ErrorRecovery: %s - %s (detail: %s)", desc.title, desc.message, error_msg)
        if not self._should_suppress_duplicate_alert(f"model_fail_{model_name}"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        return desc

    def handle_backend_timeout(self, request_id: Optional[str] = None) -> ErrorDescriptor:
        """7. Handle backend request or local LLM generation timeout."""
        desc = ErrorDescriptor(
            error_type="backend_timeout",
            title="Request Timed Out",
            message="The request timed out while waiting for a response from the backend or local AI model.",
            recovery_action="retry_request",
            recovery_label="Retry",
            urgency="warning",
        )
        logger.warning("ErrorRecovery: %s - %s (request_id=%s)", desc.title, desc.message, request_id)
        if not self._should_suppress_duplicate_alert("backend_timeout"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        return desc

    def handle_tts_failure(self, error_msg: str, engine_name: str = "") -> ErrorDescriptor:
        """8. Handle neural TTS synthesis failure with automatic fallback."""
        desc = ErrorDescriptor(
            error_type="tts_failure",
            title="Speech Playback Notice",
            message=f"Neural TTS ({engine_name or 'engine'}) synthesis failed; falling back to alternative voice.",
            recovery_action="fallback_tts",
            recovery_label="Use Default Voice",
            urgency="info",
        )
        logger.warning("ErrorRecovery: %s - %s (%s)", desc.title, desc.message, error_msg)
        if not self._should_suppress_duplicate_alert("tts_failure"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        return desc

    def handle_audio_playback_failure(self, error_msg: str = "", audio_player: Optional[Any] = None) -> ErrorDescriptor:
        """9. Handle output audio stream failure or speaker disconnection."""
        desc = ErrorDescriptor(
            error_type="playback_failure",
            title="Audio Playback Failed",
            message="Audio output device unavailable or stream failed. Spoken audio paused.",
            recovery_action="retry_playback",
            recovery_label="Retry Speaker",
            urgency="warning",
        )
        logger.error("ErrorRecovery: %s - %s (%s)", desc.title, desc.message, error_msg)
        if not self._should_suppress_duplicate_alert("playback_failure"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        if audio_player:
            try:
                audio_player.stop()
            except Exception as e:
                logger.debug("Error stopping audio player on playback failure: %s", e)
        return desc

    def handle_interrupted_request(self) -> ErrorDescriptor:
        """10. Handle deliberate request cancellation or user barge-in."""
        desc = ErrorDescriptor(
            error_type="interrupted_request",
            title="Request Stopped",
            message="Response generation was stopped by user.",
            recovery_action="none",
            recovery_label="",
            urgency="info",
        )
        logger.debug("ErrorRecovery: %s", desc.title)
        # Deliberate cancellations do not trigger intrusive warning alerts
        self.structured_error_emitted.emit(desc)
        return desc

    def handle_duplicate_request(self, prompt: str = "") -> ErrorDescriptor:
        """11. Handle duplicate concurrent message or turn submission."""
        desc = ErrorDescriptor(
            error_type="duplicate_request",
            title="Duplicate Request Ignored",
            message="Duplicate request ignored — already processing your message.",
            recovery_action="none",
            recovery_label="",
            urgency="info",
        )
        logger.info("ErrorRecovery: %s - Prompt '%s' already in-flight", desc.title, prompt[:40] if prompt else "")
        self.structured_error_emitted.emit(desc)
        return desc

    def classify_and_handle(self, error_str: str, context: Optional[Dict[str, Any]] = None) -> ErrorDescriptor:
        """Classify any incoming error string into a structured ErrorDescriptor and trigger recovery."""
        ctx = context or {}
        lowered = error_str.lower()

        # 1. Microphone permission
        if "permission" in lowered or "access denied" in lowered or "-9996" in lowered or "-9999" in lowered:
            return self.handle_microphone_permission_denied()

        # 2. Microphone unavailable / disconnected
        if (
            "microphone unavailable" in lowered
            or "device unavailable" in lowered
            or "no audio input" in lowered
            or "mic_disconnect" in lowered
        ):
            return self.handle_microphone_unavailable(error_str, voice_service=ctx.get("voice_service"))

        # 3. Empty transcription / no speech
        if "no speech" in lowered or "empty transcription" in lowered or "no clear speech" in lowered or "silence" in lowered:
            return self.handle_empty_transcription(voice_controller=ctx.get("voice_controller"))

        # 4. STT timeout
        if "stt" in lowered and ("timeout" in lowered or "timed out" in lowered):
            return self.handle_stt_timeout(voice_controller=ctx.get("voice_controller"))

        # 10. Interrupted / cancelled request
        if "cancel" in lowered or "interrupt" in lowered or "barge-in" in lowered:
            return self.handle_interrupted_request()

        # 11. Duplicate request
        if "duplicate" in lowered:
            return self.handle_duplicate_request(prompt=ctx.get("prompt", ""))

        # 5. LLM unavailable / Ollama offline
        if (
            "ollama" in lowered and ("offline" in lowered or "unreachable" in lowered or "not running" in lowered or "connection refused" in lowered)
        ) or "connection refused" in lowered or "service is not running" in lowered:
            return self.handle_llm_unavailable(model_name=ctx.get("model_name", ""), client=ctx.get("client"))

        # 6. Model-loading failure
        if "not found" in lowered or "model loading" in lowered or "out of memory" in lowered or "cuda oom" in lowered:
            model_name = ctx.get("model_name", "llama3.2:3b")
            return self.handle_model_loading_failure(model_name, error_str)

        # 7. Backend timeout
        if "timeout" in lowered or "timed out" in lowered:
            return self.handle_backend_timeout(request_id=ctx.get("request_id"))

        # 8. TTS generation failure
        if "tts" in lowered or "synthesis" in lowered or "kokoro" in lowered or "piper" in lowered:
            return self.handle_tts_failure(error_str, engine_name=ctx.get("engine_name", ""))

        # 9. Audio playback failure
        if "playback" in lowered or "output stream" in lowered or "speaker" in lowered:
            return self.handle_audio_playback_failure(error_str, audio_player=ctx.get("audio_player"))

        # Fallback generic error
        desc = ErrorDescriptor(
            error_type="generic_error",
            title="System Alert",
            message=error_str,
            recovery_action="retry",
            recovery_label="Dismiss",
            urgency="warning",
        )
        if not self._should_suppress_duplicate_alert(f"generic_{error_str[:30]}"):
            self.user_alert_requested.emit(desc.title, desc.message, desc.urgency)
        self.structured_error_emitted.emit(desc)
        return desc

    def handle_tts_error(self, error_msg: str, engine_name: str = "") -> None:
        """Alias for handle_tts_failure."""
        self.handle_tts_failure(error_msg, engine_name=engine_name)

    # -------------------------------------------------------------------------
    # Worker Crash Recovery
    # -------------------------------------------------------------------------

    def handle_worker_crash(self, worker_name: str, exc: Exception) -> None:
        """Handle unexpected exceptions in background threads/runnables."""
        logger.critical("ErrorRecovery: Worker '%s' crashed with error: %s", worker_name, exc, exc_info=True)
        if not self._should_suppress_duplicate_alert(f"worker_{worker_name}"):
            self.user_alert_requested.emit(
                "Background Task Error",
                f"Task '{worker_name}' encountered an error and recovered.",
                "warning",
            )

    # -------------------------------------------------------------------------
    # Post-Sleep / Resume Subsystem Revalidation
    # -------------------------------------------------------------------------

    def revalidate_after_resume(
        self,
        ai_service: Optional[Any] = None,
        voice_service: Optional[Any] = None,
    ) -> None:
        """Revalidate audio devices, background connections, and service states after Windows resumes."""
        logger.info("ErrorRecovery: Initiating post-resume hardware & service revalidation...")

        revalidated_items = []

        # 1. Revalidate Audio Devices
        if voice_service:
            try:
                # Re-query input and output devices through sounddevice
                import sounddevice as sd
                sd._terminate()
                sd._initialize()
                inputs = voice_service.mic_manager.get_input_devices()
                outputs = voice_service.audio_player.get_output_devices()
                logger.info(
                    "ErrorRecovery: Re-enumerated audio hardware: %d inputs, %d outputs.",
                    len(inputs),
                    len(outputs),
                )
                revalidated_items.append("Audio Devices")
                self.subsystem_recovered.emit("audio_subsystem")
            except Exception as e:
                logger.warning("Error re-initializing PortAudio after resume: %s", e)

        # 2. Revalidate Ollama
        if ai_service:
            try:
                is_online = False
                if hasattr(ai_service, "model_manager") and hasattr(ai_service.model_manager, "is_available"):
                    is_online = ai_service.model_manager.is_available()
                elif hasattr(ai_service, "client") and hasattr(ai_service.client, "check_health"):
                    is_online = ai_service.client.check_health()

                logger.info("ErrorRecovery: Ollama connection post-resume: %s", "Online" if is_online else "Offline")
                if is_online:
                    revalidated_items.append("AI Service")
                    self.subsystem_recovered.emit("ai_engine")
            except Exception as e:
                logger.warning("Error checking Ollama post-resume: %s", e)

        summary_msg = f"Revalidated {', '.join(revalidated_items)} after system sleep." if revalidated_items else "System services refreshed."
        self.user_alert_requested.emit("System Resumed", summary_msg, "info")
