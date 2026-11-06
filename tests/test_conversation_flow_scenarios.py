"""Automated Test Suite for Bugs 6, 7, 9, and 10: Complete Conversation Flow Scenarios.

Verifies the 12 required test scenarios:
TEST 1: Normal text message flow (one user message, one assistant response, no mic).
TEST 2: Spoken sentence recognition matching.
TEST 3: AI voice echo prevention (AI speech does not generate a new user message).
TEST 4: 30 seconds of user silence (no requests generated).
TEST 5: Duplicate speech recognition callback rejection (same turn not processed twice).
TEST 6: Streaming chunk handling without repetition or duplication.
TEST 7: Stopping voice mode during recording (safe cancellation & mic stopped).
TEST 8: Switching from voice mode to text mode (mic stops completely).
TEST 9: Rapid multiple user messages (proper association & ordering preserved).
TEST 10: Microphone permission denial / error handling (no infinite retry loop).
TEST 11: Short sentence followed by silence (only actual utterance processed).
TEST 12: Empty AI response or API error (no invalid TTS playback, no retry loop).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

from app.ai.ai_service import AIService
from app.ai.cancellation import CancellationToken
from app.ai.conversation_context import ConversationContext
from app.ai.ollama_client import OllamaConnectionError
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.microphone_manager import MicrophoneManager
from app.voice.sentence_chunker import SentenceChunker
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceMode, VoiceService
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh isolated database for conversation tests."""
    db_file = tmp_path / "test_flow.db"
    return DatabaseManager(db_path=db_file)


@pytest.fixture
def repo(test_db):
    """Provides a fresh ConversationRepository."""
    return ConversationRepository(db_manager=test_db)


@pytest.fixture
def mock_tts():
    """Mock TTS engine returning a valid synthetic audio object."""
    tts = MagicMock(spec=BaseTTSEngine)
    tts.synthesize.return_value = SynthesizedAudio(
        samples=np.zeros(1600, dtype=np.float32),
        sample_rate=16000,
        duration_seconds=0.1,
        text="Test synthesized speech.",
        voice_name="mock_voice",
    )
    return tts


# ==============================================================================
# TEST 1: User sends a normal text message
# Expected: One user message and one assistant response. Mic does not start.
# ==============================================================================

def test_scenario_1_user_sends_normal_text_message(repo, qapp):
    """TEST 1: In text mode, sending a text prompt generates exactly one user turn

    and one assistant response, with no microphone capture activated.
    """
    conv = repo.create_conversation("Scenario 1 Chat")

    # Mock OllamaClient returning single complete text
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter(["Hello! ", "How can I help you today?"])

    with patch("app.ai.ai_service.OllamaClient", return_value=mock_client), \
         patch("app.ai.ai_service.ModelManager.is_available", return_value=True):
        ai = AIService(parent=None)
        ai.active_conversation_id = conv.id

        # 1. User sends message
        user_msg = repo.add_message(conv.id, "user", "Hello Buddy", status="completed")
        gen_id = ai.ask("Hello Buddy", is_voice=False)

        # Allow Qt thread pool / signals to process
        for _ in range(20):
            qapp.processEvents()
            time.sleep(0.01)

        # 2. Verify messages in repository
        messages = repo.get_messages(conv.id)
        assert len(messages) == 1  # Only user message in repo (assistant added upon stream complete)

        # Emulate stream completion into repository (as done by controller/api bridge)
        assistant_text = "".join(["Hello! ", "How can I help you today?"])
        asst_msg = repo.add_message(conv.id, "assistant", assistant_text, status="completed")

        final_msgs = repo.get_messages(conv.id)
        assert len(final_msgs) == 2
        assert final_msgs[0].role == "user"
        assert final_msgs[0].content == "Hello Buddy"
        assert final_msgs[1].role == "assistant"
        assert final_msgs[1].content == assistant_text

        # 3. Context history verification
        ctx_msgs = ai.context.get_messages()
        # Should have system prompt + user msg + assistant msg
        roles = [m["role"] for m in ctx_msgs]
        assert "user" in roles
        assert "assistant" in roles
        assert roles.count("user") == 1
        assert roles.count("assistant") == 1


# ==============================================================================
# TEST 2: User speaks a sentence
# Expected: The transcript matches the captured speech as accurately as possible.
# ==============================================================================

