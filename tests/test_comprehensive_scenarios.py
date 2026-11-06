"""Comprehensive Verification Suite for All 10 Required Scenarios (Task 10).

Validates:
1. Normal text conversations.
2. Continuous voice conversations.
3. Repeated conversations.
4. Long responses.
5. Short responses.
6. Interruption during assistant speech (barge-in).
7. Stopping a response (cancellation).
8. Microphone permission errors.
9. TTS generation failure.
10. Multiple consecutive conversations (alternating text and voice).
"""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from app.core.controller import ApplicationController
from app.core.error_recovery import ErrorRecoveryCoordinator
from app.core.signals import signals
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.sentence_chunker import SentenceChunker
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.voice_conversation_controller import VoiceConversationController


@pytest.fixture
def mock_controller(qapp_instance):
    """Create a mock ApplicationController with stubbed components for rapid testing."""
    mock_cfg = MagicMock()
    mock_cfg.get.side_effect = lambda key, default=None: {
        "ai.model": "llama3.2:3b",
        "voice.activation_mode": "continuous",
        "voice.mode": "continuous",
        "voice.tts_engine": "sapi5",
        "voice.vad_silence_threshold_ms": 300,
    }.get(key, default)

    controller = ApplicationController(app=qapp_instance, config_manager=mock_cfg)
    controller.ai_service = MagicMock()
    controller.ai_service._is_generating = False
    controller.ai_service.active_conversation_id = "test_conv_id"
    controller.voice_service = MagicMock()
    controller.voice_service.audio_player.is_playing = False
    controller.voice_service.command_dispatcher.dispatch.return_value = False
    controller.voice_service.conversation_controller.echo_suppressor.is_echo.return_value = (False, 0.0)
    
    mock_repo = MagicMock()
    mock_user_msg = MagicMock(id=1, conversation_id="test_conv_id", role="user", content="msg", created_at="2026-11-01", status="completed", _is_duplicate=False)
    mock_asst_msg = MagicMock(id=2, conversation_id="test_conv_id", role="assistant", content="", created_at="2026-11-01", status="streaming")
    mock_repo.add_message.side_effect = lambda cid, role, content, status="": mock_user_msg if role == "user" else mock_asst_msg
    mock_repo.list_conversations.return_value = [MagicMock(id="test_conv_id")]
    controller.conv_repo = mock_repo

    controller.error_recovery = ErrorRecoveryCoordinator(parent=controller)
    return controller


# -----------------------------------------------------------------------------
# 1. Test Normal Text Conversations
# -----------------------------------------------------------------------------

def test_scenario_1_normal_text_conversations(mock_controller):
    """Verify normal text conversation: THINKING -> tokens -> IDLE state transitions."""
    emitted_states = []
    signals.character_state_changed.connect(lambda s: emitted_states.append(s))

    broadcasts = []
    def mock_broadcast(evt, payload):
        broadcasts.append((evt, payload))

    try:
        with patch("app.api.websocket.ws_manager.broadcast_sync", side_effect=mock_broadcast):
            # User submits text -> thinking state
            mock_controller._on_char_state_changed("thinking")
            assert any(e == "app_state" and p["state"] == "THINKING" for e, p in broadcasts)

            # AI streams response chunks
            mock_controller._on_ai_chunk("Hello friend, ")
            mock_controller._on_ai_chunk("how are you doing today?")

            # AI generation completes -> returns to idle
            mock_controller._on_ai_complete("Hello friend, how are you doing today?")
            assert emitted_states[-1] == "idle"

            mock_controller._on_char_state_changed("idle")
            assert any(e == "app_state" and p["state"] == "IDLE" for e, p in broadcasts)
    finally:
        signals.character_state_changed.disconnect()


# -----------------------------------------------------------------------------
# 2. Test Continuous Voice Conversations
# -----------------------------------------------------------------------------

