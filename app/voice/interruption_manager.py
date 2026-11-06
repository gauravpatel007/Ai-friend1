"""Interruption Controller and Echo-Aware Speech Discrimination (Phase 9.1 - 9.4).

Manages user interruptions while the AI is speaking. Distinguishes genuine user
speech from acoustic feedback, background noises, keyboard clicks, and speaker echo.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import List, Optional

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

from app.utils.logger import get_logger
from app.voice.audio_player import AudioPlayer
from app.voice.vad_engine import VADEngine

logger = get_logger(__name__)


@dataclass
class InterruptionConfig:
    """Tuning parameters for interruption sensitivity and false-positive rejection."""

    min_speech_duration_sec: float = 0.40          # Minimum sustained utterance (400ms) to trigger interruption
    consecutive_frames_threshold: int = 5          # Require at least 5 consecutive positive VAD frames
    playback_grace_period_sec: float = 0.25        # Ignore mic frames for 250ms immediately after audio starts
    vad_confidence_threshold: float = 0.75         # Elevated VAD probability required while AI is speaking
    echo_mode: str = "speaker"                     # "speaker", "headset", or "auto" (default to speaker for laptops)
    speaker_attenuation_ratio: float = 1.60        # In speaker mode, mic RMS must exceed playback level * ratio
    sample_rate: int = 16000


class InterruptionManager(QObject):
    """Detects and validates user speech interruptions during AI audio playback."""

    # Emitted when a sustained, verified interruption occurs: (turn_id, accumulated_audio)
    interruption_detected = Signal(int, object)

    # Emitted when a transient noise or echo is successfully rejected
    false_interruption_filtered = Signal(str, float)

    # Emitted when echo cancellation profile changes
    echo_mode_changed = Signal(str)

    def __init__(
        self,
        audio_player: AudioPlayer,
        vad_engine: VADEngine,
        config: Optional[InterruptionConfig] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.audio_player = audio_player
        self.vad_engine = vad_engine
        self.config = config or InterruptionConfig()

        self._playback_start_time: float = 0.0
        self._is_ai_speaking: bool = False
        self._current_playback_amplitude: float = 0.0
        self._current_turn_id: int = 0

        # Interruption verification buffer
        self._interruption_chunks: List[np.ndarray] = []
        self._consecutive_speech_frames: int = 0
        self._interruption_onset_time: float = 0.0

        # Wire audio player hooks
        self._wire_audio_player()

    def _wire_audio_player(self) -> None:
        """Connect audio player lifecycle to interruption tracker."""
        self.audio_player.playback_started.connect(self._on_playback_started)
        self.audio_player.playback_finished.connect(self._on_playback_stopped)
        self.audio_player.playback_stopped.connect(self._on_playback_stopped)
        self.audio_player.amplitude_updated.connect(self._on_playback_amplitude_updated)

    @Slot()
    def _on_playback_started(self) -> None:
        """Invoked when AI audio playback begins."""
        self._is_ai_speaking = True
        self._playback_start_time = time.time()
        self.reset()
        logger.debug("InterruptionManager: Playback started; speech monitor armed.")

    @Slot()
    def _on_playback_stopped(self) -> None:
        """Invoked when AI audio playback completes or stops."""
        self._is_ai_speaking = False
        self._playback_start_time = 0.0
        self._current_playback_amplitude = 0.0
        self.reset()
        logger.debug("InterruptionManager: Playback stopped.")

    @Slot(float)
    def _on_playback_amplitude_updated(self, amplitude: float) -> None:
        """Update active output amplitude for acoustic echo compensation."""
        self._current_playback_amplitude = max(0.0, min(1.0, float(amplitude)))

    @property
    def is_ai_speaking(self) -> bool:
        return self._is_ai_speaking or self.audio_player.is_playing

    @property
    def echo_mode(self) -> str:
        return self.config.echo_mode

    def set_echo_mode(self, mode: str) -> None:
        """Select echo handling mode ('headset', 'speaker', 'auto')."""
        cleaned = mode.lower().strip()
        if cleaned in ("headset", "speaker", "auto"):
            self.config.echo_mode = cleaned
            logger.info("InterruptionManager echo mode set to: '%s'", cleaned)
            self.echo_mode_changed.emit(cleaned)

    def reset(self) -> None:
        """Clear partial interruption accumulation state."""
        self._interruption_chunks.clear()
        self._consecutive_speech_frames = 0
        self._interruption_onset_time = 0.0

    def process_mic_frame(self, frame: np.ndarray, turn_id: int) -> bool:
        """Analyze an incoming microphone frame during AI playback.

        Returns True if a confirmed interruption was triggered, False otherwise.
        """
        # If AI is not actively speaking, standard continuous VAD handles it
        if not self.is_ai_speaking:
            if self._consecutive_speech_frames > 0:
                self.reset()
            return False

        now = time.time()

        # 9.3: Playback startup grace period filter
        if (now - self._playback_start_time) < self.config.playback_grace_period_sec:
            return False

        # Calculate microphone frame RMS energy
        mic_rms = float(np.sqrt(np.mean(np.square(frame)))) if frame.size > 0 else 0.0

        # 9.4: Acoustic Echo Handling for Speaker Mode
        if self.config.echo_mode in ("speaker", "auto"):
            # If playing through open speakers and mic energy is low relative to speaker output,
            # it's likely speaker spillover rather than a user trying to talk over the AI.
            threshold_energy = self._current_playback_amplitude * (0.08 * self.config.speaker_attenuation_ratio)
            if self._current_playback_amplitude > 0.15 and mic_rms < threshold_energy:
                if self._consecutive_speech_frames > 0:
                    self.false_interruption_filtered.emit("speaker_echo", mic_rms)
                    self.reset()
                return False

        # 9.3: VAD Confidence Check
        vad_prob = self.vad_engine.get_speech_probability(frame)
        is_speech = vad_prob >= self.config.vad_confidence_threshold

        if not is_speech:
            # If speech paused before reaching minimum duration, reject as transient noise/click
            if self._consecutive_speech_frames > 0:
                duration_so_far = (
                    len(self._interruption_chunks) * len(frame) / float(self.config.sample_rate)
                )
                logger.debug(
                    "Interruption filtered: transient noise/short burst (%.2fs, %d frames).",
                    duration_so_far,
                    self._consecutive_speech_frames,
                )
                self.false_interruption_filtered.emit("transient_noise", duration_so_far)
                self.reset()
            return False

        # Speech frame detected while AI is speaking!
        if self._consecutive_speech_frames == 0:
            self._interruption_onset_time = now

        self._consecutive_speech_frames += 1
        self._interruption_chunks.append(frame.copy())

        accumulated_samples = sum(len(c) for c in self._interruption_chunks)
        accumulated_duration_sec = accumulated_samples / float(self.config.sample_rate)

        # 9.2 & 9.3: Check if sustained utterance criteria is met
        if (
            accumulated_duration_sec >= self.config.min_speech_duration_sec
            and self._consecutive_speech_frames >= self.config.consecutive_frames_threshold
        ):
            # VALID INTERRUPTION DETECTED!
            logger.info(
                "💥 VALID INTERRUPTION DETECTED in turn #%d! Sustained: %.2fs (%d frames, VAD=%.2f, RMS=%.3f)",
                turn_id,
                accumulated_duration_sec,
                self._consecutive_speech_frames,
                vad_prob,
                mic_rms,
            )

            # Combine captured speech so user doesn't lose the first few words of their interruption!
            combined_utterance = np.concatenate(self._interruption_chunks).astype(np.float32)
            self.reset()

            # Emit interruption signal
            self.interruption_detected.emit(turn_id, combined_utterance)
            return True

        return False
