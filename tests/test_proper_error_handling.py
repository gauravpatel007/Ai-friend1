"""Comprehensive Test Suite for Proper Error Handling (Task 7).

Validates the 11 error conditions required by the user:
1. Microphone permission denied
2. Microphone unavailable
3. Empty speech transcription
4. STT timeout
5. LLM unavailable
6. Model-loading failures
7. Backend timeout
8. TTS generation failure
9. Audio playback failure
10. Interrupted requests
11. Duplicate requests

Verifies:
- Understandable, human-readable error messages.
- Appropriate recovery actions and labels.
- State machine stability (no permanently frozen or corrupted states).
"""

from unittest.mock import MagicMock, patch
import pytest

from app.core.error_recovery import ErrorDescriptor, ErrorRecoveryCoordinator
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.whisper_engine import TranscriptionResult
from app.ai.ollama_client import (
    OllamaCancelledError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)


@pytest.fixture
def recovery_coordinator(qapp_instance):
    """Fixture providing an ErrorRecoveryCoordinator instance."""
    return ErrorRecoveryCoordinator()


# ─── 1. Microphone Permission Denied ──────────────────────────────────────────

def test_microphone_permission_denied(recovery_coordinator):
    """Verify understandable error and recovery action for mic permission denied."""
    alerts = []
    descriptors = []
    recovery_coordinator.user_alert_requested.connect(lambda t, m, u: alerts.append((t, m, u)))
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    desc = recovery_coordinator.handle_microphone_permission_denied()

    assert desc.error_type == "mic_permission_denied"
    assert "Microphone Access Denied" in desc.title
    assert "privacy settings" in desc.message.lower()
    assert desc.recovery_action == "open_privacy_settings"
    assert "Settings" in desc.recovery_label
    assert desc.urgency == "error"
    assert len(descriptors) == 1
    assert descriptors[0].error_type == "mic_permission_denied"


# ─── 2. Microphone Unavailable ───────────────────────────────────────────────

def test_microphone_unavailable(recovery_coordinator):
    """Verify understandable error and recovery action when microphone is disconnected."""
    descriptors = []
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    desc = recovery_coordinator.handle_microphone_unavailable("No input devices found")

    assert desc.error_type == "mic_unavailable"
    assert "Microphone Unavailable" in desc.title
    assert "no active microphone detected" in desc.message.lower()
    assert desc.recovery_action == "retry_device"
    assert "Retry" in desc.recovery_label
    assert desc.urgency == "warning"


# ─── 3. Empty Speech Transcription ───────────────────────────────────────────

def test_empty_speech_transcription(recovery_coordinator):
    """Verify graceful handling of empty speech transcription (no freezing)."""
    descriptors = []
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    mock_ctrl = MagicMock()
    desc = recovery_coordinator.handle_empty_transcription(voice_controller=mock_ctrl)

    assert desc.error_type == "empty_transcription"
    assert "No Speech Heard" in desc.title
    assert "speak a little louder" in desc.message.lower()
    assert desc.recovery_action == "listen_again"
    assert "Try Speaking Again" in desc.recovery_label
    assert desc.urgency == "info"
    mock_ctrl.vad_engine.reset_states.assert_called_once()


# ─── 4. STT Timeout ──────────────────────────────────────────────────────────

def test_stt_timeout(recovery_coordinator):
    """Verify STT timeout generates clear error and buffer reset action."""
    descriptors = []
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    mock_ctrl = MagicMock()
    desc = recovery_coordinator.handle_stt_timeout(voice_controller=mock_ctrl)

    assert desc.error_type == "stt_timeout"
    assert "Speech Transcription Timed Out" in desc.title
    assert "audio buffer has been reset" in desc.message.lower()
    assert desc.recovery_action == "retry"
    assert desc.urgency == "warning"
    mock_ctrl.vad_engine.reset_states.assert_called_once()


# ─── 5. LLM Unavailable ──────────────────────────────────────────────────────

