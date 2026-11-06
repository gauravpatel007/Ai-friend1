"""Tests for Voice Command Parser and Intent Dispatcher (Bug 1 Fix)."""

import pytest
from unittest.mock import MagicMock, patch

from app.core.signals import signals
from app.voice.command_dispatcher import VoiceCommandDispatcher, VoiceCommandParser


# ─── 1. Parser Pattern Tests ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,expected_intent",
    [
        ("open settings", "open_settings"),
        ("show settings", "open_settings"),
        ("launch settings", "open_settings"),
        ("settings", "open_settings"),
        ("hey buddy, please open settings", "open_settings"),
        ("hide pet", "hide_pet"),
        ("buddy please hide yourself now", "hide_pet"),
        ("go away", "hide_pet"),
        ("show pet", "show_pet"),
        ("come back buddy", "show_pet"),
        ("toggle pet", "toggle_pet"),
        ("open chat", "open_chat"),
        ("show chat window", "open_chat"),
        ("close chat", "close_chat"),
        ("open voice window", "open_voice_window"),
        ("show voice portal", "open_voice_window"),
        ("close voice window", "close_voice_window"),
        ("hide voice window", "close_voice_window"),
        ("વૉઇસ વિન્ડો ખોલો", "open_voice_window"),
        ("વૉઇસ વિન્ડો બંધ કરો", "close_voice_window"),
        ("वॉयस विंडो खोलो", "open_voice_window"),
        ("वॉयस विंडो बंद करो", "close_voice_window"),
        ("minimize", "minimize_chat"),
        ("minimize window", "minimize_chat"),
        ("maximize", "maximize_chat"),
        ("mute", "mute"),
        ("mute voice", "mute"),
        ("be quiet", "mute"),
        ("silence", "mute"),
        ("unmute", "unmute"),
        ("unmute voice", "unmute"),
        ("go to sleep", "sleep"),
        ("sleep mode", "sleep"),
        ("take a nap", "sleep"),
        ("wake up", "wake"),
        ("rise and shine", "wake"),
        ("stop", "stop"),
        ("emergency stop", "stop"),
        ("shut up", "stop"),
        ("clear chat", "clear_chat"),
        ("clear conversation", "clear_chat"),
        ("new chat", "clear_chat"),
        ("change model", "change_model"),
        ("switch model", "change_model"),
        ("exit", "exit"),
        ("quit app", "exit"),
        ("bye bye buddy", "exit"),
        # Gujarati commands
        ("સેટિંગ્સ ખોલો", "open_settings"),
        ("સંતાઈ જા", "hide_pet"),
        ("ચેટ ખોલો", "open_chat"),
        ("ચેટ બંધ કર", "close_chat"),
        ("મ્યુટ કર", "mute"),
        ("સુઈ જા", "sleep"),
        ("જાગી જા", "wake"),
        ("આવજો", "exit"),
        # Hindi commands
        ("सेटिंग्स खोलो", "open_settings"),
        ("छिप जाओ", "hide_pet"),
        ("चैट खोलो", "open_chat"),
        ("सो जाओ", "sleep"),
        ("अलविदा", "exit"),
    ],
)
def test_voice_command_parser_matching(text, expected_intent):
    """Verify standard imperative speech phrases parse into correct canonical intents."""
    result = VoiceCommandParser.parse(text)
    assert result is not None
    intent, _ = result
    assert intent == expected_intent


@pytest.mark.parametrize(
    "text",
    [
        "How do I open settings in Windows 11?",
        "What is the weather like in New York today?",
        "Tell me a bedtime story about a friendly robot",
        "Explain the difference between Python and JavaScript",
        "Why is the sky blue?",
        "Can you write a poem about artificial intelligence?",
        "Who was the first president of the United States?",
    ],
)
def test_voice_command_parser_rejects_conversational_queries(text):
    """Verify general questions and long conversational prompts are NOT treated as commands."""
    assert VoiceCommandParser.parse(text) is None


# ─── 2. Dispatcher Action Tests ──────────────────────────────────────────────

