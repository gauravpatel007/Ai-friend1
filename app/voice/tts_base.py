"""Abstract Text-to-Speech (TTS) Engine Interface.

Defines the contract for interchangeable local speech synthesis engines
(Piper TTS, Kokoro TTS, and fallbacks).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


def clean_text_for_speech(text: str) -> str:
    """Preprocess text before TTS synthesis to strip markup, code, and noise."""
    if not text:
        return ""

    # Remove <think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Remove code blocks and inline code
    cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    # Replace markdown links [label](url) with just label
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)

    # Remove raw URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)

    # Remove markdown headers (e.g. ### Header -> Header)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)

    # Remove bold/italic markers (*, **, _, __, ~~)
    cleaned = re.sub(r"(\*\*|__)(.*?)\1", r"\2", cleaned)
    cleaned = re.sub(r"(\*|_)(.*?)\1", r"\2", cleaned)
    cleaned = re.sub(r"~~(.*?)~~", r"\1", cleaned)

    # Remove list bullets and numbered prefixes
    cleaned = re.sub(r"^[\s]*[-*+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^[\s]*\d+\.\s+", "", cleaned, flags=re.MULTILINE)

    # Remove HTML tags (e.g. <br>, <span>, <div>)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)

    # Remove markdown tables (| Col 1 | Col 2 | and |---|---| dividers)
    cleaned = re.sub(r"^[ \t]*\|.*?\|[ \t]*$", " ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\|", " ", cleaned)

    # Remove blockquotes (> quote -> quote)
    cleaned = re.sub(r"^>\s+", "", cleaned, flags=re.MULTILINE)

    # Remove emojis and decorative symbols that sound jarring or garbled when read aloud
    # (keeps Gujarati, Devanagari, Latin, common digits, and basic punctuation)
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned)

    # Collapse repeated whitespace and blank lines
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n", cleaned)

    return cleaned.strip()


@dataclass
class SynthesizedAudio:
    """Container for synthesized audio waveform data."""
    samples: np.ndarray          # 1D float32 numpy array in [-1.0, 1.0]
    sample_rate: int             # Audio sampling rate in Hz (e.g. 22050, 24000)
    duration_seconds: float      # Duration of the synthesized speech in seconds
    text: str                    # Original text prompt synthesized
    voice_name: str              # Identifier of the voice model used

    @property
    def is_empty(self) -> bool:
        return self.samples.size == 0 or self.duration_seconds <= 0.0


class BaseTTSEngine(QObject):
    """Base class for local Text-to-Speech synthesis engines."""

    # Qt Signals for UI/Controller observation
    model_loaded = Signal(str)           # voice_name
    synthesis_started = Signal(str)      # text
    synthesis_completed = Signal(object) # SynthesizedAudio
    error_occurred = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._is_loaded = False
        self._is_synthesizing = False
        self._speed: float = 1.0

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def is_available(self) -> bool:
        """Check whether the TTS engine is installed, available, and ready to synthesize."""
        return self._is_loaded

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = max(0.5, min(2.0, float(value)))

    def load_model(self, voice_name: Optional[str] = None) -> bool:
        """Load or switch the active voice model into memory."""
        raise NotImplementedError("Subclasses must implement load_model()")

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        """Synthesize plain text into a float32 audio waveform synchronously."""
        raise NotImplementedError("Subclasses must implement synthesize()")

    def stop(self) -> None:
        """Cancel ongoing synthesis operations."""
        raise NotImplementedError("Subclasses must implement stop()")

    def unload_model(self) -> None:
        """Unload voice model weights to free RAM/VRAM."""
        raise NotImplementedError("Subclasses must implement unload_model()")

    def get_available_voices(self) -> List[str]:
        """Return a list of available voice identifiers for this engine."""
        raise NotImplementedError("Subclasses must implement get_available_voices()")
