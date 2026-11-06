"""Comprehensive tests for Phase 9 — Interruption, Wake-Word, and Hands-Free Control.

Covers:
- 9.1 Speech detection during AI playback
- 9.2 Interruption Manager & conversation takeover
- 9.3 False interruption rejection (clicks, duration, VAD confidence)
- 9.4 Echo handling (headset vs speaker mode)
- 9.5 & 9.6 Wake-Word Detection & low-power standby
- 9.7 Wake-Word conversation lifecycle & inactivity timeout
- 9.8 Configurable activation modes (PTT, Wake Word, Continuous, Off)
- 9.9 Emergency stop
- 9.10 Voice interaction testing
"""

import time
import numpy as np
import pytest
from PySide6.QtCore import QObject

from app.character.states import CharacterState
from app.core.signals import signals
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.interruption_manager import InterruptionConfig, InterruptionManager
from app.voice.microphone_manager import MicrophoneManager
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceMode, VoiceService
from app.voice.wake_word_engine import WakeWordConfig, WakeWordEngine
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


# ─────────────────────────────────────────────────────────────────────────────
# Mocks & Fixtures
# ─────────────────────────────────────────────────────────────────────────────

class MockTTS(BaseTTSEngine):
    """Mock TTS Engine producing dummy audio."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.synthesize_calls = []

    def is_available(self) -> bool:
        return True

    def load_model(self, model_name: str) -> bool:
        return True

    def synthesize(self, text: str) -> SynthesizedAudio:
        self.synthesize_calls.append(text)
        samples = np.ones(3200, dtype=np.float32) * 0.1  # 200ms dummy audio
        return SynthesizedAudio(
            samples=samples,
            sample_rate=16000,
            duration_seconds=0.2,
            text=text,
            voice_name="mock_piper",
        )


class MockWhisper(WhisperEngine):
    """Mock Whisper STT Engine."""

    def __init__(self, mock_text: str = "Wait, stop!", mock_lang: str = "en") -> None:
        super().__init__()
        self.mock_text = mock_text
        self.mock_lang = mock_lang

    def ensure_model_loaded(self) -> bool:
        return True

    def transcribe(self, audio_data: np.ndarray, language=None, prompt=None, beam_size=1) -> TranscriptionResult:
        return TranscriptionResult(
            text=self.mock_text,
            language=language or self.mock_lang,
            language_probability=0.99,
            duration_seconds=len(audio_data) / 16000.0,
        )

    def transcribe_async(self, audio_data: np.ndarray, callback=None, language=None, prompt=None) -> None:
        res = self.transcribe(audio_data, language=language, prompt=prompt)
        if callback:
            callback(res)


class MockAIService(QObject):
    """Mock AI Service for streaming response simulation."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cancel_called = False
        self.last_prompt = None

    def ask(self, user_prompt: str, is_voice: bool = True) -> None:
        self.last_prompt = user_prompt

    def cancel_generation(self) -> None:
        self.cancel_called = True


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tests for InterruptionManager (Phase 9.1 - 9.4)
# ─────────────────────────────────────────────────────────────────────────────