def test_scenario_2_continuous_voice_conversations(mock_controller):
    """Verify continuous voice conversation lifecycle: LISTENING -> TRANSCRIBING -> SPEAKING -> IDLE."""
    emitted_states = []
    signals.character_state_changed.connect(lambda s: emitted_states.append(s))

    try:
        # 1. Speech detected -> listening
        mock_controller._on_speech_detected()
        assert emitted_states[-1] == "listening"

        # 2. Transcription starts -> transcribing
        mock_controller._on_transcription_started()
        assert emitted_states[-1] == "transcribing"

        # 3. Transcription completed -> triggers AI ask
        with patch("app.api.websocket.ws_manager.broadcast_sync"):
            mock_controller._on_voice_transcription_ready("What is the weather?", "en")
            mock_controller.ai_service.ask.assert_called_once()

        # 4. Speaking starts -> speaking
        mock_controller._on_speaking_started()
        assert emitted_states[-1] == "speaking"

        # 5. Speaking finished -> returns to idle (ready to listen again)
        mock_controller._on_speaking_finished()
        assert emitted_states[-1] == "idle"
    finally:
        signals.character_state_changed.disconnect()


# -----------------------------------------------------------------------------
# 3. Test Repeated Conversations
# -----------------------------------------------------------------------------

def test_scenario_3_repeated_conversations(mock_controller):
    """Verify multiple back-to-back conversation turns return to IDLE without lingering state."""
    emitted_states = []
    signals.character_state_changed.connect(lambda s: emitted_states.append(s))

    try:
        with patch("app.api.websocket.ws_manager.broadcast_sync"):
            for turn in range(3):
                # Start turn
                mock_controller._on_char_state_changed("thinking")
                mock_controller._on_ai_chunk(f"Token from turn {turn}")
                mock_controller._on_ai_complete(f"Complete reply for turn {turn}")
                assert emitted_states[-1] == "idle"
    finally:
        signals.character_state_changed.disconnect()


# -----------------------------------------------------------------------------
# 4. Test Long Responses
# -----------------------------------------------------------------------------

def test_scenario_4_long_responses():
    """Verify long multi-sentence responses are cleanly chunked and pipelined."""
    chunker = SentenceChunker(min_chars=10, max_chars=100)
    long_response = (
        "Artificial intelligence is transforming many industries across the world. "
        "It enables faster decision-making across healthcare, science, and education. "
        "Moreover, continuous improvements in edge models allow fully private on-device execution. "
        "In the future, companions will seamlessly support daily workflows."
    )

    chunks = chunker.add_chunk(long_response)
    flushed = chunker.flush()
    all_chunks = chunks + flushed

    assert len(all_chunks) >= 3

    # StreamingAudioQueue test
    mock_player = MagicMock()
    mock_player.is_playing = False
    mock_player.is_in_cooldown.return_value = False

    class MockTTS(BaseTTSEngine):
        def synthesize(self, text: str) -> SynthesizedAudio:
            return SynthesizedAudio(
                samples=np.zeros(1600, dtype=np.float32),
                sample_rate=16000,
                duration_seconds=0.1,
                text=text,
                voice_name="mock",
            )
        def is_available(self) -> bool:
            return True

    queue = StreamingAudioQueue(audio_player=mock_player, tts_engine=MockTTS())
    queue.start_new_turn(turn_id=1)
    queue.enqueue_sentence(all_chunks[0], turn_id=1, is_final=False)
    queue.enqueue_sentence(all_chunks[1], turn_id=1, is_final=False)
    assert not queue.is_empty or queue._next_chunk_index > 0
    queue.clear()
    assert queue.is_empty


# -----------------------------------------------------------------------------
# 5. Test Short Responses
# -----------------------------------------------------------------------------

def test_scenario_5_short_responses():
    """Verify short 1-sentence responses are immediately emitted without buffering delays."""
    chunker = SentenceChunker()
    short_reply = "Paris is the capital of France."
    chunks = chunker.add_chunk(short_reply)
    assert len(chunks) == 1
    assert chunks[0] == "Paris is the capital of France."
    assert chunker.flush() == []


# -----------------------------------------------------------------------------
# 6. Test Interruption During Assistant Speech (Barge-In)
# -----------------------------------------------------------------------------

