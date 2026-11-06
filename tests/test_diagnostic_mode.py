"""Tests for Phase 10: Diagnostic Mode.

Covers:
- Safe, useful status exposure for all 11 voice pipeline stages:
  1. Microphone status
  2. Recording status
  3. Audio duration and sample count
  4. Transcription status
  5. Recognized-text availability and preview
  6. User-message submission status
  7. Backend connection status
  8. Model-generation status
  9. Assistant-response status
  10. TTS generation status
  11. Audio playback status
- Safe error message matching:
  - "Microphone permission denied."
  - "No speech was detected. Please try again."
  - "Speech was recognized, but the message could not be sent."
  - "The AI model is unavailable. Check that the local model service is running."
  - "The AI replied, but text-to-speech failed."
- Sanitization: no internal stack traces, API keys, or private data exposed in UI status.
- Enabling/disabling diagnostic mode.
- FastAPI endpoints GET /api/diagnostic/status and POST /api/diagnostic/toggle.
"""

import pytest
import logging
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.core.diagnostic_mode import (
    DiagnosticTracker,
    DiagnosticState,
    diagnostic_tracker,
    ERROR_MIC_PERMISSION,
    ERROR_NO_SPEECH,
    ERROR_SUBMISSION_FAILED,
    ERROR_MODEL_UNAVAILABLE,
    ERROR_TTS_FAILED,
)
from app.api.server import app
from app.settings.config_manager import ConfigManager
from app.memory.conversation_repository import ConversationRepository


@pytest.fixture(autouse=True)
def cleanup_diagnostic_state():
    yield
    diagnostic_tracker.set_enabled(False)
    diagnostic_tracker.reset_turn()


