"""Tests for MicrophoneManager and audio capture pipeline."""

import queue
import numpy as np
import pytest

from app.voice.microphone_manager import (
    AudioDeviceInfo,
    MicrophoneManager,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_FRAME_SAMPLES,
)


class TestMicrophoneManager:
    """Unit tests for microphone detection and buffering."""

    def test_audio_device_info_display_name(self) -> None:
        info = AudioDeviceInfo(
            index=1,
            name="USB Mic",
            hostapi_name="MME",
            max_input_channels=1,
            default_samplerate=16000.0,
            is_default=True,
        )
        assert info.display_name() == "USB Mic (MME)"
        assert info.is_default is True

    def test_get_input_devices_returns_list(self) -> None:
        devices = MicrophoneManager.get_input_devices()
        assert isinstance(devices, list)
        for dev in devices:
            assert isinstance(dev, AudioDeviceInfo)
            assert dev.max_input_channels > 0

    def test_set_device_default(self) -> None:
        mgr = MicrophoneManager()
        assert mgr.set_device("default") is True
        assert mgr.active_device_name == "default"
        assert mgr.active_device_index is None

    def test_set_device_by_invalid_index(self) -> None:
        mgr = MicrophoneManager()
        # High index that doesn't exist
        assert mgr.set_device(999999) is False

    def test_audio_callback_queuing_and_level(self, qtbot) -> None:
        mgr = MicrophoneManager(frame_samples=512)
        # Manually enable recording flag for testing callback
        mgr._is_recording = True

        level_emitted = []
        mgr.audio_level.connect(level_emitted.append)

        # Generate synthetic test frame (sine wave)
        t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
        sine_frame = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        mgr._audio_callback(sine_frame, 512, None, None)

        # Frame should be in buffer
        chunk = mgr.get_chunk(timeout=0.1)
        assert chunk is not None
        assert chunk.shape == (512,)
        assert np.allclose(chunk, sine_frame)

        # Check audio level signal emitted
        assert len(level_emitted) >= 1
        assert 0.0 < level_emitted[0] <= 1.0

    def test_drain_and_clear_buffer(self) -> None:
        mgr = MicrophoneManager()
        mgr._is_recording = True

        # Push 3 test chunks
        for i in range(3):
            mgr._audio_callback(np.ones(512, dtype=np.float32) * i, 512, None, None)

        drained = mgr.drain_chunks()
        assert len(drained) == 3

        # After drain, buffer should be empty
        assert mgr.get_chunk(timeout=0.01) is None

        # Test clear
        mgr._audio_callback(np.ones(512, dtype=np.float32), 512, None, None)
        mgr.clear_buffer()
        assert mgr.get_chunk(timeout=0.01) is None

    def test_subscriber_dispatch(self) -> None:
        mgr = MicrophoneManager()
        mgr._is_recording = True

        received_chunks = []
        callback = lambda c: received_chunks.append(c)

        mgr.subscribe(callback)

        test_data = np.zeros(512, dtype=np.float32)
        mgr._audio_callback(test_data, 512, None, None)

        assert len(received_chunks) == 1
        assert np.array_equal(received_chunks[0], test_data)

        # Unsubscribe
        mgr.unsubscribe(callback)
        mgr._audio_callback(test_data, 512, None, None)
        assert len(received_chunks) == 1

    def test_set_device_alias_default_system_microphone(self) -> None:
        mgr = MicrophoneManager()
        assert mgr.set_device("Default System Microphone") is True
        assert mgr.active_device_name == "default"
        assert mgr.active_device_index is None
        assert mgr._device_unavailable is False

    def test_set_device_no_silent_fallback(self) -> None:
        mgr = MicrophoneManager()
        errors = []
        mgr.error_occurred.connect(errors.append)
        statuses = []
        mgr.status_changed.connect(statuses.append)

        # Non-existent device name
        assert mgr.set_device("NonExistentPhantomMicrophone12345") is False
        assert mgr._device_unavailable is True
        assert mgr.active_device_index == -1
        assert len(errors) == 1
        assert "Microphone unavailable" in errors[0]
        assert "unavailable" in statuses

        # start_recording should fail cleanly and not silently pick another device
        assert mgr.start_recording() is False

    def test_stream_active_telemetry(self) -> None:
        mgr = MicrophoneManager(frame_samples=512)
        mgr._is_recording = True
        
        # When _stream is None, stream is not active
        assert mgr.is_stream_active() is False

        # Mock an active stream object
        class DummyStream:
            active = True
        mgr._stream = DummyStream()
        assert mgr.is_stream_active() is True

        test_frame = np.ones(512, dtype=np.float32) * 0.05
        mgr._audio_callback(test_frame, 512, None, None)

        assert mgr._frames_captured == 1
        assert mgr._samples_captured == 512
        assert mgr._last_callback_time > 0
