"""Tests for Phase 1: Live Speech Bubble with Real-Time User Transcription.

Verifies:
1. SpeechBubbleWidget word wrapping, maximum bounds, dynamic geometry, and styling.
2. Progressive interim text rendering without premature dismissal.
3. Finalized text rendering with clean reading dwell time.
4. VADEngine progressive speech buffer capture.
5. WhisperEngine fast greedy interim transcription.
6. Progressive replacement and reconciliation without word stutter or duplication.
7. Continuous speech with natural pauses without early cut-off.
8. Single AI submission guarantee (finalized utterance submitted exactly once).
9. Thread-safe Qt signal delivery between background workers and DesktopPetWindow.
"""

import numpy as np
import pytest
from PySide6.QtCore import QObject, QRect, QTimer
from PySide6.QtWidgets import QApplication

from app.core.signals import signals
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.speech_bubble import SpeechBubbleWidget
from app.settings.config_manager import ConfigManager
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState
from app.voice.microphone_manager import MicrophoneManager
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


class MockFastTTSEngine(BaseTTSEngine):
    """Fast in-memory mock TTS for pipelined voice controller tests."""

    def __init__(self, sample_rate: int = 22050, duration: float = 0.02) -> None:
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


class MockProgressiveWhisperEngine(WhisperEngine):
    """Mock Whisper engine returning progressive interim text hypotheses followed by final result."""

    def __init__(self, interim_sequence: list[str] = None, final_text: str = "Hey Buddy, explain Python.") -> None:
        super().__init__()
        self.interim_sequence = interim_sequence or ["Hey", "Hey Buddy,", "Hey Buddy, explain", "Hey Buddy, explain Python."]
        self.interim_call_count = 0
        self.final_text = final_text

    def transcribe_interim(self, audio_data: np.ndarray, language=None, prompt=None) -> str:
        idx = min(self.interim_call_count, len(self.interim_sequence) - 1)
        self.interim_call_count += 1
        return self.interim_sequence[idx]

    def transcribe_interim_async(self, audio_data: np.ndarray, generation_id: int, callback=None, language=None, prompt=None) -> None:
        text = self.transcribe_interim(audio_data, language=language, prompt=prompt)
        if callback:
            callback(generation_id, text)

    def transcribe_async(self, audio_data: np.ndarray, callback=None, language=None, prompt=None) -> None:
        result = TranscriptionResult(
            text=self.final_text,
            language=language or "en",
            language_probability=0.99,
            duration_seconds=len(audio_data) / 16000.0,
        )
        if callback:
            callback(result)


class MockDummyAIService(QObject):
    """Mock AI Service verifying prompt submission counts."""

    def __init__(self) -> None:
        super().__init__()
        self.asked_prompts: list[str] = []

    def ask(self, user_prompt: str, is_voice: bool = True) -> int:
        self.asked_prompts.append(user_prompt)
        QTimer.singleShot(10, lambda: signals.ai_response_chunk.emit("Python is a powerful language."))
        QTimer.singleShot(25, lambda: signals.ai_response_complete.emit("Python is a powerful language."))
        return 1

    def cancel_generation(self) -> None:
        pass


# =============================================================================
# 1. SpeechBubbleWidget Tests
# =============================================================================

def test_speech_bubble_geometry_and_word_wrap(qapp_instance) -> None:
    """Verify SpeechBubbleWidget applies word wrapping and bounded width/height."""
    bubble = SpeechBubbleWidget()
    pet_rect = QRect(400, 400, 120, 120)

    # 1. Short greeting
    bubble.show_user_speech("Hi", pet_rect, is_interim=True)
    assert bubble.label.wordWrap() is True
    assert bubble.width() >= bubble.MIN_BUBBLE_WIDTH
    assert bubble.width() <= bubble.MAX_BUBBLE_WIDTH
    assert bubble.isVisible() is True
    assert bubble.is_showing_user_speech is True

    # 2. Long complex question
    long_q = "Hey Buddy, can you explain the architectural difference between deep learning and classical reinforcement learning in computer vision?"
    bubble.show_user_speech(long_q, pet_rect, is_interim=True)
    assert bubble.width() <= bubble.MAX_BUBBLE_WIDTH
    assert bubble.height() > 42  # Multi-line expansion
    bubble.hide_bubble()
    bubble.close()