class TestDiagnosticModeTracking:
    """Tests for the DiagnosticTracker unit functionality."""

    def test_safe_error_constants_match_specification(self):
        """All 5 required safe error strings must match prompt specification exactly."""
        assert ERROR_MIC_PERMISSION == "Microphone permission denied."
        assert ERROR_NO_SPEECH == "No speech was detected. Please try again."
        assert ERROR_SUBMISSION_FAILED == "Speech was recognized, but the message could not be sent."
        assert ERROR_MODEL_UNAVAILABLE == "The AI model is unavailable. Check that the local model service is running."
        assert ERROR_TTS_FAILED == "The AI replied, but text-to-speech failed."

    def test_initial_state_defaults(self):
        """Initial state should have valid default values for all 11 statuses."""
        tracker = DiagnosticTracker(enabled=True)
        status = tracker.get_status()

        assert status["enabled"] is True
        assert status["microphone_status"] == "idle"
        assert status["recording_status"] == "idle"
        assert status["audio_duration_sec"] == 0.0
        assert status["audio_sample_count"] == 0
        assert status["transcription_status"] == "idle"
        assert status["recognized_text_available"] is False
        assert status["recognized_text_preview"] == ""
        assert status["user_message_submission_status"] == "idle"
        assert status["backend_connection_status"] == "idle"
        assert status["model_generation_status"] == "idle"
        assert status["assistant_response_status"] == "idle"
        assert status["tts_generation_status"] == "idle"
        assert status["audio_playback_status"] == "idle"
        assert status["last_error"] is None

    def test_microphone_and_recording_updates(self):
        """Test tracking mic setup and audio recording samples/duration."""
        tracker = DiagnosticTracker(enabled=True)

        tracker.update_microphone("ready", sample_rate=16000, channels=1, device_name="Test Mic")
        status = tracker.get_status()
        assert status["microphone_status"] == "ready"

        tracker.update_recording("recording", sample_count=32000, duration_sec=2.0)
        status = tracker.get_status()
        assert status["recording_status"] == "recording"
        assert status["audio_sample_count"] == 32000
        assert status["audio_duration_sec"] == 2.0

        tracker.update_recording("stopped")
        assert tracker.get_status()["recording_status"] == "stopped"

    def test_transcription_and_preview_updates(self):
        """Test tracking transcription status and recognized text preview."""
        tracker = DiagnosticTracker(enabled=True)

        tracker.update_transcription("transcribing")
        status = tracker.get_status()
        assert status["transcription_status"] == "transcribing"
        assert status["recognized_text_available"] is False

        # Completed with text
        tracker.update_transcription("completed", recognized_text="What is the weather today?")
        status = tracker.get_status()
        assert status["transcription_status"] == "completed"
        assert status["recognized_text_available"] is True
        assert "What is the weather" in status["recognized_text_preview"]

        # Empty / no speech
        tracker.update_transcription("empty", error=ERROR_NO_SPEECH)
        status = tracker.get_status()
        assert status["transcription_status"] == "empty"
        assert status["recognized_text_available"] is False
        assert status["last_error"] == ERROR_NO_SPEECH

    def test_submission_and_backend_status(self):
        """Test tracking user message submission and WebSocket connection."""
        tracker = DiagnosticTracker(enabled=True)

        tracker.update_backend_connection("connected")
        assert tracker.get_status()["backend_connection_status"] == "connected"

        tracker.update_submission("submitting")
        assert tracker.get_status()["user_message_submission_status"] == "submitting"

        tracker.update_submission("submitted")
        assert tracker.get_status()["user_message_submission_status"] == "submitted"

        tracker.update_submission("failed", error=ERROR_SUBMISSION_FAILED)
        status = tracker.get_status()
        assert status["user_message_submission_status"] == "failed"
        assert status["last_error"] == ERROR_SUBMISSION_FAILED

    def test_ai_model_and_assistant_response_tracking(self):
        """Test tracking model thinking, generating, and completion."""
        tracker = DiagnosticTracker(enabled=True)

        tracker.update_model("thinking", model_name="llama3.2:latest")
        assert tracker.get_status()["model_generation_status"] == "thinking"

        tracker.update_model("generating")
        assert tracker.get_status()["model_generation_status"] == "generating"

        tracker.update_assistant_response("streaming")
        assert tracker.get_status()["assistant_response_status"] == "streaming"

        tracker.update_model("completed")
        tracker.update_assistant_response("completed")
        status = tracker.get_status()
        assert status["model_generation_status"] == "completed"
        assert status["assistant_response_status"] == "completed"

        # Model failure
        tracker.update_model("failed", error=ERROR_MODEL_UNAVAILABLE)
        status = tracker.get_status()
        assert status["model_generation_status"] == "failed"
        assert status["last_error"] == ERROR_MODEL_UNAVAILABLE

    def test_tts_and_playback_tracking(self):
        """Test tracking TTS generation and audio playback."""
        tracker = DiagnosticTracker(enabled=True)

        tracker.update_tts("synthesizing")
        assert tracker.get_status()["tts_generation_status"] == "synthesizing"

        tracker.update_tts("synthesized")
        tracker.update_playback("playing")
        status = tracker.get_status()
        assert status["tts_generation_status"] == "synthesized"
        assert status["audio_playback_status"] == "playing"

        tracker.update_playback("completed")
        assert tracker.get_status()["audio_playback_status"] == "completed"

        # TTS failure
        tracker.update_tts("failed", error=ERROR_TTS_FAILED)
        status = tracker.get_status()
        assert status["tts_generation_status"] == "failed"
        assert status["last_error"] == ERROR_TTS_FAILED

    def test_error_sanitization_suppresses_stack_traces_and_secrets(self):
        """Raw tracebacks or sensitive internal exceptions must be sanitized."""
        tracker = DiagnosticTracker(enabled=True)

        raw_traceback = """Traceback (most recent call last):
  File "app/ai/ollama_client.py", line 124, in stream_chat
    raise ConnectionRefusedError("HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded")
ConnectionRefusedError: Failed to connect to Ollama daemon
"""
        sanitized = tracker._sanitize_error(raw_traceback)
        # Must map to the safe user error, never expose python traceback
        assert "Traceback" not in sanitized
        assert "HTTPConnectionPool" not in sanitized
        assert sanitized == ERROR_MODEL_UNAVAILABLE

        # Permission error with system path
        raw_permission = "PermissionError: [WinError 5] Access is denied: 'C:\\Windows\\System32\\microphone.sys'"
        sanitized_mic = tracker._sanitize_error(raw_permission)
        assert "WinError" not in sanitized_mic
        assert "System32" not in sanitized_mic
        assert sanitized_mic == ERROR_MIC_PERMISSION

        # Text-to-speech error with internal python details
        raw_tts = "RuntimeError: PiperEngine failed to synthesize audio buffer (exit code 1)"
        sanitized_tts = tracker._sanitize_error(raw_tts)
        assert "RuntimeError" not in sanitized_tts
        assert "exit code" not in sanitized_tts
        assert sanitized_tts == ERROR_TTS_FAILED

    def test_diagnostic_toggle_and_disabled_state(self):
        """When disabled, tracker status reflects enabled=False and ignores state mutations."""
        tracker = DiagnosticTracker(enabled=False)
        assert tracker.is_enabled is False

        # Attempted updates while disabled
        tracker.update_microphone("recording")
        assert tracker.get_status()["microphone_status"] == "idle"

        # Enable
        tracker.set_enabled(True)
        assert tracker.is_enabled is True
        tracker.update_microphone("ready")
        assert tracker.get_status()["microphone_status"] == "ready"

    def test_reset_turn(self):
        """Turn reset clears transient speech and response statuses while retaining mic and backend status."""
        tracker = DiagnosticTracker(enabled=True)
        tracker.update_microphone("ready")
        tracker.update_backend_connection("connected")
        tracker.update_recording("recording", sample_count=16000, duration_sec=1.0)
        tracker.update_transcription("completed", recognized_text="Hello")
        tracker.update_model("completed")
        tracker.set_error(ERROR_NO_SPEECH)

        tracker.reset_turn()
        status = tracker.get_status()

        # Retained
        assert status["microphone_status"] == "ready"
        assert status["backend_connection_status"] == "connected"

        # Reset
        assert status["recording_status"] == "idle"
        assert status["audio_sample_count"] == 0
        assert status["audio_duration_sec"] == 0.0
        assert status["transcription_status"] == "idle"
        assert status["recognized_text_available"] is False
        assert status["recognized_text_preview"] == ""
        assert status["model_generation_status"] == "idle"
        assert status["last_error"] is None

    def test_structured_diagnostic_logging(self, caplog):
        """Diagnostic updates must emit structured [DIAGNOSTIC] log entries."""
        tracker = DiagnosticTracker(enabled=True)
        with caplog.at_level(logging.DEBUG):
            tracker.update_recording("recording", duration_sec=1.5, sample_count=24000)

        assert any("[DIAGNOSTIC] [RECORDING]" in record.message for record in caplog.records)


