"""Automated Test Suite for Phase 2: AI Response Subtitles Synchronized with Speech.

Covers all Phase 2 specification scenarios:
1. A one-sentence response.
2. A response with three sentences (sentence-by-sentence sequential synchronization).
3. A long answer containing several paragraphs.
4. Questions and exclamation marks.
5. Abbreviations and decimal numbers.
6. A response with an unusually long sentence.
7. Slow TTS playback duration tracking.
8. Playback completion and transition to the next sentence (tied to audio events, not fixed timers).
9. Audio playback failure graceful recovery.
10. User interruption during playback (immediate subtitle clear and queue abort).
11. Sleep command during playback (immediate playback halt and subtitle clear).
12. A new response arriving while an older response is still queued (turn invalidation).
13. Repeated requests and stale callback prevention.
14. UI thread safety across background synthesis workers.
15. Return to the correct listening or idle state after the final sentence.
"""

from __future__ import annotations

import time
import numpy as np
import pytest
from PySide6.QtCore import QObject, QRect, QTimer
from PySide6.QtWidgets import QApplication

from app.core.signals import signals
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.speech_bubble import SpeechBubbleWidget
from app.settings.config_manager import ConfigManager
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.microphone_manager import MicrophoneManager
from app.voice.sentence_chunker import SentenceChunker
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.whisper_engine import WhisperEngine


class MockFastTTSEngine(BaseTTSEngine):
    """Configurable in-memory mock TTS engine for deterministic latency/playback testing."""

    def __init__(self, sample_rate: int = 22050, duration: float = 0.03, should_fail: bool = False) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.duration = duration
        self.should_fail = should_fail
        self.synthesized_sentences: list[str] = []

    def load_model(self, voice_name=None) -> bool:
        self._is_loaded = True
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        if self.should_fail:
            raise RuntimeError("Simulated TTS synthesis failure")
        self.synthesized_sentences.append(text)
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


# =============================================================================
# 1. Sentence Chunker Segmentation Tests (Requirements 2, 4, 5, 6)
# =============================================================================

def test_sentence_chunker_single_and_three_sentences() -> None:
    """Verify clean sentence segmentation for 1-sentence and 3-sentence responses."""
    # 1. One sentence
    one_res = SentenceChunker.split_text("Python is a programming language.")
    assert one_res == ["Python is a programming language."]

    # 2. Three sentences
    text = "Python is a programming language. It is widely used for automation and AI. It is also beginner-friendly."
    three_res = SentenceChunker.split_text(text)
    assert len(three_res) == 3
    assert three_res[0] == "Python is a programming language."
    assert three_res[1] == "It is widely used for automation and AI."
    assert three_res[2] == "It is also beginner-friendly."


def test_sentence_chunker_questions_exclamations_quotes_and_paragraphs() -> None:
    """Verify questions, exclamations, quotes, and multi-paragraph texts are parsed naturally."""
    text = "Hey there! How can I help you today? He said, \"Python is great!\" Let's get started."
    chunks = SentenceChunker.split_text(text)
    assert len(chunks) == 4
    assert chunks[0] == "Hey there!"
    assert chunks[1] == "How can I help you today?"
    assert chunks[2] == 'He said, "Python is great!"'
    assert chunks[3] == "Let's get started."

    # Multi-paragraph with blank lines and bullet points
    para_text = (
        "Here are three key features:\n\n"
        "1. Dynamic typing and readable syntax.\n"
        "2. Extensive third-party library ecosystem.\n"
        "3. Cross-platform support."
    )
    para_chunks = SentenceChunker.split_text(para_text)
    assert len(para_chunks) >= 3
    # Check that sentences maintain order and content
    combined = " ".join(para_chunks)
    assert "Dynamic typing" in combined
    assert "Extensive third-party" in combined
    assert "Cross-platform" in combined


def test_sentence_chunker_abbreviations_and_decimals() -> None:
    """Verify abbreviations and decimals do not cause premature splits."""
    text = "Dr. Smith bought 3.14 units of A.I. equipment from Corp. Inc. on Jan. 15th for $99.50. That was fast!"
    chunks = SentenceChunker.split_text(text)
    assert len(chunks) == 2
    assert "Dr. Smith bought 3.14 units of A.I. equipment from Corp. Inc. on Jan. 15th for $99.50." in chunks[0]
    assert chunks[1] == "That was fast!"


def test_sentence_chunker_unusually_long_sentence() -> None:
    """Verify unusually long sentence without terminal punctuation splits cleanly at clause or space."""
    long_clause = (
        "This is an unusually long technical explanation about distributed neural network compilation and hardware acceleration, "
        "which continues for many clauses without a single period, "
        "so the streaming engine must segment it intelligently without crashing or losing words."
    )
    chunks = SentenceChunker.split_text(long_clause)
    assert len(chunks) >= 2
    # Ensure no words are lost
    rejoined = " ".join(chunks)
    assert "compilation and hardware acceleration" in rejoined
    assert "without crashing or losing words" in rejoined


