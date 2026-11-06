"""Microphone Manager and Audio Capture Pipeline.

Captures mono, float32 audio at 16000 Hz using sounddevice with bounded buffering,
device enumeration, level metering, and graceful disconnection recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import queue
import threading
import time
from typing import Callable, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QObject, Signal

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Standard audio constants for VAD & Whisper
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_FRAME_SAMPLES = 512  # 32 ms at 16kHz
DEFAULT_QUEUE_MAXSIZE = 300  # ~9.6 seconds buffer capacity to prevent runaway memory


@dataclass
class AudioDeviceInfo:
    """Descriptor for an audio input device."""
    index: int
    name: str
    hostapi_name: str
    max_input_channels: int
    default_samplerate: float
    is_default: bool = False

    def display_name(self) -> str:
        return f"{self.name} ({self.hostapi_name})"


class MicrophoneManager(QObject):
    """Manages audio input devices and non-blocking streaming capture."""

    # Qt Signals for GUI integration
    device_changed = Signal(str)
    recording_started = Signal()
    recording_stopped = Signal()
    audio_level = Signal(float)  # Normalized 0.0 to 1.0 (RMS)
    error_occurred = Signal(str)
    status_changed = Signal(str)  # "unavailable", "permission_denied", "recording_started", "recording", "idle"

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        frame_samples: int = DEFAULT_FRAME_SAMPLES,
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_samples = frame_samples
        self.queue_maxsize = queue_maxsize

        self._active_device_index: Optional[int] = None
        self._active_device_name: str = "default"
        self._device_unavailable: bool = False
        self._is_recording = False
        self._is_muted = False
        self._is_shutdown = False
        self._last_status: str = "idle"
        self._stream = None
        self._stream_lock = threading.Lock()

        # Telemetry & Health Tracking
        self._frames_captured: int = 0
        self._samples_captured: int = 0
        self._last_callback_time: float = 0.0

        # Thread-safe bounded buffer for audio chunks (numpy float32 1D arrays)
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=self.queue_maxsize)

        # External callbacks for streaming consumers
        self._chunk_subscribers: List[Callable[[np.ndarray], None]] = []
        self._subscribers_lock = threading.Lock()

        # Throttling for audio level emissions to prevent UI flooding
        self._last_level_emit_time = 0.0
        self._level_emit_interval = 0.04  # ~25 Hz update rate

    # -------------------------------------------------------------------------
    # Device Enumeration and Selection
    # -------------------------------------------------------------------------

    @staticmethod
    def get_input_devices() -> List[AudioDeviceInfo]:
        """Detect and return all available microphone input devices."""
        devices: List[AudioDeviceInfo] = []
        try:
            import sounddevice as sd
            host_apis = sd.query_hostapis()
            all_devices = sd.query_devices()
            default_input_idx = -1
            try:
                default_input = sd.default.device[0]
                default_input_idx = int(default_input) if default_input is not None else -1
            except Exception:
                pass

            for idx, dev in enumerate(all_devices):
                if dev.get("max_input_channels", 0) > 0:
                    api_idx = dev.get("hostapi", 0)
                    api_name = host_apis[api_idx].get("name", "Unknown") if api_idx < len(host_apis) else "Unknown"
                    is_def = (idx == default_input_idx)
                    devices.append(
                        AudioDeviceInfo(
                            index=idx,
                            name=str(dev.get("name", f"Device {idx}")),
                            hostapi_name=api_name,
                            max_input_channels=int(dev.get("max_input_channels", 1)),
                            default_samplerate=float(dev.get("default_samplerate", 16000.0)),
                            is_default=is_def,
                        )
                    )
        except Exception as e:
            logger.error("Failed to query audio input devices: %s", e)
        return devices

    def set_device(self, device_identifier: Optional[int | str]) -> bool:
        """Select input device by index or partial name.
        
        Pass None or 'default' to use the system default device.
        Do NOT silently fall back to an unrelated audio input if a specific device fails.
        """
        was_recording = self._is_recording
        if was_recording:
            self.stop_recording()

        norm_id = str(device_identifier).lower().strip() if device_identifier is not None else "default"
        is_default_request = (
            device_identifier is None
            or norm_id in ("default", "system default", "default microphone", "default system microphone", "")
        )

        if is_default_request:
            self._active_device_index = None
            self._active_device_name = "default"
            self._device_unavailable = False
            logger.info("Microphone reset to system default input device.")
            self.device_changed.emit("default")
            if was_recording:
                self.start_recording()
            return True

        if isinstance(device_identifier, int):
            devices = self.get_input_devices()
            matching = [d for d in devices if d.index == device_identifier]
            if matching:
                self._active_device_index = device_identifier
                self._active_device_name = matching[0].name
                self._device_unavailable = False
                logger.info("Selected microphone index %d: %s", device_identifier, matching[0].name)
                self.device_changed.emit(self._active_device_name)
                if was_recording:
                    self.start_recording()
                return True
            else:
                self._active_device_index = -1
                self._active_device_name = f"Index {device_identifier}"
                self._device_unavailable = True
                logger.warning("[DIAGNOSTIC] Microphone unavailable: Index %d not found.", device_identifier)
                self.error_occurred.emit(f"Microphone unavailable: Index {device_identifier} not found.")
                self._set_status("unavailable")
                return False

        # Match by name string
        devices = self.get_input_devices()
        for dev in devices:
            if norm_id in dev.name.lower() or norm_id in dev.display_name().lower():
                self._active_device_index = dev.index
                self._active_device_name = dev.name
                self._device_unavailable = False
                logger.info("Selected microphone '%s' (index %d)", dev.name, dev.index)
                self.device_changed.emit(self._active_device_name)
                if was_recording:
                    self.start_recording()
                return True

        # Do NOT silently fall back to an unrelated audio input!
        self._active_device_index = -1
        self._active_device_name = str(device_identifier)
        self._device_unavailable = True
        logger.warning("[DIAGNOSTIC] Microphone unavailable: No microphone matching '%s' found.", device_identifier)
        self.error_occurred.emit(f"Microphone unavailable: Device '{device_identifier}' not found.")
        self._set_status("unavailable")
        return False

    @property
    def active_device_name(self) -> str:
        return self._active_device_name

    @property
    def active_device_index(self) -> Optional[int]:
        return self._active_device_index

    def _set_status(self, status: str) -> None:
        """Update internal status and emit Qt signal."""
        self._last_status = status
        self.status_changed.emit(status)

    @property
    def last_status(self) -> str:
        return self._last_status

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def is_stream_active(self) -> bool:
        """Check whether the audio stream is currently opened, started, and active."""
        if not self._is_recording or self._stream is None:
            return False
        try:
            return bool(getattr(self._stream, "active", False))
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Audio Stream Management
    # -------------------------------------------------------------------------

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    def start_recording(self) -> bool:
        """Start capturing audio from the active microphone."""
        if self._is_shutdown:
            logger.warning("[DIAGNOSTIC] Microphone start recording rejected: MicrophoneManager is shut down.")
            return False

        with self._stream_lock:
            if self._is_recording:
                return True

            if self._device_unavailable:
                err_msg = f"Microphone unavailable: Requested device '{self._active_device_name}' is not connected."
                logger.error("[DIAGNOSTIC] Microphone unavailable: %s", err_msg)
                self.error_occurred.emit(err_msg)
                self._set_status("unavailable")
                return False

            try:
                import sounddevice as sd
            except ImportError as e:
                err = f"sounddevice library not available: {e}"
                logger.error("[DIAGNOSTIC] Microphone unavailable: %s", err)
                self.error_occurred.emit(err)
                self._set_status("unavailable")
                return False

            devices = self.get_input_devices()
            if not devices:
                err = "Microphone unavailable: No audio input devices detected on system."
                logger.error("[DIAGNOSTIC] Microphone unavailable: %s", err)
                self.error_occurred.emit(err)
                self._set_status("unavailable")
                return False

            # Clear any stale queued audio
            self.clear_buffer()

            try:
                device_target = self._active_device_index
                open_channels = self.channels

                try:
                    self._stream = sd.InputStream(
                        samplerate=self.sample_rate,
                        channels=open_channels,
                        dtype="float32",
                        blocksize=self.frame_samples,
                        device=device_target,
                        callback=self._audio_callback,
                    )
                except Exception as first_err:
                    # If mono (channels=1) failed on a stereo-only audio device, try fallback to 2 channels
                    if open_channels == 1:
                        logger.info("Opening mono input stream failed (%s); attempting stereo fallback (channels=2)...", first_err)
                        self._stream = sd.InputStream(
                            samplerate=self.sample_rate,
                            channels=2,
                            dtype="float32",
                            blocksize=self.frame_samples,
                            device=device_target,
                            callback=self._audio_callback,
                        )
                    else:
                        raise first_err

                self._stream.start()
                self._is_recording = True
                self._frames_captured = 0
                self._samples_captured = 0
                self._last_callback_time = time.time()
                logger.info(
                    "[DIAGNOSTIC] Recording started: device='%s', rate=%d, channels=%d, blocksize=%d",
                    str(device_target if device_target is not None else "default"),
                    self.sample_rate,
                    self.channels,
                    self.frame_samples,
                )
                self.recording_started.emit()
                self._set_status("recording_started")
                self._set_status("recording")
                try:
                    from app.core.diagnostic_mode import diagnostic_tracker
                    diagnostic_tracker.update_microphone("recording")
                    diagnostic_tracker.update_recording("recording")
                except Exception:
                    pass
                return True
            except Exception as e:
                err_str = str(e).lower()
                if "permission" in err_str or "access denied" in err_str or "-9996" in err_str or "-9999" in err_str:
                    err_msg = f"Permission denied: Microphone access denied by system privacy settings ({e})."
                    logger.error("[DIAGNOSTIC] Permission denied: %s", err_msg)
                    self._set_status("permission_denied")
                    try:
                        from app.core.diagnostic_mode import diagnostic_tracker, ERROR_MIC_PERMISSION
                        diagnostic_tracker.update_microphone("permission_denied", error=ERROR_MIC_PERMISSION)
                        diagnostic_tracker.update_recording("idle")
                    except Exception:
                        pass
                else:
                    err_msg = f"Microphone unavailable: Failed to open microphone stream ({e})."
                    logger.error("[DIAGNOSTIC] Microphone unavailable: %s", err_msg)
                    self._set_status("unavailable")
                    try:
                        from app.core.diagnostic_mode import diagnostic_tracker
                        diagnostic_tracker.update_microphone("unavailable", error="Microphone unavailable")
                        diagnostic_tracker.update_recording("idle")
                    except Exception:
                        pass

                self._stream = None
                self._is_recording = False
                self.error_occurred.emit(err_msg)
                return False

    def stop_recording(self) -> None:
        """Stop capturing audio and close the input stream."""
        with self._stream_lock:
            if not self._is_recording and self._stream is None:
                return

            self._is_recording = False
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.debug("Exception closing audio stream: %s", e)
                finally:
                    self._stream = None

            logger.info("[DIAGNOSTIC] Microphone stopped.")
            logger.info("[DIAGNOSTIC] Recording stopped: %d frames (%d samples) captured.", self._frames_captured, self._samples_captured)
            self.recording_stopped.emit()
            self.status_changed.emit("idle")
            try:
                from app.core.diagnostic_mode import diagnostic_tracker
                diagnostic_tracker.update_recording("stopped")
                diagnostic_tracker.update_microphone("idle")
            except Exception:
                pass

    def emergency_stop(self) -> None:
        """Immediately halt microphone stream, purge input buffer, and transition to idle."""
        logger.warning("[DIAGNOSTIC] MicrophoneManager emergency stop invoked.")
        self.stop_recording()
        self.clear_buffer()

    def shutdown(self) -> None:
        """Permanently shut down MicrophoneManager, close input stream, and unsubscribe listeners."""
        logger.info("[DIAGNOSTIC] MicrophoneManager shutdown initiated.")
        with self._stream_lock:
            self._is_shutdown = True
        self.emergency_stop()
        with self._subscribers_lock:
            self._chunk_subscribers.clear()

    @property
    def is_muted(self) -> bool:
        """Return True if microphone audio streaming is muted."""
        return self._is_muted

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute microphone audio capture (Phase 8.4)."""
        self._is_muted = muted
        if muted:
            self.audio_level.emit(0.0)

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """Internal audio thread callback invoked by PortAudio / sounddevice."""
        if status:
            if status.input_overflow:
                logger.debug("Audio input status flag (transient startup buffer): %s", status)
            else:
                logger.warning("Audio input status flag: %s", status)

        if not self._is_recording:
            return

        if self._is_muted:
            now = time.time()
            if now - self._last_level_emit_time >= self._level_emit_interval:
                self._last_level_emit_time = now
                self.audio_level.emit(0.0)
            return

        if indata is None or indata.size == 0:
            logger.warning("[DIAGNOSTIC] Unexpected audio capture detected: empty audio chunk.")
            return

        # Ensure 1D float32 array with proper multi-channel downmixing
        if indata.ndim > 1:
            if indata.shape[1] > 1:
                chunk = np.mean(indata, axis=1).astype(np.float32)
            else:
                chunk = indata[:, 0].flatten().astype(np.float32)
        else:
            chunk = indata.flatten().astype(np.float32)

        self._frames_captured += 1
        self._samples_captured += len(chunk)
        self._last_callback_time = time.time()

        # Calculate RMS for visual audio level meter
        rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size > 0 else 0.0
        # Normalize RMS (typical speech is ~0.02 - 0.2, saturate at 0.3)
        normalized_level = min(1.0, rms * 5.0)

        now = time.time()
        if now - self._last_level_emit_time >= self._level_emit_interval:
            self._last_level_emit_time = now
            self.audio_level.emit(normalized_level)

        if self._frames_captured == 1 or self._frames_captured % 100 == 0:
            peak = float(np.max(np.abs(chunk))) if chunk.size > 0 else 0.0
            logger.info(
                "[DIAGNOSTIC] Recording in progress: %d frames (%d samples) captured. (RMS=%.5f, peak=%.5f, active=%s)",
                self._frames_captured,
                self._samples_captured,
                rms,
                peak,
                self.is_stream_active(),
            )

        # Place into bounded buffer (drop oldest if full)
        try:
            self._audio_queue.put_nowait(chunk)
        except queue.Full:
            try:
                _ = self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(chunk)
            except Exception:
                pass

        # Notify active subscribers
        with self._subscribers_lock:
            for sub in self._chunk_subscribers:
                try:
                    sub(chunk)
                except Exception as e:
                    logger.error("Error in audio chunk subscriber: %s", e)

    # -------------------------------------------------------------------------
    # Buffer Access and Subscription
    # -------------------------------------------------------------------------

    def subscribe(self, callback: Callable[[np.ndarray], None]) -> None:
        """Register a callback to receive real-time audio frames directly."""
        with self._subscribers_lock:
            if callback not in self._chunk_subscribers:
                self._chunk_subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[np.ndarray], None]) -> None:
        """Unregister a real-time audio frame subscriber."""
        with self._subscribers_lock:
            if callback in self._chunk_subscribers:
                self._chunk_subscribers.remove(callback)

    def get_chunk(self, timeout: Optional[float] = 0.1) -> Optional[np.ndarray]:
        """Retrieve the next queued audio frame."""
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain_chunks(self) -> List[np.ndarray]:
        """Drain all currently queued audio chunks without blocking."""
        chunks: List[np.ndarray] = []
        while True:
            try:
                chunks.append(self._audio_queue.get_nowait())
            except queue.Empty:
                break
        return chunks

    def clear_buffer(self) -> None:
        """Clear all pending chunks in the queue."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