class TestDiagnosticAPIEndpoints:
    """Tests for FastAPI diagnostic endpoints."""

    @pytest.fixture
    def client(self):
        cfg = ConfigManager()
        repo = ConversationRepository()
        app.state.config_manager = cfg
        app.state.conv_repo = repo
        return TestClient(app)

    def test_get_diagnostic_status_endpoint(self, client):
        """GET /api/diagnostic/status returns current telemetry status."""
        res = client.get("/api/diagnostic/status")
        assert res.status_code == 200
        data = res.json()

        assert "enabled" in data
        assert "microphone_status" in data
        assert "recording_status" in data
        assert "audio_duration_sec" in data
        assert "audio_sample_count" in data
        assert "transcription_status" in data
        assert "recognized_text_available" in data
        assert "recognized_text_preview" in data
        assert "user_message_submission_status" in data
        assert "backend_connection_status" in data
        assert "model_generation_status" in data
        assert "assistant_response_status" in data
        assert "tts_generation_status" in data
        assert "audio_playback_status" in data
        assert "last_error" in data

    def test_post_diagnostic_toggle_endpoint(self, client):
        """POST /api/diagnostic/toggle enables or disables diagnostic mode."""
        # Enable
        res = client.post("/api/diagnostic/toggle", json={"enabled": True})
        assert res.status_code == 200
        assert res.json()["enabled"] is True

        # Verify through GET
        get_res = client.get("/api/diagnostic/status")
        assert get_res.json()["enabled"] is True

        # Disable
        res2 = client.post("/api/diagnostic/toggle", json={"enabled": False})
        assert res2.status_code == 200
        assert res2.json()["enabled"] is False

        # Reset back to False for clean test isolation across the test suite
        client.post("/api/diagnostic/toggle", json={"enabled": False})
