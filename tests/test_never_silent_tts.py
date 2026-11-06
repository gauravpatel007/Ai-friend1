"""Tests for Bug 21: Never-Silent TTS Architecture, SAPI5 Fallback, and Chat Voice Playback."""

from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtCore import QCoreApplication
from app.core.controller import ApplicationController
from app.core.signals import signals
from app.settings.config_manager import ConfigManager
from app.voice.piper_engine import PiperTTSEngine
from app.voice.sapi5_engine import Sapi5TTSEngine
from app.voice.voice_service import VoiceMode, VoiceService
from main_api import setup_signal_bridges, teardown_signal_bridges


def test_piper_engine_delegates_to_sapi_fallback(qapp_instance):
    """Verify that when Piper weights are not downloaded, synthesis delegates to fallback engine."""
    mock_sapi = MagicMock(spec=Sapi5TTSEngine)
    mock_sapi.is_available.return_value = True
    fake_audio = MagicMock()
    fake_audio.duration_seconds = 2.0
    fake_audio.text = "Hello world"
    mock_sapi.synthesize.return_value = fake_audio

    piper = PiperTTSEngine(fallback_engine=mock_sapi)
    # Ensure piper is not loaded
    piper._is_loaded = False
    piper._voice = None

    # Patch load_model to simulate offline / missing model files
    with patch.object(piper, "load_model", return_value=False):
        res = piper.synthesize("Hello world")
        assert res is fake_audio
        mock_sapi.synthesize.assert_called_once_with("Hello world")


def test_voice_service_sapi_availability_on_windows(qapp_instance):
    """Verify VoiceService defaults or cascades to an operational TTS engine on Windows."""
    vs = VoiceService()
    assert vs.is_tts_available() is True
    assert vs.sapi_engine.is_available() is True

    # When piper is active with sapi fallback, speak executes without errors
    assert vs.piper_engine.fallback_engine is vs.sapi_engine
    vs.stop()


def test_chat_response_speaks_aloud_in_controller(qapp_instance):
    """Verify that completed voice responses trigger spoken playback, while text-chat responses remain silent."""
    cfg = ConfigManager()
    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)
    mock_voice = MagicMock(spec=VoiceService)
    mock_voice.tts_enabled = True
    ctrl.voice_service = mock_voice

    mock_ai = MagicMock()
    mock_ai.is_current_generation_voice = True
    ctrl.ai_service = mock_ai

    # When continuous conversation controller is not handling this turn
    mock_conv_ctrl = MagicMock()
    mock_conv_ctrl.is_enabled = False
    mock_voice.conversation_controller = mock_conv_ctrl

    ctrl._on_ai_response_tts("The answer is 105,698.")
    mock_voice.speak.assert_called_once_with("The answer is 105,698.")

    # When turn is from text chat (is_voice=False), TTS must NOT be called
    mock_ai.is_current_generation_voice = False
    ctrl._on_ai_response_tts("This is a typed message.")
    # Total speak calls remains 1 (silent for text chat)
    assert mock_voice.speak.call_count == 1


def test_api_signal_bridges_teardown_and_deduplication(qapp_instance):
    """Verify that teardown_signal_bridges cleanly disconnects listeners preventing slot accumulation."""
    mock_repo = MagicMock()
    teardown_signal_bridges()

    # Call setup twice
    setup_signal_bridges(qapp_instance, mock_repo)
    setup_signal_bridges(qapp_instance, mock_repo)

    # Clean teardown
    teardown_signal_bridges()
    # Emitting signals after teardown should not trigger any listeners or errors
    signals.ai_response_chunk.emit("test chunk")
    signals.ai_response_complete.emit("test complete")
