"""Unit tests for ErrorRecoveryCoordinator (Phase 11.6)."""

from unittest.mock import MagicMock

import pytest
from app.ai.ollama_client import (
    OllamaCancelledError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)
from app.core.error_recovery import ErrorRecoveryCoordinator


def test_handle_missing_model_error(qapp_instance):
    coordinator = ErrorRecoveryCoordinator()

    alerts_received = []
    coordinator.user_alert_requested.connect(
        lambda title, msg, urgency: alerts_received.append((title, msg, urgency))
    )

    err = OllamaModelNotFoundError("Model 'qwen3:1.7b' not found")
    coordinator.handle_ollama_error(err, model_name="qwen3:1.7b")

    assert len(alerts_received) == 1
    title, msg, urgency = alerts_received[0]
    assert "AI Model Not Found" in title
    assert "ollama pull qwen3:1.7b" in msg
    assert urgency == "warning"


def test_handle_cancelled_error_suppressed(qapp_instance):
    coordinator = ErrorRecoveryCoordinator()

    alerts_received = []
    coordinator.user_alert_requested.connect(
        lambda title, msg, urgency: alerts_received.append((title, msg, urgency))
    )

    err = OllamaCancelledError("Cancelled by user")
    coordinator.handle_ollama_error(err, model_name="qwen3:1.7b")

    # Deliberate cancellations must never trigger user-facing error banners
    assert len(alerts_received) == 0


def test_handle_ollama_connection_error_starts_probe(qapp_instance):
    coordinator = ErrorRecoveryCoordinator()

    alerts_received = []
    coordinator.user_alert_requested.connect(
        lambda title, msg, urgency: alerts_received.append((title, msg, urgency))
    )

    err = OllamaConnectionError("Connection refused to 127.0.0.1:11434")
    coordinator.handle_ollama_error(err, model_name="qwen3:1.7b")

    assert len(alerts_received) == 1
    title, msg, urgency = alerts_received[0]
    assert "AI Engine Disconnected" in title
    assert "Ollama service is not running" in msg
    assert urgency == "error"

    # Verify background probe timer was activated
    assert coordinator._ollama_probe_timer.isActive()
    coordinator._ollama_probe_timer.stop()


def test_handle_audio_device_error(qapp_instance):
    coordinator = ErrorRecoveryCoordinator()

    alerts_received = []
    coordinator.user_alert_requested.connect(
        lambda title, msg, urgency: alerts_received.append((title, msg, urgency))
    )

    coordinator.handle_audio_device_error("Microphone device index 1 disconnected")

    assert len(alerts_received) == 1
    title, msg, urgency = alerts_received[0]
    assert "Audio Device Issue" in title
    assert "Microphone or speaker connection" in msg


def test_handle_tts_error(qapp_instance):
    coordinator = ErrorRecoveryCoordinator()

    alerts_received = []
    coordinator.user_alert_requested.connect(
        lambda title, msg, urgency: alerts_received.append((title, msg, urgency))
    )

    coordinator.handle_tts_error("Piper synthesis buffer underrun", engine_name="piper")

    assert len(alerts_received) == 1
    title, msg, urgency = alerts_received[0]
    assert "Speech Playback Notice" in title


def test_revalidate_after_resume(qapp_instance):
    coordinator = ErrorRecoveryCoordinator()

    mock_ai = MagicMock()
    mock_ai.client.check_health.return_value = True

    mock_voice = MagicMock()
    mock_voice.mode = MagicMock(value="push_to_talk")
    mock_voice.mic_manager.is_recording.return_value = False

    recovers = []
    coordinator.subsystem_recovered.connect(lambda name: recovers.append(name))

    coordinator.revalidate_after_resume(mock_ai, mock_voice)

    assert "ai_engine" in recovers
    assert "audio_subsystem" in recovers
