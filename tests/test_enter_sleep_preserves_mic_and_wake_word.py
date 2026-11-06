"""Tests for Bug #21: BuddyStateManager.enter_sleep() preserves mic capture and wake word engine.

Verifies:
1. BuddyStateManager.enter_sleep() does NOT emit signals.emergency_stop_requested.
2. signals.ai_cancel_requested is emitted when entering sleep.
3. Registered audio_player.stop() is called upon entering sleep.
4. VoiceCommandDispatcher 'go to sleep' transitions to SLEEPING without firing emergency_stop_requested.
5. In VoiceService / VoiceConversationController, entering sleep preserves microphone recording and wake word engine readiness.
"""

from unittest.mock import MagicMock
import pytest

from app.core.buddy_state_manager import BuddyState, BuddyStateManager
from app.core.signals import signals
from app.voice.command_dispatcher import VoiceCommandDispatcher
from app.voice.voice_service import VoiceMode, VoiceService


def test_enter_sleep_does_not_emit_emergency_stop():
    """Verify enter_sleep() never emits signals.emergency_stop_requested."""
    sm = BuddyStateManager()
    emergency_stops = []
    ai_cancels = []
    signals.emergency_stop_requested.connect(lambda: emergency_stops.append(True))
    signals.ai_cancel_requested.connect(lambda: ai_cancels.append(True))

    mock_player = MagicMock()
    sm.set_audio_player(mock_player)

    ok = sm.enter_sleep(reason="test")
    assert ok is True
    assert sm.is_sleeping is True

    # Critical assertions for Bug #21:
    assert len(emergency_stops) == 0, "enter_sleep() must NOT emit emergency_stop_requested!"
    assert len(ai_cancels) >= 1, "enter_sleep() must emit ai_cancel_requested!"
    assert mock_player.stop.called is True, "enter_sleep() must stop audio player!"


def test_voice_command_sleep_does_not_emit_emergency_stop():
    """Verify 'go to sleep' voice command does not emit emergency_stop_requested."""
    mock_vs = MagicMock()
    mock_vs.is_muted = False
    dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)
    dispatcher.buddy_state_manager.reset()

    emergency_stops = []
    signals.emergency_stop_requested.connect(lambda: emergency_stops.append(True))

    res = dispatcher.dispatch("go to sleep")
    assert res is True
    assert dispatcher.buddy_state_manager.is_sleeping is True

    # Verify no emergency stop was emitted
    assert len(emergency_stops) == 0, "Dispatching 'go to sleep' must NOT emit emergency_stop_requested!"


def test_enter_sleep_preserves_voice_service_and_wake_detector(qapp_instance):
    """Verify VoiceService retains microphone capture and wake word engine across sleep cycle."""
    mock_player = MagicMock()
    vs = VoiceService(audio_player=mock_player)
    vs.buddy_state_manager.reset()

    # Configure wake word mode
    vs.wake_word_engine.enable()
    vs.set_mode(VoiceMode.WAKE_WORD)

    assert vs.wake_word_engine.is_enabled is True
    assert vs.mode == VoiceMode.WAKE_WORD

    # Enter sleep
    vs.buddy_state_manager.enter_sleep(reason="unit_test")
    assert vs.buddy_state_manager.is_sleeping is True

    # Voice mode must NOT be OFF; wake word detector must remain enabled
    assert vs.mode != VoiceMode.OFF
    assert vs.wake_word_engine.is_enabled is True

    # Clean shutdown
    vs.stop()
