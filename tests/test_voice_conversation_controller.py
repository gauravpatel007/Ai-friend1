"""Tests for VoiceConversationController, SentenceChunker, StreamingAudioQueue, and Latency Tracking (Phase 8)."""

import numpy as np
import pytest
from PySide6.QtCore import QObject

from app.character.states import CharacterState
from app.core.signals import signals
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationLatencyMetrics, ConversationState
from app.voice.microphone_manager import MicrophoneManager
from app.voice.sentence_chunker import SentenceChunker
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


class MockTTSEngine(BaseTTSEngine):
    """Fast in-memory mock TTS for pipelined audio queue tests."""

    def __init__(self, sample_rate: int = 22050, duration: float = 0.05) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.duration = duration
        self.synthesized_texts: list[str] = []

    def load_model(self, voice_name=None) -> bool:
        self._is_loaded = True
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        self.synthesized_texts.append(text)
        samples = np.ones(int(self.sample_rate * self.duration), dtype=np.float32) * 0.05
        return SynthesizedAudio(
            samples=samples,
            sample_rate=self.sample_rate,
            duration_seconds=self.duration,
            text=text,
            voice_name="mock_voice",
        )

    def stop(self) -> None:
        pass

    def unload_model(self) -> None:
        self._is_loaded = False

    def get_available_voices(self) -> list[str]:
        return ["mock_voice"]


class MockWhisperEngine(WhisperEngine):
    """Mock Whisper engine with instantaneous transcription."""

    def __init__(self, text: str = "Hello Buddy!", lang: str = "en") -> None:
        super().__init__()
        self.text = text
        self.lang = lang

    def transcribe_async(self, audio_data: np.ndarray, callback=None, language=None, prompt=None) -> None:
        result = TranscriptionResult(
            text=self.text,
            language=language or self.lang,
            language_probability=0.98,
            duration_seconds=len(audio_data) / 16000.0,
        )
        if callback:
            callback(result)


# =============================================================================
# 1. Tests for SentenceChunker (Phase 8.5)
# =============================================================================

def test_sentence_chunker_basic_and_exclamation() -> None:
    chunker = SentenceChunker()

    # Streaming chunks: "Hey! That's actually a really interesting idea. What made you think about building it?"
    res1 = chunker.add_chunk("Hey! ")
    assert res1 == ["Hey!"]

    res2 = chunker.add_chunk("That's actually a really ")
    assert res2 == []

    res3 = chunker.add_chunk("interesting idea. ")
    assert res3 == ["That's actually a really interesting idea."]

    res4 = chunker.add_chunk("What made you think about building it?")
    assert res4 == ["What made you think about building it?"]

    # Stream completes
    res5 = chunker.flush()
    assert res5 == []


def test_sentence_chunker_abbreviations_and_decimals() -> None:
    chunker = SentenceChunker()

    # "Dr. Smith bought 3.14 units of A.I. hardware today. That is awesome!"
    tokens = [
        "Dr. ",
        "Smith bought ",
        "3.14 units ",
        "of A.I. hardware today. ",
        "That is awesome!",
    ]
    extracted = []
    for t in tokens:
        extracted.extend(chunker.add_chunk(t))
    extracted.extend(chunker.flush())

    assert len(extracted) == 2
    assert "Dr. Smith bought 3.14 units of A.I. hardware today." in extracted[0]
    assert "That is awesome!" in extracted[1]


def test_sentence_chunker_hindi_purna_viram() -> None:
    chunker = SentenceChunker()

    tokens = ["नमस्ते दोस्त। ", "आप कैसे हैं?"]
    extracted = []
    for t in tokens:
        extracted.extend(chunker.add_chunk(t))
    extracted.extend(chunker.flush())

    assert len(extracted) == 2
    assert extracted[0] == "नमस्ते दोस्त।"
    assert extracted[1] == "आप कैसे हैं?"


# =============================================================================
# 2. Tests for StreamingAudioQueue (Phase 8.6, 8.8)
# =============================================================================

