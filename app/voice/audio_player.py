"""Audio Playback Manager and Lip-Sync Amplitude Dispatcher.

Handles non-blocking sound output using sounddevice OutputStream with volume control,
immediate interruption, device selection, multi-channel stereo compatibility for Windows WASAPI,
and real-time amplitude analysis for lip sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd
import threading
import time
from typing import List, Optional

import numpy as np
from PySide6.QtCore import QObject, Signal
import sounddevice as sd

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BLOCK_SIZE = 512  # ~23ms at 22050Hz or ~21ms at 24000Hz


@dataclass
class AudioOutputDeviceInfo:
    """Descriptor for an audio output device."""
    index: int
    name: str
    hostapi_name: str
    max_output_channels: int
    default_samplerate: float
    is_default: bool = False

    def display_name(self) -> str:
        return f"{self.name} ({self.hostapi_name})"


class AudioPlayer(QObject):
    """Manages audio waveform playback, volume, and real-time lip sync amplitude."""

    # Playback lifecycle signals
    playback_started = Signal()
    playback_finished = Signal()
    playback_stopped = Signal()
    playback_progress = Signal(float, float)  # (current_sec, total_sec)
    amplitude_updated = Signal(float)         # Normalized mouth openness (0.0 to 1.0)
    playback_reference_ready = Signal(object, int)  # (samples: np.ndarray, sample_rate: int)
    device_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        block_size: int = DEFAULT_BLOCK_SIZE,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.block_size = block_size

        self._volume: float = 1.0
        self._is_muted: bool = False
        self._is_playing: bool = False
        self._is_shutdown: bool = False
        self._active_device_index: Optional[int] = None
        self._active_device_name: str = "default"

        # Internal playback state
        self._samples: Optional[np.ndarray] = None
        self._sample_rate: int = 22050
        self._output_channels: int = 2
        self._current_index: int = 0
        self._total_samples: int = 0
        self._stream = None
        self._last_playback_stop_time: float = 0.0
        self._last_progress_ratio: float = 0.0
        self._last_played_sec: float = 0.0
        self._lock = threading.Lock()

        # Throttling progress & amplitude emissions
        self._last_progress_emit = 0.0
        self._progress_interval = 0.05  # 20 Hz update rate

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    @property
    def output_channels(self) -> int:
        return self._output_channels

    @property
    def last_playback_stop_time(self) -> float:
        return self._last_playback_stop_time

    @property
    def last_progress_ratio(self) -> float:
        """Fraction (0.0 to 1.0) of audio played before the most recent stop/interruption."""
        return self._last_progress_ratio

    @property
    def last_played_sec(self) -> float:
        """Seconds of audio played before the most recent stop/interruption."""
        return self._last_played_sec

    def get_playback_progress(self) -> tuple[float, float, float]:
        """Return (current_played_seconds, total_seconds, progress_ratio_0_to_1)."""
        with self._lock:
            if not self._is_playing or self._total_samples <= 0 or self._sample_rate <= 0:
                return (self._last_played_sec, 0.0, self._last_progress_ratio)
            current_sec = self._current_index / float(self._sample_rate)
            total_sec = self._total_samples / float(self._sample_rate)
            progress = min(1.0, max(0.0, self._current_index / float(self._total_samples)))
            return (current_sec, total_sec, progress)

    def is_in_cooldown(self, cooldown_sec: float = 0.45) -> bool:
        """Return True if audio is actively playing or stopped within cooldown window."""
        return self._is_playing or ((time.time() - self._last_playback_stop_time) < cooldown_sec)

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def is_muted(self) -> bool:
        return self._is_muted

    def set_volume(self, volume: float) -> None:
        """Set output volume level between 0.0 and 1.0."""
        self._volume = max(0.0, min(1.0, float(volume)))

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute audio output."""
        self._is_muted = bool(muted)

    # -------------------------------------------------------------------------
    # Device Enumeration and Selection
    # -------------------------------------------------------------------------

    @staticmethod
    def get_output_devices() -> List[AudioOutputDeviceInfo]:
        """Detect and return all available audio output devices."""
        devices: List[AudioOutputDeviceInfo] = []
        try:
            import sounddevice as sd
            host_apis = sd.query_hostapis()
            all_devices = sd.query_devices()
            default_output_idx = -1
            try:
                default_output = sd.default.device[1]
                default_output_idx = int(default_output) if default_output is not None else -1
            except Exception:
                pass

            for idx, dev in enumerate(all_devices):
                if dev.get("max_output_channels", 0) > 0:
                    api_idx = dev.get("hostapi", 0)
                    api_name = host_apis[api_idx].get("name", "Unknown") if api_idx < len(host_apis) else "Unknown"
                    devices.append(
                        AudioOutputDeviceInfo(
                            index=idx,
                            name=str(dev.get("name", f"Output {idx}")),
                            hostapi_name=api_name,
                            max_output_channels=int(dev.get("max_output_channels", 2)),
                            default_samplerate=float(dev.get("default_samplerate", 44100.0)),
                            is_default=(idx == default_output_idx),
                        )
                    )
        except Exception as e:
            logger.error("Failed to query audio output devices: %s", e)
        return devices

    def set_device(self, device_identifier: Optional[int | str]) -> bool:
        """Select output device by index or partial name."""
        if device_identifier is None or device_identifier == "default":
            self._active_device_index = None
            self._active_device_name = "default"
            self.device_changed.emit("default")
            return True

        devices = self.get_output_devices()
        if isinstance(device_identifier, int):
            matching = [d for d in devices if d.index == device_identifier]
            if matching:
                self._active_device_index = device_identifier
                self._active_device_name = matching[0].name
                self.device_changed.emit(self._active_device_name)
                return True
        else:
            search = str(device_identifier).lower()
            for dev in devices:
                if search in dev.name.lower():
                    self._active_device_index = dev.index
                    self._active_device_name = dev.name
                    self.device_changed.emit(self._active_device_name)
                    return True

        logger.warning("Audio output device '%s' not found.", device_identifier)
        return False

    # -------------------------------------------------------------------------
    # Audio Processing Helpers (Resampling & Channel Selection)
    # -------------------------------------------------------------------------

    @staticmethod
    def _determine_output_channels(device_target: Optional[int]) -> int:
        """Determine optimal output channel count (prefer stereo 2 for Windows WASAPI/DirectSound)."""
        try:
            import sounddevice as sd
            dev_idx = device_target
            if dev_idx is None:
                try:
                    default_output = sd.default.device[1]
                    dev_idx = int(default_output) if default_output is not None and default_output >= 0 else None
                except Exception:
                    dev_idx = None

            if dev_idx is not None and dev_idx >= 0:
                dev_info = sd.query_devices(dev_idx)
                max_ch = int(dev_info.get("max_output_channels", 2))
                if max_ch >= 2:
                    return 2
                elif max_ch == 1:
                    return 1
        except Exception as e:
            logger.debug("Failed to query device max_output_channels: %s", e)
        return 2

    @staticmethod
    def _determine_output_samplerates(requested_rate: int, device_target: Optional[int]) -> List[int]:
        """Return list of candidate sample rates (requested first, followed by device native rate if different)."""
        rates = [requested_rate]
        try:
            import sounddevice as sd
            dev_idx = device_target
            if dev_idx is None:
                try:
                    default_output = sd.default.device[1]
                    dev_idx = int(default_output) if default_output is not None and default_output >= 0 else None
                except Exception:
                    dev_idx = None

            if dev_idx is not None and dev_idx >= 0:
                dev_info = sd.query_devices(dev_idx)
                native_sr = int(dev_info.get("default_samplerate", 0))
                if native_sr > 0 and native_sr not in rates:
                    rates.append(native_sr)
        except Exception as e:
            logger.debug("Failed to query device default_samplerate: %s", e)
        return rates

    @staticmethod
    def _resample_audio(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Resample 1D float32 audio waveform to target sample rate."""
        if orig_sr == target_sr or samples.size == 0:
            return samples
        try:
            from scipy.signal import resample_poly
            g = gcd(orig_sr, target_sr)
            up = target_sr // g
            down = orig_sr // g
            return resample_poly(samples, up, down).astype(np.float32)
        except Exception as e:
            logger.debug("scipy.signal.resample_poly failed, falling back to np.interp: %s", e)
            duration = len(samples) / float(orig_sr)
            target_len = int(round(duration * target_sr))
            old_indices = np.linspace(0.0, duration, len(samples), endpoint=False)
            new_indices = np.linspace(0.0, duration, target_len, endpoint=False)
            return np.interp(new_indices, old_indices, samples).astype(np.float32)

    # -------------------------------------------------------------------------
    # Playback Control
    # -------------------------------------------------------------------------

    def play(self, samples: np.ndarray, sample_rate: int) -> bool:
        """Play a 1D float32 audio waveform through the active output device, supporting stereo upmixing."""
        if self._is_shutdown:
            logger.warning("[DIAGNOSTIC] Audio playback rejected: AudioPlayer is shut down.")
            return False

        self.stop()

        if samples is None or samples.size == 0:
            logger.debug("Attempted to play empty audio samples.")
            return False

        with self._lock:
            # Ensure 1D float32
            if samples.dtype != np.float32:
                samples = samples.astype(np.float32)
            if samples.ndim > 1:
                samples = samples.flatten()

            try:
                import sounddevice as sd
                device_target = self._active_device_index

                target_channels = self._determine_output_channels(device_target)
                channel_candidates = [target_channels]
                if target_channels == 2:
                    channel_candidates.append(1)
                elif target_channels == 1:
                    channel_candidates.append(2)

                samplerate_candidates = self._determine_output_samplerates(sample_rate, device_target)

                stream = None
                last_exc = None
                chosen_sr = sample_rate
                chosen_ch = target_channels
                active_samples = samples

                for sr in samplerate_candidates:
                    if sr != sample_rate:
                        curr_samples = self._resample_audio(samples, sample_rate, sr)
                    else:
                        curr_samples = samples

                    for ch in channel_candidates:
                        try:
                            stream = sd.OutputStream(
                                samplerate=sr,
                                channels=ch,
                                dtype="float32",
                                blocksize=self.block_size,
                                device=device_target,
                                callback=self._audio_callback,
                                finished_callback=self._on_stream_finished,
                            )
                            chosen_sr = sr
                            chosen_ch = ch
                            active_samples = curr_samples
                            break
                        except Exception as exc:
                            last_exc = exc
                            logger.debug(
                                "Failed OutputStream(rate=%d, ch=%d, dev=%s): %s",
                                sr, ch, device_target, exc
                            )
                    if stream is not None:
                        break

                if stream is None:
                    raise last_exc or RuntimeError("Failed to open audio output stream on any supported configuration.")

                self._samples = active_samples
                self._sample_rate = chosen_sr
                self._output_channels = chosen_ch
                self._total_samples = len(active_samples)
                self._current_index = 0
                self._stream = stream
                self._stream.start()
                self._is_playing = True
                duration_sec = self._total_samples / float(self._sample_rate)
                logger.info("[DIAGNOSTIC] TTS playback started.")
                logger.info(
                    "Audio playback started (duration=%.2fs, rate=%dHz, channels=%d, device=%s)",
                    duration_sec, self._sample_rate, self._output_channels, self._active_device_name,
                )
                self.playback_started.emit()
                try:
                    self.playback_reference_ready.emit(samples, sample_rate)
                except Exception:
                    pass
                return True

            except Exception as e:
                err_msg = f"Failed to start audio playback: {e}"
                logger.error(err_msg)
                self._is_playing = False
                self._stream = None
                self.error_occurred.emit(err_msg)
                return False

    def stop(self) -> None:
        """Immediately stop playback and reset lip sync amplitude to zero."""
        with self._lock:
            was_active = self._is_playing or (self._stream is not None)
            self._is_playing = False
            if was_active:
                self._last_playback_stop_time = time.time()
                if self._total_samples > 0:
                    self._last_progress_ratio = min(1.0, max(0.0, self._current_index / float(self._total_samples)))
                    self._last_played_sec = self._current_index / float(self._sample_rate) if self._sample_rate > 0 else 0.0
                else:
                    self._last_progress_ratio = 0.0
                    self._last_played_sec = 0.0
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.debug("Exception closing audio output stream: %s", e)
                finally:
                    self._stream = None

            self._samples = None
            self._current_index = 0
            self._total_samples = 0

        if was_active:
            logger.info("[DIAGNOSTIC] TTS playback completed.")
            # Reset lip sync mouth openness to closed (0.0)
            try:
                self.amplitude_updated.emit(0.0)
                self.playback_stopped.emit()
            except RuntimeError:
                pass

    def emergency_stop(self) -> None:
        """Immediately halt audio output, purge samples, and mark player state stopped."""
        logger.warning("[DIAGNOSTIC] AudioPlayer emergency stop invoked.")
        self.stop()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def shutdown(self) -> None:
        """Permanently shut down AudioPlayer, close PortAudio streams, and reject future playback."""
        logger.info("[DIAGNOSTIC] AudioPlayer shutdown initiated.")
        with self._lock:
            self._is_shutdown = True
        self.emergency_stop()

    def __del__(self) -> None:
        try:
            if hasattr(self, "_stream") and self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
        except Exception:
            pass

    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status) -> None:
        """Internal audio thread callback invoked by PortAudio to fill output buffer."""
        if status:
            logger.warning("Audio playback status flag: %s", status)

        if not self._is_playing or self._samples is None:
            outdata.fill(0)
            return

        chunk_start = self._current_index
        chunk_end = chunk_start + frames

        if chunk_start >= self._total_samples:
            # End of audio reached
            outdata.fill(0)
            raise sd.CallbackStop()

        gain = 0.0 if self._is_muted else self._volume

        if chunk_end > self._total_samples:
            # Final partial chunk
            valid_len = self._total_samples - chunk_start
            chunk = self._samples[chunk_start:self._total_samples]
            scaled = chunk * gain
            if outdata.ndim == 1:
                outdata[:valid_len] = scaled
                outdata[valid_len:] = 0
            else:
                outdata[:valid_len, :] = scaled[:, np.newaxis]
                outdata[valid_len:, :] = 0
            self._current_index = self._total_samples
        else:
            chunk = self._samples[chunk_start:chunk_end]
            scaled = chunk * gain
            if outdata.ndim == 1:
                outdata[:] = scaled
            else:
                outdata[:, :] = scaled[:, np.newaxis]
            self._current_index = chunk_end

        # ---------------------------------------------------------------------
        # Lip Synchronization Amplitude Analysis (7.6)
        # ---------------------------------------------------------------------
        # Instantaneous RMS amplitude for mouth movement
        rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size > 0 else 0.0
        # Map amplitude to mouth openness (0.0 = closed, 1.0 = wide open)
        mouth_openness = min(1.0, max(0.0, rms * 4.0))

        # Progress reporting
        now = time.time()
        if now - self._last_progress_emit >= self._progress_interval:
            self._last_progress_emit = now
            current_sec = self._current_index / float(self._sample_rate)
            total_sec = self._total_samples / float(self._sample_rate)
            try:
                self.playback_progress.emit(current_sec, total_sec)
                self.amplitude_updated.emit(mouth_openness)
            except RuntimeError:
                pass

    def _on_stream_finished(self) -> None:
        """Callback invoked when audio stream reaches end of audio buffer."""
        with self._lock:
            self._is_playing = False
            self._last_playback_stop_time = time.time()
            self._stream = None

        logger.info("[DIAGNOSTIC] TTS playback completed.")
        logger.info("Audio playback completed.")
        try:
            self.amplitude_updated.emit(0.0)
            self.playback_finished.emit()
        except RuntimeError:
            pass