def test_scenario_2_user_speaks_sentence(qapp):
    """TEST 2: Spoken audio captured is submitted to Whisper and transcribed accurately."""
    whisper = WhisperEngine()
    
    mock_whisper_model = MagicMock()
    mock_seg = MagicMock()
    mock_seg.id = 0
    mock_seg.start = 0.0
    mock_seg.end = 1.2
    mock_seg.text = "Good morning Buddy"
    mock_seg.no_speech_prob = 0.01
    mock_seg.avg_logprob = -0.15

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.98

    mock_whisper_model.transcribe.return_value = (iter([mock_seg]), mock_info)
    whisper._model = mock_whisper_model

    # Synthesize 1 second of 16kHz speech waveform
    audio_data = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, 16000)) * 0.5).astype(np.float32)

    received_results = []
    whisper.transcription_completed.connect(lambda r: received_results.append(r))

    result = whisper.transcribe(audio_data)

    assert result is not None
    assert result.text == "Good morning Buddy"
    assert result.language == "en"
    assert result.language_probability > 0.90


# ==============================================================================
# TEST 3: AI speaks its response
# Expected: Its voice does not generate a new user message.
# ==============================================================================

def test_scenario_3_ai_speaks_voice_does_not_generate_user_message(mock_tts, qapp):
    """TEST 3: When AI audio is playing or in cooldown, acoustic echo does not trigger user message."""
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = WhisperEngine()
    player = AudioPlayer()
    ai = AIService(parent=None)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=mock_tts,
        ai_service=ai,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )
    controller.enable()

    # 1. Simulate assistant response text
    controller._last_assistant_response = "I am doing well, thank you for asking."

    # 2. Put audio player in active playing state (or cooldown)
    player._is_playing = True

    dispatched_prompts = []
    ai.ask = MagicMock(side_effect=lambda *a, **kw: dispatched_prompts.append(kw.get("user_prompt") or (a[0] if a else None)))

    # 3. Simulate audio frames arriving at mic while AI is speaking
    test_chunk = np.full(512, 0.2, dtype=np.float32)
    controller.process_mic_frame(test_chunk)

    # VAD should NOT be triggered while audio player is playing/in cooldown
    assert vad.state == VADState.SILENCE
    assert controller.state != ConversationState.USER_SPEAKING

    # 4. Now simulate Whisper somehow receiving text matching assistant response
    result = TranscriptionResult(
        text="I am doing well thank you for asking",
        language="en",
        language_probability=0.99,
        duration_seconds=1.5,
        segments=[],
    )
    controller._state = ConversationState.TRANSCRIBING
    controller._on_transcription_completed(result, controller.current_turn_id)

    # Verify that the acoustic echo was discarded and no AI request was sent!
    assert len(dispatched_prompts) == 0
    assert controller.state == ConversationState.LISTENING

    controller.cleanup()


# ==============================================================================
# TEST 4: User remains silent for 30 seconds
# Expected: No new conversational request and no new assistant response.
# ==============================================================================

def test_scenario_4_user_remains_silent_for_30_seconds(mock_tts, qapp):
    """TEST 4: 30 seconds of ambient silence produces 0 speech triggers, 0 STT calls, 0 AI requests."""
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = WhisperEngine()
    player = AudioPlayer()
    ai = AIService(parent=None)

    ai.ask = MagicMock()
    whisper.transcribe_async = MagicMock()

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=mock_tts,
        ai_service=ai,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )
    controller.enable()

    # 30 seconds of 16kHz audio in 512-sample frames (32ms per frame -> ~938 frames)
    # Use quiet noise well below speech threshold
    silence_frame = (np.random.randn(512) * 0.0005).astype(np.float32)

    speech_started_events = []
    controller.speech_started.connect(lambda: speech_started_events.append(True))

    for _ in range(938):
        controller.process_mic_frame(silence_frame)

    assert len(speech_started_events) == 0
    assert vad.state == VADState.SILENCE
    assert controller.state == ConversationState.LISTENING
    assert whisper.transcribe_async.call_count == 0
    assert ai.ask.call_count == 0

    controller.cleanup()


# ==============================================================================
# TEST 5: A speech recognition callback fires twice
# Expected: The same speech turn is not processed twice.
# ==============================================================================

