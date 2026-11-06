"""Voice Activity Detection (VAD) Engine.

Distinguishes speech from silence using Silero VAD (with ONNX/PyTorch or adaptive
spectral energy fallback), detects speech onset with pre-roll buffering, and identifies
speech completion with configurable silence thresholds.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
import math
import os
from pathlib import Path
import threading
from typing import Deque, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QObject, Signal

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Audio sample rate required by Silero VAD
VAD_SAMPLE_RATE = 16000
# Silero VAD standard chunk size: 512 samples (32 ms)
VAD_FRAME_SIZE = 512


class VADState(Enum):
    SILENCE = "silence"
    TRIGGERING = "triggering"   # consecutive speech frames accumulating
    SPEAKING = "speaking"       # active speech confirmed


class VADEngine(QObject):
    """Voice Activity Detector with speech onset & end-of-speech state machine."""

    speech_started = Signal()
    speech_ended = Signal(np.ndarray)  # Emits complete utterance (1D float32 array)
    vad_probability = Signal(float)    # Current frame speech probability (0.0 to 1.0)
    no_speech_detected = Signal(str)   # Emitted when utterance has no valid speech
    recording_completed = Signal(float) # Emitted when utterance capture completes (duration in seconds)

    def __init__(
        self,
        sample_rate: int = VAD_SAMPLE_RATE,
        frame_size: int = VAD_FRAME_SIZE,
        speech_threshold: float = 0.5,
        min_speech_frames: int = 3,          # ~96 ms consecutive speech to trigger
        silence_threshold_ms: int = 400,      # Snappy 400ms conversational turn-taking pause
        pre_roll_ms: int = 320,              # ~320 ms pre-buffer before speech onset
        min_utterance_ms: int = 120,          # Minimum speech duration to prevent mouth clicks (120ms)
        max_utterance_ms: int = 12000,        # Maximum speech duration safety cutoff (12s, before 15s watchdog)
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.speech_threshold = speech_threshold
        self.min_speech_frames = min_speech_frames
        self.silence_threshold_ms = silence_threshold_ms
        self.pre_roll_ms = pre_roll_ms
        self.min_utterance_ms = min_utterance_ms
        self.max_utterance_ms = max_utterance_ms

        # Phase 6: Natural Conversational Turn-Taking & Dynamic Pause Handling (6.1 & 6.5)
        self._ambient_noise_rms: float = 0.005
        self._has_trailing_connector: bool = False
        self._is_thinking_pause: bool = False
        self._last_calculated_silence_threshold_ms: int = silence_threshold_ms

        # State machine tracking
        self._state = VADState.SILENCE
        self._consecutive_speech_frames = 0
        self._consecutive_silence_frames = 0
        self._active_speech_frame_count = 0
        self._active_utterance_frames: List[np.ndarray] = []

        # Ring buffer for audio frames captured right before speech was confirmed
        frame_ms = (self.frame_size / self.sample_rate) * 1000.0
        pre_roll_frame_count = max(2, math.ceil(self.pre_roll_ms / frame_ms))
        self._pre_roll_buffer: Deque[np.ndarray] = deque(maxlen=pre_roll_frame_count)

        self._model = None
        self._onnx_session = None
        self._backend_type = "fallback"  # "silero_torch", "silero_onnx", or "fallback"
        self._fallback_noise_floor = 0.015
        self._lock = threading.RLock()

        # Initialize neural VAD backend
        self._init_backend()

    def _init_backend(self) -> None:
        """Initialize Silero VAD model if available, else setup fallback."""
        # 1. Attempt Silero ONNX model (preferred for minimum CPU & single-thread efficiency)
        try:
            import silero_vad
            model = silero_vad.load_silero_vad(onnx=True)
            self._model = model
            self._backend_type = "silero_onnx_wrapper"
            logger.info("Initialized Silero VAD via ONNX backend.")
            return
        except Exception as e:
            logger.debug("Silero ONNX wrapper initialization failed: %s", e)

        # 2. Attempt Silero PyTorch model with single-thread optimization
        try:
            import torch
            torch.set_num_threads(1)
            import silero_vad
            model = silero_vad.load_silero_vad(onnx=False)
            self._model = model
            self._backend_type = "silero_torch"
            logger.info("Initialized Silero VAD via PyTorch backend (single-thread mode).")
            return
        except Exception as e:
            logger.debug("Silero PyTorch initialization skipped/failed: %s", e)

        # 3. Attempt direct ONNX session via onnxruntime if available
        try:
            import onnxruntime as ort
            import silero_vad
            onnx_path = silero_vad.silero_vad.files("silero_vad.data").joinpath("silero_vad.onnx")
            if Path(str(onnx_path)).exists():
                opts = ort.SessionOptions()
                opts.inter_op_num_threads = 1
                opts.intra_op_num_threads = 1
                self._onnx_session = ort.InferenceSession(str(onnx_path), opts)
                self._backend_type = "silero_onnx"
                self._init_onnx_state()
                logger.info("Initialized Silero VAD via ONNX runtime backend: %s", onnx_path)
                return
        except Exception as e:
            logger.debug("Silero ONNX direct initialization failed: %s", e)

        # 4. Fallback: Adaptive Energy / RMS VAD
        self._backend_type = "fallback"
        self._fallback_noise_floor = 0.015
        logger.info("Silero VAD not loaded; using adaptive energy/RMS VAD backend.")

    def _init_onnx_state(self) -> None:
        """Initialize ONNX hidden states for Silero recurrent network."""
        self._onnx_h = np.zeros((2, 1, 64), dtype=np.float32)
        self._onnx_c = np.zeros((2, 1, 64), dtype=np.float32)

    @property
    def state(self) -> VADState:
        """Current operational state of VAD state machine."""
        return self._state

    def set_silence_threshold(self, threshold_ms: int) -> None:
        """Update end-of-speech silence detection timeout in milliseconds (e.g. 500ms to 2000ms)."""
        with self._lock:
            self.silence_threshold_ms = max(250, min(5000, int(threshold_ms)))
            logger.info("[DIAGNOSTIC] VAD silence threshold set to %d ms.", self.silence_threshold_ms)

    def set_speech_threshold(self, threshold: float) -> None:
        """Update VAD speech onset confidence threshold (0.1 to 0.9)."""
        with self._lock:
            self.speech_threshold = max(0.1, min(0.9, float(threshold)))
            logger.info("[DIAGNOSTIC] VAD speech threshold set to %.2f.", self.speech_threshold)

    def set_trailing_connector(self, has_connector: bool) -> None:
        """Flag whether the active speech utterance ends with a connector/hesitation word (Phase 6.1)."""
        with self._lock:
            self._has_trailing_connector = bool(has_connector)

    def set_thinking_pause(self, is_thinking: bool) -> None:
        """Flag whether user is currently in a detected mid-utterance thinking pause (Phase 6.1)."""
        with self._lock:
            self._is_thinking_pause = bool(is_thinking)

    def get_adaptive_silence_threshold_ms(self, speech_duration_ms: float = 0.0) -> int:
        """Calculate dynamic silence threshold based on speech progression, connectors, and ambient noise (Phase 6.1).
        
        Prevents aggressive fixed timeouts from cutting off natural thinking pauses
        or trailing conjunctions ('and...', 'because...', 'aur...', 'ane...'), while
        maintaining crisp endpointing for concise completed commands.
        """
        with self._lock:
            base_threshold = self.silence_threshold_ms

            # Honor low thresholds explicitly configured in tests / low-latency configs (< 300ms)
            if base_threshold < 300:
                if self._has_trailing_connector or self._is_thinking_pause:
                    return int(base_threshold * 2)
                return base_threshold

            # 1. Trailing connectors / thinking pause: extend threshold significantly (850-950ms)
            if self._has_trailing_connector or self._is_thinking_pause:
                adapted = max(base_threshold, 900)
            # 2. Utterance duration progression:
            # Very short utterance (< 600ms): user may be pausing right after saying a word/hesitation
            elif 0 < speech_duration_ms < 600:
                adapted = max(base_threshold, 650)
            # Normal speech (> 1800ms) with clean completion: keep snappy base threshold (400-450ms)
            elif speech_duration_ms >= 1800:
                adapted = base_threshold
            else:
                adapted = base_threshold

            # 3. Ambient noise adjustment: in noisier rooms (ambient RMS > 0.015),
            # provide a slight margin (+50ms) to prevent noise modulation from cutting speech
            if self._ambient_noise_rms > 0.015:
                adapted += 50

            clamped = max(base_threshold, min(3000, adapted))
            self._last_calculated_silence_threshold_ms = clamped
            return clamped

    def reset_states(self) -> None:
        """Reset internal recurrent neural network states and speech buffer."""
        with self._lock:
            self._state = VADState.SILENCE
            self._consecutive_speech_frames = 0
            self._consecutive_silence_frames = 0
            self._active_speech_frame_count = 0
            self._active_utterance_frames.clear()
            self._pre_roll_buffer.clear()
            self._has_trailing_connector = False
            self._is_thinking_pause = False
            if hasattr(self, "_onnx_h"):
                self._init_onnx_state()
            if self._model is not None and hasattr(self._model, "reset_states"):
                try:
                    self._model.reset_states()
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # Frame Processing & Probability
    # -------------------------------------------------------------------------

    def get_speech_probability(self, frame: np.ndarray) -> float:
        """Compute speech probability for a single 512-sample float32 frame."""
        if frame.size != self.frame_size:
            # Resample or pad/truncate to exact frame_size if needed
            if frame.size < self.frame_size:
                frame = np.pad(frame, (0, self.frame_size - frame.size))
            else:
                frame = frame[:self.frame_size]

        # Fast energy gating for pure digital zero/silence to skip unnecessary forward passes:
        # Note: Center audio frame to remove microphone DC bias so hardware offset doesn't inflate RMS.
        frame_centered = frame - float(np.mean(frame))
        rms = float(np.sqrt(np.mean(np.square(frame_centered))))
        if rms < 0.0004:
            return 0.0

        prob = 0.0
        if self._backend_type in ("silero_onnx_wrapper", "silero_torch") and self._model is not None:
            try:
                import torch
                tensor = torch.from_numpy(frame).unsqueeze(0)
                prob = float(self._model(tensor, self.sample_rate).item())
            except Exception as e:
                logger.debug("Silero VAD inference error: %s", e)

        elif self._backend_type == "silero_onnx" and self._onnx_session is not None:
            try:
                inputs = {
                    "input": frame[np.newaxis, :],
                    "sr": np.array([self.sample_rate], dtype=np.int64),
                    "h": self._onnx_h,
                    "c": self._onnx_c,
                }
                out, self._onnx_h, self._onnx_c = self._onnx_session.run(None, inputs)
                prob = float(out[0][0])
            except Exception as e:
                logger.debug("ONNX VAD inference error: %s", e)
        else:
            # Fallback: RMS Energy with adaptive dynamic noise floor
            if self._state != VADState.SPEAKING:
                self._fallback_noise_floor = 0.95 * self._fallback_noise_floor + 0.05 * min(rms, self._fallback_noise_floor * 1.5)
            threshold = max(0.002, self._fallback_noise_floor * 1.8)
            if rms > threshold:
                prob = min(1.0, (rms - threshold) / threshold + 0.5)
            else:
                prob = max(0.0, rms / threshold * 0.4)

        # High-energy assist for unambiguous speech/vocal tones (RMS > 0.08):
        # Set safely above typical room noise floors (0.01-0.04) so ambient noise
        # never locks the VAD into perpetual speech, while ensuring real user speech
        # (typically RMS 0.08-0.35) and synthetic test tones are reliably recognized.
        if prob < self.speech_threshold and rms > 0.08:
            prob = max(prob, 0.75)

        return float(prob)

    def is_speech(self, frame: np.ndarray) -> bool:
        """Check whether the given frame contains speech above threshold."""
        return self.get_speech_probability(frame) >= self.speech_threshold

    def process_frame(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Process an incoming audio frame and return completed utterance when speech ends."""
        with self._lock:
            prob = self.get_speech_probability(frame)
            self.vad_probability.emit(prob)

            is_speech = prob >= self.speech_threshold
            frame_ms = (self.frame_size / self.sample_rate) * 1000.0

            if self._state == VADState.SILENCE:
                self._pre_roll_buffer.append(frame.copy())
                # Dynamic background ambient noise tracking (Phase 6.1)
                frame_centered = frame - float(np.mean(frame))
                frame_rms = float(np.sqrt(np.mean(np.square(frame_centered))))
                if frame_rms > 0.0:
                    self._ambient_noise_rms = 0.95 * self._ambient_noise_rms + 0.05 * frame_rms

                if is_speech:
                    self._state = VADState.TRIGGERING
                    self._consecutive_speech_frames = 1
                else:
                    self._consecutive_speech_frames = 0

            elif self._state == VADState.TRIGGERING:
                self._pre_roll_buffer.append(frame.copy())
                if is_speech:
                    self._consecutive_speech_frames += 1
                    if self._consecutive_speech_frames >= self.min_speech_frames:
                        # Confirmed Speech Start!
                        self._state = VADState.SPEAKING
                        self._consecutive_silence_frames = 0
                        self._active_speech_frame_count = self._consecutive_speech_frames
                        # Prepend buffered audio captured prior to trigger
                        self._active_utterance_frames = list(self._pre_roll_buffer)
                        self._pre_roll_buffer.clear()
                        rms = float(np.sqrt(np.mean(np.square(frame))))
                        logger.info("[DIAGNOSTIC] Speech detected: frame RMS=%.5f, onset frames=%d", rms, self._consecutive_speech_frames)
                        self.speech_started.emit()
                else:
                    # Transient spike/noise, return to silence
                    self._consecutive_speech_frames = 0
                    self._active_speech_frame_count = 0
                    self._state = VADState.SILENCE

            elif self._state == VADState.SPEAKING:
                self._active_utterance_frames.append(frame.copy())

                if is_speech:
                    self._active_speech_frame_count += 1
                    # Hangover / hysteresis smoothing:
                    # Once a speech pause begins (>3 silence frames / ~96ms), do not let an isolated
                    # single transient noise blip completely reset the silence counter.
                    # Require 2 consecutive speech frames to cancel an ongoing silence pause.
                    if self._consecutive_silence_frames > 3:
                        self._consecutive_speech_frames += 1
                        if self._consecutive_speech_frames >= 2:
                            self._consecutive_silence_frames = 0
                    else:
                        self._consecutive_silence_frames = 0
                        self._consecutive_speech_frames = 1
                else:
                    self._consecutive_speech_frames = 0
                    self._consecutive_silence_frames += 1

                silence_duration_ms = self._consecutive_silence_frames * frame_ms
                utterance_duration_ms = len(self._active_utterance_frames) * frame_ms
                speech_duration_ms = self._active_speech_frame_count * frame_ms

                # Check End-of-Speech conditions with Adaptive Silence Threshold (Phase 6.1)
                effective_silence_threshold_ms = self.get_adaptive_silence_threshold_ms(speech_duration_ms)
                silence_timed_out = silence_duration_ms >= effective_silence_threshold_ms
                max_duration_exceeded = utterance_duration_ms >= self.max_utterance_ms

                if silence_timed_out or max_duration_exceeded:
                    if not self._active_utterance_frames:
                        self._state = VADState.SILENCE
                        self._has_trailing_connector = False
                        self._is_thinking_pause = False
                        return None

                    # Trim excessive trailing silence from the end of utterance:
                    # Keep at most 4 frames (~128ms) of trailing silence so Whisper doesn't transcribe dead air.
                    trailing_silence_frames = min(self._consecutive_silence_frames, 4)
                    if self._consecutive_silence_frames > trailing_silence_frames:
                        cut_count = self._consecutive_silence_frames - trailing_silence_frames
                        frames_to_keep = max(1, len(self._active_utterance_frames) - cut_count)
                        active_frames = self._active_utterance_frames[:frames_to_keep]
                    else:
                        active_frames = self._active_utterance_frames

                    complete_utterance = np.concatenate(active_frames)
                    utterance_duration_sec = len(complete_utterance) / float(self.sample_rate)

                    # Reset states for next utterance
                    self._state = VADState.SILENCE
                    self._consecutive_speech_frames = 0
                    self._consecutive_silence_frames = 0
                    self._active_speech_frame_count = 0
                    self._has_trailing_connector = False
                    self._is_thinking_pause = False
                    self._active_utterance_frames.clear()
                    self._pre_roll_buffer.clear()

                    # Require actual speech duration and audible RMS energy
                    rms = float(np.sqrt(np.mean(np.square(complete_utterance)))) if complete_utterance.size > 0 else 0.0

                    if speech_duration_ms < self.min_utterance_ms or rms < 0.0006:
                        reason = f"speech={speech_duration_ms:.1f}ms (<{self.min_utterance_ms}ms) or RMS={rms:.5f} (<0.0006)"
                        logger.info("[DIAGNOSTIC] No speech detected: %s. Utterance discarded.", reason)
                        self.no_speech_detected.emit(reason)
                        return None

                    logger.info(
                        "[LATENCY_PROFILE] VAD utterance capture completed: duration=%.2fs (speech=%.1fms, silence=%.1fms, RMS=%.5f)",
                        utterance_duration_sec,
                        speech_duration_ms,
                        silence_duration_ms,
                        rms,
                    )
                    logger.info(
                        "[DIAGNOSTIC] Recording completed: duration=%.2fs (speech=%.1fms, silence=%.1fms, RMS=%.5f)",
                        utterance_duration_sec,
                        speech_duration_ms,
                        silence_duration_ms,
                        rms,
                    )
                    self.recording_completed.emit(utterance_duration_sec)
                    self.speech_ended.emit(complete_utterance)
                    return complete_utterance

            return None

    def get_current_speech_buffer(self) -> Optional[np.ndarray]:
        """Return a thread-safe snapshot of speech audio frames captured so far in the active utterance."""
        with self._lock:
            if self._state == VADState.SPEAKING and self._active_utterance_frames:
                if len(self._active_utterance_frames) >= 2:
                    return np.concatenate(self._active_utterance_frames)
            return None

    def force_finalize_utterance(self) -> Optional[np.ndarray]:
        """Force-finalize active utterance immediately (e.g. on max utterance watchdog timeout)."""
        with self._lock:
            active_frames: list[np.ndarray] = []
            if self._active_utterance_frames:
                active_frames = list(self._active_utterance_frames)
            elif self._pre_roll_buffer:
                active_frames = list(self._pre_roll_buffer)

            if not active_frames:
                logger.info(
                    "[DIAGNOSTIC] force_finalize_utterance called but no frames collected (state=%s)",
                    self._state.name,
                )
                self.reset_states()
                return None

            complete_utterance = np.concatenate(active_frames)
            utterance_duration_sec = len(complete_utterance) / float(self.sample_rate)

            self.reset_states()

            centered_utterance = complete_utterance - float(np.mean(complete_utterance))
            rms = float(np.sqrt(np.mean(np.square(centered_utterance)))) if complete_utterance.size > 0 else 0.0
            if len(complete_utterance) < int(self.sample_rate * 0.12) or rms < 0.0004:
                reason = f"force_finalized_insufficient (duration={utterance_duration_sec:.2f}s, RMS={rms:.5f})"
                logger.info("[DIAGNOSTIC] No speech detected in force-finalized segment: %s.", reason)
                self.no_speech_detected.emit(reason)
                return None

            logger.info(
                "[DIAGNOSTIC] Recording completed (force-finalized): duration=%.2fs, RMS=%.5f",
                utterance_duration_sec,
                rms,
            )
            self.recording_completed.emit(utterance_duration_sec)
            self.speech_ended.emit(complete_utterance)
            return complete_utterance