class TestInterruptionManager:
    """Tests for InterruptionManager speech detection, false positive filtering, and echo."""

    def test_startup_grace_period_ignores_transients(self, qtbot) -> None:
        """9.3: Speech frames arriving right at playback start (< grace period) are ignored."""
        player = AudioPlayer()
        vad = VADEngine()
        config = InterruptionConfig(playback_grace_period_sec=0.30)
        mgr = InterruptionManager(audio_player=player, vad_engine=vad, config=config)

        interrupted = []
        mgr.interruption_detected.connect(lambda tid, audio: interrupted.append((tid, audio)))

        # Simulate audio playback starting right now
        player._is_playing = True
        mgr._playback_start_time = time.time()  # Just started!

        # Loud frame
        loud_frame = np.ones(512, dtype=np.float32) * 0.5
        for _ in range(5):
            mgr.process_mic_frame(loud_frame, turn_id=1)

        # Nothing should be emitted because we are inside the 300ms grace window
        assert len(interrupted) == 0

    def test_rejects_single_click_and_short_noise(self, qtbot) -> None:
        """9.3: Single keyboard click / brief noise below consecutive frame threshold is rejected."""
        player = AudioPlayer()
        vad = VADEngine()
        config = InterruptionConfig(
            playback_grace_period_sec=0.0,
            consecutive_frames_threshold=3,
            vad_confidence_threshold=0.65,
        )
        mgr = InterruptionManager(audio_player=player, vad_engine=vad, config=config)

        interrupted = []
        mgr.interruption_detected.connect(lambda tid, audio: interrupted.append((tid, audio)))

        player._is_playing = True
        mgr._playback_start_time = time.time() - 1.0  # Well past grace window

        # Mock VAD get_speech_probability to return high confidence for only 1 frame then 0
        original_get_prob = vad.get_speech_probability

        vad.get_speech_probability = lambda frame: 0.85

        # Feed 1 frame
        click_frame = np.ones(512, dtype=np.float32) * 0.3
        mgr.process_mic_frame(click_frame, turn_id=1)
        assert len(interrupted) == 0
        assert mgr._consecutive_speech_frames == 1

        # Feed a frame that falls below threshold
        vad.get_speech_probability = lambda frame: 0.1
        silence_frame = np.zeros(512, dtype=np.float32)
        mgr.process_mic_frame(silence_frame, turn_id=1)

        # Consecutive counter should reset back to 0!
        assert mgr._consecutive_speech_frames == 0
        assert len(interrupted) == 0

        vad.get_speech_probability = original_get_prob

    def test_valid_interruption_detected_and_emits_audio(self, qtbot) -> None:
        """9.2: Sustained user speech triggers interruption with speech audio."""
        player = AudioPlayer()
        vad = VADEngine()
        config = InterruptionConfig(
            playback_grace_period_sec=0.0,
            consecutive_frames_threshold=3,
            min_speech_duration_sec=0.05,
            vad_confidence_threshold=0.65,
        )
        mgr = InterruptionManager(audio_player=player, vad_engine=vad, config=config)

        interrupted = []
        mgr.interruption_detected.connect(lambda tid, audio: interrupted.append((tid, audio)))

        player._is_playing = True
        mgr._playback_start_time = time.time() - 1.0

        # Mock VAD high speech confidence
        vad.get_speech_probability = lambda frame: 0.90

        speech_frame = np.ones(512, dtype=np.float32) * 0.2
        for _ in range(3):
            mgr.process_mic_frame(speech_frame, turn_id=42)

        assert len(interrupted) == 1
        tid, audio = interrupted[0]
        assert tid == 42
        assert len(audio) == 512 * 3  # All 3 chunks accumulated for VAD seeding!

    def test_speaker_echo_handling(self, qtbot) -> None:
        """9.4: Rejects audio feedback when mic amplitude is dominated by speaker output."""
        player = AudioPlayer()
        vad = VADEngine()
        config = InterruptionConfig(
            playback_grace_period_sec=0.0,
            echo_mode="speaker",
            speaker_attenuation_ratio=1.5,
            consecutive_frames_threshold=2,
            min_speech_duration_sec=0.02,
        )
        mgr = InterruptionManager(audio_player=player, vad_engine=vad, config=config)

        interrupted = []
        mgr.interruption_detected.connect(lambda tid, audio: interrupted.append((tid, audio)))

        player._is_playing = True
        mgr._playback_start_time = time.time() - 1.0
        vad.get_speech_probability = lambda frame: 0.95

        # AI Speaker is playing at amplitude 0.8
        mgr._current_playback_amplitude = 0.8

        # Microphone picks up quiet speaker spillover (RMS ~ 0.05 < 0.8 * (0.08 * 1.5) = 0.096)
        echo_frame = np.ones(512, dtype=np.float32) * 0.05
        for _ in range(3):
            mgr.process_mic_frame(echo_frame, turn_id=1)

        # Rejected as speaker feedback
        assert len(interrupted) == 0

        # Now user speaks loud over the speaker (RMS ~ 0.5 > 0.096)
        loud_user_frame = np.ones(512, dtype=np.float32) * 0.5
        for _ in range(2):
            mgr.process_mic_frame(loud_user_frame, turn_id=1)

        # User interruption confirmed!
        assert len(interrupted) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tests for WakeWordEngine (Phase 9.5 - 9.7)
# ─────────────────────────────────────────────────────────────────────────────

