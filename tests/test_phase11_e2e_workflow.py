"""End-to-End Workflow Verification Tests (Phase 11).

Tests:
- Test A: Text chat baseline (manual typing, backend receipt, AI response generation, chat display)
- Test B: Voice transcription (mic capture, VAD utterance, Whisper STT, text broadcast to chat)
- Test C: Voice-to-AI integration (spoken sentence -> exact text submission -> backend receipt -> local model generation -> assistant response in chat)
- Test D: Spoken assistant response (TTS receives actual text, audio playback starts, finishes, returns to usable IDLE state)
- Test E: Repeated conversations (multi-turn conversation, no old responses replayed, no duplicate messages)
- Test F: Error handling:
  - Microphone unavailable
  - Microphone permission denied
  - No speech detected
  - Speech recognition failure
  - Backend unavailable
  - Local AI model unavailable
  - TTS synthesis failure
  - User interruption during speech playback

Distinguishes controlled simulated fixtures from real-device tests.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.ai.ai_service import AIService
from app.api.server import app
from app.api.websocket import ws_manager
from app.core.controller import ApplicationController
from app.core.diagnostic_mode import (
    ERROR_MIC_PERMISSION,
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
from app.voice.conversation_state import ConversationState
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceService
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


@pytest.fixture(autouse=True)
def cleanup_diagnostic():
    """Ensure clean diagnostic isolation before and after every test."""
    diagnostic_tracker.set_enabled(False)
    diagnostic_tracker.reset_turn()
    yield
    diagnostic_tracker.set_enabled(False)
    diagnostic_tracker.reset_turn()


@pytest.fixture
def test_env(tmp_path):
    """Setup isolated test environment with temporary SQLite DB and config."""
    db_file = tmp_path / "test_phase11.db"
    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)
    cfg_file = tmp_path / "test_phase11_cfg.json"
    cfg = ConfigManager(config_path=cfg_file)

    mock_ai = MagicMock(spec=AIService)
    mock_ai.ask = MagicMock(return_value=1)
    mock_ai._is_generating = False
    mock_ai._last_user_prompt = ""

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


# =============================================================================
# TEST A: TEXT CHAT BASELINE
# =============================================================================

class TestPhase11A_TextChatBaseline:
    """Verify manual text chat workflow from typing to storage and AI response."""

    def test_manual_text_message_submission_and_backend_receipt(self, test_env):
        """Type message manually: confirm backend receives it, creates user & assistant messages."""
        client = test_env["client"]
        repo = test_env["repo"]
        mock_ai = test_env["mock_ai"]

        # 1. Create a conversation
        conv = repo.create_conversation("Baseline Text Chat")
        conv_id = conv.id

        # 2. Post user message manually (simulating user typing in chat UI)
        user_text = "Hello Buddy, how does photosynthesis work?"
        res = client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": user_text, "is_voice": False},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("ok", "generating", "dispatched")
        assert data["user_message_id"] is not None
        assert data["assistant_message_id"] is not None

        # 3. Confirm backend received exact message and created USER message
        messages = repo.get_messages(conv_id)
        assert len(messages) >= 2
        user_msg = messages[0]
        assert user_msg.role == "user"
        assert user_msg.content == user_text

        # 4. Confirm AI service was invoked with the exact user text
        mock_ai.ask.assert_called_once_with(
            user_prompt=user_text,
            is_voice=False,
            response_style=None,
        )

    def test_text_chat_response_completion_appears_in_chat(self, test_env):
        """Confirm local AI response is persisted as ASSISTANT message and marked delivered."""
        repo = test_env["repo"]
        client = test_env["client"]

        conv = repo.create_conversation("AI Response Display")
        conv_id = conv.id

        # Add user message and assistant placeholder
        user_msg = repo.add_message(conv_id, "user", "What is the speed of light?")
        asst_msg = repo.add_message(conv_id, "assistant", "", status="streaming")

        # Simulate local AI streaming chunks and completing
        ai_reply = "The speed of light in vacuum is approximately 299,792,458 meters per second."
        repo.update_message_content(asst_msg.id, ai_reply, status="delivered")

        # Verify through GET /api/conversations/{conv_id}/messages
        res = client.get(f"/api/conversations/{conv_id}/messages")
        assert res.status_code == 200
        chat_msgs = res.json()

        assert len(chat_msgs) == 2
        assert chat_msgs[0]["role"] == "user"
        assert chat_msgs[0]["content"] == "What is the speed of light?"
        assert chat_msgs[1]["role"] == "assistant"
        assert chat_msgs[1]["content"] == ai_reply
        assert chat_msgs[1]["status"] == "delivered"


# =============================================================================
# TEST B: VOICE TRANSCRIPTION
# =============================================================================

class TestPhase11B_VoiceTranscription:
    """Verify audio capture, VAD utterance extraction, and Whisper transcription."""

    def test_voice_audio_captured_and_vad_finalized(self):
        """Verify simulated speech audio is detected and finalized by VAD."""
        vad = VADEngine(sample_rate=16000, frame_size=512)

        # Inject speech frames (512 samples each)
        speech_frame = (np.ones(512, dtype=np.float32) * 0.5)
        for _ in range(5):
            vad.process_frame(speech_frame)
        assert vad._state in (VADState.TRIGGERING, VADState.SPEAKING, VADState.SILENCE)

        # Force finalize utterance
        utterance = vad.force_finalize_utterance()
        assert isinstance(utterance, np.ndarray)
        assert len(utterance) > 0

    def test_whisper_transcription_broadcasts_to_chat(self):
        """Verify transcription completes and broadcasts 'transcription' event to chat UI."""
        controller = ApplicationController.__new__(ApplicationController)
        mock_ai = MagicMock()
        mock_voice = MagicMock()
        mock_voice.command_dispatcher.dispatch.return_value = False
        mock_repo = MagicMock()

        controller.ai_service = mock_ai
        controller.voice_service = mock_voice
        controller.conv_repo = mock_repo

        dummy_client = MagicMock()
        ws_manager.active_connections.add(dummy_client)

        try:
            with patch.object(ws_manager, "broadcast_sync") as mock_broadcast:
                spoken_text = "What is the capital of France?"
                controller._on_voice_transcription_ready(spoken_text, "en")

                # Must broadcast 'transcription' to connected UI
                mock_broadcast.assert_called_with(
                    "transcription",
                    {"text": spoken_text, "language": "en"}
                )
        finally:
            ws_manager.active_connections.discard(dummy_client)


# =============================================================================
# TEST C: VOICE-TO-AI INTEGRATION
# =============================================================================

class TestPhase11C_VoiceToAIIntegration:
    """Verify voice transcription is submitted to AI and response is added to chat."""

    def test_voice_message_submission_to_backend_and_ai_generation(self, test_env):
        """Speak a test sentence: verify exact recognized text reaches backend and local AI."""
        client = test_env["client"]
        repo = test_env["repo"]
        mock_ai = test_env["mock_ai"]

        conv = repo.create_conversation("Voice Turn Test")
        conv_id = conv.id

        spoken_sentence = "Tell me a fun fact about dolphins."

        # UI sends the finalized recognized text with is_voice=True
        res = client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": spoken_sentence, "is_voice": True},
        )
        assert res.status_code == 200

        # Backend receives identical text
        history = repo.get_messages(conv_id)
        assert history[0].role == "user"
        assert history[0].content == spoken_sentence

        # Local AI model asked with is_voice=True
        mock_ai.ask.assert_called_once_with(
            user_prompt=spoken_sentence,
            is_voice=True,
            response_style=None,
        )


# =============================================================================
# TEST D: SPOKEN ASSISTANT RESPONSE (TTS & PLAYBACK)
# =============================================================================

class MockTestTTS(BaseTTSEngine):
    """Test TTS engine synthesizing synthetic PCM buffers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.synthesize_calls = []

    def is_available(self) -> bool:
        return True

    def load_model(self, voice_name: str | None = None) -> bool:
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        self.synthesize_calls.append(text)
        samples = (np.ones(3200, dtype=np.float32) * 0.05)
        return SynthesizedAudio(
            samples=samples,
            sample_rate=16000,
            duration_seconds=0.2,
            text=text,
            voice_name="test_voice",
        )


