"""Wake-Word Detection Engine and Standby Lifecycle Manager (Phase 9.5 - 9.7).

Provides ultra-lightweight, hands-free keyword activation ('Hey Buddy') with
standby mode, inactivity timeout, and seamless fallback for offline operation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_WAKE_WORDS = [
    "hey_buddy", "hey buddy", "hey, buddy", "hi buddy", "hello buddy", "ok buddy", "okay buddy",
    "hey bond", "hey, bond", "hi bond", "hello bond", "ok bond", "okay bond",
    "wake up", "wake up buddy", "wake up, buddy", "buddy wake up", "buddy, wake up",
    "wake up bond", "wake up, bond", "bond wake up", "bond, wake up",
    "rise and shine", "are you awake",
    "i'm talking to you", "im talking to you", "i am talking to you",
    "i'm talking to you buddy", "i'm talking to you, buddy", "i am talking to you buddy",
    "i'm talking to you bond", "i'm talking to you, bond", "i am talking to you bond",
    "buddy are you there", "buddy, are you there", "are you there buddy", "are you there",
    "bond are you there", "bond, are you there", "are you there bond",
    "come back", "come back buddy", "come back, buddy", "come back bond", "come back, bond",
    "start listening", "resume listening",
    "activate buddy", "activate bond",
    "हे बडी", "अरे बडी", "सुनो बडी", "जाग जाओ", "उठो", "सुनना शुरू करो",
    "હે બડી", "એલા બડી", "સાંભળ બડી", "જાગી જા", "જાાગ જાઓ", "ઊઠ", "ઉઠો", "સાંભળવાનું શરૂ કર",
]

WAKE_WORD_PATTERN = re.compile(
    r"^(?:hey|hi|hello|ok|okay)\s+(?:buddy|bond|friend|assistant)\b|"
    r"^(?:buddy|bond)\s*,\s*(?:wake\s*up|are\s*you\s*there)\b|"
    r"^(?:buddy|bond)$|"
    r"\b(?:wake\s*up(?:\s*(?:buddy|bond|friend|assistant))?|"
    r"(?:buddy|bond|friend|assistant)\s*wake\s*up|"
    r"rise\s*and\s*shine|are\s*you\s*awake|"
    r"(?:buddy|bond|friend|assistant)\s*are\s*you\s*there|"
    r"are\s*you\s*there(?:\s*(?:buddy|bond|friend|assistant))?|"
    r"(?:i\s*m|i\s*am)\s*talking\s*to\s*you(?:\s*(?:buddy|bond|friend|assistant))?|"
    r"come\s*back(?:\s*(?:buddy|bond|friend|assistant))?|"
    r"(?:start|resume)\s*listening|"
    r"activate\s+(?:buddy|bond|friend|assistant)|^activate$)\b|"
    r"(हे\s*बडी|अरे\s*बडी|सुनो\s*बडी|जाग\s*जाओ|उठो|सुनना\s*शुरू\s*करो)|"
    r"(હે\s*બડી|એલા\s*બડી|સાંભળ\s*બડી|જાગી\s*જા|જાાગ\s*જાઓ|ઊઠ|ઉઠો|સાંભળવાનું\s*શરૂ\s*કર)",
    re.IGNORECASE,
)

DEFAULT_ACTIVATION_THRESHOLD = 0.70
DEFAULT_INACTIVITY_TIMEOUT_SEC = 15.0


@dataclass
class WakeWordConfig:
    """Configuration options for wake-word engine."""

    activation_phrase: str = "hey_bond"
    threshold: float = DEFAULT_ACTIVATION_THRESHOLD
    inactivity_timeout_sec: float = DEFAULT_INACTIVITY_TIMEOUT_SEC
    sample_rate: int = 16000
    chunk_size: int = 1280  # 80ms at 16kHz
    allow_energy_trigger: bool = False  # Strict mode: never wake on acoustic noise alone


class WakeWordEngine(QObject):
    """Detects keyword triggers and manages the wake-word standby conversation lifecycle."""

    # Emitted when the wake phrase is recognized: (phrase_name, confidence_score)
    wake_word_detected = Signal(str, float)

    # Emitted when transitioning to/from low-power standby mode
    standby_entered = Signal()
    standby_exited = Signal()

    # Emitted when user inactivity causes auto-return to standby
    inactivity_timeout = Signal()

    # Diagnostics
    score_updated = Signal(str, float)
    error_occurred = Signal(str)

    def __init__(
        self,
        config: Optional[WakeWordConfig] = None,
        whisper_engine: Optional[Any] = None,
        vad_engine: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config or WakeWordConfig()
        self.whisper_engine = whisper_engine
        self.vad_engine = vad_engine
        self._custom_wake_phrases: List[str] = []

        self._is_standby: bool = False
        self._is_enabled: bool = False
        self._model = None
        self._is_loaded: bool = False
        self._backend: str = "fallback"  # "openwakeword", "whisper_phonetic", or "fallback"

        # Buffer to accumulate incoming 16kHz samples up to chunk_size (1280 samples)
        self._audio_buffer: list[float] = []

        # Buffer to accumulate speech frames for phonetic wake-word detection
        self._speech_buffer: list[float] = []
        self._silence_frames: int = 0

        # Inactivity countdown timer
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.timeout.connect(self._on_inactivity_timeout)

        # Recent detection debounce to avoid rapid double-triggers
        self._last_detection_time: float = 0.0
        self._debounce_period_sec: float = 2.0

        # Attempt to load model
        self.is_speaking: bool = False
        self.audio_player_is_playing: bool = False
        self.allow_energy_trigger: bool = getattr(self.config, "allow_energy_trigger", False)
        self._init_backend()
        logger.info("[WAKE_WORD_ENGINE] Initialized in SLEEP/STANDBY mode for activation phrase '%s'.", self.config.activation_phrase)

    def set_engines(
        self,
        whisper_engine: Optional[object] = None,
        vad_engine: Optional[object] = None,
    ) -> None:
        """Attach or update Whisper STT and VAD engines for phonetic wake-word recognition."""
        if whisper_engine is not None:
            self.whisper_engine = whisper_engine
            if self._backend == "fallback":
                self._backend = "whisper_phonetic"
        if vad_engine is not None:
            self.vad_engine = vad_engine

    def _init_backend(self) -> None:
        """Attempt to load openWakeWord model or configure phonetic whisper keyword spotting."""
        try:
            import openwakeword
            from openwakeword.model import Model

            # Check if any pretrained openWakeWord models are available
            try:
                self._model = Model(wakeword_models=[self.config.activation_phrase])
                self._backend = "openwakeword"
                self._is_loaded = True
                logger.info("OpenWakeWord model initialized for '%s'.", self.config.activation_phrase)
                return
            except Exception as e:
                logger.debug(
                    "OpenWakeWord models not locally cached (%s); using resilient phonetic keyword engine.",
                    e,
                )
        except ImportError:
            logger.debug("openwakeword library not found; using resilient phonetic keyword engine.")

        if self.whisper_engine is not None:
            self._backend = "whisper_phonetic"
        else:
            self._backend = "fallback"
        self._is_loaded = True

    @property
    def is_standby(self) -> bool:
        return self._is_standby

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def activation_phrase(self) -> str:
        return self.config.activation_phrase

    def set_activation_phrase(self, phrase: str) -> None:
        """Update target activation phrase (e.g. 'hey_buddy', 'buddy')."""
        self.config.activation_phrase = phrase.lower().strip()
        self._init_backend()

    def set_threshold(self, threshold: float) -> None:
        """Set detection confidence threshold between 0.1 and 1.0."""
        self.config.threshold = max(0.1, min(1.0, float(threshold)))

    # ─── Lifecycle & Standby Mode (Phase 9.6 & 9.7) ─────────────────────

    def enable(self) -> None:
        """Enable wake-word engine and enter standby mode."""
        self._is_enabled = True
        self.enter_standby()

    def disable(self) -> None:
        """Disable wake-word engine and stop timers."""
        self._is_enabled = False
        self._inactivity_timer.stop()
        self._audio_buffer.clear()
        self._speech_buffer.clear()
        self._silence_frames = 0
        if self._is_standby:
            self._is_standby = False
            self.standby_exited.emit()

    def enter_standby(self) -> None:
        """Enter low-power standby mode awaiting activation phrase."""
        if not self._is_enabled:
            return

        self._is_standby = True
        self._audio_buffer.clear()
        self._speech_buffer.clear()
        self._silence_frames = 0
        self._inactivity_timer.stop()
        logger.info("WakeWordEngine entered STANDBY mode. Listening for '%s'...", self.config.activation_phrase)
        self.standby_entered.emit()

    def exit_standby(self) -> None:
        """Exit standby mode upon activation and start inactivity countdown."""
        if not self._is_standby:
            return

        self._is_standby = False
        logger.info("WakeWordEngine exited STANDBY mode. Active dialogue engaged.")
        self.standby_exited.emit()
        self.reset_inactivity_timer()

    def reset_inactivity_timer(self) -> None:
        """Reset countdown timer on user interaction (speech or turn)."""
        if self._is_enabled and not self._is_standby:
            timeout_ms = int(self.config.inactivity_timeout_sec * 1000)
            self._inactivity_timer.start(timeout_ms)

    def pause_inactivity_timer(self) -> None:
        """Pause countdown while AI is thinking or speaking."""
        self._inactivity_timer.stop()

    @Slot()
    def _on_inactivity_timeout(self) -> None:
        """User remained silent past the inactivity timeout; return to standby."""
        logger.info(
            "Wake-word inactivity timeout (%.1fs elapsed). Returning to STANDBY.",
            self.config.inactivity_timeout_sec,
        )
        self.inactivity_timeout.emit()
        self.enter_standby()

    def is_wake_phrase(self, text: Optional[str] = None) -> bool:
        """Check if candidate text matches any primary wake command or variation (Phase 5)."""
        # Support invocation both as instance method and class method: WakeWordEngine.is_wake_phrase(text)
        if text is None and isinstance(self, str):
            text = self
            self = None

        if not text or not text.strip():
            return False
        clean = text.strip().lower()
        clean = re.sub(r"[,;:\'\"\-_?.]+", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        # Reject long unrelated conversational queries unless they start with a wake invocation
        words = clean.split()
        if len(words) > 7 and not clean.startswith(("hey buddy", "hey bond", "wake up")):
            return False

        if WAKE_WORD_PATTERN.search(clean):
            return True

        # Check whole-phrase or prefix matching against default wake phrases
        for w in DEFAULT_WAKE_WORDS:
            clean_w = w.replace("_", " ")
            if clean == clean_w or clean.startswith(clean_w + " "):
                return True

        if self is not None and hasattr(self, "_custom_wake_phrases"):
            for cw in self._custom_wake_phrases:
                clean_cw = cw.replace("_", " ")
                if clean == clean_cw or clean.startswith(clean_cw + " "):
                    return True

        if self is not None and hasattr(self, "config") and getattr(self.config, "activation_phrase", None):
            act_phrase = self.config.activation_phrase.replace("_", " ")
            if clean == act_phrase or clean.startswith(act_phrase + " "):
                return True

        return False

    def load_configuration(self, config_manager: Optional[Any] = None) -> None:
        """Sync custom wake words from config manager into wake detector (Phase 5)."""
        if not config_manager or not hasattr(config_manager, "get"):
            return
        wake_words = config_manager.get("voice.custom_wake_words", [])
        if wake_words and isinstance(wake_words, list):
            for w in wake_words:
                clean_w = str(w).strip().lower()
                if clean_w and clean_w not in self._custom_wake_phrases:
                    self._custom_wake_phrases.append(clean_w)

    # ─── Audio Stream Processing (Phase 9.5) ────────────────────────────

    def process_frame(self, frame: np.ndarray) -> bool:
        """Feed incoming audio frame to wake-word model while in standby.

        Returns True if the wake phrase was detected, False otherwise.
        """
        if not self._is_enabled or not self._is_standby:
            return False

        # Suppress wake-word detection during TTS playback to prevent self-voice activation
        if getattr(self, "is_speaking", False) or getattr(self, "audio_player_is_playing", False):
            return False

        samples = frame.flatten()
        if samples.size == 0:
            return False

        now = time.time()
        # Fast exit if within debounce period
        if (now - self._last_detection_time) <= self._debounce_period_sec:
            return False

        # 1. Test mock override support
        if hasattr(self, "_test_mock_score"):
            score = float(self._test_mock_score)
            self.score_updated.emit(self.config.activation_phrase, score)
            if score >= self.config.threshold:
                self._last_detection_time = now
                self.wake_word_detected.emit(self.config.activation_phrase, score)
                self.exit_standby()
                return True
            return False

        # Calculate frame RMS energy
        rms = float(np.sqrt(np.mean(np.square(samples))))

        # 2. Synthetic acoustic burst trigger ONLY if allow_energy_trigger is explicitly enabled
        if getattr(self.config, "allow_energy_trigger", False) or getattr(self, "allow_energy_trigger", False):
            if rms >= 0.25:
                score = 0.85
                self.score_updated.emit(self.config.activation_phrase, score)
                self._last_detection_time = now
                logger.info("🎯 WAKE WORD TRIGGERED (test acoustic energy mock): score=%.2f", score)
                self.wake_word_detected.emit(self.config.activation_phrase, score)
                self.exit_standby()
                return True

        # 3. Phonetic Speech Keyword Detection via Whisper
        if self.whisper_engine is not None:
            is_speech = False
            if self.vad_engine is not None and hasattr(self.vad_engine, "is_speech"):
                try:
                    is_speech = bool(self.vad_engine.is_speech(samples))
                except Exception:
                    is_speech = rms >= 0.015
            else:
                is_speech = rms >= 0.015

            if is_speech:
                self._speech_buffer.extend(samples.tolist())
                self._silence_frames = 0
            elif len(self._speech_buffer) > 0:
                self._silence_frames += 1
                self._speech_buffer.extend(samples.tolist())

            buf_len = len(self._speech_buffer)
            # Evaluate buffer if:
            # - Speech (>0.35s / 5600 samples) followed by silence pause (>= 3 frames / ~150-200ms)
            # - Or speech duration reaches maximum phrase window (1.8s / 28800 samples)
            should_transcribe = (
                (buf_len >= 5600 and self._silence_frames >= 3)
                or (buf_len >= 28800)
            )

            if should_transcribe:
                speech_data = np.array(self._speech_buffer, dtype=np.float32)
                self._speech_buffer.clear()
                self._silence_frames = 0

                try:
                    res = self.whisper_engine.transcribe(speech_data, beam_size=1)
                    raw_text = getattr(res, "text", "") or ""
                    clean_text = raw_text.strip().lower()

                    if clean_text:
                        logger.debug("WakeWord phonetic candidate: '%s'", clean_text)
                        if self.is_wake_phrase(clean_text):
                            score = 0.95
                            self.score_updated.emit(self.config.activation_phrase, score)
                            self._last_detection_time = now
                            logger.info(
                                "🎯 WAKE WORD DETECTED (phonetic): '%s' -> phrase='%s' (score=%.2f)",
                                clean_text,
                                self.config.activation_phrase,
                                score,
                            )
                            self.wake_word_detected.emit(self.config.activation_phrase, score)
                            self.exit_standby()
                            return True
                except Exception as e:
                    logger.debug("Error during wake-word phonetic transcription: %s", e)

        # 4. OpenWakeWord model processing if active
        if self._backend == "openwakeword" and self._model is not None:
            self._audio_buffer.extend(samples.tolist())
            while len(self._audio_buffer) >= self.config.chunk_size:
                chunk = np.array(self._audio_buffer[: self.config.chunk_size], dtype=np.float32)
                self._audio_buffer = self._audio_buffer[self.config.chunk_size :]
                score = self._predict_chunk(chunk)
                self.score_updated.emit(self.config.activation_phrase, score)
                if score >= self.config.threshold and (now - self._last_detection_time) > self._debounce_period_sec:
                    self._last_detection_time = now
                    self.wake_word_detected.emit(self.config.activation_phrase, score)
                    self.exit_standby()
                    return True

        return False

    def _predict_chunk(self, chunk: np.ndarray) -> float:
        """Run inference on single 80ms chunk."""
        if self._backend == "openwakeword" and self._model is not None:
            try:
                # openWakeWord expects 16-bit PCM integer samples
                pcm16 = (chunk * 32767.0).astype(np.int16)
                prediction = self._model.predict(pcm16)
                # prediction is a dictionary of {model_name: score}
                for model_key, score in prediction.items():
                    if any(w in model_key.lower() for w in DEFAULT_WAKE_WORDS):
                        return float(score)
                # Return maximum score
                if prediction:
                    return float(max(prediction.values()))
            except Exception as e:
                logger.debug("OpenWakeWord prediction error: %s", e)

        # Resilient acoustic trigger / unit test mock
        if hasattr(self, "_test_mock_score"):
            return float(self._test_mock_score)

        # In fallback mode, evaluate acoustic signature energy ONLY if allow_energy_trigger is enabled
        if getattr(self.config, "allow_energy_trigger", False) or getattr(self, "allow_energy_trigger", False):
            rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size > 0 else 0.0
            if rms >= 0.25:
                return 0.85
        return 0.0

    def trigger_manually(self, phrase: Optional[str] = None, score: float = 0.95) -> None:
        """Manually trigger wake word for testing or shortcut activation."""
        target_phrase = phrase or self.config.activation_phrase
        self._last_detection_time = time.time()
        logger.info("Manual wake-word trigger: '%s' (score=%.2f)", target_phrase, score)
        self.wake_word_detected.emit(target_phrase, score)
        self.exit_standby()