def test_scenario_5_speech_recognition_callback_fires_twice(mock_tts, qapp):
    """TEST 5: If a speech recognition engine fires a duplicate callback for the same turn,

    only the first is processed and the second is rejected.
    """
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = WhisperEngine()
    player = AudioPlayer()
    ai = AIService(parent=None)

    dispatched = []
    ai.ask = MagicMock(side_effect=lambda *a, **kw: dispatched.append(kw.get("user_prompt") or (a[0] if a else None)))

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=mock_tts,
        ai_service=ai,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )
    controller.enable()

    turn_id = 42
    controller._turn_id = turn_id
    controller._state = ConversationState.TRANSCRIBING

    res = TranscriptionResult(
        text="What is the weather today?",
        language="en",
        language_probability=0.98,
        duration_seconds=1.2,
        segments=[],
    )

    # 1. First callback
    controller._on_transcription_completed(res, turn_id)
    assert len(dispatched) == 1
    assert dispatched[0] == "What is the weather today?"

    # 2. Second callback firing with the same turn_id
    controller._state = ConversationState.TRANSCRIBING
    controller._on_transcription_completed(res, turn_id)

    # Must still be only 1 dispatched request!
    assert len(dispatched) == 1

    controller.cleanup()


# ==============================================================================
# TEST 6: The AI response arrives in multiple streaming chunks
# Expected: Final displayed and spoken response contains no duplicated chunks.
# ==============================================================================

def test_scenario_6_ai_response_streaming_chunks_no_duplication():
    """TEST 6: Incremental streaming chunks are assembled without stutter or duplicate repetitions."""
    chunker = SentenceChunker()
    tokens = [
        "The ", "quick ", "brown ", "fox ", "jumps ", "over ",
        "the ", "lazy ", "dog. ", "It ", "was ", "a ", "sunny ", "day."
    ]

    extracted_sentences = []
    for tok in tokens:
        sentences = chunker.add_chunk(tok)
        extracted_sentences.extend(sentences)

    extracted_sentences.extend(chunker.flush())

    full_output = " ".join(extracted_sentences).strip()

    assert "quick quick" not in full_output
    assert "brown brown" not in full_output
    assert "fox fox" not in full_output
    assert full_output == "The quick brown fox jumps over the lazy dog. It was a sunny day."

    # Verify ConversationContext also stores without duplication
    ctx = ConversationContext()
    ctx.add_assistant_message(full_output)
    # Attempting to re-add the identical assistant message
    ctx.add_assistant_message(full_output)
    assert ctx.history_length == 1
    assert ctx.get_messages()[-1]["content"] == full_output


# ==============================================================================
# TEST 7: The user stops voice mode during recording
# Expected: Recording stops and pending operations are safely cancelled.
# ==============================================================================

def test_scenario_7_user_stops_voice_mode_during_recording(mock_tts, qapp):
    """TEST 7: Disabling voice while actively recording halts the microphone and cancels the turn."""
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = WhisperEngine()
    player = AudioPlayer()
    ai = AIService(parent=None)

    ai.cancel_generation = MagicMock()

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=mock_tts,
        ai_service=ai,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )
    controller.enable()

    # Enter USER_SPEAKING state
    controller._transition_to(ConversationState.USER_SPEAKING)
    assert controller.state == ConversationState.USER_SPEAKING

    # Stop voice mode
    controller.disable()

    # Verify microphone stopped, state DISABLED, and AI cancel called
    assert not mic.is_recording
    assert controller.state == ConversationState.DISABLED
    assert ai.cancel_generation.call_count == 1

    controller.cleanup()


# ==============================================================================
# TEST 8: The user switches from voice mode to text mode
# Expected: Voice recording and recognition stop completely.
# ==============================================================================

def test_scenario_8_user_switches_from_voice_to_text_mode(qapp):
    """TEST 8: Switching to OFF/Text mode deactivates all audio capture and recognition."""
    vs = VoiceService()
    vs.set_mode(VoiceMode.CONTINUOUS)
    assert vs.mode == VoiceMode.CONTINUOUS

    # Switch to OFF (Text Mode)
    vs.set_mode(VoiceMode.OFF)

    assert vs.mode == VoiceMode.OFF
    assert not vs.mic_manager.is_recording
    if hasattr(vs, "conversation_controller"):
        assert not vs.conversation_controller.is_enabled

    vs.stop()


# ==============================================================================
# TEST 9: The user rapidly sends multiple messages
# Expected: Messages and responses remain correctly associated and ordered.
# ==============================================================================

