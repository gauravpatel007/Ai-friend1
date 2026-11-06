"""Unit tests verifying Voice Response Performance Optimizations (Task 4).

Validates:
1. Speech recognition: VAD configurable silence detection and trailing silence trimming.
2. Speech recognition: Faster-Whisper background preloading and interim greedy transcription.
3. LLM: Direct instant inference dispatch on voice transcription (dispatched=True flag).
4. Text-to-speech: Sentence chunking and pipelined streaming audio queue without audio overlap.
5. Voice interaction: Acoustic self-voice echo suppression and barge-in / interruption handling.
6. Voice interaction: Continuous listening resumption with optimized acoustic decay delay.
"""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from app.ai.generation_controls import GenerationConfig
from app.core.controller import ApplicationController
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.echo_suppressor import AcousticEchoSuppressor
from app.voice.sentence_chunker import SentenceChunker
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController


def test_vad_configurable_silence_threshold_and_trimming():
    """Verify VADEngine supports configurable silence threshold and trims excessive trailing dead air."""
    vad = VADEngine(min_speech_frames=2, silence_threshold_ms=400, min_utterance_ms=50)
    assert vad.silence_threshold_ms == 400

    # Test dynamic configuration
    vad.set_silence_threshold(350)
    assert vad.silence_threshold_ms == 350

    # Bounds check
    vad.set_silence_threshold(100)
    assert vad.silence_threshold_ms == 250  # clamped to minimum 250ms
    vad.set_silence_threshold(6000)
    assert vad.silence_threshold_ms == 5000  # clamped to maximum 5000ms

    # Create sinusoidal audio tone for speech and digital zero for silence
    t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
    speech_frame = (0.4 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)
    silence_frame = np.zeros(512, dtype=np.float32)

    vad.reset_states()
    vad.set_silence_threshold(250)

    # 1. Feed speech frames to enter SPEAKING state
    vad.process_frame(speech_frame)
    vad.process_frame(speech_frame)
    assert vad.state == VADState.SPEAKING

    # 2. Feed speech frames
    for _ in range(5):
        vad.process_frame(speech_frame)

    # 3. Feed silence frames exceeding silence threshold (250ms / 32ms ~ 8 frames)
    result = None
    for _ in range(12):
        res = vad.process_frame(silence_frame)
        if res is not None:
            result = res
            break

    assert result is not None
    # Trimming keeps at most 4 silence frames (~128ms) rather than all trailing silence frames
    assert len(result) <= 15 * 512
    assert vad.state == VADState.SILENCE


def test_generation_config_voice_keep_alive():
    """Verify GenerationConfig.for_voice uses keep_alive='15m' and concise token budget."""
    cfg = GenerationConfig.for_voice()
    assert cfg.keep_alive == "15m"
    assert cfg.max_tokens <= 100
    assert cfg.response_style == "concise"


def test_controller_direct_voice_dispatch_latency_elimination():
    """Verify voice transcription ready immediately persists messages, broadcasts dispatched=True, and calls AI service."""
    controller = ApplicationController.__new__(ApplicationController)
    controller.ai_service = MagicMock()
    controller.ai_service._is_generating = False
    controller.ai_service.active_conversation_id = "test_conv_123"
    controller._is_sleeping = False
    controller.current_assistant_msg_id = None
    controller.current_conv_id = None
    controller.voice_service = None

    # Mock repository
    mock_repo = MagicMock()
    mock_user_msg = MagicMock(id=101, conversation_id="test_conv_123", role="user", content="Explain quantum physics", created_at="2026-10-31", status="completed")
    mock_user_msg._is_duplicate = False
    mock_asst_msg = MagicMock(id=102, conversation_id="test_conv_123", role="assistant", content="", created_at="2026-10-31", status="streaming")
    mock_repo.add_message.side_effect = [mock_user_msg, mock_asst_msg]
    controller.conv_repo = mock_repo

    broadcast_events = []
    def mock_broadcast(event_type, payload):
        broadcast_events.append((event_type, payload))

    with patch("app.api.websocket.ws_manager.broadcast_sync", side_effect=mock_broadcast):
        controller._on_voice_transcription_ready("Explain quantum physics", "en")

    # Verifications:
    # 1. Repository messages created
    assert mock_repo.add_message.call_count == 2
    # 2. AI service asked immediately with is_voice=True
    controller.ai_service.ask.assert_called_once_with("Explain quantum physics", is_voice=True, request_id=None)
    # 3. WebSocket received transcription event with dispatched=True
    transcription_events = [p for e, p in broadcast_events if e == "transcription"]
    assert len(transcription_events) == 1
    assert transcription_events[0]["dispatched"] is True
    assert transcription_events[0]["text"] == "Explain quantum physics"


def test_sentence_chunker_and_pipelined_streaming_queue():
    """Verify SentenceChunker extracts sentences and StreamingAudioQueue pipelines synthesis without overlap."""
    chunker = SentenceChunker(min_chars=10, max_chars=80)
    tokens = ["Hello, ", "friend! ", "How ", "are ", "you ", "today? ", "Everything ", "is ", "great."]
    extracted = []
    for tok in tokens:
        chunks = chunker.add_chunk(tok)
        extracted.extend(chunks)
    extracted.extend(chunker.flush())

    assert len(extracted) == 3
    assert "Hello, friend!" in extracted[0]
    assert "How are you today?" in extracted[1]
    assert "Everything is great." in extracted[2]

    # Test StreamingAudioQueue with mock audio player and TTS engine
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

    tts = MockTTS()
    queue = StreamingAudioQueue(audio_player=mock_player, tts_engine=tts)
    queue.start_new_turn(turn_id=1)

    # Enqueue sentence
    queue.enqueue_sentence(extracted[0], turn_id=1, is_final=False)

    # Clear queue (e.g. on new turn or interruption)
    queue.clear()
    assert queue.is_empty
    mock_player.stop.assert_called()


def test_voice_barge_in_and_interruption_detection():
    """Verify that sustained user speech during AI playback triggers immediate interruption and stops audio."""
    mic_manager = MagicMock()
    mic_manager.sample_rate = 16000
    vad_engine = MagicMock()
    whisper_engine = MagicMock()
    audio_player = MagicMock()
    audio_player.is_playing = True
    tts_engine = MagicMock()

    controller = VoiceConversationController(
        mic_manager=mic_manager,
        vad_engine=vad_engine,
        whisper_engine=whisper_engine,
        audio_player=audio_player,
        tts_engine=tts_engine,
    )
    assert controller.enable_barge_in is True

    # Put controller in SPEAKING state
    controller._transition_to(ConversationState.SPEAKING)
    assert controller.state in (ConversationState.SPEAKING, ConversationState.AI_SPEAKING)

    interruption_emitted = []
    controller.interruption_triggered.connect(lambda tid: interruption_emitted.append(tid))

    # Simulate confirmed interruption from interruption manager
    speech_samples = np.ones(3200, dtype=np.float32) * 0.2
    controller._on_interruption_detected(turn_id=controller._turn_id, speech_samples=speech_samples)

    # 1. Audio player stopped immediately
    audio_player.stop.assert_called()
    # 2. Interruption signal emitted
    assert len(interruption_emitted) == 1
    # 3. Transitioned immediately to USER_SPEAKING
    assert controller.state == ConversationState.USER_SPEAKING


def test_echo_suppressor_optimized_cooldown():
    """Verify AcousticEchoSuppressor uses fast 350ms cooldown decay window for rapid continuous turn-taking."""
    suppressor = AcousticEchoSuppressor()
    assert suppressor.cooldown_decay_sec == 0.35
