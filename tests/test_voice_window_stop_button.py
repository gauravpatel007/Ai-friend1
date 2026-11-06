"""Tests for Bug #13: Voice Window 'Stop' Control Permanently Kills Microphone Capture and Sets Voice Mode to OFF.

Validates:
1. Clicking VoiceWindow.btn_stop does NOT emit signals.emergency_stop_requested.
2. Clicking VoiceWindow.btn_stop emits signals.ai_cancel_requested and halts active playback.
3. VoiceService mode (CONTINUOUS / WAKE_WORD) remains intact and is NOT set to VoiceMode.OFF.
4. signals.voice_state_changed is NOT emitted with 'off'.
5. VoiceConversationController transitions out of SPEAKING to LISTENING / WAKE_WORD_STANDBY, not DISABLED.
6. VoiceWindow visual state resets to 'idle' with 'Ready to talk'.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

import numpy as np
import pytest
from PySide6.QtCore import Qt

from app.core.signals import signals
from app.desktop.voice_window import VoiceWindow
from app.settings.config_manager import ConfigManager
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.voice_service import VoiceMode, VoiceService

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


def test_stop_button_does_not_emit_emergency_stop(qapp_instance) -> None:
    """Verify clicking btn_stop does NOT emit emergency_stop_requested."""
    config_file = SCRATCH_DIR / f"test_voice_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))

    vw = VoiceWindow(config_manager=cfg)

    emergency_fired = []
    cancel_fired = []
    signals.emergency_stop_requested.connect(lambda: emergency_fired.append(True))
    signals.ai_cancel_requested.connect(lambda: cancel_fired.append(True))

    # Click Stop button
    vw.btn_stop.click()

    assert len(emergency_fired) == 0, "btn_stop must never emit emergency_stop_requested"
    assert len(cancel_fired) == 1, "btn_stop must emit ai_cancel_requested"
    assert vw._current_state == "idle"

    vw.close()
    if config_file.exists():
        config_file.unlink()


def test_stop_button_halts_audio_player_and_speech(qapp_instance) -> None:
    """Verify btn_stop calls audio_player.stop() and voice_service.stop_speaking()."""
    config_file = SCRATCH_DIR / f"test_voice_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))

    mock_voice = MagicMock(spec=VoiceService)
    mock_voice.audio_player = MagicMock()
    mock_voice.mode = VoiceMode.CONTINUOUS

    vw = VoiceWindow(config_manager=cfg, voice_service=mock_voice)

    vw.btn_stop.click()

    mock_voice.audio_player.stop.assert_called_once()
    mock_voice.stop_speaking.assert_called_once()
    # Confirm mode was NOT changed on mock
    assert mock_voice.set_mode.call_count == 0

    vw.close()
    if config_file.exists():
        config_file.unlink()


def test_stop_button_preserves_continuous_voice_mode(qapp_instance) -> None:
    """Verify clicking btn_stop during continuous conversation preserves VoiceMode.CONTINUOUS and does not emit 'off'."""
    config_file = SCRATCH_DIR / f"test_voice_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))

    mock_voice = MagicMock(spec=VoiceService)
    mock_voice.audio_player = MagicMock()
    mock_voice._mode = VoiceMode.CONTINUOUS
    type(mock_voice).mode = property(lambda self: self._mode)

    vw = VoiceWindow(config_manager=cfg, voice_service=mock_voice)

    off_state_emitted = []
    signals.voice_state_changed.connect(lambda s: off_state_emitted.append(s) if s == "off" else None)

    vw.set_state("speaking")
    assert vw._current_state == "speaking"

    vw.btn_stop.click()

    assert len(off_state_emitted) == 0, "voice_state_changed('off') must not be emitted on Stop click"
    assert mock_voice._mode == VoiceMode.CONTINUOUS, "Voice mode must remain CONTINUOUS"
    assert vw._current_state == "idle"

    vw.close()
    if config_file.exists():
        config_file.unlink()


def test_stop_cancels_turn_and_resumes_listening_in_controller(qapp_instance) -> None:
    """Verify ai_cancel_requested resumes controller listening instead of disabling."""
    from app.voice.voice_conversation_controller import VoiceConversationController

    mock_mic = MagicMock()
    mock_mic.start_recording.return_value = True
    mock_vad = MagicMock()
    mock_whisper = MagicMock()
    mock_player = MagicMock()
    mock_tts = MagicMock()

    ctrl = VoiceConversationController(
        mic_manager=mock_mic,
        vad_engine=mock_vad,
        whisper_engine=mock_whisper,
        audio_player=mock_player,
        tts_engine=mock_tts,
    )
    ctrl.set_activation_mode(VoiceActivationMode.CONTINUOUS)
    ctrl._state = ConversationState.SPEAKING

    # Emit cancel requested (as dispatched by VoiceWindow._on_stop_clicked)
    signals.ai_cancel_requested.emit()

    # Controller should have transitioned from SPEAKING -> CANCELED -> LISTENING
    assert ctrl.state == ConversationState.LISTENING
    assert ctrl.is_enabled is True
    assert ctrl.state != ConversationState.DISABLED

    ctrl.cleanup()


def test_stop_cancels_turn_and_resumes_standby_in_wake_word_mode(qapp_instance) -> None:
    """Verify ai_cancel_requested in wake word mode returns to WAKE_WORD_STANDBY, ready for wake word."""
    from app.voice.voice_conversation_controller import VoiceConversationController

    mock_mic = MagicMock()
    mock_mic.start_recording.return_value = True
    mock_vad = MagicMock()
    mock_whisper = MagicMock()
    mock_player = MagicMock()
    mock_tts = MagicMock()

    ctrl = VoiceConversationController(
        mic_manager=mock_mic,
        vad_engine=mock_vad,
        whisper_engine=mock_whisper,
        audio_player=mock_player,
        tts_engine=mock_tts,
    )
    ctrl.set_activation_mode(VoiceActivationMode.WAKE_WORD)
    ctrl._state = ConversationState.SPEAKING

    signals.ai_cancel_requested.emit()

    assert ctrl.state == ConversationState.WAKE_WORD_STANDBY
    assert ctrl.is_enabled is True

    ctrl.cleanup()