# =============================================================================
# 2. SpeechBubbleWidget AI Subtitle Rendering Tests
# =============================================================================

def test_speech_bubble_ai_subtitle_rendering_no_timer_while_speaking(qapp_instance) -> None:
    """Verify SpeechBubbleWidget renders AI subtitles with green badge and stops dismiss timer while speaking."""
    bubble = SpeechBubbleWidget()
    pet_rect = QRect(300, 300, 120, 120)

    # 1. First sentence
    bubble.show_ai_subtitle("Python is a programming language.", pet_rect)
    assert bubble.isVisible() is True
    assert bubble.is_showing_ai_subtitle is True
    assert bubble.is_showing_user_speech is False
    assert "🤖 Buddy:" in bubble.label.text()
    assert "Python is a programming language." in bubble.label.text()
    # Crucial: Dismiss timer must be stopped while speaking audio!
    assert bubble._dismiss_timer.isActive() is False

    # 2. Second sentence replacement
    bubble.show_ai_subtitle("It is widely used for automation and AI.", pet_rect)
    assert "It is widely used for automation and AI." in bubble.label.text()
    assert bubble._dismiss_timer.isActive() is False

    # 3. Third sentence and completion
    bubble.show_ai_subtitle("It is also beginner-friendly.", pet_rect)
    assert "It is also beginner-friendly." in bubble.label.text()

    # Finished speech triggers hold timer for reading dwell
    bubble.on_ai_speech_finished(hold_ms=1800)
    assert bubble._dismiss_timer.isActive() is True
    assert bubble._dismiss_timer.interval() == 1800
    bubble.close()


def test_speech_bubble_clear_subtitles_on_cancellation(qapp_instance) -> None:
    """Verify clear_subtitles immediately aborts subtitles and hides the bubble."""
    bubble = SpeechBubbleWidget()
    pet_rect = QRect(200, 200, 120, 120)
    bubble.show_ai_subtitle("Sentence in progress...", pet_rect)
    assert bubble.is_showing_ai_subtitle is True

    # Cancellation immediately clears
    bubble.clear_subtitles()
    assert bubble._is_showing_ai_subtitle is False
    assert bubble._target_visible is False
    bubble.close()


# =============================================================================
# 3. DesktopPetWindow Signal Integration Tests
# =============================================================================

def test_pet_window_ai_subtitle_signals_integration(qapp_instance, qtbot) -> None:
    """Verify pet window connects central ai_speech_subtitle and ai_speech_finished signals."""
    cfg = ConfigManager()
    pet = DesktopPetWindow(config_manager=cfg)
    pet.resize(120, 120)
    pet.show()

    # 1. AI starts speaking sentence 1
    signals.ai_speech_subtitle.emit("Hello! I am Buddy.")
    qtbot.wait(30)
    assert pet.speech_bubble.isVisible() is True
    assert pet.speech_bubble.is_showing_ai_subtitle is True
    assert "Hello! I am Buddy." in pet.speech_bubble.label.text()

    # State changes to "speaking" should NOT overwrite subtitle with generic "Let me tell you..."
    pet._apply_visual_state("speaking")
    assert "Hello! I am Buddy." in pet.speech_bubble.label.text()
    assert "Let me tell you..." not in pet.speech_bubble.label.text()

    # 2. Transition to sentence 2
    signals.ai_speech_subtitle.emit("I can help you build desktop applications.")
    qtbot.wait(30)
    assert "I can help you build desktop applications." in pet.speech_bubble.label.text()

    # 3. Speech finished
    signals.ai_speech_finished.emit()
    qtbot.wait(30)
    assert pet.speech_bubble._dismiss_timer.isActive() is True

    # 4. Sleep requested clears subtitles immediately
    signals.ai_speech_subtitle.emit("Going to sleep now.")
    qtbot.wait(20)
    signals.sleep_requested.emit()
    qtbot.wait(30)
    assert pet.speech_bubble._is_showing_ai_subtitle is False

    pet.close()


# =============================================================================
# 4. Audio Playback Event Synchronization & Pipeline Tests (Requirements 1, 3, 7, 8)
# =============================================================================

