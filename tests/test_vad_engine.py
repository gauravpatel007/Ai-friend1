"""Tests for Voice Activity Detection (VAD) Engine."""

import numpy as np
import pytest

from app.voice.vad_engine import VADEngine, VADState


class TestVADEngine:
    """Unit tests for VAD state machine and speech boundary detection."""

    def test_vad_initialization(self) -> None:
        vad = VADEngine(sample_rate=16000, frame_size=512)
        assert vad.sample_rate == 16000
        assert vad.frame_size == 512
        assert vad._state == VADState.SILENCE

    def test_speech_probability_silence_vs_speech(self) -> None:
        vad = VADEngine()

        silence = np.zeros(512, dtype=np.float32)
        prob_silence = vad.get_speech_probability(silence)
        assert prob_silence < 0.5

        # Loud synthetic tone representing speech amplitude
        t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
        speech_frame = (0.5 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
        prob_speech = vad.get_speech_probability(speech_frame)
        assert prob_speech > prob_silence

    def test_state_machine_speech_trigger_and_end(self, qtbot) -> None:
        # 16000Hz, 512 frame = 32ms per frame
        # min_speech_frames=2 (~64ms), silence_threshold_ms=96ms (3 frames of silence to end)
        vad = VADEngine(
            min_speech_frames=2,
            silence_threshold_ms=96,
            min_utterance_ms=50,
        )

        speech_started_called = []
        speech_ended_utterances = []

        vad.speech_started.connect(lambda: speech_started_called.append(True))
        vad.speech_ended.connect(speech_ended_utterances.append)

        silence_frame = np.zeros(512, dtype=np.float32)
        t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
        speech_frame = (0.4 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)

        # 1. Feed silence — should stay in silence
        vad.process_frame(silence_frame)
        assert vad._state == VADState.SILENCE
        assert len(speech_started_called) == 0

        # 2. Feed 1 speech frame — enters TRIGGERING
        vad.process_frame(speech_frame)
        assert vad._state == VADState.TRIGGERING

        # 3. Feed 2nd speech frame — confirmed speech onset!
        vad.process_frame(speech_frame)
        assert vad._state == VADState.SPEAKING
        assert len(speech_started_called) == 1

        # 4. Feed 3 more speech frames while talking
        vad.process_frame(speech_frame)
        vad.process_frame(speech_frame)
        vad.process_frame(speech_frame)
        assert vad._state == VADState.SPEAKING

        # 5. User stops talking: feed silence frames
        # Silence frame 1
        res1 = vad.process_frame(silence_frame)
        assert res1 is None
        # Silence frame 2
        res2 = vad.process_frame(silence_frame)
        assert res2 is None
        # Silence frame 3 (hits silence threshold >= 96ms)
        utterance = vad.process_frame(silence_frame)

        assert utterance is not None
        assert isinstance(utterance, np.ndarray)
        assert len(utterance) > 0
        assert len(speech_ended_utterances) == 1
        assert vad._state == VADState.SILENCE

    def test_min_utterance_duration_filters_noise(self) -> None:
        # If utterance is shorter than min_utterance_ms, it should be discarded
        vad = VADEngine(
            min_speech_frames=1,
            silence_threshold_ms=64,
            min_utterance_ms=300,
        )
        silence_frame = np.zeros(512, dtype=np.float32)
        t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
        speech_frame = (0.4 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)

        # Trigger speech with just 1 frame (~32ms)
        vad.process_frame(speech_frame)
        # End speech with silence
        vad.process_frame(silence_frame)
        utterance = vad.process_frame(silence_frame)

        # Discarded because 32ms < 300ms
        assert utterance is None

    def test_reset_states(self) -> None:
        vad = VADEngine()
        vad._state = VADState.SPEAKING
        vad._consecutive_speech_frames = 5
        vad._active_utterance_frames.append(np.zeros(512, dtype=np.float32))

        vad.reset_states()
        assert vad._state == VADState.SILENCE
        assert vad._consecutive_speech_frames == 0
        assert len(vad._active_utterance_frames) == 0
