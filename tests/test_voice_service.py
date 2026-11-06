"""Tests for VoiceService coordinator, Push-to-Talk, and Continuous VAD."""

import numpy as np
import pytest

from app.voice.microphone_manager import MicrophoneManager
from app.voice.vad_engine import VADEngine
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine
from app.voice.voice_service import VoiceMode, VoiceService


class MockWhisperEngine(WhisperEngine):
    """Mock whisper engine that returns predetermined transcriptions without inference."""

    def __init__(self, mock_text: str = "Test recognized speech", mock_lang: str = "en") -> None:
        super().__init__()
        self.mock_text = mock_text
        self.mock_lang = mock_lang
        self.transcribe_called_with = None

    def ensure_model_loaded(self) -> bool:
        return True

    def transcribe(self, audio_data: np.ndarray, language=None, prompt=None, beam_size=1) -> TranscriptionResult:
        self.transcribe_called_with = audio_data
        result = TranscriptionResult(
            text=self.mock_text,
            language=language or self.mock_lang,
            language_probability=0.95,
            duration_seconds=len(audio_data) / 16000.0,
        )
        self.transcription_completed.emit(result)
        return result

    def transcribe_async(self, audio_data: np.ndarray, callback=None, language=None, prompt=None) -> None:
        result = self.transcribe(audio_data, language=language, prompt=prompt)
        if callback:
            callback(result)


class TestVoiceService:
    """Unit tests for VoiceService coordination."""

    def test_voice_mode_transitions(self) -> None:
        service = VoiceService()
        assert service.mode == VoiceMode.OFF

        service.set_mode(VoiceMode.PUSH_TO_TALK)
        assert service.mode == VoiceMode.PUSH_TO_TALK

        service.set_mode(VoiceMode.CONTINUOUS)
        assert service.mode == VoiceMode.CONTINUOUS

        service.set_mode("off")
        assert service.mode == VoiceMode.OFF

    def test_language_selection(self) -> None:
        service = VoiceService()
        assert service.language is None

        service.set_language("hi")
        assert service.language == "hi"

        service.set_language("gu")
        assert service.language == "gu"

        service.set_language(None)
        assert service.language is None

    def test_push_to_talk_flow(self, qtbot) -> None:
        mock_whisper = MockWhisperEngine(mock_text="Namaste Buddy", mock_lang="hi")
        service = VoiceService(whisper_engine=mock_whisper)
        service.set_language("hi")

        transcriptions = []
        service.transcription_ready.connect(lambda txt, lang: transcriptions.append((txt, lang)))

        # 1. User clicks/holds Push-to-Talk
        service.start_push_to_talk()
        assert service._is_push_to_talking is True

        # 2. Simulate 1 second of audio frames (e.g. 32 frames of 512 samples)
        for _ in range(32):
            frame = np.ones(512, dtype=np.float32) * 0.1
            service._on_audio_frame_received(frame)

        # 3. User releases Push-to-Talk
        service.stop_push_to_talk()
        assert service._is_push_to_talking is False

        # Verify transcription emitted
        assert len(transcriptions) == 1
        assert transcriptions[0][0] == "Namaste Buddy"
        assert transcriptions[0][1] == "hi"
        service.stop()

    def test_continuous_vad_flow(self, qtbot) -> None:
        mock_whisper = MockWhisperEngine(mock_text="Kem cho Buddy", mock_lang="gu")
        service = VoiceService(whisper_engine=mock_whisper)
        service.set_mode(VoiceMode.CONTINUOUS)
        service.set_language("gu")

        speech_detected_emitted = []
        transcriptions = []
        service.speech_detected.connect(lambda: speech_detected_emitted.append(True))
        service.transcription_ready.connect(lambda txt, lang: transcriptions.append((txt, lang)))

        # Simulate VAD speech start event
        service._on_vad_speech_started()
        assert len(speech_detected_emitted) == 1

        # Simulate VAD speech ended with 1.0 second of audio
        dummy_utterance = np.ones(16000, dtype=np.float32) * 0.2
        service._on_vad_speech_ended(dummy_utterance)

        assert len(transcriptions) == 1
        assert transcriptions[0][0] == "Kem cho Buddy"
        assert transcriptions[0][1] == "gu"
        service.stop()

    def test_speak_cancellation_and_cooldown(self) -> None:
        service = VoiceService()
        if hasattr(service, "buddy_state_manager") and service.buddy_state_manager:
            service.buddy_state_manager.wake_up()
        initial_speak_id = service._current_speak_id

        # Calling speak increments speak_id
        service.speak("Test response")
        assert service._current_speak_id == initial_speak_id + 1

        # Simulate audio player playing before stop
        service.audio_player._is_playing = True

        # Calling stop_speaking cancels ongoing speak_id
        service.stop_speaking()
        assert service._current_speak_id == initial_speak_id + 2
        assert service.audio_player.is_playing is False

        # Verify acoustic cooldown is active immediately after stop
        assert service.audio_player.is_in_cooldown(0.45) is True
        service.stop()

    def test_voice_service_tts_engine_property(self) -> None:
        """Bug 4: Verify tts_engine property getter and setter works correctly."""
        service = VoiceService()
        assert service.tts_engine is not None
        assert service.tts_engine is service.active_tts_engine

        # Test setter
        original = service.tts_engine
        service.tts_engine = service.kokoro_engine
        assert service.active_tts_engine is service.kokoro_engine
        assert service.tts_engine is service.kokoro_engine

        # Restore
        service.tts_engine = original
        service.stop()

    def test_voice_service_dynamic_settings_update(self) -> None:
        """Bug 3: Verify dynamic settings updates modify runtime voice parameters."""
        service = VoiceService()

        # 1. Language update
        service._on_setting_changed("voice.language", "gu")
        assert service.language == "gu"
        service._on_setting_changed("voice.language", "auto")
        assert service.language is None

        # 2. Voice speed update
        service._on_setting_changed("voice.voice_speed", 1.35)
        assert abs(service.active_tts_engine.speed - 1.35) < 1e-4

        # 3. Silence threshold update
        service._on_setting_changed("voice.silence_threshold_ms", 850)
        assert service.vad_engine.silence_threshold_ms == 850

        # 4. Mode update
        service._on_setting_changed("voice.mode", "wake_word")
        assert service.mode == VoiceMode.WAKE_WORD

        service._on_setting_changed("voice.mode", "off")
        assert service.mode == VoiceMode.OFF

        # 5. Non-voice keys ignored safely
        service._on_setting_changed("general.theme", "light")
        service.stop()