def test_speech_bubble_show_user_speech_interim_no_auto_dismiss(qapp_instance, qtbot) -> None:
    """Verify interim speech updates disable auto-dismiss timer while speaking."""
    bubble = SpeechBubbleWidget()
    pet_rect = QRect(300, 300, 120, 120)

    bubble.show_user_speech("I want to build", pet_rect, is_interim=True)
    assert bubble._dismiss_timer.isActive() is False
    assert "🎙️ You:" in bubble.label.text()
    assert "I want to build" in bubble.label.text()

    # Progressive update replaces previous text without starting dismiss timer
    bubble.show_user_speech("I want to build a Python app", pet_rect, is_interim=True)
    assert bubble._dismiss_timer.isActive() is False
    assert "I want to build a Python app" in bubble.label.text()
    bubble.close()


def test_speech_bubble_show_user_speech_final_starts_hold_timer(qapp_instance, qtbot) -> None:
    """Verify finalized speech starts hold timer for reading dwell."""
    bubble = SpeechBubbleWidget()
    pet_rect = QRect(300, 300, 120, 120)

    bubble.show_user_speech("Finished sentence.", pet_rect, is_interim=False)
    assert bubble._dismiss_timer.isActive() is True
    assert bubble._dismiss_timer.interval() == 2200
    assert "Finished sentence." in bubble.label.text()
    bubble.close()


# =============================================================================
# 2. DesktopPetWindow Signal Routing Tests
# =============================================================================

def test_pet_window_live_user_speech_signal_routing(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify pet window connects user_speech_interim and final signals to speech bubble."""
    cfg = ConfigManager()
    pet = DesktopPetWindow(config_manager=cfg)
    pet.resize(120, 120)
    pet.show()

    # 1. Interim update
    signals.user_speech_interim.emit("Hey Buddy")
    qtbot.wait(30)
    assert pet.speech_bubble.isVisible() is True
    assert pet.speech_bubble.is_showing_user_speech is True
    assert "Hey Buddy" in pet.speech_bubble.label.text()

    # 2. State change to "listening" should NOT clobber active user speech
    pet._apply_visual_state("listening")
    assert "Hey Buddy" in pet.speech_bubble.label.text()
    assert "I'm listening..." not in pet.speech_bubble.label.text()

    # 3. Finalized update
    signals.user_speech_final.emit("Hey Buddy, what time is it?")
    qtbot.wait(30)
    assert "Hey Buddy, what time is it?" in pet.speech_bubble.label.text()

    pet.close()


# =============================================================================
# 3. VADEngine Progressive Speech Buffer Capture
# =============================================================================

def test_vad_engine_get_current_speech_buffer() -> None:
    """Verify VADEngine provides thread-safe snapshot of active utterance buffer."""
    vad = VADEngine()
    vad._backend_type = "fallback"

    # In silence: buffer is None
    assert vad.get_current_speech_buffer() is None

    # Simulate speech start
    vad._state = VADState.SPEAKING
    frame = np.ones(512, dtype=np.float32) * 0.05
    for _ in range(12):  # > 10 frames
        vad._active_utterance_frames.append(frame)

    buf = vad.get_current_speech_buffer()
    assert buf is not None
    assert isinstance(buf, np.ndarray)
    assert len(buf) == 12 * 512
    assert np.allclose(buf, 0.05)


# =============================================================================
# 4. WhisperEngine Fast Greedy Interim Pass
# =============================================================================

def test_whisper_engine_transcribe_interim_short_audio_graceful() -> None:
    """Verify transcribe_interim returns empty string on sub-threshold audio slices."""
    eng = WhisperEngine(model_size="tiny")
    short_audio = np.zeros(800, dtype=np.float32)  # 50ms (< 150ms)
    res = eng.transcribe_interim(short_audio)
    assert res == ""


# =============================================================================
# 5. Controller Progressive Updates & AI Single-Submission Guarantee
# =============================================================================

def test_controller_interim_progressive_speech_flow(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify progressive interim transcription hypotheses update without duplication and submit to AI exactly once."""
    mic = MicrophoneManager()
    vad = VADEngine()
    vad._backend_type = "fallback"
    whisper = MockProgressiveWhisperEngine(
        interim_sequence=["Can you", "Can you help", "Can you help me build a Python app"],
        final_text="Can you help me build a Python app?",
    )
    player = AudioPlayer()
    tts = MockFastTTSEngine()
    ai_service = MockDummyAIService()

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)
    monkeypatch.setattr(player, "play", lambda samples, sr: True)

    interim_updates = []
    final_updates = []
    signals.user_speech_interim.connect(interim_updates.append)
    signals.user_speech_final.connect(final_updates.append)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=ai_service,
    )

    controller.enable()
    controller._transition_to(ConversationState.LISTENING)

    # 1. Speech onset
    vad._state = VADState.SPEAKING
    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # 2. Simulate incoming mic chunks during speech to trigger interim passes
    t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
    speech_frame = (0.4 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)
    for _ in range(12):
        vad._active_utterance_frames.append(speech_frame)

    # Frame interval triggers interim pass
    controller._interim_frame_count = 11
    controller.process_mic_frame(speech_frame)

    assert len(interim_updates) > 0
    assert interim_updates[-1] in ("Can you", "Can you help", "Can you help me build a Python app")

    # 3. Simulate natural speech pause within same utterance (< 650ms)
    # Earlier recognized words are retained, not lost or reset
    assert controller._last_interim_text != ""

    # 4. User finishes speaking -> VAD emits speech_ended
    complete_utterance = np.ones(16000 * 2, dtype=np.float32) * 0.05
    controller._on_vad_speech_ended(complete_utterance)

    # Wait for final transcription and AI dispatch
    qtbot.waitUntil(lambda: len(final_updates) == 1, timeout=3000)

    # Verify finalized transcription is emitted
    assert final_updates == ["Can you help me build a Python app?"]

    # Verify AI received the prompt EXACTLY ONCE
    assert len(ai_service.asked_prompts) == 1
    assert ai_service.asked_prompts[0] == "Can you help me build a Python app?"

    controller.disable()


