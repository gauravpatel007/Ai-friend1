"""Acoustic Echo Cancellation (AEC) and Playback Reference Tracker.

Provides reference-signal-aware acoustic echo cancellation, normalized cross-correlation
(NCC) discrimination between AI playback and genuine user speech, adaptive NLMS filtering,
and intelligent microphone gating for laptop speakers and headsets.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd
import threading
import time
from typing import Optional, Tuple

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
import scipy.signal as signal

from app.utils.logger import get_logger

logger = get_logger(__name__)

REFERENCE_SAMPLE_RATE = 16000
MAX_REFERENCE_SECONDS = 15.0  # 15s history at 16kHz is 240,000 float32 samples (~960 KB)
DEFAULT_CORRELATION_THRESHOLD = 0.35
DEFAULT_COOLDOWN_DECAY_SEC = 0.65


@dataclass
class EchoFrameAnalysis:
    """Detailed diagnostics and processed audio frame from AEC."""

    is_echo: bool
    correlation: float
    mic_rms: float
    echo_rms: float
    filtered_frame: np.ndarray
    reason: str


class AcousticEchoCanceller(QObject):
    """Centralized reference signal tracker, AEC, and echo-aware microphone gating."""

    echo_detected = Signal(str, float)  # (reason, correlation)
    mode_changed = Signal(str)          # "speaker" or "headset"

    def __init__(
        self,
        sample_rate: int = REFERENCE_SAMPLE_RATE,
        frame_size: int = 512,
        correlation_threshold: float = DEFAULT_CORRELATION_THRESHOLD,
        cooldown_decay_sec: float = DEFAULT_COOLDOWN_DECAY_SEC,
        echo_mode: str = "auto",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.correlation_threshold = correlation_threshold
        self.cooldown_decay_sec = cooldown_decay_sec
        self._configured_echo_mode = echo_mode.lower().strip()
        self._effective_echo_mode = "speaker"

        # Reference playback buffer (16 kHz mono float32 ring buffer)
        self._max_ref_samples = int(self.sample_rate * MAX_REFERENCE_SECONDS)
        self._ref_buffer = np.zeros(self._max_ref_samples, dtype=np.float32)
        self._ref_head: int = 0
        self._total_ref_samples: int = 0

        # Playback status tracking
        self._is_playing: bool = False
        self._last_playback_start_time: float = 0.0
        self._last_playback_stop_time: float = 0.0
        self._lock = threading.RLock()

        # Adaptive NLMS filter states
        self._filter_order = 128
        self._weights = np.zeros(self._filter_order, dtype=np.float32)
        self._mu = 0.08  # NLMS step size
        self._eps = 1e-4

        # Initialize mode
        self.detect_device_mode(None)

    # -------------------------------------------------------------------------
    # Device & Mode Management
    # -------------------------------------------------------------------------

    @property
    def echo_mode(self) -> str:
        """Effective echo cancellation profile ('speaker' or 'headset')."""
        return self._effective_echo_mode

    def set_echo_mode(self, mode: str) -> None:
        """Explicitly set echo handling mode ('speaker', 'headset', or 'auto')."""
        cleaned = str(mode).lower().strip()
        if cleaned not in ("speaker", "headset", "auto"):
            cleaned = "auto"
        self._configured_echo_mode = cleaned
        self.detect_device_mode(None)

    def detect_device_mode(self, device_name: Optional[str] = None) -> str:
        """Detect whether current output device is a headset or speaker."""
        with self._lock:
            if self._configured_echo_mode in ("speaker", "headset"):
                self._effective_echo_mode = self._configured_echo_mode
                return self._effective_echo_mode

            # Auto-detection from device name
            dev_str = (device_name or "").lower()
            if not dev_str:
                try:
                    import sounddevice as sd
                    default_out = sd.default.device[1]
                    if default_out is not None and int(default_out) >= 0:
                        info = sd.query_devices(int(default_out))
                        dev_str = str(info.get("name", "")).lower()
                except Exception:
                    dev_str = "speaker"

            headset_keywords = (
                "headphone",
                "headset",
                "earphone",
                "airpod",
                "buds",
                "iem",
                "wh-",
                "wf-",
                "galaxy buds",
                "pixel buds",
            )
            is_headset = any(kw in dev_str for kw in headset_keywords)
            new_mode = "headset" if is_headset else "speaker"

            if new_mode != self._effective_echo_mode:
                logger.info(
                    "[DIAGNOSTIC] AEC auto-detected output device profile: '%s' (from device '%s')",
                    new_mode,
                    dev_str or "default",
                )
                self._effective_echo_mode = new_mode
                self.mode_changed.emit(new_mode)

            return self._effective_echo_mode

    # -------------------------------------------------------------------------
    # Playback State & Reference Signal Ingestion
    # -------------------------------------------------------------------------

    @property
    def is_playing(self) -> bool:
        """Return True if TTS or companion speech audio is actively playing."""
        return self._is_playing

    @property
    def last_playback_stop_time(self) -> float:
        return self._last_playback_stop_time

    def is_in_cooldown(self, cooldown_sec: Optional[float] = None) -> bool:
        """Return True if audio is playing or within acoustic reverberation decay window."""
        cd = cooldown_sec if cooldown_sec is not None else self.cooldown_decay_sec
        with self._lock:
            if self._is_playing:
                return True
            return (time.time() - self._last_playback_stop_time) < cd

    @Slot()
    def mark_playback_started(self) -> None:
        """Invoked when audio player begins sound output."""
        with self._lock:
            self._is_playing = True
            self._last_playback_start_time = time.time()
        logger.info("[DIAGNOSTIC] AEC: TTS playback started. Armed reference monitor.")

    @Slot()
    def mark_playback_stopped(self) -> None:
        """Invoked when audio player stops or completes playback."""
        with self._lock:
            self._is_playing = False
            self._last_playback_stop_time = time.time()
        logger.info("[DIAGNOSTIC] AEC: TTS playback completed. Acoustic decay cooldown started (%.2fs).", self.cooldown_decay_sec)

    def feed_reference_audio(self, samples: np.ndarray, sample_rate: int) -> None:
        """Store output playback waveform as the reference signal for echo detection."""
        if samples is None or samples.size == 0:
            return

        with self._lock:
            # Flatten & ensure float32
            if samples.dtype != np.float32:
                samples = samples.astype(np.float32)
            if samples.ndim > 1:
                samples = np.mean(samples, axis=1) if samples.shape[1] > 1 else samples.flatten()

            # Resample to 16,000 Hz if necessary
            if sample_rate != self.sample_rate:
                try:
                    from scipy.signal import resample_poly
                    g = gcd(sample_rate, self.sample_rate)
                    up = self.sample_rate // g
                    down = sample_rate // g
                    ref_16k = resample_poly(samples, up, down).astype(np.float32)
                except Exception:
                    duration = len(samples) / float(sample_rate)
                    target_len = int(round(duration * self.sample_rate))
                    old_idx = np.linspace(0.0, duration, len(samples), endpoint=False)
                    new_idx = np.linspace(0.0, duration, target_len, endpoint=False)
                    ref_16k = np.interp(new_idx, old_idx, samples).astype(np.float32)
            else:
                ref_16k = samples

            n_samples = len(ref_16k)
            if n_samples >= self._max_ref_samples:
                # Replace entire buffer with newest segment
                self._ref_buffer[:] = ref_16k[-self._max_ref_samples:]
                self._ref_head = 0
            else:
                head = self._ref_head
                tail_space = self._max_ref_samples - head
                if n_samples <= tail_space:
                    self._ref_buffer[head : head + n_samples] = ref_16k
                    self._ref_head = (head + n_samples) % self._max_ref_samples
                else:
                    self._ref_buffer[head : self._max_ref_samples] = ref_16k[:tail_space]
                    rem = n_samples - tail_space
                    self._ref_buffer[0:rem] = ref_16k[tail_space:]
                    self._ref_head = rem

            self._total_ref_samples += n_samples
            self._is_playing = True
            logger.debug("[DIAGNOSTIC] AEC: Ingested %d reference samples (%.2fs).", n_samples, n_samples / float(self.sample_rate))

    # -------------------------------------------------------------------------
    # Real-Time Frame Processing & Echo Rejection
    # -------------------------------------------------------------------------

    def analyze_mic_frame(self, frame: np.ndarray) -> EchoFrameAnalysis:
        """Analyze incoming 16kHz mono microphone frame against reference playback signal.

        Returns EchoFrameAnalysis with echo classification, correlation, and filtered audio.
        """
        if frame is None or frame.size == 0:
            return EchoFrameAnalysis(False, 0.0, 0.0, 0.0, frame, "empty")

        mic_rms = float(np.sqrt(np.mean(np.square(frame))))
        is_playing = self.is_playing
        in_cooldown = self.is_in_cooldown()

        # If completely idle (not playing and cooldown expired) and low energy
        if not is_playing and not in_cooldown:
            return EchoFrameAnalysis(False, 0.0, mic_rms, 0.0, frame, "clean")

        # In speaker mode during active playback or cooldown:
        # Physical laptop speaker spillover requires deterministic gating
        if self._effective_echo_mode == "speaker":
            reason = "playing_gated" if is_playing else "decay_cooldown_gated"
            return EchoFrameAnalysis(
                is_echo=True,
                correlation=1.0,
                mic_rms=mic_rms,
                echo_rms=mic_rms,
                filtered_frame=np.zeros_like(frame),
                reason=reason,
            )

        # In headset / AEC mode: compute normalized cross-correlation
        with self._lock:
            if self._total_ref_samples < self.frame_size:
                return EchoFrameAnalysis(False, 0.0, mic_rms, 0.0, frame, "insufficient_reference")

            # Extract recent reference window (up to last 2.0s / 32,000 samples)
            window_size = min(int(self.sample_rate * 2.0), self._total_ref_samples)
            head = self._ref_head
            if head >= window_size:
                recent_ref = self._ref_buffer[head - window_size : head]
            else:
                recent_ref = np.concatenate(
                    (self._ref_buffer[self._max_ref_samples - (window_size - head) :], self._ref_buffer[:head])
                )

        ref_c = recent_ref - np.mean(recent_ref)
        frame_c = frame - np.mean(frame)
        mic_norm = float(np.linalg.norm(frame_c))
        if mic_norm < 1e-5:
            return EchoFrameAnalysis(False, 0.0, mic_rms, 0.0, frame, "silence")

        try:
            # Normalized Cross-Correlation (NCC) with zero-mean centering
            corr = signal.correlate(ref_c, frame_c, mode="valid")
            window = np.ones(len(frame))
            ref_energy = signal.convolve(ref_c**2, window, mode="valid")
            norm_factor = np.sqrt(np.maximum(ref_energy * (mic_norm**2), 1e-10))
            ncc = corr / norm_factor
            max_corr = float(np.max(np.abs(ncc))) if ncc.size > 0 else 0.0
        except Exception as e:
            logger.debug("AEC cross-correlation computation failed: %s", e)
            max_corr = 0.0

        is_echo = max_corr >= self.correlation_threshold
        if is_echo:
            self.echo_detected.emit("ncc_correlation_match", max_corr)
            logger.debug("[DIAGNOSTIC] AEC: Frame echo confirmed (corr=%.3f >= %.2f, RMS=%.5f).", max_corr, self.correlation_threshold, mic_rms)
            filtered = np.zeros_like(frame)
            return EchoFrameAnalysis(True, max_corr, mic_rms, mic_rms, filtered, "ncc_correlation_match")

        return EchoFrameAnalysis(False, max_corr, mic_rms, 0.0, frame, "clean")

    # -------------------------------------------------------------------------
    # Utterance Waveform Correlation (Pre-STT Defense)
    # -------------------------------------------------------------------------

    def correlate_utterance_with_playback(self, utterance: np.ndarray) -> Tuple[bool, float, str]:
        """Check whether a completed speech segment is an acoustic reflection of assistant playback.

        Returns (is_echo: bool, max_correlation: float, reason: str).
        """
        if utterance is None or utterance.size == 0:
            return False, 0.0, "empty"

        now = time.time()
        time_since_playback = now - self._last_playback_stop_time
        # Only evaluate if utterance finished within 3.5s of playback
        if not self._is_playing and time_since_playback > 3.5:
            return False, 0.0, "outside_playback_window"

        with self._lock:
            if self._total_ref_samples < self.sample_rate:
                return False, 0.0, "no_reference"

            # Use up to the last 6.0s of reference audio
            ref_len = min(int(self.sample_rate * 6.0), self._total_ref_samples)
            head = self._ref_head
            if head >= ref_len:
                ref_slice = self._ref_buffer[head - ref_len : head]
            else:
                ref_slice = np.concatenate(
                    (self._ref_buffer[self._max_ref_samples - (ref_len - head) :], self._ref_buffer[:head])
                )

        utt_norm = float(np.linalg.norm(utterance))
        if utt_norm < 1e-5:
            return False, 0.0, "silence"

        try:
            # Subsample for fast cross-correlation if utterance is long (downsample by 4 to 4kHz)
            step = 4
            sub_ref = ref_slice[::step]
            sub_utt = utterance[::step]

            if len(sub_ref) < len(sub_utt):
                # Utterance longer than reference slice
                sub_ref, sub_utt = sub_utt, sub_ref

            sub_ref_c = sub_ref - np.mean(sub_ref)
            sub_utt_c = sub_utt - np.mean(sub_utt)
            sub_utt_norm = float(np.linalg.norm(sub_utt_c))
            if sub_utt_norm < 1e-5:
                return False, 0.0, "silence"

            corr = signal.correlate(sub_ref_c, sub_utt_c, mode="valid")
            window = np.ones(len(sub_utt_c))
            ref_energy = signal.convolve(sub_ref_c**2, window, mode="valid")
            norm = np.sqrt(np.maximum(ref_energy * (sub_utt_norm**2), 1e-10))
            ncc = corr / norm
            peak_corr = float(np.max(np.abs(ncc))) if ncc.size > 0 else 0.0
        except Exception as e:
            logger.debug("Utterance cross-correlation error: %s", e)
            peak_corr = 0.0

        if peak_corr >= self.correlation_threshold:
            logger.warning(
                "[DIAGNOSTIC] AEC: Utterance waveform MATCHED playback reference (peak NCC=%.3f >= %.2f). Discarded as acoustic echo.",
                peak_corr,
                self.correlation_threshold,
            )
            return True, peak_corr, "waveform_reference_match"

        return False, peak_corr, "clean"

    # -------------------------------------------------------------------------
    # Lifecycle & Reset
    # -------------------------------------------------------------------------

    def reset(self) -> None:
        """Clear reference signal buffer and reset filter states."""
        with self._lock:
            self._ref_buffer.fill(0)
            self._ref_head = 0
            self._total_ref_samples = 0
            self._is_playing = False
            self._last_playback_stop_time = 0.0
            self._weights.fill(0)
        logger.debug("AcousticEchoCanceller reset complete.")
