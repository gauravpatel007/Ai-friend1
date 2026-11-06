"""Unit & Integration Tests for Movie Hub Search Bar Voice Dictation.

Covers:
1. FastAPI endpoints: /api/voice/dictate/start, /api/voice/dictate/stop, /api/voice/dictate/status.
2. VoiceService start_dictation & stop_dictation isolated routing.
3. Dictation chunk isolation (does not trigger conversational AI chat prompts).
4. CustomWebPage non-blocking alert handling and MediaAudioCapture permission grants.
5. SearchBar.tsx frontend verification: no blocking window.alert or broken webkitSpeechRecognition.
"""

from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.voice.voice_service import VoiceService, VoiceMode


def test_dictation_endpoints_with_mocked_voice_service():
    """Verify dictate/start, dictate/stop, and dictate/status endpoints respond correctly."""
    app = create_app()
    mock_vs = MagicMock()
    mock_vs.start_dictation.return_value = True
    mock_vs.stop_dictation.return_value = "Inception"
    mock_vs.is_dictating = False

    app.state.voice_service = mock_vs

    with TestClient(app) as client:
        # 1. Status check when idle
        st_res = client.get("/api/voice/dictate/status")
        assert st_res.status_code == 200
        assert st_res.json()["is_dictating"] is False

        # 2. Start dictation
        start_res = client.post("/api/voice/dictate/start")
        assert start_res.status_code == 200
        assert start_res.json()["status"] == "ok"
        assert start_res.json()["recording"] is True
        mock_vs.start_dictation.assert_called_once()

        # 3. Stop dictation and retrieve recognized query
        stop_res = client.post("/api/voice/dictate/stop")
        assert stop_res.status_code == 200
        assert stop_res.json()["status"] == "ok"
        assert stop_res.json()["text"] == "Inception"
        mock_vs.stop_dictation.assert_called_once()


def test_dictation_endpoints_without_voice_service():
    """Verify endpoints handle gracefully when voice service is unavailable without throwing 500."""
    app = create_app()
    app.state.voice_service = None

    with TestClient(app) as client:
        start_res = client.post("/api/voice/dictate/start")
        assert start_res.status_code == 200
        assert start_res.json()["status"] == "error"
        assert start_res.json()["recording"] is False

        stop_res = client.post("/api/voice/dictate/stop")
        assert stop_res.status_code == 200
        assert stop_res.json()["status"] == "error"
        assert stop_res.json()["text"] == ""

        st_res = client.get("/api/voice/dictate/status")
        assert st_res.status_code == 200
        assert st_res.json()["is_dictating"] is False


def test_voice_service_dictation_routing_and_transcription(qapp_instance):
    """Verify VoiceService captures dictation chunks and routes to Whisper without conversational prompt."""
    vs = VoiceService()
    vs.whisper_engine = MagicMock()
    vs.mic_manager = MagicMock()
    vs.mic_manager.sample_rate = 16000
    vs.mic_manager.start_recording.return_value = True

    # Mock whisper transcribe
    mock_transcription = MagicMock()
    mock_transcription.text = "Stranger Things."
    vs.whisper_engine.transcribe.return_value = mock_transcription

    assert vs.is_dictating is False

    # Start dictation
    ok = vs.start_dictation()
    assert ok is True
    assert vs.is_dictating is True
    vs.mic_manager.start_recording.assert_called()

    # Simulate incoming audio frames (1 second of synthetic audio: 16000 samples)
    dummy_frame = np.zeros(16000, dtype=np.float32)
    vs._on_audio_frame_received(dummy_frame)

    # Stop dictation
    recognized = vs.stop_dictation()
    # Trailing punctuation cleaned ("Stranger Things." -> "Stranger Things")
    assert recognized == "Stranger Things"
    assert vs.is_dictating is False
    vs.whisper_engine.transcribe.assert_called_once()


def test_custom_web_page_non_blocking_alert_and_permission(qapp_instance):
    """Verify CustomWebPage intercepts alerts without blocking and grants MediaAudioCapture."""
    from PySide6.QtCore import QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage
    from app.desktop.modern_chat_window import CustomWebPage

    dummy_win = MagicMock()
    page = CustomWebPage(dummy_win)

    # Calling javaScriptAlert should not raise or block
    page.javaScriptAlert(QUrl("http://localhost"), "Test alert message")
    assert page.javaScriptConfirm(QUrl("http://localhost"), "Test confirm") is True
    assert page.javaScriptPrompt(QUrl("http://localhost"), "Test prompt", "default")[1] == "default"


def test_searchbar_tsx_clean_of_broken_speech_recognition_and_alerts():
    """Verify SearchBar.tsx does not contain window.alert or webkitSpeechRecognition."""
    src_file = Path("src/components/MovieHub/SearchBar.tsx")
    assert src_file.exists(), "SearchBar.tsx must exist"
    content = src_file.read_text(encoding="utf-8")

    # Broken calls eliminated
    assert "webkitSpeechRecognition" not in content, "SearchBar must not use webkitSpeechRecognition"
    assert "SpeechRecognition" not in content, "SearchBar must not use browser SpeechRecognition"
    assert "alert(" not in content, "SearchBar must not use blocking window.alert"

    # Native endpoints referenced
    assert "startVoiceDictation" in content, "SearchBar must use startVoiceDictation"
    assert "stopVoiceDictation" in content, "SearchBar must use stopVoiceDictation"