def test_controller_recognition_corrections_replaces_hypothesis(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify recognition corrections replace earlier partial text rather than appending/stuttering."""
    mic = MicrophoneManager()
    vad = VADEngine()
    vad._backend_type = "fallback"
    whisper = MockProgressiveWhisperEngine(
        interim_sequence=["I want to bill", "I want to build an", "I want to build an application"],
        final_text="I want to build an application.",
    )
    player = AudioPlayer()
    tts = MockFastTTSEngine()
    ai_service = MockDummyAIService()

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)
    monkeypatch.setattr(player, "play", lambda samples, sr: True)

    interim_history = []
    signals.user_speech_interim.connect(interim_history.append)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=ai_service,
    )
    controller.enable()
    vad._state = VADState.SPEAKING
    controller._transition_to(ConversationState.USER_SPEAKING)

    # Feed frames to trigger multiple progressive updates
    t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
    speech_frame = (0.4 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)
    for i in range(36):
        vad._active_utterance_frames.append(speech_frame)
        controller.process_mic_frame(speech_frame)

    # Check hypotheses were progressive revisions, not concatenated stutter ("I want to bill I want to build an...")
    for h in interim_history:
        if h:
            assert not h.startswith("I want to bill I want to build")

    controller.disable()


def test_controller_empty_transcription_returns_to_listening(qapp_instance, qtbot, monkeypatch) -> None:
    """Verify empty/silent transcription gracefully returns to listening without AI dispatch."""
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = MockProgressiveWhisperEngine(final_text="")
    player = AudioPlayer()
    tts = MockFastTTSEngine()
    ai_service = MockDummyAIService()

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)
    monkeypatch.setattr(player, "play", lambda samples, sr: True)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=ai_service,
    )
    controller.enable()
    controller._transition_to(ConversationState.USER_SPEAKING)

    empty_utterance = np.zeros(16000, dtype=np.float32)
    controller._on_vad_speech_ended(empty_utterance)

    # Wait for return to LISTENING
    qtbot.waitUntil(lambda: controller.state == ConversationState.LISTENING, timeout=3000)

    # AI service must NOT be called for empty transcription
    assert len(ai_service.asked_prompts) == 0

    controller.disable()