class TestWakeWordEngine:
    """Tests for WakeWordEngine standby, phrase detection, and inactivity timeout."""

    def test_wake_word_detection_and_debounce(self, qtbot) -> None:
        """9.5: Activation phrase triggers wake_word_detected with debounce protection."""
        config = WakeWordConfig(
            activation_phrase="hey_buddy",
            threshold=0.5,
            allow_energy_trigger=True,
        )
        engine = WakeWordEngine(config=config)
        engine._debounce_period_sec = 1.0
        engine.enable()

        detected = []
        engine.wake_word_detected.connect(lambda phrase, score: detected.append((phrase, score)))

        # Simulate acoustic pattern: burst above energy threshold
        loud_burst = np.ones(1280, dtype=np.float32) * 0.4
        engine.process_frame(loud_burst)

        assert len(detected) == 1
        assert detected[0][0] == "hey_buddy"
        assert detected[0][1] >= 0.5

        # Re-enter standby to test debounce prevention
        engine.enter_standby()
        engine.process_frame(loud_burst)
        assert len(detected) == 1  # Still 1 because debounce period hasn't passed!

        engine.disable()

    def test_inactivity_timer_lifecycle(self, qapp_instance, qtbot) -> None:
        """9.7: Inactivity timer triggers after timeout seconds of silence."""
        config = WakeWordConfig(
            activation_phrase="hey_buddy",
            inactivity_timeout_sec=0.1,  # 100ms for fast test
        )
        engine = WakeWordEngine(config=config, parent=qapp_instance)
        engine.enable()
        engine.exit_standby()  # Now in active dialogue state

        timeouts = []
        engine.inactivity_timeout.connect(lambda: timeouts.append(True))

        engine.reset_inactivity_timer()
        qtbot.waitUntil(lambda: len(timeouts) == 1, timeout=1500)

        assert len(timeouts) == 1
        assert engine.is_standby is True
        engine.disable()

    def test_phonetic_wake_word_detection_english(self, qtbot) -> None:
        """9.5b: Phonetic speech 'Hey Buddy' via Whisper transcribes and triggers activation."""
        mock_whisper = MockWhisper(mock_text="Hey Buddy", mock_lang="en")
        engine = WakeWordEngine(
            config=WakeWordConfig(activation_phrase="hey_buddy"),
            whisper_engine=mock_whisper,
        )
        engine._debounce_period_sec = 0.0
        engine.enable()
        assert engine.is_standby is True

        detected = []
        engine.wake_word_detected.connect(lambda phrase, score: detected.append((phrase, score)))

        # Speech frames at moderate volume (RMS ~ 0.08, below the 0.25 acoustic burst threshold)
        speech_frame = np.ones(1280, dtype=np.float32) * 0.08
        for _ in range(5):  # 5 * 1280 = 6400 samples (> 5600 min buffer)
            engine.process_frame(speech_frame)

        # Silence pause frames to complete the phrase
        silence_frame = np.zeros(1280, dtype=np.float32)
        for _ in range(3):
            engine.process_frame(silence_frame)

        assert len(detected) == 1
        assert detected[0][0] == "hey_buddy"
        assert detected[0][1] >= 0.90
        assert engine.is_standby is False
        engine.disable()

    def test_phonetic_wake_word_detection_multilingual_gujarati(self, qtbot) -> None:
        """9.5c: Gujarati wake word 'હે બડી' triggers activation."""
        mock_whisper = MockWhisper(mock_text="હે બડી", mock_lang="gu")
        engine = WakeWordEngine(
            config=WakeWordConfig(activation_phrase="hey_buddy"),
            whisper_engine=mock_whisper,
        )
        engine._debounce_period_sec = 0.0
        engine.enable()

        detected = []
        engine.wake_word_detected.connect(lambda phrase, score: detected.append((phrase, score)))

        speech_frame = np.ones(1280, dtype=np.float32) * 0.08
        for _ in range(5):
            engine.process_frame(speech_frame)

        silence_frame = np.zeros(1280, dtype=np.float32)
        for _ in range(3):
            engine.process_frame(silence_frame)

        assert len(detected) == 1
        assert detected[0][0] == "hey_buddy"
        assert engine.is_standby is False
        engine.disable()

    def test_phonetic_wake_word_detection_non_keyword_ignored(self, qtbot) -> None:
        """9.5d: Conversational speech not matching wake word leaves engine in standby."""
        mock_whisper = MockWhisper(mock_text="What time is it right now?", mock_lang="en")
        engine = WakeWordEngine(
            config=WakeWordConfig(activation_phrase="hey_buddy"),
            whisper_engine=mock_whisper,
        )
        engine._debounce_period_sec = 0.0
        engine.enable()

        detected = []
        engine.wake_word_detected.connect(lambda phrase, score: detected.append((phrase, score)))

        speech_frame = np.ones(1280, dtype=np.float32) * 0.08
        for _ in range(5):
            engine.process_frame(speech_frame)

        silence_frame = np.zeros(1280, dtype=np.float32)
        for _ in range(3):
            engine.process_frame(silence_frame)

        assert len(detected) == 0
        assert engine.is_standby is True
        engine.disable()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tests for VoiceConversationController (Phase 9 Integration)