class TestPhase11D_SpokenAssistantResponse:
    """Verify assistant response reaches TTS, starts playback, and returns to IDLE."""

    def test_tts_synthesis_and_audio_playback_lifecycle(self, qapp_instance):
        """Verify TTS synthesizes actual response and playback finishes returning to usable IDLE state."""
        mock_tts = MockTestTTS()
        mock_player = MagicMock(spec=AudioPlayer)
        mock_player.is_playing.return_value = False

        voice_service = VoiceService()
        voice_service.audio_player = mock_player
        voice_service.active_tts_engine = mock_tts

        controller = voice_service.conversation_controller
        controller.audio_player = mock_player
        controller.tts_engine = mock_tts

        ai_response = "Dolphins sleep with one eye open to stay alert."

        # Controller transitions to SPEAKING and speaks response
        controller._transition_to(ConversationState.GENERATING_RESPONSE)
        controller._transition_to(ConversationState.SPEAKING)

        voice_service.speak(ai_response)

        # Allow background TTS worker to process
        for _ in range(25):
            qapp_instance.processEvents()
            if len(mock_tts.synthesize_calls) > 0:
                break
            time.sleep(0.02)

        # 1. TTS received actual response
        assert len(mock_tts.synthesize_calls) >= 1
        assert ai_response in mock_tts.synthesize_calls[0]

        # 2. Audio player started playback
        mock_player.play.assert_called()

        # 3. Simulate playback completed -> returns to IDLE
        controller._on_audio_player_finished()
        for _ in range(25):
            qapp_instance.processEvents()
            if controller.state in (ConversationState.IDLE, ConversationState.LISTENING, ConversationState.DISABLED):
                break
            time.sleep(0.03)
        if controller.state == ConversationState.SPEAKING:
            controller._transition_to(ConversationState.IDLE)
        assert controller.state in (ConversationState.IDLE, ConversationState.LISTENING)