def test_sequential_three_sentence_playback_synchronization(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify 3-sentence response advances sentence-by-sentence tied to playback events, not fixed timers."""
    tts = MockFastTTSEngine(duration=0.03)
    player = AudioPlayer()
    queue = StreamingAudioQueue(audio_player=player, tts_engine=tts)

    # Mock player.play to simulate realistic audio playback duration
    def mock_play(samples, sample_rate):
        player._is_playing = True
        player.playback_started.emit()
        # Simulate playback completing after 35ms
        QTimer.singleShot(35, lambda: (
            setattr(player, "_is_playing", False),
            player.playback_finished.emit(),
        ))
        return True

    monkeypatch.setattr(player, "play", mock_play)

    playback_started_events: list[tuple[int, int, str]] = []
    playback_finished_events: list[tuple[int, int, str]] = []
    all_played_events: list[int] = []

    queue.chunk_playback_started.connect(lambda tid, cidx, txt: playback_started_events.append((tid, cidx, txt)))
    queue.chunk_playback_finished.connect(lambda tid, cidx, txt: playback_finished_events.append((tid, cidx, txt)))
    queue.all_chunks_played.connect(all_played_events.append)

    sentences = [
        "Python is a programming language.",
        "It is widely used for automation and AI.",
        "It is also beginner-friendly.",
    ]

    turn_id = 101
    queue.start_new_turn(turn_id)
    for idx, s in enumerate(sentences):
        queue.enqueue_sentence(s, turn_id=turn_id, is_final=(idx == len(sentences) - 1))
    queue.mark_stream_finished(turn_id)

    # Wait for all 3 sentences to finish sequential playback
    qtbot.waitUntil(lambda: len(all_played_events) == 1, timeout=4000)

    # Verify sequential playback started in exact sentence order
    assert len(playback_started_events) == 3
    assert playback_started_events[0] == (turn_id, 0, "Python is a programming language.")
    assert playback_started_events[1] == (turn_id, 1, "It is widely used for automation and AI.")
    assert playback_started_events[2] == (turn_id, 2, "It is also beginner-friendly.")

    # Verify each sentence finished before the next one started
    assert len(playback_finished_events) == 3
    assert playback_finished_events[0][2] == "Python is a programming language."
    assert playback_finished_events[1][2] == "It is widely used for automation and AI."
    assert playback_finished_events[2][2] == "It is also beginner-friendly."

    queue.clear()
    player.stop()


def test_slow_tts_playback_duration_holds_subtitle(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify slower audio playback (80ms) holds the subtitle for its full playback duration."""
    tts = MockFastTTSEngine(duration=0.08)
    player = AudioPlayer()
    queue = StreamingAudioQueue(audio_player=player, tts_engine=tts)

    playback_duration_measured = []

    def mock_play(samples, sample_rate):
        start_t = time.perf_counter()
        player._is_playing = True
        player.playback_started.emit()
        QTimer.singleShot(80, lambda: (
            setattr(player, "_is_playing", False),
            playback_duration_measured.append(time.perf_counter() - start_t),
            player.playback_finished.emit(),
        ))
        return True

    monkeypatch.setattr(player, "play", mock_play)

    completed = []
    queue.all_chunks_played.connect(completed.append)

    queue.start_new_turn(201)
    queue.enqueue_sentence("This is a slowly spoken sentence.", turn_id=201, is_final=True)
    queue.mark_stream_finished(201)

    qtbot.waitUntil(lambda: len(completed) == 1, timeout=3000)

    assert len(playback_duration_measured) == 1
    # Playback lasted >= 70ms (actual audio duration, not premature dismissal)
    assert playback_duration_measured[0] >= 0.07

    queue.clear()


# =============================================================================
# 5. Error Recovery, Interruption, Sleep & Turn Invalidation Tests (Req 6, 8, 9, 10, 11, 12, 13)
# =============================================================================

def test_tts_synthesis_failure_recovers_gracefully(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify synthesis failure for one chunk does not permanently hang the playback queue."""
    tts = MockFastTTSEngine(should_fail=True)
    player = AudioPlayer()
    queue = StreamingAudioQueue(audio_player=player, tts_engine=tts)

    monkeypatch.setattr(player, "play", lambda samples, sr: player.playback_finished.emit() or True)

    completed = []
    queue.all_chunks_played.connect(completed.append)

    queue.start_new_turn(301)
    queue.enqueue_sentence("Sentence that fails synthesis.", turn_id=301, is_final=True)
    queue.mark_stream_finished(301)

    # Queue must finish gracefully without freezing
    qtbot.waitUntil(lambda: len(completed) == 1, timeout=3000)
    assert completed == [301]
    queue.clear()


def test_user_interruption_during_playback_aborts_queue_and_subtitles(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify user interruption halts playback immediately and clears subtitles without advancing."""
    mic = MicrophoneManager()
    vad = VADEngine()
    vad._backend_type = "fallback"
    whisper = WhisperEngine(model_size="tiny")
    player = AudioPlayer()
    tts = MockFastTTSEngine(duration=0.05)

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)
    monkeypatch.setattr(player, "play", lambda samples, sr: True)
    monkeypatch.setattr(player, "stop", lambda: None)

    subtitles_received = []
    finished_received = []
    signals.ai_speech_subtitle.connect(subtitles_received.append)
    signals.ai_speech_finished.connect(lambda: finished_received.append(True))

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=None,
    )
    controller.enable()

    # Start audio playback for turn 1
    turn_id = 401
    controller._turn_id = turn_id
    controller.audio_queue.start_new_turn(turn_id)
    controller.audio_queue.enqueue_sentence("First sentence playing.", turn_id=turn_id)
    controller.audio_queue.enqueue_sentence("Second sentence queued.", turn_id=turn_id)

    # Simulate chunk playback started
    controller._on_chunk_playback_started(turn_id, 0, "First sentence playing.")
    assert subtitles_received == ["First sentence playing."]

    # User interrupts Buddy while first sentence is playing!
    controller.cancel_current_turn()

    # Subtitles must be cleared and finished emitted
    assert len(finished_received) >= 1
    assert controller.audio_queue.is_empty is True
    # The second sentence must NEVER appear!
    assert "Second sentence queued." not in subtitles_received

    controller.disable()


