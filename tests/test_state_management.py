"""Targeted Verification Suite for Application State Machine Management (Task 5).

Verifies:
1. ApplicationController emits canonical uppercase application states:
   IDLE, LISTENING, TRANSCRIBING, THINKING, SPEAKING, ERROR.
2. Character state mapping to canonical application state.
3. Voice event hooks correctly update state machine:
   - Speech detection -> LISTENING
   - Transcription start -> TRANSCRIBING
   - Speaking start -> SPEAKING
   - Speaking finished -> IDLE
4. Error handling emits ERROR state instead of premature idle.
5. Cancellation and completion return state cleanly to IDLE.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.core.controller import ApplicationController
from app.core.signals import signals


@pytest.fixture
def mock_controller(qapp_instance):
    """Create a mock ApplicationController with stubbed components."""
    mock_cfg = MagicMock()
    controller = ApplicationController(app=qapp_instance, config_manager=mock_cfg)

    # Stub dependencies
    controller.ai_service = MagicMock()
    controller.ai_service._is_generating = False
    controller.voice_service = MagicMock()

    return controller


def test_char_state_changed_broadcasts_canonical_app_state(mock_controller):
    """Verify that _on_char_state_changed maps state strings to canonical uppercase app_state."""
    states_to_test = [
        ("idle", "IDLE"),
        ("listening", "LISTENING"),
        ("transcribing", "TRANSCRIBING"),
        ("thinking", "THINKING"),
        ("speaking", "SPEAKING"),
        ("error", "ERROR"),
        ("sleeping", "IDLE"),
        ("happy", "IDLE"),
        ("unknown_state", "IDLE"),
    ]

    with patch("app.api.websocket.ws_manager.broadcast_sync") as mock_broadcast:
        for input_state, expected_canonical in states_to_test:
            mock_broadcast.reset_mock()
            mock_controller._on_char_state_changed(input_state)

            # Must broadcast both char_state and app_state
            calls = mock_broadcast.call_args_list
            assert any(
                c.args[0] == "char_state" and c.args[1] == {"state": input_state}
                for c in calls
            ), f"Missing char_state broadcast for {input_state}"

            assert any(
                c.args[0] == "app_state" and c.args[1] == {"state": expected_canonical}
                for c in calls
            ), f"Expected app_state {expected_canonical} for input {input_state}"


def test_ai_error_emits_error_state(mock_controller):
    """Verify that _on_ai_error emits character_state_changed('error') instead of idle."""
    emitted = []
    signals.character_state_changed.connect(lambda s: emitted.append(s))
    try:
        with patch("app.api.websocket.ws_manager.broadcast_sync"):
            mock_controller._on_ai_error("Ollama connection failed")
            assert "error" in emitted, f"Expected 'error' in emitted states, got: {emitted}"
    finally:
        signals.character_state_changed.disconnect()


def test_voice_pipeline_state_sequence(mock_controller):
    """Verify that voice pipeline lifecycle transitions correctly through the states."""
    emitted = []
    signals.character_state_changed.connect(lambda s: emitted.append(s))

    try:
        # 1. Speech detected -> listening
        mock_controller._on_speech_detected()
        assert emitted[-1] == "listening"

        # 2. Transcription started -> transcribing
        mock_controller._on_transcription_started()
        assert emitted[-1] == "transcribing"

        # 3. Speaking starts -> speaking
        mock_controller._on_speaking_started()
        assert emitted[-1] == "speaking"

        # 4. Speaking finished -> idle
        mock_controller._on_speaking_finished()
        assert emitted[-1] == "idle"
    finally:
        signals.character_state_changed.disconnect()


def test_ai_completed_and_cancelled_return_to_idle(mock_controller):
    """Verify that AI completion and cancellation return state to idle."""
    emitted = []
    signals.character_state_changed.connect(lambda s: emitted.append(s))

    try:
        with patch("app.api.websocket.ws_manager.broadcast_sync"):
            # When generation completes and no speech is playing
            mock_controller._on_ai_complete("Final response")
            assert emitted[-1] == "idle"

            # When generation is cancelled
            mock_controller._on_ai_cancelled()
            assert emitted[-1] == "idle"
    finally:
        signals.character_state_changed.disconnect()
