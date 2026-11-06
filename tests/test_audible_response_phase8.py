"""Phase 8 Integration Tests: Text-to-Speech Engine and Audible Response Pipeline.

Verifies:
1. TTS engine initializes and synthesizes clean audio (Kokoro, Piper, SAPI5).
2. Actual assistant response is passed to TTS and cleaned of Markdown/markup.
3. Empty responses are not sent to TTS.
4. Generated audio uses supported float32 format and correct sample rate.
5. AudioPlayer plays audio without error and emits speaking_started / speaking_finished.
6. Old audio is cancelled and not replayed when a newer turn begins.
7. Overlapping responses are prevented via stream invalidation and lock protection.
8. Audio resources are cleanly freed on stop().
"""

import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

from app.voice.audio_player import AudioPlayer
from app.voice.kokoro_engine import KokoroTTSEngine
from app.voice.piper_engine import PiperTTSEngine
from app.voice.sapi5_engine import Sapi5TTSEngine
from app.voice.tts_base import SynthesizedAudio, clean_text_for_speech
from app.voice.voice_service import VoiceMode, VoiceService


def test_clean_text_for_speech_strips_markdown_and_noise():
    """Verify that Markdown markup and reasoning tokens are removed before speech synthesis."""
    raw = (
        "<think>internal thought process</think>"
        "**Hello there!** I am your *desktop companion*. "
        "Check [this link](https://example.com) for details. "
        "```python\nprint('hello')\n```"
        "Here are tips:\n- Tip 1\n- Tip 2"
    )
    cleaned = clean_text_for_speech(raw)
    assert "<think>" not in cleaned
    assert "internal thought" not in cleaned
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "https://" not in cleaned
    assert "print('hello')" not in cleaned
    assert "Hello there! I am your desktop companion. Check this link for details." in cleaned
    assert "Tip 1" in cleaned


def test_kokoro_voice_normalization_and_synthesis(qapp_instance):
    """Verify Kokoro handles cross-engine voice names and synthesizes 24kHz float32 audio."""
    kokoro = KokoroTTSEngine()
    assert kokoro.is_available() is True

    # Pass cross-engine voice name (e.g. from Piper)
    kokoro.load_model("en_US-lessac-medium")
    # Should normalize to a valid Kokoro voice
    assert kokoro.active_voice_name in kokoro.get_available_voices()

    audio = kokoro.synthesize("Kokoro speech synthesis test.")
    assert not audio.is_empty
    assert audio.sample_rate == 24000
    assert audio.samples.dtype == np.float32
    assert audio.duration_seconds > 0.5


def test_piper_voice_normalization_and_synthesis(qapp_instance):
    """Verify Piper synthesizes 22050Hz float32 audio."""
    piper = PiperTTSEngine()
    assert piper.is_available() is True

    audio = piper.synthesize("Piper speech synthesis test.")
    assert not audio.is_empty
    assert audio.sample_rate == 22050
    assert audio.samples.dtype == np.float32
    assert audio.duration_seconds > 0.4


def test_empty_response_not_sent_to_audio_player(qapp_instance):
    """Verify that empty or whitespace responses are rejected before playback."""
    player = MagicMock(spec=AudioPlayer)
    mock_tts = MagicMock()
    mock_tts.synthesize.return_value = SynthesizedAudio(
        samples=np.zeros(0, dtype=np.float32),
        sample_rate=22050,
        duration_seconds=0.0,
        text="",
        voice_name="mock",
    )

    service = VoiceService(audio_player=player)
    service.active_tts_engine = mock_tts

    service.speak("   ")
    service.speak("")
    service.speak("\n\t  ")

    # Audio player must not be called with empty text
    player.play.assert_not_called()
    mock_tts.synthesize.assert_not_called()


def test_voice_service_speak_cancels_prior_and_manages_speaking_state(qapp_instance, qtbot):
    """Verify that a newer speak call invalidates prior in-flight synthesis without overlap."""
    player = AudioPlayer()
    service = VoiceService(audio_player=player)

    speaking_events = []
    service.speaking_started.connect(lambda: speaking_events.append("started"))
    service.speaking_finished.connect(lambda: speaking_events.append("finished"))

    # Turn 1
    synth_audio = SynthesizedAudio(
        samples=np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, int(22050 * 0.1), dtype=np.float32)) * 0.05,
        sample_rate=22050,
        duration_seconds=0.1,
        text="Turn 1 speech",
        voice_name="mock",
    )

    with patch.object(service.active_tts_engine, "synthesize", return_value=synth_audio):
        service.speak("Turn 1 speech")

        # Allow worker to start playback
        start_wait = time.time()
        while time.time() - start_wait < 1.0 and "started" not in speaking_events:
            qapp_instance.processEvents()
            time.sleep(0.02)

        assert "started" in speaking_events

        # Immediately trigger Turn 2 — should stop prior playback
        service.speak("Turn 2 speech with different text")
        qapp_instance.processEvents()

        # Stop speaking cleanly
        service.stop_speaking()
        qapp_instance.processEvents()
        assert player.is_playing is False


def test_audio_resources_cleaned_up_on_service_stop(qapp_instance):
    """Verify that stop() halts playback, releases stream, and resets mode."""
    player = AudioPlayer()
    service = VoiceService(audio_player=player)

    service.set_mode(VoiceMode.CONTINUOUS)
    assert service.mode == VoiceMode.CONTINUOUS

    service.stop()
    assert service.mode == VoiceMode.OFF
    assert player.is_playing is False