def test_llm_unavailable(recovery_coordinator):
    """Verify clear guidance and auto-probe when Ollama service is unavailable."""
    alerts = []
    descriptors = []
    recovery_coordinator.user_alert_requested.connect(lambda t, m, u: alerts.append((t, m, u)))
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    mock_client = MagicMock()
    desc = recovery_coordinator.handle_llm_unavailable("llama3.2:3b", client=mock_client)

    assert desc.error_type == "llm_unavailable"
    assert "Ollama Offline" in desc.title
    assert "127.0.0.1:11434" in desc.message
    assert desc.recovery_action == "start_ollama"
    assert desc.recovery_label == "Start Ollama"
    assert desc.urgency == "error"
    # Probing timer should be activated
    assert recovery_coordinator._probing_ollama is True
    recovery_coordinator._ollama_probe_timer.stop()


# ─── 6. Model-Loading Failures ───────────────────────────────────────────────

def test_model_loading_failures(recovery_coordinator):
    """Verify understandable error with pull instructions on missing/failed model."""
    descriptors = []
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    # Case A: Model not found
    desc_missing = recovery_coordinator.handle_model_loading_failure("deepseek-r1:7b", "Model not found")
    assert desc_missing.error_type == "model_not_found"
    assert "AI Model Not Found" in desc_missing.title
    assert "ollama pull deepseek-r1:7b" in desc_missing.message
    assert desc_missing.recovery_action == "select_model"

    # Case B: Memory allocation / loading failure
    desc_oom = recovery_coordinator.handle_model_loading_failure("llama3.3:70b", "Out of memory allocating CUDA tensor")
    assert desc_oom.error_type == "model_loading_failure"
    assert "AI Model Loading Failed" in desc_oom.title
    assert "system memory is low" in desc_oom.message.lower()
    assert desc_oom.recovery_action == "select_model"


# ─── 7. Backend Timeout ──────────────────────────────────────────────────────

def test_backend_timeout(recovery_coordinator):
    """Verify backend timeout frees resources and offers retry."""
    descriptors = []
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    desc = recovery_coordinator.handle_backend_timeout(request_id="req_timeout_123")

    assert desc.error_type == "backend_timeout"
    assert "Request Timed Out" in desc.title
    assert "waiting for a response" in desc.message.lower()
    assert desc.recovery_action == "retry_request"
    assert desc.recovery_label == "Retry"
    assert desc.urgency == "warning"


# ─── 8. TTS Generation Failure ───────────────────────────────────────────────

def test_tts_generation_failure(recovery_coordinator):
    """Verify neural TTS failure informs user of fallback without crashing dialogue."""
    descriptors = []
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    desc = recovery_coordinator.handle_tts_failure("Kokoro tensor shape mismatch", engine_name="kokoro")

    assert desc.error_type == "tts_failure"
    assert "Speech Playback Notice" in desc.title
    assert "kokoro" in desc.message.lower()
    assert desc.recovery_action == "fallback_tts"
    assert desc.recovery_label == "Use Default Voice"
    assert desc.urgency == "info"


# ─── 9. Audio Playback Failure ───────────────────────────────────────────────

def test_audio_playback_failure(recovery_coordinator):
    """Verify speaker disconnection or OutputStream failure stops audio and alerts."""
    descriptors = []
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    mock_player = MagicMock()
    desc = recovery_coordinator.handle_audio_playback_failure("PortAudio stream error -9988", audio_player=mock_player)

    assert desc.error_type == "playback_failure"
    assert "Audio Playback Failed" in desc.title
    assert "audio output device unavailable" in desc.message.lower()
    assert desc.recovery_action == "retry_playback"
    assert desc.urgency == "warning"
    mock_player.stop.assert_called_once()


# ─── 10. Interrupted Requests ────────────────────────────────────────────────

def test_interrupted_requests(recovery_coordinator):
    """Verify user barge-in or deliberate cancellation does not trigger false error alerts."""
    alerts = []
    descriptors = []
    recovery_coordinator.user_alert_requested.connect(lambda t, m, u: alerts.append((t, m, u)))
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    desc = recovery_coordinator.handle_interrupted_request()

    assert desc.error_type == "interrupted_request"
    assert "Request Stopped" in desc.title
    assert "stopped by user" in desc.message.lower()
    assert desc.urgency == "info"
    # Crucial UX invariant: deliberate cancellations must NOT raise intrusive warning alerts
    assert len(alerts) == 0


# ─── 11. Duplicate Requests ──────────────────────────────────────────────────

