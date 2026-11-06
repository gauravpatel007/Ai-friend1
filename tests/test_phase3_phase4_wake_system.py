"""Tests for Phase 3 & Phase 4: Voice-Controlled Wake System & Standby Wake Detection.

Verifies:
1. Desktop pet double-click emits `open_chat_requested` to open the main chat window.
2. VoiceCommandParser parses all Primary Wake Commands and Additional Variations (including dynamic companion name 'Bond').
3. WakeWordEngine.is_wake_phrase recognizes all primary and variation wake commands.
4. When Buddy is SLEEPING:
   - Ordinary commands and conversational speech are ignored.
   - Any configured wake command transitions BuddyStateManager from SLEEPING to ACTIVE.
   - Dispatcher returns and speaks acknowledgment: "I'm here! What do you need?".
5. Controller wake_up:
   - Restores visual state to IDLE.
   - Restores configured voice mode.
   - Displays speech bubble and speaks acknowledgment aloud.
   - Broadcasts 'buddy_state_changed' active event.
6. Phase 4 Resource management:
   - Unload models with keep_wake_detector=True keeps Whisper loaded for wake-word detection.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.core.buddy_state_manager import BuddyState, get_buddy_state_manager
from app.core.signals import signals
from app.character.states import CharacterState
from app.voice.command_dispatcher import VoiceCommandParser, VoiceCommandDispatcher
from app.voice.wake_word_engine import WakeWordEngine


# ─── 1. Desktop Pet Double-Click to Open Chat Window ────────────────────────

def test_pet_double_click_requests_open_chat(qtbot):
    """Verify that double-clicking the pet window requests opening the main chat window."""
    from app.desktop.pet_window import DesktopPetWindow

    config_mock = MagicMock()
    config_mock.get.side_effect = lambda key, default=None: "Buddy" if "name" in key else default
    window = DesktopPetWindow(config_manager=config_mock)
    qtbot.addWidget(window)

    opened = []
    signals.open_chat_requested.connect(lambda: opened.append(True))

    # Simulate double-click callback
    window._on_double_click()

    assert len(opened) == 1
    window.close()


# ─── 2. Phase 3: Primary & Additional Wake Phrases Parsing ───────────────────

@pytest.mark.parametrize(
    "phrase,expected_intent",
    [
        # Primary wake commands
        ("Hey Buddy", "wake"),
        ("Hey, Buddy", "wake"),
        ("Wake up", "wake"),
        ("Wake up, Buddy", "wake"),
        ("Buddy, wake up", "wake"),

        # Additional wake variations
        ("I'm talking to you, Buddy", "wake"),
        ("Buddy, are you there?", "wake"),
        ("Come back, Buddy", "show_pet"),  # Handled as show_pet / companion wake
        ("Start listening", "wake"),
        ("Resume listening", "wake"),
        ("Activate Buddy", "wake"),

        # Dynamic companion name variations ('Bond')
        ("Hey Bond", "wake"),
        ("Hey, Bond", "wake"),
        ("Wake up, Bond", "wake"),
        ("Bond, wake up", "wake"),
        ("I'm talking to you, Bond", "wake"),
        ("Bond, are you there?", "wake"),
        ("Come back, Bond", "show_pet"),
        ("Activate Bond", "wake"),

        # Other standard wake phrases
        ("rise and shine", "wake"),
        ("are you awake", "wake"),
        ("get up", "wake"),
        ("hello again", "wake"),

        # Multilingual
        ("જાગી જા", "wake"),
        ("ઊઠ", "wake"),
        ("ઉઠો", "wake"),
        ("સાંભળવાનું શરૂ કર", "wake"),
        ("जाग जाओ", "wake"),
        ("उठो", "wake"),
        ("सुनना शुरू करो", "wake"),
    ],
)
def test_wake_command_parsing(phrase, expected_intent):
    """Verify VoiceCommandParser recognizes all Phase 3 primary and additional wake commands."""
    res = VoiceCommandParser.parse(phrase)
    assert res is not None, f"Failed to parse wake phrase: {phrase}"
    intent, _ = res
    assert intent == expected_intent, f"Phrase '{phrase}' parsed as '{intent}', expected '{expected_intent}'"


# ─── 3. Standby Wake-Word Engine Recognition ────────────────────────────────

@pytest.mark.parametrize(
    "phrase",
    [
        "Hey Buddy",
        "Hey, Buddy",
        "Wake up",
        "Wake up, Buddy",
        "Buddy, wake up",
        "I'm talking to you, Buddy",
        "Buddy, are you there?",
        "Come back, Buddy",
        "Start listening",
        "Resume listening",
        "Activate Buddy",
        "Hey Bond",
        "Wake up, Bond",
        "Bond, wake up",
        "Bond, are you there?",
        "Activate Bond",
        "Rise and shine",
        "Are you awake",
        "જાગી જા",
        "સાંભળવાનું શરૂ કર",
        "जाग जाओ",
        "उठो",
        "सुनना शुरू करो",
    ],
)
def test_wake_word_engine_recognizes_phrases(phrase):
    """Verify WakeWordEngine.is_wake_phrase identifies all wake variants in standby."""
    wwe = WakeWordEngine()
    assert wwe.is_wake_phrase(phrase) is True, f"WakeWordEngine rejected: {phrase}"


# ─── 4. Sleeping State Transitions & Spoken Acknowledgment ──────────────────

def test_sleeping_state_wake_transitions_and_spoken_ack():
    """Verify sleeping Buddy transitions to ACTIVE and speaks acknowledgment on wake."""
    sm = get_buddy_state_manager()
    sm.enter_sleep(reason="test")
    assert sm.is_sleeping is True

    voice_mock = MagicMock()
    voice_mock.is_muted = False
    voice_mock.speak = MagicMock()

    dispatcher = VoiceCommandDispatcher(voice_service=voice_mock)

    wake_requested_fired = []
    signals.wake_requested.connect(lambda: wake_requested_fired.append(True))

    # Dispatch primary wake phrase
    handled = dispatcher.dispatch("Wake up, Buddy")
    assert handled is True
    assert sm.state == BuddyState.ACTIVE
    assert len(wake_requested_fired) >= 1

    # Verify spoken acknowledgment was requested
    voice_mock.speak.assert_called_with("I'm here! What do you need?")


def test_sleeping_state_ignores_non_wake_commands():
    """Verify non-wake commands are silently intercepted and ignored when Buddy is sleeping."""
    sm = get_buddy_state_manager()
    sm.enter_sleep(reason="test")
    assert sm.is_sleeping is True

    voice_mock = MagicMock()
    voice_mock.is_muted = False
    voice_mock.speak = MagicMock()

    dispatcher = VoiceCommandDispatcher(voice_service=voice_mock)

    # Ordinary commands should be intercepted and consumed without executing actions
    settings_requested = []
    signals.open_settings_requested.connect(lambda: settings_requested.append(True))

    handled = dispatcher.dispatch("open settings")
    assert handled is True  # Consumed so it does not trigger AI chat
    assert len(settings_requested) == 0  # Action NOT executed
    assert sm.is_sleeping is True  # Remains sleeping
    voice_mock.speak.assert_not_called()


def test_come_back_buddy_wakes_sleeping_companion():
    """Verify 'Come back, Buddy' brings companion back and transitions from SLEEPING to ACTIVE."""
    sm = get_buddy_state_manager()
    sm.enter_sleep(reason="test")
    assert sm.is_sleeping is True

    voice_mock = MagicMock()
    voice_mock.speak = MagicMock()

    dispatcher = VoiceCommandDispatcher(voice_service=voice_mock)

    handled = dispatcher.dispatch("Come back, Buddy")
    assert handled is True
    assert sm.state == BuddyState.ACTIVE


# ─── 5. Controller Wake Up Visual & Pipeline Restoration ────────────────────

def test_controller_wake_up_restoration():
    """Verify ApplicationController.wake_up restores pet animation, voice mode, and bubble."""
    from app.core.controller import ApplicationController

    controller = ApplicationController.__new__(ApplicationController)
    controller._is_sleeping = True
    controller.buddy_state_manager = get_buddy_state_manager()
    controller.buddy_state_manager.enter_sleep(reason="test")

    pet_mock = MagicMock()
    # Pet starts hidden, then becomes visible once show() is invoked
    is_vis = [False]
    def _mock_show():
        is_vis[0] = True
    pet_mock.show.side_effect = _mock_show
    pet_mock.isVisible.side_effect = lambda: is_vis[0]
    controller.pet_window = pet_mock

    voice_mock = MagicMock()
    voice_mock.is_muted = False
    voice_mock.speak = MagicMock()
    controller.voice_service = voice_mock

    config_mock = MagicMock()
    config_mock.get.return_value = "continuous"
    controller.config_manager = config_mock

    with patch("app.api.websocket.ws_manager.broadcast_sync") as ws_broadcast:
        controller.wake_up()

        # 1. State manager restored to active
        assert controller.buddy_state_manager.state == BuddyState.ACTIVE
        assert controller._is_sleeping is False

        # 2. Pet made visible and set to IDLE
        pet_mock.show.assert_called_once()
        pet_mock.anim_controller.request_state.assert_called_with(CharacterState.IDLE, force=True)

        # 3. Voice mode restored to continuous
        voice_mock.set_mode.assert_called_with("continuous")

        # 4. Spoken acknowledgment and speech bubble
        voice_mock.speak.assert_called_with("I'm here! What do you need?")
        pet_mock.speech_bubble.show_message.assert_called_once()

        # 5. WebSocket broadcast
        ws_broadcast.assert_called_with("buddy_state_changed", {"state": "active"})


# ─── 6. Phase 4: Standby Model Retention ─────────────────────────────────────

def test_voice_service_unload_models_preserves_wake_detector():
    """Verify unload_models(keep_wake_detector=True) unloads TTS but preserves Whisper."""
    from app.voice.voice_service import VoiceService

    vs = VoiceService.__new__(VoiceService)
    vs.piper_engine = MagicMock()
    vs.kokoro_engine = MagicMock()
    vs.sapi_engine = MagicMock()
    vs.whisper_engine = MagicMock()

    vs.unload_models(keep_wake_detector=True)

    vs.piper_engine.unload_model.assert_called_once()
    vs.kokoro_engine.unload_model.assert_called_once()
    vs.sapi_engine.unload_model.assert_called_once()
    # Whisper engine must NOT be unloaded when keep_wake_detector is True
    vs.whisper_engine.unload_model.assert_not_called()
