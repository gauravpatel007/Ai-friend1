"""Tests for TTS engines (Piper, Kokoro) and VoiceService speech synthesis loop."""

from pathlib import Path
import numpy as np
import pytest

from app.voice.audio_player import AudioPlayer
from app.voice.kokoro_engine import KokoroTTSEngine
from app.voice.piper_engine import PiperTTSEngine
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.voice_service import VoiceMode, VoiceService


class MockTTSEngine(BaseTTSEngine):
    """Mock TTS synthesizer for testing speech pipeline without network models."""

    def __init__(self, sample_rate: int = 22050) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.synthesize_calls = []

    def load_model(self, voice_name=None) -> bool:
        self._is_loaded = True
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        self.synthesize_calls.append(text)
        samples = np.ones(int(self.sample_rate * 0.2), dtype=np.float32) * 0.1
        audio = SynthesizedAudio(
            samples=samples,
            sample_rate=self.sample_rate,
            duration_seconds=0.2,
            text=text,
            voice_name="mock_voice",
        )
        self.synthesis_completed.emit(audio)
        return audio

    def stop(self) -> None:
        pass

    def unload_model(self) -> None:
        self._is_loaded = False

    def get_available_voices(self) -> list[str]:
        return ["mock_voice"]


class TestTTSEngines:
    """Unit tests for TTS engines."""

    def test_synthesized_audio_properties(self) -> None:
        samples = np.zeros(22050, dtype=np.float32)
        audio = SynthesizedAudio(
            samples=samples,
            sample_rate=22050,
            duration_seconds=1.0,
            text="Hello world",
            voice_name="test_voice",
        )
        assert audio.duration_seconds == 1.0
        assert not audio.is_empty

        empty_audio = SynthesizedAudio(
            samples=np.zeros(0, dtype=np.float32),
            sample_rate=22050,
            duration_seconds=0.0,
            text="",
            voice_name="test",
        )
        assert empty_audio.is_empty

    def test_piper_engine_properties_and_fallback(self, qapp_instance, monkeypatch) -> None:
        piper = PiperTTSEngine()
        voices = piper.get_available_voices()
        assert "en_US-lessac-medium" in voices
        assert "en_US-amy-low" in voices

        # Speed setting
        piper.speed = 1.5
        assert piper.speed == 1.5

        # Ensure download does not hang when offline in tests
        monkeypatch.setattr(piper, "download_voice_if_needed", lambda voice_name: False)

        # Synthesis with fallback when offline
        audio = piper.synthesize("Hello Buddy!")
        assert isinstance(audio, SynthesizedAudio)
        assert len(audio.samples) > 0
        assert audio.sample_rate == 22050
        assert audio.duration_seconds > 0.0

    def test_kokoro_engine_properties_and_fallback(self, qapp_instance, monkeypatch) -> None:
        kokoro = KokoroTTSEngine()
        voices = kokoro.get_available_voices()
        assert "af_heart" in voices

        kokoro.speed = 1.2
        assert kokoro.speed == 1.2

        # Ensure download does not hang when offline in tests
        monkeypatch.setattr(kokoro, "download_model_if_needed", lambda: False)

        # Synthesis with fallback when offline
        audio = kokoro.synthesize("How are you today?")
        assert isinstance(audio, SynthesizedAudio)
        assert len(audio.samples) > 0
        assert audio.sample_rate == 24000
        assert audio.duration_seconds > 0.0

    def test_voice_service_tts_speak_and_interrupt(self, qtbot) -> None:
        mock_tts = MockTTSEngine()
        player = AudioPlayer()
        service = VoiceService(audio_player=player)
        service.buddy_state_manager.wake_up()
        service.active_tts_engine = mock_tts

        speaking_started_events = []
        speaking_finished_events = []
        service.speaking_started.connect(lambda: speaking_started_events.append(True))
        service.speaking_finished.connect(lambda: speaking_finished_events.append(True))

        # Speak text
        service.speak("I am speaking now.")

        # Wait until mock synthesized audio starts playing
        qtbot.waitUntil(lambda: len(mock_tts.synthesize_calls) == 1, timeout=3000)

        # Interrupt playback
        service.stop_speaking()
        assert player.is_playing is False
        service.stop()
        player.stop()

    def test_tts_engine_is_available_method(self, qapp_instance, tmp_path, monkeypatch) -> None:
        """Bug 6: Verify is_available() method on BaseTTSEngine, Piper, and Kokoro."""
        import sys
        from unittest.mock import MagicMock

        # 1. Base engine
        base = MockTTSEngine()
        assert base.is_available() is False
        base.load_model()
        assert base.is_available() is True

        # 2. Piper engine
        monkeypatch.setitem(sys.modules, "piper", MagicMock())
        piper = PiperTTSEngine(models_dir=tmp_path / "piper")
        # Empty dir -> False
        assert piper.is_available() is False

        # Create mock piper model files
        (tmp_path / "piper").mkdir(parents=True, exist_ok=True)
        (tmp_path / "piper" / f"{piper.active_voice_name}.onnx").write_bytes(b"dummy_onnx")
        (tmp_path / "piper" / f"{piper.active_voice_name}.onnx.json").write_text("{}")
        assert piper.is_available() is True

        # 3. Kokoro engine
        monkeypatch.setitem(sys.modules, "kokoro_onnx", MagicMock())
        kokoro = KokoroTTSEngine(models_dir=tmp_path / "kokoro")
        assert kokoro.is_available() is False

        (tmp_path / "kokoro").mkdir(parents=True, exist_ok=True)
        (tmp_path / "kokoro" / "kokoro-v0_19.onnx").write_bytes(b"dummy_onnx")
        (tmp_path / "kokoro" / "voices.bin").write_bytes(b"dummy_voices")
        assert kokoro.is_available() is True

    def test_kokoro_delegates_to_fallback_engine(self, qapp_instance, monkeypatch) -> None:
        """Bug 6: When Kokoro models are absent, speech synthesis delegates to fallback engine."""
        mock_fallback = MockTTSEngine(sample_rate=22050)
        mock_fallback.load_model()
        assert mock_fallback.is_available() is True

        kokoro = KokoroTTSEngine(models_dir=Path("/nonexistent/kokoro"), fallback_engine=mock_fallback)
        # Prevent downloading in unit test
        monkeypatch.setattr(kokoro, "download_model_if_needed", lambda: False)

        fallback_completed = []
        kokoro_completed = []
        mock_fallback.synthesis_completed.connect(lambda a: fallback_completed.append(a))
        kokoro.synthesis_completed.connect(lambda a: kokoro_completed.append(a))

        # Synthesize should cleanly delegate to mock_fallback rather than returning acoustic tones
        audio = kokoro.synthesize("Hello through fallback!")
        assert len(mock_fallback.synthesize_calls) == 1
        assert mock_fallback.synthesize_calls[0] == "Hello through fallback!"
        assert audio.voice_name == "mock_voice"
        # Bug #19: Fallback engine emits its own signal; Kokoro must NOT emit duplicate
        assert len(fallback_completed) == 1
        assert len(kokoro_completed) == 0

    def test_kokoro_download_model_if_needed_flow(self, tmp_path, monkeypatch) -> None:
        """Bug 6: Verify Kokoro automated model download logic handles both model and voices."""
        kokoro_dir = tmp_path / "kokoro_models"
        kokoro = KokoroTTSEngine(models_dir=kokoro_dir)

        download_calls = []

        def mock_download_file(url: str, dest_path, timeout=60.0) -> bool:
            download_calls.append((url, str(dest_path)))
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"mock_bytes")
            return True

        monkeypatch.setattr(kokoro, "_download_file", mock_download_file)

        # Mock huggingface_hub to fail so it exercises GitHub releases fallback
        def mock_hf_hub_download(*args, **kwargs):
            raise RuntimeError("HF hub offline")

        import huggingface_hub
        monkeypatch.setattr(huggingface_hub, "hf_hub_download", mock_hf_hub_download)

        success = kokoro.download_model_if_needed()
        assert success is True
        assert (kokoro_dir / "kokoro-v0_19.onnx").exists()
        assert (kokoro_dir / "voices.bin").exists()

        # Calling again when files exist should return immediately without downloading
        download_calls.clear()
        assert kokoro.download_model_if_needed() is True
        assert len(download_calls) == 0

    def test_voice_service_tts_availability_and_switching(self, qapp_instance) -> None:
        """Bug 6 & Bug 16: Verify VoiceService switches engines and reports is_tts_available."""
        service = VoiceService()
        service.set_tts_engine("piper")
        assert hasattr(service, "is_tts_available")
        assert service.active_tts_engine is service.piper_engine

        # Switch to Kokoro
        service.set_tts_engine("kokoro")
        assert service.active_tts_engine is service.kokoro_engine
        assert service.conversation_controller.tts_engine is service.kokoro_engine
        assert service.kokoro_engine.fallback_engine is service.piper_engine

        # Switch to System SAPI5 (Bug 16)
        service.set_tts_engine("system")
        from app.voice.sapi5_engine import Sapi5TTSEngine
        assert isinstance(service.active_tts_engine, Sapi5TTSEngine)
        assert service.active_tts_engine is service.sapi_engine
        assert service.conversation_controller.tts_engine is service.sapi_engine
        assert service.tts_engine is service.sapi_engine

        # Test aliases: sapi5, windows
        service.set_tts_engine("sapi5")
        assert service.active_tts_engine is service.sapi_engine
        service.set_tts_engine("windows")
        assert service.active_tts_engine is service.sapi_engine

        # Available TTS engines
        engines = service.get_available_tts_engines()
        assert "piper" in engines
        assert "system" in engines

        # Switch back to Piper
        service.set_tts_engine("piper")
        assert service.active_tts_engine is service.piper_engine
        assert service.conversation_controller.tts_engine is service.piper_engine
        service.stop()

    def test_sapi5_engine_properties_and_synthesis(self, qapp_instance) -> None:
        """Bug 16 & Bug 2: Verify Sapi5TTSEngine native win32com automation and synthesis."""
        from app.voice.sapi5_engine import Sapi5TTSEngine

        engine = Sapi5TTSEngine()
        assert engine.is_available() is True
        voices = engine.get_available_voices()
        assert isinstance(voices, list)
        assert len(voices) > 0

        # Speed property
        engine.speed = 1.3
        assert abs(engine.speed - 1.3) < 1e-4

        # Voice selection
        engine.load_model(voices[0])
        assert engine.active_voice_name == voices[0]

        # Synthesis via native win32com COM automation
        audio = engine.synthesize("Testing Windows speech synthesizer.")
        assert isinstance(audio, SynthesizedAudio)
        assert not audio.is_empty
        assert audio.sample_rate == 22050
        assert len(audio.samples) > 0
        assert audio.duration_seconds > 0.0

        # Empty text
        empty_audio = engine.synthesize("")
        assert empty_audio.is_empty
        assert len(empty_audio.samples) == 0

        engine.stop()
        engine.unload_model()
        assert engine.is_loaded is False

    def test_sapi5_engine_fallback_when_win32com_fails(self, qapp_instance, monkeypatch) -> None:
        """Verify Sapi5TTSEngine handles win32com unavailability gracefully."""
        from app.voice.sapi5_engine import Sapi5TTSEngine
        import sys

        engine = Sapi5TTSEngine()

        # Simulate win32com unavailable
        with monkeypatch.context() as m:
            m.setitem(sys.modules, "win32com", None)
            m.setitem(sys.modules, "win32com.client", None)
            m.setitem(sys.modules, "clr", None)
            # When both win32com and clr are unavailable, is_available evaluates to False
            assert engine.is_available() is False

            # Synthesis returns safe fallback synthetic audio without raising unhandled exceptions
            fallback_audio = engine.synthesize("Fallback test.")
            assert isinstance(fallback_audio, SynthesizedAudio)
            assert len(fallback_audio.samples) > 0

