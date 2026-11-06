"""Tests for Phase 5 & Phase 6: False Activation Prevention & Safe Speech/Task Management.

Verifies:
1. Punctuation, case, and whitespace normalization for commands.
2. Prevention of false activations on unrelated sentences containing keywords
   (e.g. "I need to shut up this program's background noise" does NOT trigger sleep).
3. Compound wake command detection ("Hey Buddy, explain Python."):
   - Wakes Buddy if sleeping.
   - Forwards prompt to AI pipeline without long greeting.
   - If no prompt ("Hey Buddy"), acknowledges waking and waits for prompt.
4. Prevention of assistant self-echo interpretation as new commands.
5. Debouncing repeated sleep/wake events.
6. Configurable custom wake and sleep commands.
7. Safe cancellation and suppression of in-flight AI and TTS tasks upon entering sleep.
8. In-flight / cancelled tasks cannot revert character animation from SLEEPING back to IDLE.
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from app.core.buddy_state_manager import BuddyState, get_buddy_state_manager
from app.core.signals import signals
from app.character.states import CharacterState
from app.character.animation_controller import AnimationController
from app.voice.command_dispatcher import VoiceCommandParser, VoiceCommandDispatcher
from app.voice.wake_word_engine import WakeWordEngine


# ─── 1. Case, Whitespace, & Punctuation Normalization ───────────────────────

@pytest.mark.parametrize(
    "raw_input,expected_intent",
    [
        ("   HEY,   buddy!  ", "wake"),
        ("  BUDDY,   GO   TO   SLEEP...  ", "sleep"),
        ("  WAKE   UP,   BUDDY?? ", "wake"),
        ("   be   quiet...  ", "mute"),
        ("  STOP   TALKING! ", "stop"),
    ],
)
def test_command_normalization(raw_input, expected_intent):
    """Verify parser normalizes irregular spacing, casing, and punctuation."""
    res = VoiceCommandParser.parse(raw_input)
    assert res is not None, f"Failed to parse normalized command: {raw_input}"
    intent, _ = res
    assert intent == expected_intent


# ─── 2. Preventing False Activations on Unrelated Sentences ──────────────────

@pytest.mark.parametrize(
    "unrelated_sentence",
    [
        "I need to shut up this program's background noise.",
        "I was talking to my friend yesterday about Python.",
        "Please activate windows on this computer.",
        "In the wake of recent developments in machine learning.",
        "Hello.",
        "What is the weather outside today?",
        "Can you explain how to sleep better at night?",
    ],
)
def test_unrelated_sentences_do_not_trigger_commands(unrelated_sentence):
    """Verify unrelated phrases containing command words do NOT falsely activate commands."""
    res = VoiceCommandParser.parse(unrelated_sentence)
    assert res is None, f"Sentence '{unrelated_sentence}' falsely matched command intent '{res}'"

    # Also verify WakeWordEngine does not falsely trigger standby wake
    wwe = WakeWordEngine()
    assert wwe.is_wake_phrase(unrelated_sentence) is False, f"WakeWordEngine falsely triggered on: {unrelated_sentence}"


# ─── 3. Compound Wake + Prompt Handling ("Hey Buddy, explain Python.") ───────

def test_extract_wake_and_prompt():
    """Verify extraction of wake invocation and conversational prompt."""
    res = VoiceCommandParser.extract_wake_and_prompt("Hey Buddy, explain Python.")
    assert res is not None
    wake, prompt = res
    assert "buddy" in wake.lower()
    assert "explain python" in prompt.lower()

    # Plain wake phrase has empty prompt
    res_plain = VoiceCommandParser.extract_wake_and_prompt("Hey Buddy")
    assert res_plain is not None
    wake2, prompt2 = res_plain
    assert "buddy" in wake2.lower()
    assert prompt2 == ""


def test_compound_wake_wakes_sleeping_buddy_and_routes_prompt():
    """Verify 'Hey Buddy, explain Python.' wakes sleeping Buddy and dispatches prompt to AI."""
    from app.core.controller import ApplicationController

    controller = ApplicationController.__new__(ApplicationController)
    controller._is_sleeping = True
    controller.conv_repo = None
    controller.buddy_state_manager = get_buddy_state_manager()
    controller.buddy_state_manager.enter_sleep(reason="test")

    pet_mock = MagicMock()
    pet_mock.isVisible.return_value = True
    controller.pet_window = pet_mock

    voice_mock = MagicMock()
    voice_mock.is_muted = False
    voice_mock.speak = MagicMock()
    voice_mock.audio_player.is_playing = False
    voice_mock.command_dispatcher = VoiceCommandDispatcher(voice_service=voice_mock)
    controller.voice_service = voice_mock

    config_mock = MagicMock()
    config_mock.get.return_value = "continuous"
    controller.config_manager = config_mock

    ai_mock = MagicMock()
    ai_mock._is_generating = False
    controller.ai_service = ai_mock

    with patch("app.api.websocket.ws_manager.active_connections", []):
        with patch.object(controller, "wake_up", wraps=controller.wake_up) as spy_wake:
            controller._on_voice_transcription_ready("Hey Buddy, explain Python.", "en")

            # 1. Buddy must have been woken up
            assert controller.buddy_state_manager.state == BuddyState.ACTIVE
            assert controller._is_sleeping is False
            # speak_ack=False because AI is going to answer immediately
            spy_wake.assert_called_with(speak_ack=False)

            # 2. Prompt forwarded to AI service
            ai_mock.ask.assert_called_once()
            called_prompt = ai_mock.ask.call_args[0][0]
            assert "explain python" in called_prompt.lower()


def test_plain_wake_while_sleeping_acknowledges_and_waits():
    """Verify 'Hey Buddy' while sleeping acknowledges with spoken greeting and waits."""
    from app.core.controller import ApplicationController

    controller = ApplicationController.__new__(ApplicationController)
    controller._is_sleeping = True
    controller.conv_repo = None
    controller.buddy_state_manager = get_buddy_state_manager()
    controller.buddy_state_manager.enter_sleep(reason="test")

    pet_mock = MagicMock()
    pet_mock.isVisible.return_value = True
    controller.pet_window = pet_mock

    voice_mock = MagicMock()
    voice_mock.is_muted = False
    voice_mock.speak = MagicMock()
    voice_mock.audio_player.is_playing = False
    voice_mock.command_dispatcher = VoiceCommandDispatcher(voice_service=voice_mock)
    controller.voice_service = voice_mock

    config_mock = MagicMock()
    config_mock.get.return_value = "continuous"
    controller.config_manager = config_mock

    ai_mock = MagicMock()
    controller.ai_service = ai_mock

    with patch("app.api.websocket.ws_manager.active_connections", []):
        controller._on_voice_transcription_ready("Hey Buddy", "en")

        # 1. Buddy wakes up
        assert controller.buddy_state_manager.state == BuddyState.ACTIVE
        # 2. Spoken acknowledgment greeting given
        voice_mock.speak.assert_called_with("I'm here! What do you need?")
        # 3. No question asked yet, so AI service not invoked
        ai_mock.ask.assert_not_called()


# ─── 4. Assistant Self-Echo Suppression ──────────────────────────────────────

def test_self_echo_suppression_prevents_dispatch():
    """Verify voice transcription is discarded when audio player is actively playing speech."""
    from app.core.controller import ApplicationController

    controller = ApplicationController.__new__(ApplicationController)
    controller._is_sleeping = False
    controller.buddy_state_manager = get_buddy_state_manager()

    voice_mock = MagicMock()
    voice_mock.audio_player.is_playing = True  # Buddy is currently speaking
    controller.voice_service = voice_mock

    ai_mock = MagicMock()
    controller.ai_service = ai_mock

    # Transcription matching Buddy's own words arrives
    controller._on_voice_transcription_ready("I'm here! What do you need?", "en")

    # Must be discarded as echo without executing commands or AI calls
    ai_mock.ask.assert_not_called()


# ─── 5. Debouncing Repeated Commands ─────────────────────────────────────────

def test_repeated_sleep_commands_debounced():
    """Verify rapid repeated sleep commands are safely debounced."""
    sm = get_buddy_state_manager()
    sm.wake_up()
    assert sm.is_active is True

    dispatcher = VoiceCommandDispatcher()

    # First sleep succeeds
    handled1 = dispatcher.dispatch("go to sleep")
    assert handled1 is True
    assert sm.is_sleeping is True

    # Immediate second sleep invocation is debounced
    handled2 = dispatcher.dispatch("go to sleep")
    assert handled2 is True
    assert sm.is_sleeping is True


# ─── 6. Configurable Custom Commands ─────────────────────────────────────────

def test_configurable_custom_wake_and_sleep_commands():
    """Verify user-configured custom wake and sleep phrases are registered and parsed."""
    config_mock = MagicMock()
    config_mock.get.side_effect = lambda key, default=None: {
        "voice.custom_wake_words": ["rise up buddy", "power on buddy"],
        "voice.custom_sleep_words": ["hibernate buddy", "power off buddy"],
    }.get(key, default)

    VoiceCommandParser.load_configuration(config_mock)

    assert VoiceCommandParser.parse("rise up buddy")[0] == "wake"
    assert VoiceCommandParser.parse("power on buddy")[0] == "wake"
    assert VoiceCommandParser.parse("hibernate buddy")[0] == "sleep"
    assert VoiceCommandParser.parse("power off buddy")[0] == "sleep"


# ─── 7. Safe Async Task & Model Inference Cancellation (Phase 6) ─────────────

def test_ai_generation_cancelled_on_sleep():
    """Verify active generation is halted and tokens invalidated when sleep is entered."""
    from app.ai.ai_service import AIService

    ai = AIService.__new__(AIService)
    ai._lock = MagicMock()
    ai._is_generating = True
    ai._current_gen_id = 42

    token_mock = MagicMock()
    ai._active_token = token_mock

    gen_cancelled_fired = []
    ai.generation_cancelled = MagicMock()
    ai.generation_cancelled.emit.side_effect = lambda gid: gen_cancelled_fired.append(gid)

    # Cancel generation
    ai.cancel_generation()

    assert ai._is_generating is False
    assert ai._current_gen_id == 43  # Invalidate future worker completions
    token_mock.cancel.assert_called_once()
    assert 42 in gen_cancelled_fired


def test_late_ai_chunk_and_completed_discarded_during_sleep():
    """Verify late chunks and completion results from worker threads are suppressed during sleep."""
    from app.ai.ai_service import AIService

    sm = get_buddy_state_manager()
    sm.enter_sleep(reason="test")
    assert sm.is_sleeping is True

    ai = AIService.__new__(AIService)
    ai._lock = MagicMock()
    ai._is_generating = True
    ai._current_gen_id = 10

    chunk_signals = []
    signals.ai_response_chunk.connect(lambda c: chunk_signals.append(c))

    # Late chunk received
    ai._on_chunk_received(10, "Hello late chunk")
    assert len(chunk_signals) == 0  # Discarded!

    # Late completion received
    ai._on_completed(10, "Full late response")
    # Character state must not revert to idle
    assert sm.is_sleeping is True


# ─── 8. Cancelled Tasks Cannot Revert SLEEPING Character State ───────────────

def test_cancelled_tasks_cannot_revert_sleeping_character_state(qapp_instance):
    """Verify AnimationController blocks unforced transitions from SLEEPING to IDLE."""
    sm = get_buddy_state_manager()
    sm.enter_sleep(reason="test")

    controller = AnimationController(renderer=MagicMock())
    controller.request_state(CharacterState.SLEEPING, force=True)
    assert controller.current_state == CharacterState.SLEEPING

    # Attempt unforced transition to IDLE (e.g. from cancelled task or timer)
    result = controller.request_state(CharacterState.IDLE, force=False)
    assert result is False
    # Character remains SLEEPING
    assert controller.current_state == CharacterState.SLEEPING

    # Forced wake succeeds
    result_forced = controller.request_state(CharacterState.IDLE, force=True)
    assert result_forced is True
    assert controller.current_state == CharacterState.IDLE