def test_dispatcher_open_settings():
    """Verify dispatching open_settings emits open_settings_requested signal."""
    mock_vs = MagicMock()
    dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)

    signal_fired = []
    signals.open_settings_requested.connect(lambda: signal_fired.append(True))

    handled = dispatcher.dispatch("open settings")
    assert handled is True
    assert len(signal_fired) == 1
    mock_vs.speak.assert_called_with("Opening settings.")


def test_dispatcher_hide_and_show_pet():
    """Verify dispatching hide_pet and show_pet emit corresponding signals."""
    mock_vs = MagicMock()
    dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)

    hide_fired = []
    show_fired = []
    signals.hide_pet_requested.connect(lambda: hide_fired.append(True))
    signals.show_pet_requested.connect(lambda: show_fired.append(True))

    assert dispatcher.dispatch("hide pet") is True
    assert len(hide_fired) == 1

    assert dispatcher.dispatch("show pet") is True
    assert len(show_fired) == 1


def test_dispatcher_open_and_close_voice_window():
    """Verify dispatching open_voice_window and close_voice_window emit proper dedicated signals."""
    mock_vs = MagicMock()
    dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)

    open_fired = []
    close_fired = []
    signals.open_voice_window_requested.connect(lambda: open_fired.append(True))
    signals.close_voice_window_requested.connect(lambda: close_fired.append(True))

    assert dispatcher.dispatch("open voice window") is True
    assert len(open_fired) == 1
    mock_vs.speak.assert_called_with("Opening voice window.")

    assert dispatcher.dispatch("close voice window") is True
    assert len(close_fired) == 1
    mock_vs.speak.assert_called_with("Closing voice window.")


def test_dispatcher_mute_and_unmute():
    """Verify mute/unmute calls voice_service methods."""
    mock_vs = MagicMock()
    dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)

    assert dispatcher.dispatch("mute") is True
    mock_vs.set_muted.assert_called_with(True)

    assert dispatcher.dispatch("unmute") is True
    mock_vs.set_muted.assert_called_with(False)


def test_dispatcher_sleep_and_wake():
    """Verify sleep and wake intents emit proper lifecycle signals."""
    mock_vs = MagicMock()
    dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)

    sleep_fired = []
    wake_fired = []
    signals.sleep_requested.connect(lambda: sleep_fired.append(True))
    signals.wake_requested.connect(lambda: wake_fired.append(True))

    assert dispatcher.dispatch("go to sleep") is True
    assert len(sleep_fired) == 1

    assert dispatcher.dispatch("wake up") is True
    assert len(wake_fired) == 1


def test_dispatcher_clear_chat():
    """Verify clear_chat clears messages and ai context."""
    mock_ai = MagicMock()
    mock_repo = MagicMock()
    mock_ai.active_conversation_id = "test-conv-123"

    dispatcher = VoiceCommandDispatcher(ai_service=mock_ai, conv_repo=mock_repo)
    assert dispatcher.dispatch("clear conversation") is True
    mock_repo.clear_conversation_messages.assert_called_with("test-conv-123")
    mock_ai.clear_context.assert_called_once()


def test_dispatcher_custom_handler_registration():
    """Verify custom command intents can be registered and dispatched."""
    dispatcher = VoiceCommandDispatcher()
    custom_fired = []
    dispatcher.register_handler("custom_action", lambda: custom_fired.append(42) or "Custom OK")

    # Manually register pattern for test
    VoiceCommandParser.COMMAND_PATTERNS["custom_action"] = [r"^run\s+custom\s+test$"]

    assert dispatcher.dispatch("run custom test") is True
    assert custom_fired == [42]


def test_dispatcher_deduplication_window():
    """Verify immediate duplicate commands within 1.5 seconds are suppressed from re-executing."""
    mock_vs = MagicMock()
    dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)

    signal_count = []
    signals.open_chat_requested.connect(lambda: signal_count.append(1))

    # First dispatch triggers
    assert dispatcher.dispatch("open chat") is True
    assert len(signal_count) == 1

    # Second immediate dispatch is deduplicated
    assert dispatcher.dispatch("open chat") is True
    assert len(signal_count) == 1  # Not fired twice!
