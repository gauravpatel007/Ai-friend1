"""Tests for WhisperEngine speech-to-text inference."""

import numpy as np
import pytest

from app.voice.whisper_engine import (
    TranscriptionResult,
    WhisperEngine,
    DEFAULT_WHISPER_MODEL,
)


class TestWhisperEngine:
    """Unit and mock tests for Faster-Whisper integration."""

    def test_transcription_result_properties(self) -> None:
        result = TranscriptionResult(
            text="Hello world",
            language="en",
            language_probability=0.98,
            duration_seconds=1.5,
        )
        assert result.text == "Hello world"
        assert result.language == "en"
        assert not result.is_empty

        empty_res = TranscriptionResult(
            text="   ",
            language="en",
            language_probability=0.5,
            duration_seconds=0.2,
        )
        assert empty_res.is_empty

    def test_prepare_audio_normalization(self) -> None:
        engine = WhisperEngine()

        # 2D int16 array
        int_audio = np.array([[1000, 2000, -3000]], dtype=np.int16)
        prepared = engine._prepare_audio(int_audio)
        assert prepared.dtype == np.float32
        assert prepared.ndim == 1
        assert np.max(np.abs(prepared)) <= 1.0

        # Clipped float array > 1.0
        loud_audio = np.array([0.5, 2.0, -2.5], dtype=np.float32)
        norm_audio = engine._prepare_audio(loud_audio)
        assert np.max(np.abs(norm_audio)) <= 1.0

    def test_transcribe_short_audio_returns_empty(self) -> None:
        engine = WhisperEngine()
        # Mock model so we don't reload
        engine._model = object()

        # Audio less than 1600 samples (< 100ms)
        tiny_audio = np.zeros(500, dtype=np.float32)
        res = engine.transcribe(tiny_audio)
        assert res.is_empty
        assert res.duration_seconds < 0.1

    def test_transcribe_with_model(self) -> None:
        from unittest.mock import MagicMock
        engine = WhisperEngine(model_size="tiny", compute_type="int8", device="cpu")
        mock_model = MagicMock()
        mock_seg = MagicMock()
        mock_seg.id = 0
        mock_seg.start = 0.0
        mock_seg.end = 1.0
        mock_seg.text = "Hello world"
        mock_seg.avg_logprob = -0.2
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_model.transcribe.return_value = ([mock_seg], mock_info)
        engine._model = mock_model

        silence = np.zeros(16000, dtype=np.float32)
        result = engine.transcribe(silence)
        assert isinstance(result, TranscriptionResult)
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.duration_seconds == 1.0

    def test_transcribe_async(self, qtbot) -> None:
        from unittest.mock import MagicMock
        engine = WhisperEngine()
        mock_model = MagicMock()
        mock_seg = MagicMock()
        mock_seg.id = 0
        mock_seg.start = 0.0
        mock_seg.end = 0.5
        mock_seg.text = "Async speech"
        mock_seg.avg_logprob = -0.1
        mock_info = MagicMock()
        mock_info.language = "hi"
        mock_info.language_probability = 0.95
        mock_model.transcribe.return_value = ([mock_seg], mock_info)
        engine._model = mock_model

        results = []
        engine.transcribe_async(
            audio_data=np.zeros(8000, dtype=np.float32),
            callback=results.append,
            language="hi",
        )
        qtbot.waitUntil(lambda: len(results) == 1, timeout=3000)
        assert results[0].text == "Async speech"
        assert results[0].language == "hi"

    def test_thank_you_and_bye_preserved(self) -> None:
        from unittest.mock import MagicMock
        engine = WhisperEngine()
        mock_model = MagicMock()
        mock_seg = MagicMock()
        mock_seg.id = 0
        mock_seg.start = 0.0
        mock_seg.end = 1.0
        mock_seg.text = "Thank you."
        mock_seg.no_speech_prob = 0.1
        mock_seg.avg_logprob = -0.1
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_model.transcribe.return_value = ([mock_seg], mock_info)
        engine._model = mock_model

        result = engine.transcribe(np.zeros(16000, dtype=np.float32))
        assert result.text == "Thank you."

        mock_seg.text = "Bye"
        result_bye = engine.transcribe(np.zeros(16000, dtype=np.float32))
        assert result_bye.text == "Bye"

    def test_subtitle_hallucination_filtered(self) -> None:
        from unittest.mock import MagicMock
        engine = WhisperEngine()
        mock_model = MagicMock()
        mock_seg = MagicMock()
        mock_seg.id = 0
        mock_seg.start = 0.0
        mock_seg.end = 1.0
        mock_seg.text = "subtitles by the amara.org community"
        mock_seg.no_speech_prob = 0.1
        mock_seg.avg_logprob = -0.1
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_model.transcribe.return_value = ([mock_seg], mock_info)
        engine._model = mock_model

        result = engine.transcribe(np.zeros(16000, dtype=np.float32))
        assert result.text == ""

    def test_no_speech_prob_threshold(self) -> None:
        from unittest.mock import MagicMock
        engine = WhisperEngine()
        mock_model = MagicMock()
        mock_seg = MagicMock()
        mock_seg.id = 0
        mock_seg.start = 0.0
        mock_seg.end = 1.0
        mock_seg.text = "Quiet speech"
        # 0.75 should NOT be discarded under 0.88 threshold
        mock_seg.no_speech_prob = 0.75
        mock_seg.avg_logprob = -0.3
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_model.transcribe.return_value = ([mock_seg], mock_info)
        engine._model = mock_model

        result = engine.transcribe(np.zeros(16000, dtype=np.float32))
        assert result.text == "Quiet speech"

        # 0.95 should be discarded
        mock_seg.no_speech_prob = 0.95
        result_discarded = engine.transcribe(np.zeros(16000, dtype=np.float32))
        assert result_discarded.text == ""

    def test_load_model_import_error_graceful_handling(self) -> None:
        """Verify that faster_whisper import failure does not trigger UnboundLocalError."""
        from unittest.mock import patch

        engine = WhisperEngine(model_size="base")
        emitted_errors: list[str] = []
        engine.error_occurred.connect(emitted_errors.append)

        # Simulate faster_whisper missing or failing to import
        with patch.dict("sys.modules", {"faster_whisper": None}):
            success = engine.load_model()
            assert success is False
            assert engine._model is None
            assert len(emitted_errors) == 1
            assert "Failed to import Faster-Whisper" in emitted_errors[0]

    def test_load_model_fallback_to_tiny_on_model_load_failure(self) -> None:
        """Verify that when base model load fails, fallback to tiny works without UnboundLocalError."""
        from unittest.mock import MagicMock, patch

        engine = WhisperEngine(model_size="base")
        emitted_models: list[str] = []
        engine.model_loaded.connect(emitted_models.append)

        mock_whisper_module = MagicMock()

        def side_effect(model_size_or_path, **kwargs):
            if model_size_or_path == "base":
                raise RuntimeError("Failed to load base weights")
            mock_tiny = MagicMock()
            mock_tiny.model_size = "tiny"
            return mock_tiny

        mock_whisper_module.WhisperModel.side_effect = side_effect

        with patch.dict("sys.modules", {"faster_whisper": mock_whisper_module}):
            success = engine.load_model()
            assert success is True
            assert engine._model is not None
            assert engine.model_size == "tiny"
            assert emitted_models == ["tiny"]

    def test_load_model_fallback_failure_graceful_handling(self) -> None:
        """Verify that when both primary and fallback model loading fail, it errors gracefully."""
        from unittest.mock import MagicMock, patch

        engine = WhisperEngine(model_size="base")
        emitted_errors: list[str] = []
        engine.error_occurred.connect(emitted_errors.append)

        mock_whisper_module = MagicMock()
        mock_whisper_module.WhisperModel.side_effect = RuntimeError("Out of memory on all models")

        with patch.dict("sys.modules", {"faster_whisper": mock_whisper_module}):
            success = engine.load_model()
            assert success is False
            assert engine._model is None
            assert len(emitted_errors) == 1
            assert "Failed to load Faster-Whisper fallback model" in emitted_errors[0]