def test_streaming_audio_queue_sequential_synthesis_and_playback(qapp_instance, qtbot) -> None:
    tts = MockTTSEngine(duration=0.02)
    player = AudioPlayer()
    queue = StreamingAudioQueue(audio_player=player, tts_engine=tts)

    played_chunks: list[tuple[int, int, str]] = []
    completed_turns: list[int] = []

    queue.chunk_playback_started.connect(lambda t_id, c_idx, txt: played_chunks.append((t_id, c_idx, txt)))
    queue.all_chunks_played.connect(completed_turns.append)

    queue.start_new_turn(turn_id=1)
    queue.enqueue_sentence("First sentence.", turn_id=1)
    queue.enqueue_sentence("Second sentence.", turn_id=1)
    queue.mark_stream_finished(turn_id=1)

    # Wait for all queued audio to finish playing
    qtbot.waitUntil(lambda: len(completed_turns) == 1, timeout=3000)

    assert len(played_chunks) == 2
    assert played_chunks[0] == (1, 0, "First sentence.")
    assert played_chunks[1] == (1, 1, "Second sentence.")
    assert completed_turns == [1]
    queue.clear()
    player.stop()


def test_streaming_audio_queue_turn_cancellation(qapp_instance) -> None:
    tts = MockTTSEngine()
    player = AudioPlayer()
    queue = StreamingAudioQueue(audio_player=player, tts_engine=tts)

    queue.start_new_turn(turn_id=5)
    queue.enqueue_sentence("Sentence to cancel.", turn_id=5)

    # Cancel turn immediately
    queue.clear()
    assert len(queue._pending_sentences) == 0
    assert len(queue._synthesized_audio_map) == 0
    assert player.is_playing is False


# =============================================================================
# 3. Tests for VoiceConversationController Orchestrator (Phase 8.1 - 8.10)
# =============================================================================

@pytest.fixture(autouse=True)
def fallback_vad_only(monkeypatch):
    """Ensure VADEngine uses fast energy fallback in unit tests to avoid PyTorch CUDA driver issues."""
    monkeypatch.setattr(VADEngine, "_init_backend", lambda self: setattr(self, "_backend_type", "fallback"))


class DummyAIService(QObject):
    """Dummy AI Service providing fast token streaming for orchestrator tests."""

    def __init__(self) -> None:
        super().__init__()
        self.asked_prompts: list[str] = []

    def ask(self, user_prompt: str, is_voice: bool = True, **kwargs) -> int:
        self.asked_prompts.append(user_prompt)
        from PySide6.QtCore import QTimer
        # Emit tokens through global signals
        QTimer.singleShot(10, lambda: signals.ai_response_chunk.emit("Hey there! "))
        QTimer.singleShot(25, lambda: signals.ai_response_chunk.emit("I am Buddy. "))
        QTimer.singleShot(40, lambda: signals.ai_response_complete.emit("Hey there! I am Buddy."))
        return 1

    def cancel_generation(self) -> None:
        pass


def test_conversation_controller_full_automatic_flow(qapp_instance, qtbot, monkeypatch) -> None:
    from PySide6.QtCore import QTimer
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = MockWhisperEngine(text="How are you?", lang="en")
    player = AudioPlayer()
    tts = MockTTSEngine(duration=0.02)
    ai_service = DummyAIService()

    # Prevent hardware dependencies in headless tests
    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)

    def mock_play(samples, sample_rate):
        player._is_playing = True
        player.playback_started.emit()
        QTimer.singleShot(20, lambda: (setattr(player, "_is_playing", False), player.playback_finished.emit()))
        return True

    monkeypatch.setattr(player, "play", mock_play)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=ai_service,
        parent=None,
    )

    state_history: list[ConversationState] = []
    latencies: list[dict] = []
    controller.state_changed.connect(state_history.append)
    controller.latency_measured.connect(latencies.append)

    # 1. Enable continuous mode
    assert controller.enable() is True
    assert controller.state == ConversationState.LISTENING

    # 2. Simulate User Speech Onset
    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # 3. Simulate User Utterance Completion (1.0 second of speech)
    dummy_utterance = np.ones(16000, dtype=np.float32) * 0.1
    controller._on_vad_speech_ended(dummy_utterance)

    # 4. Wait until the entire AI response has been synthesized and played,
    # returning back to LISTENING hands-free!
    qtbot.waitUntil(lambda: controller.state == ConversationState.LISTENING, timeout=4000)

    # Verify state machine lifecycle progression
    assert ConversationState.LISTENING in state_history
    assert ConversationState.USER_SPEAKING in state_history
    assert ConversationState.TRANSCRIBING in state_history
    assert ConversationState.AI_THINKING in state_history
    assert ConversationState.AI_SPEAKING in state_history

    # Verify AI received user transcription
    assert ai_service.asked_prompts == ["How are you?"]

    # Verify TTS synthesized both sentences
    assert "Hey there!" in tts.synthesized_texts[0]
    assert "I am Buddy." in tts.synthesized_texts[1]

    # Verify latency metrics were measured (Phase 8.9)
    assert len(latencies) == 1
    metrics = latencies[0]
    assert metrics["turn_id"] == 1
    assert metrics["user_text"] == "How are you?"
    assert metrics["stt_latency_ms"] >= 0.0
    assert metrics["total_turn_duration_ms"] > 0.0

    # Clean shutdown
    controller.disable()
    assert controller.state == ConversationState.DISABLED