def test_duplicate_requests(recovery_coordinator):
    """Verify duplicate message submissions are politely acknowledged and discarded."""
    descriptors = []
    recovery_coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    desc = recovery_coordinator.handle_duplicate_request(prompt="What is quantum physics?")

    assert desc.error_type == "duplicate_request"
    assert "Duplicate Request Ignored" in desc.title
    assert "already processing your message" in desc.message.lower()
    assert desc.recovery_action == "none"
    assert desc.urgency == "info"


# ─── Dynamic Error Classifier Integration ────────────────────────────────────

def test_classify_and_handle_all_conditions(recovery_coordinator):
    """Verify classify_and_handle correctly routes all 11 failure variants from raw strings."""
    # 1. Permission
    d1 = recovery_coordinator.classify_and_handle("Permission denied: access denied to sound device")
    assert d1.error_type == "mic_permission_denied"

    # 2. Mic unavailable
    d2 = recovery_coordinator.classify_and_handle("Microphone unavailable: Index 3 not found")
    assert d2.error_type == "mic_unavailable"

    # 3. Empty transcription
    d3 = recovery_coordinator.classify_and_handle("No speech detected: silence in utterance")
    assert d3.error_type == "empty_transcription"

    # 4. STT timeout
    d4 = recovery_coordinator.classify_and_handle("STT transcription timed out after 12s")
    assert d4.error_type == "stt_timeout"

    # 5. LLM offline
    d5 = recovery_coordinator.classify_and_handle("Ollama is offline or unreachable")
    assert d5.error_type == "llm_unavailable"

    # 6. Model loading failure
    d6 = recovery_coordinator.classify_and_handle("Model 'llama3.2:3b' not found in library")
    assert d6.error_type == "model_not_found"

    # 7. Backend timeout
    d7 = recovery_coordinator.classify_and_handle("Request timed out waiting for backend")
    assert d7.error_type == "backend_timeout"

    # 8. TTS failure
    d8 = recovery_coordinator.classify_and_handle("Neural TTS Kokoro synthesis failed")
    assert d8.error_type == "tts_failure"

    # 9. Playback failure
    d9 = recovery_coordinator.classify_and_handle("Playback failed: output stream could not open")
    assert d9.error_type == "playback_failure"

    # 10. Interrupted request
    d10 = recovery_coordinator.classify_and_handle("Cancelled by user via barge-in interruption")
    assert d10.error_type == "interrupted_request"

    # 11. Duplicate request
    d11 = recovery_coordinator.classify_and_handle("Duplicate request rejected: already in-flight")
    assert d11.error_type == "duplicate_request"


# ─── Controller Signal & WebSocket Broadcasting Integration ─────────────────

def test_controller_voice_error_broadcasting(qapp_instance):
    """Verify ApplicationController._on_voice_error broadcasts structured voice_error event."""
    from app.core.controller import ApplicationController
    from app.settings.config_manager import ConfigManager
    from unittest.mock import MagicMock

    cfg = ConfigManager()
    cfg.set("general.show_tray_notifications", True)
    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)

    broadcasted_events = []
    with patch("app.api.websocket.ws_manager.broadcast_sync", side_effect=lambda evt, payload: broadcasted_events.append((evt, payload))):
        ctrl._on_voice_error("Permission denied: Microphone access denied by system privacy settings")

    assert len(broadcasted_events) == 1
    evt, data = broadcasted_events[0]
    assert evt == "voice_error"
    assert data["error_type"] == "mic_permission_denied"
    assert "privacy settings" in data["message"].lower()
    assert data["recovery_action"] == "open_privacy_settings"
    assert "Settings" in data["recovery_label"]


def test_controller_ai_error_broadcasting(qapp_instance):
    """Verify ApplicationController._on_ai_error broadcasts structured ai_error event."""
    from app.core.controller import ApplicationController
    from app.settings.config_manager import ConfigManager
    from unittest.mock import MagicMock

    cfg = ConfigManager()
    cfg.set("general.show_tray_notifications", True)
    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)
    ctrl.conv_repo = MagicMock()

    broadcasted_events = []
    with patch("app.api.websocket.ws_manager.broadcast_sync", side_effect=lambda evt, payload: broadcasted_events.append((evt, payload))):
        ctrl._on_ai_error("Ollama service is offline or unreachable on 127.0.0.1:11434")

    assert len(broadcasted_events) == 1
    evt, data = broadcasted_events[0]
    assert evt == "ai_error"
    assert data["error_type"] == "llm_unavailable"
    assert "Ollama Offline" in data["title"]
    assert data["recovery_action"] == "start_ollama"
    assert data["recovery_label"] == "Start Ollama"


