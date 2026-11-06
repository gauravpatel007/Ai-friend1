"""Tests for AudioPlayer output streaming, stereo upmixing, and lip sync amplitude analysis."""

from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
import sounddevice as sd

from app.voice.audio_player import AudioOutputDeviceInfo, AudioPlayer


class TestAudioPlayer:
    """Unit tests for AudioPlayer."""

    def test_audio_output_device_info(self) -> None:
        info = AudioOutputDeviceInfo(
            index=3,
            name="Speakers",
            hostapi_name="DirectSound",
            max_output_channels=2,
            default_samplerate=44100.0,
            is_default=True,
        )
        assert info.display_name() == "Speakers (DirectSound)"
        assert info.is_default is True

    def test_volume_and_mute_controls(self) -> None:
        player = AudioPlayer()
        assert player.volume == 1.0
        assert player.is_muted is False

        player.set_volume(0.65)
        assert player.volume == 0.65

        # Clamp boundaries
        player.set_volume(1.8)
        assert player.volume == 1.0
        player.set_volume(-0.5)
        assert player.volume == 0.0

        player.set_muted(True)
        assert player.is_muted

    def test_device_selection(self) -> None:
        player = AudioPlayer()
        assert player.set_device("default") is True
        assert player._active_device_name == "default"

        # Invalid index returns False
        assert player.set_device(999999) is False

    def test_audio_callback_mono_buffer(self, qtbot) -> None:
        player = AudioPlayer(block_size=512)
        sine = (0.3 * np.sin(np.linspace(0, 10, 1024, dtype=np.float32))).astype(np.float32)
        player._samples = sine
        player._sample_rate = 22050
        player._total_samples = len(sine)
        player._current_index = 0
        player._is_playing = True

        amplitudes = []
        player.amplitude_updated.connect(amplitudes.append)

        outdata = np.zeros((512, 1), dtype=np.float32)
        player._audio_callback(outdata, 512, None, None)

        assert player._current_index == 512
        assert not np.allclose(outdata, 0.0)
        assert len(amplitudes) >= 1
        assert 0.0 < amplitudes[0] <= 1.0

    def test_audio_callback_stereo_upmixing(self, qtbot) -> None:
        """Verify Bug 15: mono audio samples are duplicated identically across stereo channels."""
        player = AudioPlayer(block_size=512)
        sine = (0.4 * np.sin(np.linspace(0, 10, 1024, dtype=np.float32))).astype(np.float32)
        player._samples = sine
        player._sample_rate = 22050
        player._total_samples = len(sine)
        player._current_index = 0
        player._is_playing = True

        outdata = np.zeros((512, 2), dtype=np.float32)
        player._audio_callback(outdata, 512, None, None)

        assert player._current_index == 512
        # Both Left and Right channels must contain audio
        assert not np.allclose(outdata[:, 0], 0.0)
        assert not np.allclose(outdata[:, 1], 0.0)
        # Left and Right channels must be perfectly identical (mono-to-stereo upmix)
        assert np.array_equal(outdata[:, 0], outdata[:, 1])

    def test_determine_output_channels(self) -> None:
        """Verify _determine_output_channels correctly picks stereo or mono based on device info."""
        with patch("sounddevice.query_devices") as mock_query:
            # Stereo device -> 2
            mock_query.return_value = {"max_output_channels": 2}
            assert AudioPlayer._determine_output_channels(0) == 2

            # 5.1 Surround device -> 2
            mock_query.return_value = {"max_output_channels": 6}
            assert AudioPlayer._determine_output_channels(1) == 2

            # Single-channel mono device -> 1
            mock_query.return_value = {"max_output_channels": 1}
            assert AudioPlayer._determine_output_channels(2) == 1

            # Query failure -> defaults to 2 (safe for Windows WASAPI)
            mock_query.side_effect = Exception("Query error")
            assert AudioPlayer._determine_output_channels(3) == 2

    def test_resample_audio_helper(self) -> None:
        """Verify _resample_audio correctly converts sampling rates."""
        orig_samples = np.ones(22050, dtype=np.float32)
        resampled = AudioPlayer._resample_audio(orig_samples, 22050, 48000)
        assert len(resampled) == 48000
        assert resampled.dtype == np.float32

        # Same rate returns original reference
        same = AudioPlayer._resample_audio(orig_samples, 22050, 22050)
        assert same is orig_samples

    def test_play_configures_stereo_output_by_default(self) -> None:
        """Verify play() configures OutputStream with channels=2 on stereo devices."""
        player = AudioPlayer()
        samples = (0.5 * np.sin(np.linspace(0, 10, 1000, dtype=np.float32))).astype(np.float32)

        mock_stream = MagicMock()
        with patch("sounddevice.query_devices", return_value={"max_output_channels": 2, "default_samplerate": 48000.0}), \
             patch("sounddevice.OutputStream", return_value=mock_stream) as mock_out:
            ok = player.play(samples, 22050)
            assert ok is True
            assert player.is_playing is True
            assert player.output_channels == 2
            # Verify channels=2 was requested
            assert mock_out.call_args.kwargs["channels"] == 2
            assert mock_out.call_args.kwargs["samplerate"] == 22050
            mock_stream.start.assert_called_once()

        player.stop()

    def test_play_fallback_channel_on_portaudio_error(self) -> None:
        """Verify play() falls back from stereo to mono if stereo stream fails."""
        player = AudioPlayer()
        samples = np.ones(500, dtype=np.float32)

        mock_stream = MagicMock()

        def stream_side_effect(**kwargs):
            if kwargs.get("channels") == 2:
                raise sd.PortAudioError("Invalid number of channels [PaErrorCode -9998]", -9998)
            return mock_stream

        with patch("sounddevice.query_devices", return_value={"max_output_channels": 2, "default_samplerate": 44100.0}), \
             patch("sounddevice.OutputStream", side_effect=stream_side_effect) as mock_out:
            ok = player.play(samples, 22050)
            assert ok is True
            assert player.output_channels == 1
            assert mock_out.call_count == 2
            mock_stream.start.assert_called_once()

        player.stop()

    def test_play_resamples_on_invalid_sample_rate(self) -> None:
        """Verify play() falls back to device default samplerate when requested rate is rejected."""
        player = AudioPlayer()
        samples = np.ones(2205, dtype=np.float32)

        mock_stream = MagicMock()

        def stream_side_effect(**kwargs):
            if kwargs.get("samplerate") == 22050:
                raise sd.PortAudioError("Invalid sample rate [PaErrorCode -9997]", -9997)
            return mock_stream

        with patch("sounddevice.query_devices", return_value={"max_output_channels": 2, "default_samplerate": 48000.0}), \
             patch("sounddevice.OutputStream", side_effect=stream_side_effect) as mock_out:
            ok = player.play(samples, 22050)
            assert ok is True
            assert player._sample_rate == 48000
            assert mock_out.call_count == 3
            assert mock_out.call_args.kwargs["samplerate"] == 48000
            assert mock_out.call_args.kwargs["channels"] == 2
            mock_stream.start.assert_called_once()

        player.stop()

    def test_stop_playback_resets_lip_sync(self, qtbot) -> None:
        player = AudioPlayer()
        player._is_playing = True
        player._samples = np.ones(1000, dtype=np.float32)

        amplitudes = []
        stopped_emitted = []
        player.amplitude_updated.connect(amplitudes.append)
        player.playback_stopped.connect(lambda: stopped_emitted.append(True))

        player.stop()

        assert player.is_playing is False
        assert len(stopped_emitted) == 1
        # Crucial for lip sync: mouth returns to closed (0.0)
        assert len(amplitudes) >= 1
        assert amplitudes[-1] == 0.0