def test_scenario_6_interruption_during_assistant_speech():
    """Verify barge-in: user speech during assistant playback immediately stops audio and switches state."""
    mic_manager = MagicMock()
    vad_engine = MagicMock()
    whisper_engine = MagicMock()
    audio_player = MagicMock()
    audio_player.is_playing = True
    tts_engine = MagicMock()

    vc = VoiceConversationController(
        mic_manager=mic_manager,
        vad_engine=vad_engine,
        whisper_engine=whisper_engine,
        audio_player=audio_player,
        tts_engine=tts_engine,
    )
    vc._transition_to(ConversationState.SPEAKING)

    # Trigger interruption
    speech_samples = np.ones(3200, dtype=np.float32) * 0.2
    vc._on_interruption_detected(turn_id=vc._turn_id, speech_samples=speech_samples)

    # Audio player must be stopped and state transitions to USER_SPEAKING
    assert audio_player.stop.called
    assert vc.state == ConversationState.USER_SPEAKING


# -----------------------------------------------------------------------------
# 7. Test Stopping a Response (Explicit Cancellation)
# -----------------------------------------------------------------------------

def test_scenario_7_stopping_a_response(mock_controller):
    """Verify explicit cancellation halts generation and returns application to IDLE."""
    emitted = []
    signals.character_state_changed.connect(lambda s: emitted.append(s))

    try:
        with patch("app.api.websocket.ws_manager.broadcast_sync"):
            mock_controller._on_ai_cancelled()
            assert emitted[-1] == "idle"
    finally:
        signals.character_state_changed.disconnect()


# -----------------------------------------------------------------------------
# 8. Test Microphone Permission Errors
# -----------------------------------------------------------------------------

def test_scenario_8_microphone_permission_errors(mock_controller):
    """Verify microphone permission denial generates structured error with settings action."""
    broadcasted_events = []
    with patch("app.api.websocket.ws_manager.broadcast_sync", side_effect=lambda evt, payload: broadcasted_events.append((evt, payload))):
        mock_controller._on_voice_error("Permission denied: Microphone access denied by Windows privacy settings")

    assert len(broadcasted_events) == 1
    evt, data = broadcasted_events[0]
    assert evt == "voice_error"
    assert data["error_type"] == "mic_permission_denied"
    assert data["recovery_action"] == "open_privacy_settings"
    assert "Settings" in data["recovery_label"]


# -----------------------------------------------------------------------------
# 9. Test TTS Generation Failure
# -----------------------------------------------------------------------------

def test_scenario_9_tts_failure(mock_controller):
    """Verify TTS generation failure produces structured warning without application crash."""
    desc = mock_controller.error_recovery.handle_tts_failure("TTS audio synthesis buffer failed")
    assert desc.error_type == "tts_failure"
    assert desc.recovery_action == "fallback_tts"
    assert "Default Voice" in desc.recovery_label


# -----------------------------------------------------------------------------
# 10. Test Multiple Consecutive Conversations
# -----------------------------------------------------------------------------

def test_scenario_10_multiple_consecutive_conversations(mock_controller):
    """Verify alternating 5 turns between Text and Voice modes without collision or state corruption."""
    emitted = []
    signals.character_state_changed.connect(lambda s: emitted.append(s))

    modes = ["text", "voice", "text", "voice", "text"]

    try:
        with patch("app.api.websocket.ws_manager.broadcast_sync"):
            for i, mode in enumerate(modes):
                if mode == "text":
                    mock_controller._on_char_state_changed("thinking")
                    mock_controller._on_ai_chunk(f"Text token {i}")
                    mock_controller._on_ai_complete(f"Text reply {i}")
                    assert emitted[-1] == "idle"
                else:
                    mock_controller._on_speech_detected()
                    assert emitted[-1] == "listening"
                    mock_controller._on_transcription_started()
                    assert emitted[-1] == "transcribing"
                    mock_controller._on_speaking_started()
                    assert emitted[-1] == "speaking"
                    mock_controller._on_speaking_finished()
                    assert emitted[-1] == "idle"
    finally:
        signals.character_state_changed.disconnect()
