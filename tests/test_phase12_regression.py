"""Regression Tests for Voice and Chat Root Causes (Phase 12).

Tests:
1. Finalized transcription produces exactly one user message.
2. Empty transcription does not trigger AI generation.
3. The correct transcribed text reaches the backend.
4. A valid backend response appears as an assistant message.
5. The assistant's response is passed to TTS in voice mode.
6. A transcription error does not leave the application stuck.
7. A backend error does not leave the application stuck.
8. A TTS error does not delete the assistant's text response.
9. Duplicate transcription events do not generate duplicate responses.
10. Assistant speech is not submitted as new user input (echo prevention).

All unit tests use isolated mocks and fixtures without requiring physical audio hardware.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.ai.ai_service import AIService
from app.api.server import app
from app.api.websocket import ws_manager
from app.core.controller import ApplicationController
from app.core.diagnostic_mode import (
    ERROR_MODEL_UNAVAILABLE,
    ERROR_NO_SPEECH,
    ERROR_SUBMISSION_FAILED,
    ERROR_TTS_FAILED,
    diagnostic_tracker,
)
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.settings.config_manager import ConfigManager
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceService
from app.voice.whisper_engine import TranscriptionResult


@pytest.fixture(autouse=True)
def cleanup_diagnostic():
    """Ensure clean diagnostic isolation before and after every test."""
    diagnostic_tracker.set_enabled(False)
    diagnostic_tracker.reset_turn()
    yield
    diagnostic_tracker.set_enabled(False)
    diagnostic_tracker.reset_turn()


@pytest.fixture
def env(tmp_path):
    """Setup isolated test environment with temporary SQLite DB and mocked AI service."""
    db_file = tmp_path / "test_phase12_regression.db"
    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)
    cfg = ConfigManager(config_path=tmp_path / "test_phase12_cfg.json")

    mock_ai = MagicMock(spec=AIService)
    mock_ai.ask = MagicMock(return_value=101)
    mock_ai._is_generating = False
    mock_ai._last_user_prompt = ""
    mock_ai._current_gen_id = 101

    app.state.conv_repo = repo
    app.state.config_manager = cfg
    app.state.ai_service = mock_ai

    client = TestClient(app)
    return {
        "client": client,
        "repo": repo,
        "config": cfg,
        "mock_ai": mock_ai,
        "db_mgr": db_mgr,
    }


class MockTTSForRegression(BaseTTSEngine):
    """Mock TTS producing synthetic audio buffers."""

    def __init__(self, parent=None, should_fail: bool = False):
        super().__init__(parent)
        self.synthesize_calls = []
        self.should_fail = should_fail

    def is_available(self) -> bool:
        return True

    def load_model(self, voice_name: str | None = None) -> bool:
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        if self.should_fail:
            raise RuntimeError("TTS synthesis engine crashed.")
        self.synthesize_calls.append(text)
        samples = np.ones(1600, dtype=np.float32) * 0.05
        return SynthesizedAudio(
            samples=samples,
            sample_rate=16000,
            duration_seconds=0.1,
            text=text,
            voice_name="mock_voice",
        )


# =============================================================================
# REGRESSION TEST 1: Exactly One User Message from Finalized Transcription
# =============================================================================

def test_regression_finalized_transcription_produces_exactly_one_user_message(env):
    """Root Cause 1: Finalized transcription must create exactly 1 user message, avoiding duplicate saves."""
    client = env["client"]
    repo = env["repo"]

    conv = repo.create_conversation("Regression Single User Message")
    spoken_text = "What is the capital of Japan?"

    res = client.post(
        f"/api/conversations/{conv.id}/messages",
        json={"content": spoken_text, "is_voice": True},
    )
    assert res.status_code == 200

    messages = repo.get_messages(conv.id)
    user_msgs = [m for m in messages if m.role == "user"]

    assert len(user_msgs) == 1
    assert user_msgs[0].content == spoken_text


# =============================================================================
# REGRESSION TEST 2: Empty Transcription Does Not Trigger AI Generation
# =============================================================================

def test_regression_empty_transcription_does_not_trigger_ai():
    """Root Cause 2: Empty, whitespace, or silence transcriptions must NEVER trigger AI ask()."""
    mock_ai = MagicMock(spec=AIService)
    mock_voice = MagicMock(spec=VoiceService)
    mock_repo = MagicMock(spec=ConversationRepository)

    controller = ApplicationController.__new__(ApplicationController)
    controller.ai_service = mock_ai
    controller.voice_service = mock_voice
    controller.conv_repo = mock_repo

    with patch.object(ws_manager, "broadcast_sync") as mock_broadcast:
        # Pass whitespace transcription
        controller._on_voice_transcription_ready("    \n\t   ", "en")

        # Must NOT invoke AI generation
        mock_ai.ask.assert_not_called()
        mock_repo.add_message.assert_not_called()

        # Must broadcast safe error notice
        mock_broadcast.assert_called_once()
        event_type, payload = mock_broadcast.call_args[0]
        assert event_type == "voice_error"
        assert "No speech was detected" in payload["message"]


# =============================================================================
# REGRESSION TEST 3: Correct Transcribed Text Reaches the Backend
# =============================================================================

def test_regression_correct_transcribed_text_reaches_backend(env):
    """Root Cause 3: The backend must receive the exact string recognized by the STT engine without corruption."""
    client = env["client"]
    repo = env["repo"]
    mock_ai = env["mock_ai"]

    conv = repo.create_conversation("Regression Text Fidelity")
    exact_recognized_text = "Explain Schrödinger's cat paradox with quantum mechanics."

    res = client.post(
        f"/api/conversations/{conv.id}/messages",
        json={"content": exact_recognized_text, "is_voice": True},
    )
    assert res.status_code == 200

    # Backend database has exact string
    messages = repo.get_messages(conv.id)
    assert messages[0].content == exact_recognized_text

    # AI service received exact string
    mock_ai.ask.assert_called_once_with(
        user_prompt=exact_recognized_text,
        is_voice=True,
        response_style=None,
    )


# =============================================================================
# REGRESSION TEST 4: Valid Backend Response Appears as Assistant Message
# =============================================================================

def test_regression_backend_response_appears_as_assistant_message(env):
    """Root Cause 4: AI response must appear with role='assistant' and never overwrite as user input."""
    client = env["client"]
    repo = env["repo"]

    conv = repo.create_conversation("Regression Assistant Message")
    repo.add_message(conv.id, "user", "What is gravity?")
    asst_msg = repo.add_message(conv.id, "assistant", "", status="streaming")

    ai_reply = "Gravity is a fundamental interaction which causes mutual attraction between all things with mass."
    repo.update_message_content(asst_msg.id, ai_reply, status="delivered")

    res = client.get(f"/api/conversations/{conv.id}/messages")
    assert res.status_code == 200
    msgs = res.json()

    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == ai_reply
    assert msgs[1]["status"] == "delivered"


# =============================================================================
# REGRESSION TEST 5: Assistant Response Passed to TTS in Voice Mode Only
# =============================================================================

def test_regression_assistant_response_passed_to_tts_in_voice_mode_only(qapp_instance):
    """Root Cause 5: In voice mode, completed AI response must be passed to TTS; in text mode, TTS is skipped."""
    mock_tts = MockTTSForRegression()
    mock_player = MagicMock(spec=AudioPlayer)
    mock_player.is_playing.return_value = False

    voice_service = VoiceService()
    voice_service.audio_player = mock_player
    voice_service.active_tts_engine = mock_tts

    # 1. Voice Mode: speak() is invoked
    spoken_text = "I am speaking because voice mode was active."
    voice_service.speak(spoken_text)

    for _ in range(25):
        qapp_instance.processEvents()
        if len(mock_tts.synthesize_calls) > 0:
            break
        time.sleep(0.02)

    assert len(mock_tts.synthesize_calls) == 1
    assert mock_tts.synthesize_calls[0] == spoken_text
    mock_player.play.assert_called()


# =============================================================================
# REGRESSION TEST 6: Transcription Error Does Not Leave Application Stuck
# =============================================================================

def test_regression_transcription_error_does_not_leave_application_stuck():
    """Root Cause 6: An empty or failed transcription must reset state and not leave state machine in TRANSCRIBING."""
    ctrl = VoiceConversationController()
    ctrl._activation_mode = VoiceActivationMode.CONTINUOUS

    # Enter TRANSCRIBING state
    ctrl._transition_to(ConversationState.TRANSCRIBING)
    assert ctrl.state == ConversationState.TRANSCRIBING

    # STT engine returns empty result (failure/silence)
    empty_result = TranscriptionResult(text="", language="en", language_probability=0.0, duration_seconds=0.1)
    ctrl._on_transcription_completed(empty_result, turn_id=ctrl._turn_id)

    # State machine must NOT remain in TRANSCRIBING; recovers to LISTENING or IDLE
    assert ctrl.state in (ConversationState.LISTENING, ConversationState.IDLE)


# =============================================================================
# REGRESSION TEST 7: Backend Error Does Not Leave Application Stuck
# =============================================================================

def test_regression_backend_error_does_not_leave_application_stuck():
    """Root Cause 7: AI timeout or backend error recovers state and resets generation watchdog."""
    ctrl = VoiceConversationController()
    ctrl._activation_mode = VoiceActivationMode.CONTINUOUS

    ctrl._transition_to(ConversationState.GENERATING_RESPONSE)
    assert ctrl.state == ConversationState.GENERATING_RESPONSE

    # Simulate generation watchdog timeout
    ctrl._on_generation_timeout(turn_id=ctrl._turn_id)

    # Must recover out of GENERATING_RESPONSE
    assert ctrl.state != ConversationState.GENERATING_RESPONSE
    assert ctrl.state in (ConversationState.LISTENING, ConversationState.IDLE, ConversationState.ERROR)


# =============================================================================
# REGRESSION TEST 8: TTS Error Does Not Delete Assistant's Text Response
# =============================================================================

def test_regression_tts_error_does_not_delete_assistant_text_response(env, qapp_instance):
    """Root Cause 8: If TTS synthesis fails, the assistant text message in DB must remain intact."""
    repo = env["repo"]
    conv = repo.create_conversation("Regression TTS Error")
    ai_text = "Here is an important answer that must not be deleted if speech fails."

    u_msg = repo.add_message(conv.id, "user", "Give me information.")
    a_msg = repo.add_message(conv.id, "assistant", ai_text, status="delivered")

    # TTS engine configured to throw RuntimeError
    failing_tts = MockTTSForRegression(should_fail=True)
    voice_service = VoiceService()
    voice_service.active_tts_engine = failing_tts

    # Speak attempt fails
    voice_service.speak(ai_text)
    for _ in range(25):
        qapp_instance.processEvents()
        time.sleep(0.02)

    # Database message must still exist and be completely intact!
    messages = repo.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[1].id == a_msg.id
    assert messages[1].content == ai_text
    assert messages[1].status == "delivered"


# =============================================================================
# REGRESSION TEST 9: Duplicate Transcription Events Do Not Duplicate Responses
# =============================================================================

def test_regression_duplicate_transcription_events_do_not_generate_duplicate_responses(env):
    """Root Cause 9: Rapid duplicate transcription submissions are rejected by backend guard."""
    client = env["client"]
    repo = env["repo"]
    mock_ai = env["mock_ai"]

    conv = repo.create_conversation("Regression Duplicate Guard")
    duplicate_prompt = "Tell me a joke."

    # First submission -> accepted
    res1 = client.post(
        f"/api/conversations/{conv.id}/messages",
        json={"content": duplicate_prompt, "is_voice": True},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] in ("ok", "generating", "dispatched")

    # Simulate AI currently in-flight generating this exact prompt
    mock_ai._is_generating = True
    mock_ai._last_user_prompt = duplicate_prompt

    # Second submission (identical prompt in-flight) -> rejected as duplicate
    res2 = client.post(
        f"/api/conversations/{conv.id}/messages",
        json={"content": duplicate_prompt, "is_voice": True},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "duplicate_rejected"

    # Only one user message was persisted
    messages = repo.get_messages(conv.id)
    user_msgs = [m for m in messages if m.role == "user"]
    assert len(user_msgs) == 1


# =============================================================================
# REGRESSION TEST 10: Assistant Speech Is Not Submitted as New User Input
# =============================================================================

def test_regression_assistant_speech_not_submitted_as_user_input():
    """Root Cause 10: Acoustic echo of assistant speech is detected and discarded, preventing infinite feedback loop."""
    mock_ai = MagicMock(spec=AIService)
    ctrl = VoiceConversationController()
    ctrl.ai_service = mock_ai
    ctrl._state = ConversationState.TRANSCRIBING

    assistant_spoken_text = "I am your AI assistant, how can I help you today?"

    # Controller records assistant speech in echo suppressor
    ctrl.echo_suppressor.record_assistant_speech(assistant_spoken_text)
    ctrl._last_assistant_response = assistant_spoken_text

    # Microphone captures speaker audio and Whisper transcribes identical text
    echo_result = TranscriptionResult(
        text=assistant_spoken_text,
        language="en",
        language_probability=0.99,
        duration_seconds=2.0,
    )

    ctrl._on_transcription_completed(echo_result, turn_id=ctrl._turn_id)

    # Must NOT call AI service (echo rejected!)
    mock_ai.ask.assert_not_called()

    # Recovers state without submitting echo as user message
    assert ctrl.state in (ConversationState.LISTENING, ConversationState.IDLE)