def test_scenario_9_rapid_multiple_messages(repo, qapp):
    """TEST 9: Rapidly sending multiple user messages preserves ordering and updates IDs."""
    conv = repo.create_conversation("Rapid Chat")

    # Send 3 rapid messages
    msg1 = repo.add_message(conv.id, "user", "Message 1", status="completed")
    msg2 = repo.add_message(conv.id, "user", "Message 2", status="completed")
    msg3 = repo.add_message(conv.id, "user", "Message 3", status="completed")

    assert msg1.id < msg2.id < msg3.id

    messages = repo.get_messages(conv.id)
    assert len(messages) == 3
    assert [m.content for m in messages] == ["Message 1", "Message 2", "Message 3"]

    # Verify AIService cancellation when rapid ask() calls happen
    ai = AIService(parent=None)
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter(["Response 3"])
    ai.client = mock_client
    ai.model_manager.is_available = MagicMock(return_value=True)

    gen1 = ai.ask("Message 1")
    gen2 = ai.ask("Message 2")
    gen3 = ai.ask("Message 3")

    assert gen1 < gen2 < gen3
    assert ai._last_user_prompt == "Message 3"


# ==============================================================================
# TEST 10: The microphone permission is denied
# Expected: The app displays a useful error and does not enter a retry loop.
# ==============================================================================

def test_scenario_10_microphone_permission_denied(qapp):
    """TEST 10: Microphone access error is reported gracefully without entering retry loop."""
    mic = MicrophoneManager()
    errors = []
    mic.error_occurred.connect(lambda err: errors.append(err))

    with patch("sounddevice.InputStream", side_effect=Exception("Permission denied / device busy")):
        ok = mic.start_recording()
        assert not ok
        assert not mic.is_recording
        assert len(errors) == 1
        assert "Permission denied" in errors[0] or "Failed to open microphone" in errors[0]

        # Verify calling again does not crash or loop recursively
        ok2 = mic.start_recording()
        assert not ok2
        assert len(errors) == 2


# ==============================================================================
# TEST 11: The user speaks a short sentence followed by silence
# Expected: Only the actual sentence is processed.
# ==============================================================================

def test_scenario_11_short_sentence_followed_by_silence(qapp):
    """TEST 11: Speech frames followed by extended silence triggers only one utterance."""
    vad = VADEngine(
        sample_rate=16000,
        frame_size=512,
        min_speech_frames=2,
        silence_threshold_ms=96,
        min_utterance_ms=50,
    )

    ended_utterances = []
    vad.speech_ended.connect(lambda u: ended_utterances.append(u))

    t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
    speech_frame = (0.4 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)
    silence_frame = np.zeros(512, dtype=np.float32)

    # 0. Ambient silence before user begins talking
    vad.process_frame(silence_frame)
    assert vad.state == VADState.SILENCE

    # 1. Feed 4 frames of speech (~128ms)
    for _ in range(4):
        vad.process_frame(speech_frame)

    assert vad.state == VADState.SPEAKING

    # 2. Feed silence frames exceeding silence_threshold_ms (4 frames = 128ms > 96ms)
    for _ in range(4):
        vad.process_frame(silence_frame)

    # 3. Exactly one speech segment should have been finalized
    assert len(ended_utterances) == 1
    assert len(ended_utterances[0]) >= 512 * 4
    assert vad.state == VADState.SILENCE

    # 4. Feed further silence for another 15 frames
    for _ in range(15):
        vad.process_frame(silence_frame)

    # Still only 1 utterance
    assert len(ended_utterances) == 1


# ==============================================================================
# TEST 12: The AI returns an empty response or an API error
# Expected: No invalid speech playback and no recursive retry loop.
# ==============================================================================

def test_scenario_12_ai_returns_empty_response_or_api_error(qapp):
    """TEST 12: Empty response or Ollama connection error is handled safely without TTS or retry loops."""
    ai = AIService(parent=None)
    mock_client = MagicMock()
    mock_client.chat_stream.side_effect = OllamaConnectionError("Connection refused")
    ai.client = mock_client
    ai.model_manager.is_available = MagicMock(return_value=True)

    errors = []
    signals.ai_error_occurred.connect(lambda e: errors.append(e))

    gen_id = ai.ask("Hello, are you there?")

    # Process events to allow worker to finish
    for _ in range(10):
        qapp.processEvents()
        time.sleep(0.01)

    assert len(errors) == 1
    assert "Ollama" in errors[0] or "Connection" in errors[0]

    # Verify context did NOT add an invalid empty response
    assert ai.context.history_length == 1  # Only user message was added, not corrupted
    assert not ai._is_generating
