"""Diagnostic Mode and Structured Voice Pipeline Telemetry.

Phase 10 — Diagnostic Mode:
Provides safe, structured diagnostic statuses and development logging
to identify where voice communication fails across:
1. Microphone status
2. Recording status
3. Audio duration or sample count
4. Transcription status
5. Recognized-text availability
6. User-message submission status
7. Backend connection status
8. Model-generation status
9. Assistant-response status
10. TTS generation status
11. Audio playback status

Ensures internal stack traces, credentials, and private data are never exposed in UI,
while keeping detailed diagnostic information in development logs.
Enables clean runtime toggling behind the project's debug setting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import threading
import time
from typing import Any, Dict, Optional

from app.utils.logger import get_logger

logger = get_logger("ai_desktop_friend.diagnostic")


# Standard safe user-facing error constants
ERROR_MIC_PERMISSION = "Microphone permission denied."
ERROR_NO_SPEECH = "No speech was detected. Please try again."
ERROR_SUBMISSION_FAILED = "Speech was recognized, but the message could not be sent."
ERROR_MODEL_UNAVAILABLE = "The AI model is unavailable. Check that the local model service is running."
ERROR_TTS_FAILED = "The AI replied, but text-to-speech failed."


@dataclass
class DiagnosticState:
    """Structured snapshot of voice communication pipeline health."""

    enabled: bool = False
    microphone_status: str = "idle"            # idle | ready | recording | permission_denied | unavailable
    recording_status: str = "idle"             # idle | recording | stopped
    audio_duration_sec: float = 0.0            # Duration of captured utterance
    audio_sample_count: int = 0                # Sample count of captured utterance
    transcription_status: str = "idle"         # idle | in_progress | completed | failed | no_speech | empty
    recognized_text_available: bool = False    # True if transcription produced valid text
    recognized_text_preview: str = ""          # Safe truncated preview (no credentials/private data)
    user_message_submission_status: str = "idle"  # idle | submitting | submitted | failed
    backend_connection_status: str = "idle"    # idle | connected | disconnected | connecting
    model_generation_status: str = "idle"      # idle | thinking | generating | completed | unavailable | failed
    assistant_response_status: str = "idle"    # idle | receiving | streaming | received | completed | failed
    tts_generation_status: str = "idle"        # idle | synthesizing | synthesized | failed
    audio_playback_status: str = "idle"        # idle | playing | completed | stopped | failed
    last_error: Optional[str] = None           # Safe user-facing error message

    # Phase 13: Stage latency telemetry (milliseconds)
    speech_recognition_latency_ms: float = 0.0
    backend_request_latency_ms: float = 0.0
    model_time_to_first_output_ms: float = 0.0
    total_model_generation_ms: float = 0.0
    tts_generation_time_ms: float = 0.0
    time_to_first_audible_response_ms: float = 0.0

    timestamp: float = 0.0


class DiagnosticTracker:
    """Central thread-safe manager for diagnostic mode and structured voice pipeline logs."""

    # Re-export error constants
    ERROR_MIC_PERMISSION = ERROR_MIC_PERMISSION
    ERROR_NO_SPEECH = ERROR_NO_SPEECH
    ERROR_SUBMISSION_FAILED = ERROR_SUBMISSION_FAILED
    ERROR_MODEL_UNAVAILABLE = ERROR_MODEL_UNAVAILABLE
    ERROR_TTS_FAILED = ERROR_TTS_FAILED

    def __init__(self, enabled: bool = False) -> None:
        self._lock = threading.Lock()
        self._state = DiagnosticState(enabled=enabled, timestamp=time.time())
        self._ws_manager = None

    def set_ws_manager(self, ws_manager: Any) -> None:
        """Register the WebSocket manager for real-time diagnostic updates."""
        self._ws_manager = ws_manager

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._state.enabled

    @property
    def is_enabled(self) -> bool:
        """Alias for enabled property."""
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable diagnostic instrumentation."""
        with self._lock:
            self._state.enabled = enabled
            self._state.timestamp = time.time()
        logger.info("[DIAGNOSTIC] Diagnostic mode set to: %s", "ENABLED" if enabled else "DISABLED")
        # Always broadcast the enable/disable transition so clients know the current state
        self._broadcast(force=True)

    def get_state(self) -> DiagnosticState:
        with self._lock:
            # Return a shallow copy
            return DiagnosticState(**asdict(self._state))

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            d = asdict(self._state)
            d["audio_duration_sec"] = round(d["audio_duration_sec"], 2)
            d["speech_recognition_latency_ms"] = round(d["speech_recognition_latency_ms"], 1)
            d["backend_request_latency_ms"] = round(d["backend_request_latency_ms"], 1)
            d["model_time_to_first_output_ms"] = round(d["model_time_to_first_output_ms"], 1)
            d["total_model_generation_ms"] = round(d["total_model_generation_ms"], 1)
            d["tts_generation_time_ms"] = round(d["tts_generation_time_ms"], 1)
            d["time_to_first_audible_response_ms"] = round(d["time_to_first_audible_response_ms"], 1)
            return d

    def get_status(self) -> Dict[str, Any]:
        """Fetch current diagnostic status dictionary."""
        return self.to_dict()

    def reset_turn(self) -> None:
        """Reset turn-specific metrics for a new conversational utterance."""
        with self._lock:
            if not self._state.enabled:
                return
            self._state.recording_status = "idle"
            self._state.audio_duration_sec = 0.0
            self._state.audio_sample_count = 0
            self._state.transcription_status = "idle"
            self._state.recognized_text_available = False
            self._state.recognized_text_preview = ""
            self._state.user_message_submission_status = "idle"
            self._state.model_generation_status = "idle"
            self._state.assistant_response_status = "idle"
            self._state.tts_generation_status = "idle"
            self._state.audio_playback_status = "idle"
            self._state.speech_recognition_latency_ms = 0.0
            self._state.backend_request_latency_ms = 0.0
            self._state.model_time_to_first_output_ms = 0.0
            self._state.total_model_generation_ms = 0.0
            self._state.tts_generation_time_ms = 0.0
            self._state.time_to_first_audible_response_ms = 0.0
            self._state.last_error = None
            self._state.timestamp = time.time()
        logger.debug("[DIAGNOSTIC] Voice turn metrics reset.")
        self._broadcast()

    def update_stage_latencies(self, metrics: Dict[str, Any]) -> None:
        """Update measured stage performance latencies (Phase 13)."""
        with self._lock:
            if not self._state.enabled:
                return
            if "speech_recognition_latency_ms" in metrics:
                self._state.speech_recognition_latency_ms = float(metrics["speech_recognition_latency_ms"])
            elif "stt_latency_ms" in metrics:
                self._state.speech_recognition_latency_ms = float(metrics["stt_latency_ms"])

            if "backend_request_latency_ms" in metrics:
                self._state.backend_request_latency_ms = float(metrics["backend_request_latency_ms"])

            if "model_time_to_first_output_ms" in metrics:
                self._state.model_time_to_first_output_ms = float(metrics["model_time_to_first_output_ms"])
            elif "llm_first_token_latency_ms" in metrics:
                self._state.model_time_to_first_output_ms = float(metrics["llm_first_token_latency_ms"])

            if "total_model_generation_ms" in metrics:
                self._state.total_model_generation_ms = float(metrics["total_model_generation_ms"])

            if "tts_generation_time_ms" in metrics:
                self._state.tts_generation_time_ms = float(metrics["tts_generation_time_ms"])
            elif "tts_first_audio_latency_ms" in metrics:
                self._state.tts_generation_time_ms = float(metrics["tts_first_audio_latency_ms"])

            if "time_to_first_audible_response_ms" in metrics:
                self._state.time_to_first_audible_response_ms = float(metrics["time_to_first_audible_response_ms"])
            elif "time_to_first_playback_ms" in metrics:
                self._state.time_to_first_audible_response_ms = float(metrics["time_to_first_playback_ms"])

            self._state.timestamp = time.time()

        logger.info(
            "[PERFORMANCE] Stage Latencies: STT=%.1fms | Backend=%.1fms | TTFT=%.1fms | Total LLM=%.1fms | TTS=%.1fms | Sound=%.1fms",
            self._state.speech_recognition_latency_ms,
            self._state.backend_request_latency_ms,
            self._state.model_time_to_first_output_ms,
            self._state.total_model_generation_ms,
            self._state.tts_generation_time_ms,
            self._state.time_to_first_audible_response_ms,
        )
        self._broadcast()

    # ─── Stage Updaters with Structured Logging ──────────────────────────────

    def update_microphone(
        self,
        status: str,
        error: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        device_name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Record microphone hardware/permission status."""
        safe_err = None
        if error:
            safe_err = self._sanitize_error(error, fallback=ERROR_MIC_PERMISSION)

        with self._lock:
            if not self._state.enabled:
                return
            self._state.microphone_status = status
            if safe_err:
                self._state.last_error = safe_err
            self._state.timestamp = time.time()

        if status == "permission_denied":
            logger.error("[DIAGNOSTIC] [MIC] status: permission_denied | Error: %s", safe_err)
        elif status == "unavailable":
            logger.warning("[DIAGNOSTIC] [MIC] status: unavailable | Error: %s", safe_err)
        else:
            logger.info(
                "[DIAGNOSTIC] [MIC] status=%s | Device: %s | Format: %sHz %sch",
                status,
                device_name or "default",
                sample_rate or 16000,
                channels or 1,
            )

        self._broadcast()

    def update_recording(
        self,
        status: str,
        duration_sec: float = 0.0,
        sample_count: int = 0,
        **kwargs: Any,
    ) -> None:
        """Record microphone recording and audio capture telemetry."""
        with self._lock:
            if not self._state.enabled:
                return
            self._state.recording_status = status
            if duration_sec > 0:
                self._state.audio_duration_sec = duration_sec
            if sample_count > 0:
                self._state.audio_sample_count = sample_count
            self._state.timestamp = time.time()

        logger.info(
            "[DIAGNOSTIC] [RECORDING] status=%s | Duration: %.2fs | Samples: %d",
            status,
            duration_sec,
            sample_count,
        )
        self._broadcast()

    def update_transcription(
        self,
        status: str,
        text: Optional[str] = None,
        recognized_text: Optional[str] = None,
        error: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Record speech recognition (STT) progress, recognized-text availability, or rejection."""
        if recognized_text is not None and text is None:
            text = recognized_text

        safe_err = None
        preview = ""
        has_text = False

        if status in ("no_speech", "empty"):
            safe_err = error if error else ERROR_NO_SPEECH
        elif error:
            safe_err = self._sanitize_error(error, fallback=ERROR_NO_SPEECH)

        if text is not None:
            cleaned = text.strip()
            if cleaned:
                has_text = True
                # Generate safe preview: truncate to 48 characters, no newlines
                preview = cleaned[:48].replace("\n", " ")
                if len(cleaned) > 48:
                    preview += "..."

        with self._lock:
            if not self._state.enabled:
                return
            self._state.transcription_status = status
            self._state.recognized_text_available = has_text
            if preview:
                self._state.recognized_text_preview = preview
            if safe_err:
                self._state.last_error = safe_err
            self._state.timestamp = time.time()

        if status in ("no_speech", "empty"):
            logger.warning("[DIAGNOSTIC] [TRANSCRIPTION] status=%s | Notice: %s", status, safe_err)
        elif status == "completed":
            logger.info(
                "[DIAGNOSTIC] [TRANSCRIPTION] status=completed | Text available: %s | Preview: '%s'",
                has_text,
                preview,
            )
        else:
            logger.info("[DIAGNOSTIC] [TRANSCRIPTION] status=%s", status)

        self._broadcast()

    def update_submission(self, status: str, error: Optional[str] = None, **kwargs: Any) -> None:
        """Record user message submission from frontend/voice to chat backend."""
        safe_err = None
        if error or status == "failed":
            safe_err = self._sanitize_error(error, fallback=ERROR_SUBMISSION_FAILED)

        with self._lock:
            if not self._state.enabled:
                return
            self._state.user_message_submission_status = status
            if safe_err:
                self._state.last_error = safe_err
            self._state.timestamp = time.time()

        if status == "failed":
            logger.error("[DIAGNOSTIC] [SUBMISSION] status=failed | Error: %s", safe_err)
        else:
            logger.info("[DIAGNOSTIC] [SUBMISSION] status=%s", status)

        self._broadcast()

    def update_backend_connection(self, status: str, **kwargs: Any) -> None:
        """Record backend WebSocket / server connection status."""
        with self._lock:
            if not self._state.enabled:
                return
            self._state.backend_connection_status = status
            self._state.timestamp = time.time()
        logger.info("[DIAGNOSTIC] [BACKEND] status=%s", status)
        self._broadcast()

    def update_model_generation(
        self,
        status: str,
        error: Optional[str] = None,
        model_name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Record local AI model execution status."""
        safe_err = None
        if status in ("unavailable", "failed") or error:
            safe_err = self._sanitize_error(error, fallback=ERROR_MODEL_UNAVAILABLE)

        with self._lock:
            if not self._state.enabled:
                return
            self._state.model_generation_status = status
            if safe_err:
                self._state.last_error = safe_err
            self._state.timestamp = time.time()

        if status in ("unavailable", "failed"):
            logger.error(
                "[DIAGNOSTIC] [MODEL] status=%s | Model: %s | Error: %s",
                status,
                model_name or "local",
                safe_err,
            )
        else:
            logger.info(
                "[DIAGNOSTIC] [MODEL] status=%s | Model: %s",
                status,
                model_name or "local",
            )

        self._broadcast()

    def update_model(
        self,
        status: str,
        model_name: Optional[str] = None,
        error: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Alias for update_model_generation."""
        self.update_model_generation(status=status, error=error, model_name=model_name, **kwargs)

    def update_assistant_response(self, status: str, **kwargs: Any) -> None:
        """Record assistant response delivery status."""
        with self._lock:
            if not self._state.enabled:
                return
            self._state.assistant_response_status = status
            self._state.timestamp = time.time()
        logger.info("[DIAGNOSTIC] [ASSISTANT] status=%s", status)
        self._broadcast()

    def update_tts(self, status: str, error: Optional[str] = None, **kwargs: Any) -> None:
        """Record text-to-speech synthesis status."""
        safe_err = None
        if status == "failed" or error:
            safe_err = self._sanitize_error(error, fallback=ERROR_TTS_FAILED)

        with self._lock:
            if not self._state.enabled:
                return
            self._state.tts_generation_status = status
            if safe_err:
                self._state.last_error = safe_err
            self._state.timestamp = time.time()

        if status == "failed":
            logger.error("[DIAGNOSTIC] [TTS] status=failed | Error: %s", safe_err)
        else:
            logger.info("[DIAGNOSTIC] [TTS] status=%s", status)

        self._broadcast()

    def update_playback(self, status: str, error: Optional[str] = None, **kwargs: Any) -> None:
        """Record audio playback status through speaker hardware."""
        safe_err = None
        if status == "failed" or error:
            safe_err = self._sanitize_error(error, fallback=ERROR_TTS_FAILED)

        with self._lock:
            if not self._state.enabled:
                return
            self._state.audio_playback_status = status
            if safe_err:
                self._state.last_error = safe_err
            self._state.timestamp = time.time()

        if status == "failed":
            logger.error("[DIAGNOSTIC] [PLAYBACK] status=failed | Error: %s", safe_err)
        else:
            logger.info("[DIAGNOSTIC] [PLAYBACK] status=%s", status)

        self._broadcast()

    def set_error(self, error: str, stage: Optional[str] = None) -> None:
        """Alias for setting a diagnostic error."""
        self.record_error(safe_error=error, stage=stage)

    def record_error(
        self,
        safe_error: str,
        raw_error: Optional[Any] = None,
        stage: Optional[str] = None,
    ) -> None:
        """Log structured error in dev logs and update user-facing safe error message."""
        sanitized = self._sanitize_error(safe_error)
        with self._lock:
            if not self._state.enabled:
                return
            self._state.last_error = sanitized
            self._state.timestamp = time.time()

        logger.error(
            "[DIAGNOSTIC] Stage: %s | User Error: '%s' | Internal Detail: %s",
            stage or "general",
            sanitized,
            str(raw_error) if raw_error is not None else "None",
            exc_info=bool(isinstance(raw_error, BaseException)),
        )
        self._broadcast()

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _sanitize_error(self, err: Any, fallback: str = "Voice error encountered.") -> str:
        """Map raw error or exception string to a user-safe message without stack traces or secrets."""
        if not err:
            return fallback
        raw_str = str(err)
        lowered = raw_str.lower()

        # Check for specific recognized failure cases
        if any(k in lowered for k in ("permission", "access denied", "access is denied", "winerror 5")) or (
            "microphone" in lowered and "denied" in lowered
        ):
            return ERROR_MIC_PERMISSION

        if any(k in lowered for k in ("no speech", "silence", "empty", "no audio")):
            return ERROR_NO_SPEECH

        if any(k in lowered for k in ("submit", "submission", "could not be sent")):
            return ERROR_SUBMISSION_FAILED

        if any(
            k in lowered
            for k in (
                "ollama",
                "connectionrefused",
                "connection refused",
                "httpconnectionpool",
                "max retries exceeded",
                "offline",
                "unreachable",
                "model service",
                "model unavailable",
                "daemon",
                "failed to connect",
            )
        ):
            return ERROR_MODEL_UNAVAILABLE

        if any(
            k in lowered
            for k in (
                "piper",
                "synthesiz",
                "tts",
                "speech synthesis",
                "audio player",
                "playback",
                "speaker",
                "audio output",
            )
        ):
            return ERROR_TTS_FAILED

        # Avoid stack traces, file paths, or private data in user messages
        if any(
            k in lowered
            for k in (
                "traceback",
                "file \"",
                "line ",
                "runtimeerror",
                "winerror",
                "exception",
                "error:",
                "c:\\",
                "c:/",
            )
        ) or "\\" in raw_str or "/" in raw_str:
            return fallback

        return raw_str[:120]

    def _broadcast(self, force: bool = False) -> None:
        """Broadcast state updates to connected clients over WebSocket."""
        with self._lock:
            if not force and not self._state.enabled:
                return

        mgr = self._ws_manager
        if not mgr:
            try:
                from app.api.websocket import ws_manager
                mgr = ws_manager
                self._ws_manager = mgr
            except Exception:
                return

        if mgr and getattr(mgr, "active_connections", None):
            try:
                mgr.broadcast_sync("diagnostic_update", self.to_dict())
            except Exception as e:
                logger.debug("Failed to broadcast diagnostic update: %s", e)


# Global singleton instance
diagnostic_tracker = DiagnosticTracker()