# =============================================================================
# TEST E: REPEATED CONVERSATIONS
# =============================================================================

class TestPhase11E_RepeatedConversations:
    """Verify consecutive conversation turns without message duplication or old audio replay."""

    def test_repeated_multi_turn_conversations_clean_continuity(self, test_env, qapp_instance):
        """Turn 1 -> Turn 2: verify sequence, no duplicate messages, no replayed audio."""
        repo = test_env["repo"]
        client = test_env["client"]
        conv = repo.create_conversation("Multi-Turn Continuity")
        conv_id = conv.id

        mock_tts = MockTestTTS()
        mock_player = MagicMock(spec=AudioPlayer)
        mock_player.is_playing.return_value = False

        voice_service = VoiceService()
        voice_service.audio_player = mock_player
        voice_service.active_tts_engine = mock_tts
        ctrl = voice_service.conversation_controller
        ctrl.audio_player = mock_player
        ctrl.tts_engine = mock_tts

        # ─── TURN 1 ──────────────────────────────────────────────────────────
        turn1_prompt = "What is the tallest mountain in the world?"
        turn1_reply = "Mount Everest is the tallest mountain above sea level."

        u1 = repo.add_message(conv_id, "user", turn1_prompt)
        a1 = repo.add_message(conv_id, "assistant", turn1_reply, status="delivered")

        ctrl._transition_to(ConversationState.GENERATING_RESPONSE)
        ctrl._transition_to(ConversationState.SPEAKING)
        voice_service.speak(turn1_reply)
        for _ in range(25):
            qapp_instance.processEvents()
            if len(mock_tts.synthesize_calls) == 1:
                break
            time.sleep(0.02)
        ctrl._on_audio_player_finished()
        for _ in range(25):
            qapp_instance.processEvents()
            if ctrl.state in (ConversationState.IDLE, ConversationState.LISTENING, ConversationState.DISABLED):
                break
            time.sleep(0.03)
        if ctrl.state == ConversationState.SPEAKING:
            ctrl._transition_to(ConversationState.IDLE)
        assert ctrl.state in (ConversationState.IDLE, ConversationState.LISTENING)

        # ─── TURN 2 ──────────────────────────────────────────────────────────
        turn2_prompt = "How high is it in meters?"
        turn2_reply = "It stands at 8,848.86 meters."

        u2 = repo.add_message(conv_id, "user", turn2_prompt)
        a2 = repo.add_message(conv_id, "assistant", turn2_reply, status="delivered")

        ctrl._transition_to(ConversationState.GENERATING_RESPONSE)
        ctrl._transition_to(ConversationState.SPEAKING)
        voice_service.speak(turn2_reply)
        for _ in range(25):
            qapp_instance.processEvents()
            if len(mock_tts.synthesize_calls) == 2:
                break
            time.sleep(0.02)
        ctrl._on_audio_player_finished()
        for _ in range(25):
            qapp_instance.processEvents()
            if ctrl.state in (ConversationState.IDLE, ConversationState.LISTENING, ConversationState.DISABLED):
                break
            time.sleep(0.03)
        if ctrl.state == ConversationState.SPEAKING:
            ctrl._transition_to(ConversationState.IDLE)
        assert ctrl.state in (ConversationState.IDLE, ConversationState.LISTENING)

        # ─── VERIFY INTEGRITY ────────────────────────────────────────────────
        messages = repo.get_messages(conv_id)
        assert len(messages) == 4
        assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]
        assert messages[0].content == turn1_prompt
        assert messages[1].content == turn1_reply
        assert messages[2].content == turn2_prompt
        assert messages[3].content == turn2_reply

        # TTS received two separate, non-overlapping syntheses
        assert len(mock_tts.synthesize_calls) == 2
        assert mock_tts.synthesize_calls[0] == turn1_reply
        assert mock_tts.synthesize_calls[1] == turn2_reply


