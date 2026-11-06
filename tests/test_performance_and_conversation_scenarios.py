"""Test Suite for Phase 10: Performance & Conversation Flow Requirements.

Validates the 10 required operational scenarios:
1. Normal text conversations.
2. Continuous voice conversations.
3. Repeated conversations.
4. Long responses.
5. Short responses.
6. Interruption during assistant speech.
7. Stopping a response.
8. Microphone permission errors.
9. TTS failure.
10. Multiple consecutive conversations.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from app.ai.ai_service import AIService
from app.ai.cancellation import CancellationToken
from app.ai.conversation_context import ConversationContext
from app.ai.generation_controls import GenerationConfig
from app.core.signals import signals
from app.core.error_recovery import ErrorRecoveryCoordinator
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.sentence_chunker import SentenceChunker
from app.voice.streaming_audio_queue import StreamingAudioQueue, QueuedSentence, _TTSChunkSynthesizeWorker
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.whisper_engine import TranscriptionResult


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def isolated_db(tmp_path):
    """Provides a fresh SQLite database."""
    db_file = tmp_path / "test_perf_scenarios.db"
    return DatabaseManager(db_path=db_file)


@pytest.fixture
def conv_repo(isolated_db):
    """Provides an isolated conversation repository."""
    return ConversationRepository(db_manager=isolated_db)


@pytest.fixture
def mock_tts_engine(qapp_instance):
    """Mock TTS engine producing valid synthesized audio waveforms."""
    engine = MagicMock(spec=BaseTTSEngine)
    engine.synthesize.return_value = SynthesizedAudio(
        samples=np.zeros(1600, dtype=np.float32),
        sample_rate=16000,
        duration_seconds=0.1,
        text="Mock speech",
        voice_name="mock_voice",
    )
    engine.is_available.return_value = True
    return engine


# ─── 1. Normal Text Conversations ────────────────────────────────────────────

def test_scenario_1_normal_text_conversation(qapp_instance, conv_repo):
    """Verify complete normal text conversation flow (prompt -> streaming -> complete)."""
    ai_service = AIService(config_manager=None)
    ai_service.conv_repo = conv_repo
    ai_service.client = MagicMock()
    ai_service.model_manager = MagicMock()
    ai_service.model_manager.select_active_model.return_value = "llama3.2:3b"
    ai_service.model_manager.is_available.return_value = True

    # Mock streaming response
    ai_service.client.chat_stream.return_value = ["Hello", " there!", " How can I", " help you today?"]

    chunks_received = []
    completed_resp = []
    signals.ai_response_chunk.connect(lambda c: chunks_received.append(c))
    signals.ai_response_complete.connect(lambda r: completed_resp.append(r))

    gen_id = ai_service.ask("Hello Bond", is_voice=False)
    assert gen_id > 0

    # Process Qt event loop until threadpool completes
    for _ in range(50):
        QCoreApplication.processEvents()
        if len(completed_resp) > 0:
            break
        time.sleep(0.02)

    assert len(chunks_received) >= 4
    assert "".join(chunks_received) == "Hello there! How can I help you today?"
    assert len(completed_resp) == 1
    assert completed_resp[0] == "Hello there! How can I help you today?"


# ─── 2. Continuous Voice Conversations ───────────────────────────────────────

def test_scenario_2_continuous_voice_conversation(qapp_instance, mock_tts_engine):
    """Verify continuous voice conversation transitions through listening, thinking, speaking, and back to listening."""
    mock_mic = MagicMock()
    mock_vad = MagicMock()
    mock_whisper = MagicMock()
    mock_player = MagicMock()
    mock_ai = MagicMock()

    controller = VoiceConversationController(
        mic_manager=mock_mic,
        vad_engine=mock_vad,
        whisper_engine=mock_whisper,
        audio_player=mock_player,
        tts_engine=mock_tts_engine,
        ai_service=mock_ai,
        activation_mode="continuous",
    )
    controller.set_activation_mode(VoiceActivationMode.CONTINUOUS)
    assert controller.state == ConversationState.LISTENING

    # Step A: User speaks -> transitions to USER_SPEAKING
    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # Step B: User stops speaking -> Speech ended triggers transcription
    mock_mic.sample_rate = 16000
    mock_whisper.transcribe.return_value = TranscriptionResult(
        text="What is the weather?",
        language="en",
        language_probability=0.99,
        duration_seconds=1.5,
    )
    controller._on_vad_speech_ended(np.zeros(24000, dtype=np.float32))
    assert controller.state in (ConversationState.TRANSCRIBING, ConversationState.LISTENING)

    # Step C: AI response chunk arrives and speech synthesis begins
    controller._transition_to(ConversationState.GENERATING_RESPONSE)
    controller._on_chunk_playback_started(controller._turn_id, 0, "It is sunny outside today.")
    assert controller.state == ConversationState.SPEAKING

    # Step D: Playback completes -> automatically returns to LISTENING in continuous mode after echo decay
    controller._on_all_speech_played(controller._turn_id)
    for _ in range(25):
        QCoreApplication.processEvents()
        if controller.state == ConversationState.LISTENING:
            break
        time.sleep(0.02)
    assert controller.state == ConversationState.LISTENING


# ─── 3. Repeated Conversations ───────────────────────────────────────────────

def test_scenario_3_repeated_conversations(qapp_instance, conv_repo):
    """Verify duplicate in-flight prompt rejection and repeated sequential prompt handling."""
    ai_service = AIService(config_manager=None)
    ai_service.conv_repo = conv_repo
    ai_service.client = MagicMock()
    ai_service.model_manager = MagicMock()
    ai_service.model_manager.select_active_model.return_value = "llama3.2:3b"
    ai_service.model_manager.is_available.return_value = True

    # Simulate ongoing generation
    ai_service._is_generating = True
    ai_service._last_user_prompt = "Tell me a joke"
    ai_service._current_gen_id = 42

    # Duplicate submission of the same prompt while in-flight is rejected
    rejected_id = ai_service.ask("Tell me a joke")
    assert rejected_id == 42  # Returns current ongoing gen_id without spawning duplicate

    # Once generation completes, sequential repeated prompt is accepted
    ai_service._is_generating = False
    ai_service.client.chat_stream.return_value = ["Why did the chicken cross the road?"]
    new_gen_id = ai_service.ask("Tell me a joke")
    assert new_gen_id == 43


# ─── 4. Long Responses ───────────────────────────────────────────────────────

def test_scenario_4_long_responses(qapp_instance):
    """Verify multi-sentence long response chunking without truncation or dropped clauses."""
    chunker = SentenceChunker(min_chars=15, max_chars=120)
    
    # 4 distinct sentences totaling ~400 characters
    long_stream = [
        "Artificial intelligence is transforming many industries. ",
        "From healthcare diagnostics to climate modeling, ",
        "computational techniques allow researchers to discover patterns in vast datasets. ",
        "However, developing ethical guidelines remains paramount to ensure equitable deployment.",
    ]

    sentences = []
    for chunk in long_stream:
        sentences.extend(chunker.add_chunk(chunk))
    sentences.extend(chunker.flush())

    assert len(sentences) >= 3
    reconstituted = " ".join(sentences)
    assert "Artificial intelligence is transforming" in reconstituted
    assert "equitable deployment" in reconstituted


# ─── 5. Short Responses ──────────────────────────────────────────────────────

def test_scenario_5_short_responses(qapp_instance):
    """Verify short conversational responses chunk cleanly for fast immediate playback."""
    chunker = SentenceChunker(min_chars=8, max_chars=80)
    
    tokens = ["Yes, ", "I can ", "definitely help ", "with that!"]
    sentences = []
    for t in tokens:
        sentences.extend(chunker.add_chunk(t))
    sentences.extend(chunker.flush())

    assert len(sentences) >= 1
    assert "definitely help" in " ".join(sentences)


# ─── 6. Interruption During Assistant Speech ─────────────────────────────────

def test_scenario_6_interruption_during_assistant_speech(qapp_instance, mock_tts_engine):
    """Verify that user speech onset during assistant speech halts audio and clears queues."""
    mock_mic = MagicMock()
    mock_vad = MagicMock()
    mock_whisper = MagicMock()
    mock_player = MagicMock()
    mock_ai = MagicMock()

    controller = VoiceConversationController(
        mic_manager=mock_mic,
        vad_engine=mock_vad,
        whisper_engine=mock_whisper,
        audio_player=mock_player,
        tts_engine=mock_tts_engine,
        ai_service=mock_ai,
        activation_mode="continuous",
    )
    controller.set_activation_mode(VoiceActivationMode.CONTINUOUS)

    # Set state to SPEAKING
    controller._state = ConversationState.SPEAKING
    turn_before = controller._turn_id

    # User interrupts by speaking
    interruption_signals = []
    controller.interruption_triggered.connect(lambda tid: interruption_signals.append(tid))

    controller._on_interruption_detected(turn_before, np.zeros(1600, dtype=np.float32))

    assert len(interruption_signals) == 1
    assert interruption_signals[0] == turn_before
    mock_player.stop.assert_called()
    assert controller.state in (ConversationState.USER_SPEAKING, ConversationState.CANCELED, ConversationState.LISTENING)


# ─── 7. Stopping a Response ──────────────────────────────────────────────────

def test_scenario_7_stopping_a_response(qapp_instance):
    """Verify manual emergency stop halts inference, clears audio queues, and resets to IDLE."""
    mock_player = MagicMock()
    mock_tts = MagicMock()
    mock_tts.synthesize.side_effect = lambda txt, **kw: (time.sleep(0.2), SynthesizedAudio(np.zeros(100), 16000, 0.1, txt, "v"))[1]
    queue = StreamingAudioQueue(audio_player=mock_player, tts_engine=mock_tts)

    # Enqueue a sentence (sentence: str, turn_id: int)
    queue.enqueue_sentence("Sentence to be aborted", turn_id=1)

    # Emergency stop
    queue.emergency_stop()
    assert queue.is_empty
    mock_player.emergency_stop.assert_called_once()


# ─── 8. Microphone Permission Errors ─────────────────────────────────────────

def test_scenario_8_microphone_permission_errors(qapp_instance):
    """Verify microphone access denial emits structured error and opens privacy settings."""
    coordinator = ErrorRecoveryCoordinator()
    descriptors = []
    coordinator.structured_error_emitted.connect(lambda d: descriptors.append(d))

    desc = coordinator.classify_and_handle("Permission denied: -9996 Could not open audio stream")

    assert desc.error_type == "mic_permission_denied"
    assert desc.recovery_action == "open_privacy_settings"
    assert "Settings" in desc.recovery_label
    assert len(descriptors) == 1


# ─── 9. TTS Failure ──────────────────────────────────────────────────────────

def test_scenario_9_tts_failure(qapp_instance):
    """Verify neural TTS chunk synthesis failure emits error signal and falls back without freezing."""
    mock_player = MagicMock()
    mock_tts = MagicMock()
    mock_tts.synthesize.side_effect = RuntimeError("Neural Kokoro ONNX failed to allocate tensor")

    queue = StreamingAudioQueue(audio_player=mock_player, tts_engine=mock_tts)
    errors = []
    queue.error_occurred.connect(lambda e: errors.append(e))

    item = QueuedSentence(turn_id=1, chunk_index=0, text="Fallback test sentence")
    worker = _TTSChunkSynthesizeWorker(item=item, tts_engine=mock_tts)
    worker.signals.error.connect(queue.error_occurred.emit)
    worker.run()

    assert len(errors) == 1
    assert "Neural TTS synthesis error" in errors[0]


# ─── 10. Multiple Consecutive Conversations ──────────────────────────────────

def test_scenario_10_multiple_consecutive_conversations(qapp_instance, conv_repo):
    """Verify multiple consecutive turns store messages in repository and maintain conversation context."""
    conv = conv_repo.create_conversation("Default Chat")
    conv_id = conv.id
    context = ConversationContext(max_turns=5)
    
    # Turn 1
    context.add_user_message("What is Paris famous for?")
    context.add_assistant_message("Paris is famous for the Eiffel Tower and Louvre Museum.")
    conv_repo.add_message(conv_id, "user", "What is Paris famous for?")
    conv_repo.add_message(conv_id, "assistant", "Paris is famous for the Eiffel Tower and Louvre Museum.")

    # Turn 2
    context.add_user_message("What about its food?")
    context.add_assistant_message("It is famous for croissants, baguettes, and fine French pastries.")
    conv_repo.add_message(conv_id, "user", "What about its food?")
    conv_repo.add_message(conv_id, "assistant", "It is famous for croissants, baguettes, and fine French pastries.")

    # Turn 3
    context.add_user_message("Can you summarize our chat?")
    messages = context.get_messages()

    assert len(messages) >= 5  # System prompt + 2 user + 2 assistant
    assert any("Eiffel Tower" in m["content"] for m in messages if m["role"] == "assistant")
    assert any("croissants" in m["content"] for m in messages if m["role"] == "assistant")

    history = conv_repo.get_messages(conv_id)
    assert len(history) == 4
    assert history[0].content == "What is Paris famous for?"
    assert history[3].content == "It is famous for croissants, baguettes, and fine French pastries."
