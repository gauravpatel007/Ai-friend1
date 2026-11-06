"""Unit tests for live word-by-word speech capture and ultra-low latency response flow."""

import numpy as np
import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from app.desktop.speech_bubble import SpeechBubbleWidget
from app.voice.vad_engine import VADEngine, VADState
from app.voice.conversation_state import ConversationState


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_speech_bubble_word_by_word_progressive_stream(qapp):
    bubble = SpeechBubbleWidget()
    pet_rect = QRect(100, 100, 120, 120)

    # 1. Empty listening state
    bubble.show_user_speech("", pet_rect, is_interim=True)
    assert "Listening..." in bubble.label.text()
    assert bubble.isVisible()

    # 2. First word arrives: "What"
    bubble.show_user_speech("What", pet_rect, is_interim=True)
    assert "What" in bubble.label.text()
    assert "🎙️ You:" in bubble.label.text()

    # 3. Second word arrives: "What is"
    bubble.show_user_speech("What is", pet_rect, is_interim=True)
    assert "What" in bubble.label.text()
    assert "is" in bubble.label.text()

    # 4. Full sentence built progressively: "What is the capital of France"
    bubble.show_user_speech("What is the capital of France", pet_rect, is_interim=True)
    assert "capital of" in bubble.label.text()
    assert "France" in bubble.label.text()

    # 5. Finalized speech when user stops speaking
    bubble.show_user_speech("What is the capital of France?", pet_rect, is_interim=False)
    assert "What is the capital of France?" in bubble.label.text()
    assert "..." not in bubble.label.text()  # Interim ellipsis stripped

    bubble.close()


def test_vad_engine_early_buffer_capture():
    vad = VADEngine(sample_rate=16000, frame_size=512, silence_threshold_ms=400)
    assert vad.silence_threshold_ms == 400

    # Before speech: buffer is None
    assert vad.get_current_speech_buffer() is None

    # Simulate speech onset with 4 frames
    t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
    speech_frame = (0.5 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)

    # Feed frames to trigger SPEAKING state and accumulate active frames
    for _ in range(5):
        vad.process_frame(speech_frame)

    assert vad._state == VADState.SPEAKING

    # Buffer should be available immediately (>= 2 frames captured)
    buf = vad.get_current_speech_buffer()
    assert buf is not None
    assert len(buf) >= 1024


def test_vad_engine_snappy_silence_threshold():
    # 400ms silence threshold = ~13 frames (13 * 32ms = 416ms)
    vad = VADEngine(
        sample_rate=16000,
        frame_size=512,
        min_speech_frames=2,
        silence_threshold_ms=400,
        min_utterance_ms=50,
    )

    t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
    speech_frame = (0.5 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)
    silence_frame = np.zeros(512, dtype=np.float32)

    # 2 speech frames to trigger
    vad.process_frame(speech_frame)
    vad.process_frame(speech_frame)
    assert vad._state == VADState.SPEAKING

    # Feed silence frames up to 384ms (12 frames) -> should still be speaking
    for _ in range(12):
        res = vad.process_frame(silence_frame)
        assert res is None
        assert vad._state == VADState.SPEAKING

    # 13th silence frame (13 * 32ms = 416ms >= 400ms) -> speech ends!
    utterance = vad.process_frame(silence_frame)
    assert utterance is not None
    assert vad._state == VADState.SILENCE
