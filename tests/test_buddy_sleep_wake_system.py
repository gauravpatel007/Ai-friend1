"""Tests for Phase 1 & Phase 2: Centralized Buddy State Manager & Voice-Controlled Sleep/Wake System.

Verifies:
1. Centralized BuddyStateManager (ACTIVE, SLEEPING, MUTED states and transitions).
2. Distinction between SLEEPING (ignores ordinary speech, wake-word only) and MUTED (TTS suppressed, speech input allowed).
3. Primary sleep commands ("sleep", "go to sleep", "shut up", "be quiet", "stop listening", "quiet mode", "silence", "enough", "stop talking").
4. Natural variations with companion prefix ("Buddy, sleep", "Buddy, go to sleep", "Buddy, be quiet", "Buddy, stop talking", "Buddy, stop listening").
5. While SLEEPING: ordinary commands & chat are ignored; only explicit wake commands ("wake up", "rise and shine", "are you awake", "buddy wake up") reactivate Buddy.
6. Execution does NOT close application or trigger process exits.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.core.buddy_state_manager import BuddyState, BuddyStateManager, get_buddy_state_manager
from app.core.signals import signals
from app.voice.command_dispatcher import VoiceCommandDispatcher, VoiceCommandParser


class TestPhase1BuddyStateManager:
    """Phase 1: Centralized Buddy State Manager Unit Tests."""

    def test_initial_state_is_active(self):
        sm = BuddyStateManager()
        assert sm.state == BuddyState.ACTIVE
        assert sm.is_active is True
        assert sm.is_sleeping is False
        assert sm.is_muted is False
        assert sm.can_process_speech is True
        assert sm.can_speak is True
        assert sm.is_wake_word_only is False

    def test_transition_to_sleep(self):
        sm = BuddyStateManager()
        entered_sleep_fired = []
        state_changed_fired = []
        sm.entered_sleep.connect(lambda r: entered_sleep_fired.append(r))
        sm.state_changed.connect(lambda old, new: state_changed_fired.append((old, new)))

        assert sm.enter_sleep(reason="test_sleep") is True
        assert sm.state == BuddyState.SLEEPING
        assert sm.is_sleeping is True
        assert sm.is_active is False
        assert sm.can_process_speech is False
        assert sm.can_speak is False
        assert sm.is_wake_word_only is True

        assert len(entered_sleep_fired) == 1
        assert entered_sleep_fired[0] == "test_sleep"
        assert len(state_changed_fired) == 1
        assert state_changed_fired[0] == ("active", "sleeping")

        # Duplicate enter_sleep is idempotent and returns False
        assert sm.enter_sleep() is False

    def test_transition_from_sleep_to_wake(self):
        sm = BuddyStateManager()
        sm.enter_sleep(reason="user_command")
        assert sm.is_sleeping is True

        woken_fired = []
        state_changed_fired = []
        sm.woken_up.connect(lambda r: woken_fired.append(r))
        sm.state_changed.connect(lambda old, new: state_changed_fired.append((old, new)))

        assert sm.wake_up(reason="test_wake") is True
        assert sm.state == BuddyState.ACTIVE
        assert sm.is_active is True
        assert sm.is_sleeping is False
        assert sm.can_process_speech is True
        assert sm.can_speak is True
        assert sm.is_wake_word_only is False

        assert len(woken_fired) == 1
        assert woken_fired[0] == "test_wake"
        assert state_changed_fired[0] == ("sleeping", "active")

        # Duplicate wake_up is idempotent and returns False
        assert sm.wake_up() is False

    def test_muted_distinction_from_sleeping(self):
        """Verify clear distinction between MUTED and SLEEPING."""
        sm = BuddyStateManager()
        muted_fired = []
        unmuted_fired = []
        sm.muted.connect(lambda r: muted_fired.append(r))
        sm.unmuted.connect(lambda r: unmuted_fired.append(r))

        assert sm.set_muted(True, reason="mute_button") is True
        assert sm.state == BuddyState.MUTED
        assert sm.is_muted is True
        assert sm.is_sleeping is False
        assert sm.can_process_speech is True   # In MUTED, speech input is still processed
        assert sm.can_speak is False           # But TTS output is suppressed
        assert sm.is_wake_word_only is False   # Normal speech listening remains active, not restricted to wake-word only
        assert len(muted_fired) == 1

        assert sm.set_muted(False, reason="unmute_button") is True
        assert sm.state == BuddyState.ACTIVE
        assert sm.can_speak is True
        assert len(unmuted_fired) == 1


class TestPhase2VoiceSleepCommands:
    """Phase 2: Sleep and Wake Voice Commands Integration Tests."""

    @pytest.mark.parametrize(
        "phrase,expected_intent",
        [
            # Primary commands
            ("sleep", "sleep"),
            ("go to sleep", "sleep"),
            ("shut up", "stop"),
            ("be quiet", "mute"),
            ("stop listening", "sleep"),
            ("quiet mode", "sleep"),
            ("silence", "mute"),
            ("enough", "stop"),
            ("stop talking", "stop"),
            # Natural variations with Buddy prefix
            ("buddy, sleep", "sleep"),
            ("buddy, go to sleep", "sleep"),
            ("buddy, be quiet", "mute"),
            ("buddy, stop talking", "stop"),
            ("buddy, stop listening", "sleep"),
            ("buddy, shut up", "stop"),
            ("buddy, wake up", "wake"),
            ("wake up", "wake"),
            ("rise and shine", "wake"),
            ("are you awake", "wake"),
        ],
    )
    def test_sleep_and_wake_command_parsing(self, phrase, expected_intent):
        """Verify all primary commands and Buddy prefix variations parse to correct intents."""
        parsed = VoiceCommandParser.parse(phrase)
        assert parsed is not None, f"Failed to parse '{phrase}'"
        intent, _ = parsed
        assert intent == expected_intent, f"Expected intent '{expected_intent}' for phrase '{phrase}', got '{intent}'"

    def test_sleep_command_execution(self):
        """Verify 'sleep' command halts speech and transitions Buddy to SLEEPING."""
        mock_vs = MagicMock()
        mock_vs.is_muted = False
        dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)
        dispatcher.buddy_state_manager.reset()

        assert dispatcher.buddy_state_manager.is_active is True

        assert dispatcher.dispatch("go to sleep") is True
        assert dispatcher.buddy_state_manager.is_sleeping is True
        assert mock_vs.stop_speaking.called is True

    def test_shut_up_command_execution(self):
        """Verify 'shut up' command immediately stops speech, cancels AI, transitions to SLEEPING silently."""
        mock_vs = MagicMock()
        mock_vs.is_muted = False
        dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)
        dispatcher.buddy_state_manager.reset()

        stop_signals_fired = []
        signals.emergency_stop_requested.connect(lambda: stop_signals_fired.append(True))

        assert dispatcher.dispatch("shut up") is True
        assert dispatcher.buddy_state_manager.is_sleeping is True
        assert mock_vs.stop_speaking.called is True
        assert len(stop_signals_fired) >= 1

    def test_sleeping_buddy_ignores_ordinary_speech_and_commands(self):
        """Verify that while SLEEPING, non-wake commands and ordinary speech are ignored."""
        mock_vs = MagicMock()
        dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)
        dispatcher.buddy_state_manager.enter_sleep(reason="test")

        assert dispatcher.buddy_state_manager.is_sleeping is True

        # 1. Non-wake voice command (e.g. open settings) is intercepted and ignored
        assert dispatcher.dispatch("open settings") is True
        assert dispatcher.buddy_state_manager.is_sleeping is True

        # 2. Conversational non-command speech is ignored while sleeping
        assert dispatcher.dispatch("how is the weather today?") is True
        assert dispatcher.buddy_state_manager.is_sleeping is True

    def test_sleeping_buddy_wakes_on_explicit_wake_command(self):
        """Verify that an explicit wake command ("wake up" or "buddy wake up") reactivates Buddy."""
        mock_vs = MagicMock()
        mock_vs.is_muted = False
        dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)
        dispatcher.buddy_state_manager.enter_sleep(reason="test")
        assert dispatcher.buddy_state_manager.is_sleeping is True

        # Wake command should successfully wake Buddy up to ACTIVE
        assert dispatcher.dispatch("buddy, wake up") is True
        assert dispatcher.buddy_state_manager.is_active is True
        assert dispatcher.buddy_state_manager.is_sleeping is False