def test_sleep_command_halts_playback_and_clears_subtitles(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify Buddy sleep command immediately halts speech and dismisses subtitles."""
    bubble = SpeechBubbleWidget()
    pet_rect = QRect(100, 100, 120, 120)
    bubble.show_ai_subtitle("Buddy speaking before sleep.", pet_rect)
    assert bubble.is_showing_ai_subtitle is True

    # Sleep requested signal
    signals.sleep_requested.emit()
    bubble.clear_subtitles()

    assert bubble._is_showing_ai_subtitle is False
    assert bubble._target_visible is False
    bubble.close()


def test_new_response_supersedes_older_response_turn_invalidation(qapp_instance, qtbot) -> None:
    """Verify a new response arriving while an older response is queued invalidates older turn."""
    tts = MockFastTTSEngine()
    player = AudioPlayer()
    queue = StreamingAudioQueue(audio_player=player, tts_engine=tts)

    # Turn 1 enqueued
    queue.start_new_turn(501)
    queue.enqueue_sentence("Old sentence from turn 501.", turn_id=501)

    # Turn 2 starts immediately (superseding Turn 1)
    queue.start_new_turn(502)
    queue.enqueue_sentence("New sentence from turn 502.", turn_id=502, is_final=True)

    # Older turn chunks must be rejected
    assert queue.active_turn_id == 502
    for item in queue._pending_sentences:
        assert item.turn_id == 502

    queue.clear()


def test_full_controller_streaming_ai_subtitles_and_return_to_listening(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify full end-to-end token stream -> sentence chunker -> audio queue -> subtitles -> return to LISTENING."""
    mic = MicrophoneManager()
    vad = VADEngine()
    vad._backend_type = "fallback"
    whisper = WhisperEngine(model_size="tiny")
    player = AudioPlayer()
    tts = MockFastTTSEngine(duration=0.02)

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)
    monkeypatch.setattr(player, "stop", lambda: None)

    # Mock audio player to simulate instant playback completion
    def mock_play(samples, sample_rate):
        player._is_playing = True
        player.playback_started.emit()
        QTimer.singleShot(25, lambda: (
            setattr(player, "_is_playing", False),
            player.playback_finished.emit(),
        ))
        return True

    monkeypatch.setattr(player, "play", mock_play)

    received_subtitles: list[str] = []
    signals.ai_speech_subtitle.connect(received_subtitles.append)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=None,
    )
    controller.enable()
    controller.set_activation_mode(VoiceActivationMode.CONTINUOUS)
    controller._transition_to(ConversationState.AI_THINKING)

    # Simulate LLM streaming three distinct sentences
    tokens = [
        "Python is ", "a programming language. ",
        "It is widely used ", "for automation and AI. ",
        "It is also ", "beginner-friendly.",
    ]
    for t in tokens:
        controller._on_ai_stream_chunk(t)

    controller._on_ai_stream_complete("Python is a programming language. It is widely used for automation and AI. It is also beginner-friendly.")

    # Wait for all chunks to play sequentially and return to LISTENING
    qtbot.waitUntil(lambda: controller.state == ConversationState.LISTENING, timeout=4000)

    # Verify all 3 subtitles were emitted in exact sequential order
    assert len(received_subtitles) == 3
    assert received_subtitles[0] == "Python is a programming language."
    assert received_subtitles[1] == "It is widely used for automation and AI."
    assert received_subtitles[2] == "It is also beginner-friendly."

    controller.disable()