def test_conversation_controller_silence_recovery(qapp_instance, monkeypatch) -> None:
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = MockWhisperEngine(text="", lang="en")  # Empty text
    player = AudioPlayer()
    tts = MockTTSEngine()

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
    )

    controller.enable()
    assert controller.state == ConversationState.LISTENING

    # Speech start -> speech end
    controller._on_vad_speech_started()
    dummy_utterance = np.ones(8000, dtype=np.float32) * 0.05
    controller._on_vad_speech_ended(dummy_utterance)

    # Empty transcription automatically returns to LISTENING without error
    assert controller.state == ConversationState.LISTENING
    controller.disable()


def test_conversation_controller_cancel_turn(qapp_instance, monkeypatch) -> None:
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = MockWhisperEngine(text="Test prompt", lang="en")
    player = AudioPlayer()
    tts = MockTTSEngine()

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
    )

    controller.enable()
    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # Cancel turn
    controller.cancel_current_turn()
    assert controller.state == ConversationState.LISTENING

    controller.disable()
    assert controller.state == ConversationState.DISABLED


def test_turn_taking_mode_resumption(qapp_instance, monkeypatch) -> None:
    from app.voice.conversation_state import VoiceActivationMode
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = MockWhisperEngine(text="Test prompt", lang="en")
    player = AudioPlayer()
    tts = MockTTSEngine()

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
    )

    # 1. Continuous mode: after all speech played, returns to LISTENING
    controller.set_activation_mode(VoiceActivationMode.CONTINUOUS)
    controller.enable()
    assert controller.state == ConversationState.LISTENING

    controller._transition_to(ConversationState.AI_SPEAKING)
    # Intermediate chunk finish while queue is busy does NOT resume listening
    controller.audio_queue._is_synthesizing = True
    controller._on_audio_player_finished()
    assert controller.state == ConversationState.AI_SPEAKING
    controller.audio_queue._is_synthesizing = False

    # 2. Push-to-Talk mode: after cancel or turn, transitions to DISABLED (never auto-reopens mic)
    controller.set_activation_mode(VoiceActivationMode.PUSH_TO_TALK)
    controller.cancel_current_turn()
    assert controller.state == ConversationState.DISABLED

    controller.cleanup()


def test_voice_conversation_controller_zero_args_instantiation(qapp_instance) -> None:
    """Verify VoiceConversationController can be instantiated without any positional arguments (Bug 10)."""
    controller = VoiceConversationController()

    assert isinstance(controller.mic_manager, MicrophoneManager)
    assert isinstance(controller.vad_engine, VADEngine)
    assert isinstance(controller.whisper_engine, WhisperEngine)
    assert isinstance(controller.audio_player, AudioPlayer)
    assert isinstance(controller.tts_engine, BaseTTSEngine)
    assert controller.state == ConversationState.DISABLED
    assert controller.audio_queue is not None
    assert controller.wake_word_engine is not None

    controller.cleanup()


def test_voice_conversation_controller_partial_kwargs_instantiation(qapp_instance) -> None:
    """Verify instantiating with partial kwargs and custom TTS engine."""
    from app.voice.conversation_state import VoiceActivationMode

    mock_tts = MockTTSEngine()
    controller = VoiceConversationController(
        tts_engine=mock_tts,
        language="hi",
        activation_mode=VoiceActivationMode.WAKE_WORD,
        extra_forward_arg="test_value",
    )

    assert controller.tts_engine is mock_tts
    assert controller.language == "hi"
    assert controller.activation_mode == VoiceActivationMode.WAKE_WORD
    assert controller.audio_queue.tts_engine is mock_tts

    controller.cleanup()


def test_voice_conversation_controller_set_tts_engine_sync(qapp_instance) -> None:
    """Verify set_tts_engine updates controller and synchronizes with audio queue."""
    controller = VoiceConversationController()
    mock_tts = MockTTSEngine()

    controller.set_tts_engine(mock_tts)
    assert controller.tts_engine is mock_tts
    assert controller.audio_queue.tts_engine is mock_tts

    controller.cleanup()