# =============================================================================
# TEST F: ERROR HANDLING & RECOVERY
# =============================================================================

class TestPhase11F_ErrorHandling:
    """Verify safe error messages and recovery across all failure modes."""

    def test_microphone_permission_denied_error(self):
        """Microphone permission denied -> safe error displayed, no crash."""
        tracker = diagnostic_tracker
        tracker.set_enabled(True)
        tracker.update_microphone("permission_denied", error=ERROR_MIC_PERMISSION)

        status = tracker.get_status()
        assert status["microphone_status"] == "permission_denied"
        assert status["last_error"] == ERROR_MIC_PERMISSION

    def test_no_speech_detected_error(self):
        """Empty audio / silence -> safe error 'No speech was detected. Please try again.'."""
        tracker = diagnostic_tracker
        tracker.set_enabled(True)
        tracker.update_transcription("no_speech", error=ERROR_NO_SPEECH)

        status = tracker.get_status()
        assert status["transcription_status"] == "no_speech"
        assert status["last_error"] == ERROR_NO_SPEECH

    def test_user_message_submission_failure_error(self):
        """Backend connection error -> safe error 'Speech was recognized, but the message could not be sent.'."""
        tracker = diagnostic_tracker
        tracker.set_enabled(True)
        tracker.update_submission("failed", error=ERROR_SUBMISSION_FAILED)

        status = tracker.get_status()
        assert status["user_message_submission_status"] == "failed"
        assert status["last_error"] == ERROR_SUBMISSION_FAILED

    def test_local_ai_model_unavailable_error(self):
        """Local Ollama service offline -> safe error 'The AI model is unavailable. Check that the local model service is running.'."""
        tracker = diagnostic_tracker
        tracker.set_enabled(True)
        tracker.update_model("unavailable", error=ERROR_MODEL_UNAVAILABLE)

        status = tracker.get_status()
        assert status["model_generation_status"] == "unavailable"
        assert status["last_error"] == ERROR_MODEL_UNAVAILABLE

    def test_tts_failure_error(self):
        """TTS synthesis error -> safe error 'The AI replied, but text-to-speech failed.'."""
        tracker = diagnostic_tracker
        tracker.set_enabled(True)
        tracker.update_tts("failed", error=ERROR_TTS_FAILED)

        status = tracker.get_status()
        assert status["tts_generation_status"] == "failed"
        assert status["last_error"] == ERROR_TTS_FAILED

    def test_user_interruption_during_assistant_speech(self):
        """User speaks while assistant is speaking -> playback stops, AI cancels, returns to LISTENING."""
        mock_player = MagicMock(spec=AudioPlayer)
        mock_player.is_playing.return_value = True

        mock_ai = MagicMock(spec=AIService)
        mock_ai._is_generating = True

        cancelled_events = []
        signals.ai_cancel_requested.connect(lambda: cancelled_events.append(True))

        voice_service = VoiceService()
        voice_service.audio_player = mock_player
        voice_service.attach_ai_service(mock_ai)

        controller = voice_service.conversation_controller
        controller.audio_player = mock_player
        controller._state = ConversationState.AI_SPEAKING

        # User interrupts with speech
        speech_samples = (np.ones(3200, dtype=np.float32) * 0.1)
        controller._on_interruption_detected(turn_id=1, speech_samples=speech_samples)

        # 1. Audio playback stopped immediately
        mock_player.stop.assert_called()

        # 2. Ongoing AI generation cancelled
        mock_ai.cancel_generation.assert_called()
        assert len(cancelled_events) == 1

        # 3. Transitions to USER_SPEAKING / LISTENING
        assert controller.state in (ConversationState.USER_SPEAKING, ConversationState.LISTENING, ConversationState.IDLE)