def test_controller_user_alert_spawns_toast_and_tray(qapp_instance):
    """Verify ApplicationController._on_user_alert invokes desktop toast and tray notifications."""
    from app.core.controller import ApplicationController
    from app.settings.config_manager import ConfigManager
    from unittest.mock import MagicMock, patch

    cfg = ConfigManager()
    cfg.set("general.show_tray_notifications", True)
    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)
    ctrl.tray_manager = MagicMock()

    with patch("app.desktop.notification_toast.show_buddy_toast") as mock_toast:
        ctrl._on_user_alert("Warning Title", "Test warning message", "warning")
        mock_toast.assert_called_once_with("Warning Title", "Test warning message")
        ctrl.tray_manager.show_message.assert_called_once_with("Warning Title", "Test warning message")


def test_streaming_audio_queue_error_forwarding(qapp_instance):
    """Verify StreamingAudioQueue emits error_occurred when chunk synthesis fails."""
    from app.voice.streaming_audio_queue import StreamingAudioQueue, QueuedSentence, _TTSChunkSynthesizeWorker
    from unittest.mock import MagicMock
    import numpy as np

    mock_player = MagicMock()
    mock_tts = MagicMock()
    mock_tts.synthesize.side_effect = RuntimeError("Kokoro engine model failed to synthesize")

    queue = StreamingAudioQueue(audio_player=mock_player, tts_engine=mock_tts)
    errors_emitted = []
    queue.error_occurred.connect(lambda err: errors_emitted.append(err))

    item = QueuedSentence(turn_id=1, chunk_index=0, text="Hello world")
    worker = _TTSChunkSynthesizeWorker(item=item, tts_engine=mock_tts)
    worker.signals.error.connect(queue.error_occurred.emit)
    worker.run()

    assert len(errors_emitted) == 1
    assert "Neural TTS synthesis error" in errors_emitted[0]
    assert "Kokoro" in errors_emitted[0]


def test_recovery_actions_api(qapp_instance):
    """Verify FastAPI /api/recovery/action endpoint handles select_model, fallback_tts, retry_playback, and retry_request."""
    import asyncio
    from app.api.server import app as fastapi_app, RecoveryActionRequest
    from app.core.signals import signals
    from unittest.mock import MagicMock

    # Find /api/recovery/action endpoint
    recovery_endpoint = None
    for r in fastapi_app.routes:
        if getattr(r, "path", None) == "/api/recovery/action":
            recovery_endpoint = r.endpoint
            break
    assert recovery_endpoint is not None

    async def _run_checks():
        # 1. select_model
        signal_received = []
        signals.open_settings_requested.connect(lambda: signal_received.append(True))
        res1 = await recovery_endpoint(RecoveryActionRequest(action="select_model"))
        assert res1.get("status") == "ok"
        assert res1.get("target") == "model"
        assert len(signal_received) >= 1

        # 2. fallback_tts
        mock_ctrl = MagicMock()
        fastapi_app.state.controller = mock_ctrl
        res2 = await recovery_endpoint(RecoveryActionRequest(action="fallback_tts"))
        assert res2.get("status") == "ok"
        assert res2.get("engine") == "sapi5"
        mock_ctrl.config_manager.set.assert_called_with("voice.engine", "sapi5")
        mock_ctrl.config_manager.save.assert_called_once()

        # 3. retry_playback
        res3 = await recovery_endpoint(RecoveryActionRequest(action="retry_playback"))
        assert res3.get("status") == "ok"
        mock_ctrl.voice_service.audio_player.stop.assert_called_once()

        # 4. retry_request
        res4 = await recovery_endpoint(RecoveryActionRequest(action="retry_request", payload={"prompt": "Kem cho?"}))
        assert res4.get("status") == "ok"
        mock_ctrl.ai_service.generate_response.assert_called_with("Kem cho?")

    asyncio.run(_run_checks())

