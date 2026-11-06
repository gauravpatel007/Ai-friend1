"""Tests for Bug #19: KokoroTTSEngine Emits Duplicate synthesis_completed Signal When Delegating to Fallback Engine.

Verifies:
1. When Kokoro model is missing and delegates to fallback_engine, Kokoro does NOT emit synthesis_completed.
2. When Kokoro runtime synthesis throws an exception and delegates to fallback_engine, Kokoro does NOT emit synthesis_completed.
3. When Kokoro synthesizes successfully without fallback, Kokoro emits synthesis_completed exactly once.
4. Fallback engine (Piper / Sapi5 / Mock) emits its own synthesis_completed signal without duplication.
5. PiperTTSEngine also delegates to fallback without duplicate synthesis_completed emission.
"""

from unittest.mock import MagicMock
import numpy as np
import pytest

from app.voice.kokoro_engine import KokoroTTSEngine
from app.voice.piper_engine import PiperTTSEngine
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio


class SpyFallbackEngine(BaseTTSEngine):
    """Fallback engine tracking synthesis calls and signal emissions."""

    def __init__(self, sample_rate: int = 22050):
        super().__init__()
        self.sample_rate = sample_rate
        self.calls = []
        self._is_loaded = True

    def is_available(self) -> bool:
        return True

    def load_model(self, voice_name=None) -> bool:
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        self.calls.append(text)
        audio = SynthesizedAudio(
            samples=np.zeros(1000, dtype=np.float32),
            sample_rate=self.sample_rate,
            duration_seconds=0.1,
            text=text,
            voice_name="spy_fallback",
        )
        self.synthesis_completed.emit(audio)
        return audio

    def stop(self) -> None:
        pass

    def unload_model(self) -> None:
        pass

    def get_available_voices(self) -> list[str]:
        return ["spy_fallback"]


def test_kokoro_missing_model_fallback_no_duplicate_signal(tmp_path, monkeypatch):
    """When Kokoro model weights are missing, delegating to fallback must not double-emit synthesis_completed."""
    fallback = SpyFallbackEngine()
    kokoro = KokoroTTSEngine(models_dir=tmp_path / "empty_kokoro", fallback_engine=fallback)
    monkeypatch.setattr(kokoro, "download_model_if_needed", lambda: False)

    kokoro_events = []
    fallback_events = []
    kokoro.synthesis_completed.connect(kokoro_events.append)
    fallback.synthesis_completed.connect(fallback_events.append)

    audio = kokoro.synthesize("Fallback test")

    assert audio.voice_name == "spy_fallback"
    assert len(fallback.calls) == 1
    # Fallback engine emitted its completion
    assert len(fallback_events) == 1
    # Kokoro must NOT emit duplicate signal
    assert len(kokoro_events) == 0


def test_kokoro_exception_fallback_no_duplicate_signal():
    """When Kokoro._kokoro.create() raises an exception and delegates to fallback, Kokoro must not double-emit."""
    fallback = SpyFallbackEngine()
    kokoro = KokoroTTSEngine(fallback_engine=fallback)

    mock_session = MagicMock()
    mock_session.create.side_effect = RuntimeError("ONNX inference crash")
    mock_session.get_voices.return_value = ["af_bella"]
    kokoro._kokoro = mock_session
    kokoro._is_loaded = True

    kokoro_events = []
    fallback_events = []
    kokoro.synthesis_completed.connect(kokoro_events.append)
    fallback.synthesis_completed.connect(fallback_events.append)

    audio = kokoro.synthesize("Crash and fallback")

    assert audio.voice_name == "spy_fallback"
    assert len(fallback.calls) == 1
    assert len(fallback_events) == 1
    # Kokoro must NOT emit duplicate signal
    assert len(kokoro_events) == 0


def test_kokoro_successful_synthesis_emits_signal_once():
    """When Kokoro succeeds natively, Kokoro emits synthesis_completed exactly once."""
    fallback = SpyFallbackEngine()
    kokoro = KokoroTTSEngine(fallback_engine=fallback)

    mock_session = MagicMock()
    mock_session.create.return_value = (np.zeros(2400, dtype=np.float32), 24000)
    mock_session.get_voices.return_value = ["af_bella"]
    kokoro._kokoro = mock_session
    kokoro._is_loaded = True

    kokoro_events = []
    fallback_events = []
    kokoro.synthesis_completed.connect(kokoro_events.append)
    fallback.synthesis_completed.connect(fallback_events.append)

    audio = kokoro.synthesize("Native synthesis")

    assert audio.voice_name == "af_bella"
    assert len(fallback.calls) == 0
    assert len(fallback_events) == 0
    # Kokoro emitted exactly once
    assert len(kokoro_events) == 1


def test_piper_fallback_no_duplicate_signal(tmp_path, monkeypatch):
    """When Piper model is missing and delegates to fallback, Piper must not double-emit synthesis_completed."""
    fallback = SpyFallbackEngine()
    piper = PiperTTSEngine(models_dir=tmp_path / "empty_piper", fallback_engine=fallback)
    monkeypatch.setattr(piper, "download_voice_if_needed", lambda voice_name: False)

    piper_events = []
    fallback_events = []
    piper.synthesis_completed.connect(piper_events.append)
    fallback.synthesis_completed.connect(fallback_events.append)

    audio = piper.synthesize("Piper fallback test")

    assert audio.voice_name == "spy_fallback"
    assert len(fallback.calls) == 1
    assert len(fallback_events) == 1
    # Piper must NOT emit duplicate signal
    assert len(piper_events) == 0