# ─────────────────────────────────────────────────────────────────────────────

class TestVoiceConversationControllerPhase9:
    """Full dialogue lifecycle tests for interruption, wake word, and emergency stop."""

    def _create_controller(self, parent=None, activation_mode=VoiceActivationMode.CONTINUOUS):
        mic = MicrophoneManager()
        vad = VADEngine()
        whisper = MockWhisper()
        player = AudioPlayer()
        tts = MockTTS()
        ai = MockAIService()

        interruption_config = InterruptionConfig(
            playback_grace_period_sec=0.0,
            consecutive_frames_threshold=2,
            min_speech_duration_sec=0.02,
            vad_confidence_threshold=0.6,
        )
        int_mgr = InterruptionManager(
            audio_player=player,
            vad_engine=vad,
            config=interruption_config,
        )

        wake_config = WakeWordConfig(
            activation_phrase="hey_buddy",
            inactivity_timeout_sec=0.15,
            allow_energy_trigger=True,
        )
        wake_engine = WakeWordEngine(config=wake_config)

        controller = VoiceConversationController(
            mic_manager=mic,
            vad_engine=vad,
            whisper_engine=whisper,
            audio_player=player,
            tts_engine=tts,
            ai_service=ai,
            interruption_manager=int_mgr,
            wake_word_engine=wake_engine,
            activation_mode=activation_mode,
            parent=parent,
        )
        return controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine

    def test_interruption_during_ai_playback(self, qtbot) -> None:
        """9.1 & 9.2: User speech during AI_SPEAKING halts audio, clears queue, cancels AI, and listens."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = self._create_controller()

        # Enable barge-in and headset mode for interruption test
        controller.enable_barge_in = True
        int_mgr.set_echo_mode("headset")
        if hasattr(controller, "echo_canceller"):
            controller.echo_canceller.set_echo_mode("headset")
        int_mgr.config.min_speech_duration_sec = 0.05
        int_mgr.config.consecutive_frames_threshold = 2

        interrupted_turns = []
        controller.interruption_triggered.connect(lambda tid: interrupted_turns.append(tid))

        # Put controller into AI_SPEAKING state
        controller._transition_to(ConversationState.AI_SPEAKING)
        initial_turn_id = controller.current_turn_id

        # Enqueue dummy chunk in audio queue
        controller.audio_queue.enqueue_sentence("I think the best way to implement this would be", initial_turn_id)
        player._is_playing = True
        int_mgr._playback_start_time = time.time() - 1.0

        # Mock VAD high speech confidence
        vad.get_speech_probability = lambda f: 0.9

        # Feed 2 consecutive speech frames
        speech_frame = np.ones(512, dtype=np.float32) * 0.25
        controller.process_mic_frame(speech_frame)
        controller.process_mic_frame(speech_frame)

        # Interruption must have been triggered!
        assert len(interrupted_turns) == 1
        assert interrupted_turns[0] == initial_turn_id

        # Verification of 9.2 actions:
        # 1. Audio player stopped
        assert player.is_playing is False

        # 2. Audio queue cleared
        assert controller.audio_queue.is_empty is True

        # 3. AI generation cancelled
        assert ai.cancel_called is True

        # 4. New turn generated (turn ID advanced)
        assert controller.current_turn_id > initial_turn_id

        # 5. Controller state switched to USER_SPEAKING with user utterance preserved in VAD
        assert controller.state == ConversationState.USER_SPEAKING
        assert len(vad._active_utterance_frames) > 0

        controller.cleanup()

    def test_false_interruption_does_not_halt_ai(self, qtbot) -> None:
        """9.3: Single click during AI_SPEAKING does not interrupt dialogue."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = self._create_controller()

        interrupted_turns = []
        controller.interruption_triggered.connect(lambda tid: interrupted_turns.append(tid))

        controller._transition_to(ConversationState.AI_SPEAKING)
        player._is_playing = True
        int_mgr._playback_start_time = time.time() - 1.0

        # Click: only 1 frame above threshold
        vad.get_speech_probability = lambda f: 0.8
        click_frame = np.ones(512, dtype=np.float32) * 0.1
        controller.process_mic_frame(click_frame)

        # AI should continue speaking!
        assert len(interrupted_turns) == 0
        assert controller.state == ConversationState.AI_SPEAKING

        controller.cleanup()

    def test_wake_word_lifecycle_and_timeout(self, qtbot) -> None:
        """9.6 & 9.7: Standby -> Wake Word -> Listening -> Timeout -> Standby."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = self._create_controller(
            activation_mode=VoiceActivationMode.WAKE_WORD
        )

        controller.enable()
        assert controller.state == ConversationState.WAKE_WORD_STANDBY
        assert wake_engine.is_enabled is True

        # User utters wake phrase (energy burst triggers fallback wake detection)
        burst = np.ones(1280, dtype=np.float32) * 0.5
        controller.process_mic_frame(burst)

        # Transitioned to LISTENING!
        assert controller.state == ConversationState.LISTENING

        # Wait for inactivity timeout (150ms configured above)
        qtbot.wait(200)

        # Returned to WAKE_WORD_STANDBY!
        assert controller.state == ConversationState.WAKE_WORD_STANDBY

        controller.cleanup()

    def test_dynamic_activation_mode_switching(self, qtbot) -> None:
        """9.8: Switch between modes dynamically without restart."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = self._create_controller()

        modes_emitted = []
        controller.activation_mode_changed.connect(lambda m: modes_emitted.append(m))

        controller.set_activation_mode(VoiceActivationMode.WAKE_WORD)
        assert controller.activation_mode == VoiceActivationMode.WAKE_WORD
        assert controller.state == ConversationState.WAKE_WORD_STANDBY
        assert wake_engine.is_enabled is True

        controller.set_activation_mode(VoiceActivationMode.CONTINUOUS)
        assert controller.activation_mode == VoiceActivationMode.CONTINUOUS
        assert controller.state == ConversationState.LISTENING
        assert wake_engine.is_enabled is False

        controller.set_activation_mode(VoiceActivationMode.PUSH_TO_TALK)
        assert controller.activation_mode == VoiceActivationMode.PUSH_TO_TALK
        assert controller.state == ConversationState.DISABLED

        controller.cleanup()

    def test_emergency_stop_halts_everything(self, qtbot) -> None:
        """9.9: Emergency stop halts audio player, clears queues, and stops mic capture."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = self._create_controller()

        controller._transition_to(ConversationState.AI_SPEAKING)
        player._is_playing = True
        controller.audio_queue.enqueue_sentence("Some ongoing speech", controller.current_turn_id)

        stopped_signals = []
        controller.emergency_stopped.connect(lambda: stopped_signals.append(True))

        controller.emergency_stop()

        assert len(stopped_signals) == 1
        assert controller.state == ConversationState.DISABLED
        assert player.is_playing is False
        assert controller.audio_queue.is_empty is True
        assert wake_engine.is_enabled is False

        controller.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tests for VoiceService Phase 9 Controls
# ─────────────────────────────────────────────────────────────────────────────

class TestVoiceServicePhase9:
    """Tests for VoiceService integration with Wake Word and Emergency Stop."""

    def test_voice_service_wake_word_and_emergency_stop(self, qtbot) -> None:
        whisper = MockWhisper()
        service = VoiceService(whisper_engine=whisper)

        assert service.mode == VoiceMode.OFF

        # Switch to wake word mode
        service.set_mode(VoiceMode.WAKE_WORD)
        assert service.mode == VoiceMode.WAKE_WORD
        assert service.conversation_controller.state == ConversationState.WAKE_WORD_STANDBY

        # Set echo mode
        service.set_echo_mode("speaker")
        assert service.interruption_manager.config.echo_mode == "speaker"

        # Emergency stop
        service.emergency_stop()
        assert service.mode == VoiceMode.OFF
        assert service.conversation_controller.state == ConversationState.DISABLED

        service.stop()
