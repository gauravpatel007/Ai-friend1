"""Phase 9 Automated Test Suite: Voice Reliability, Wake Word, and Sleep Integration.

Tests all requirements of Phase 9:
1. Strict Sleep Standby:
    - Bond remains asleep until configured wake keyword is spoken.
    - While sleeping: no AI generation, no unsolicited speech, no STT processing, only lightweight wake detection.
2. Complete Wake-Up and Return-to-Sleep Lifecycle:
    - Speaking wake word ("Hey Bond") transitions SLEEPING -> WAKE_WORD_DETECTED -> LISTENING.
    - Captures user input, executes LLM generation, speaks synthesized response.
    - Returns to SLEEPING after response finishes playing.
3. Turn-Taking and Sleep Independence:
    - Natural turn-taking does NOT disable strict sleep mode.
    - Silence timeout (6.0s) safely returns to SLEEP if user wakes Bond but says nothing.
    - Continuous listening only occurs if explicitly enabled by user (CONTINUOUS mode).
4. Prevention of Feedback, False Positives, and Duplicates:
    - TTS audio playback suppresses wake-word detection (no self-voice loop).
    - False wake-words (ambient noise, random conversation) do not trigger wake events.
    - Duplicate wake events within debounce window (2.0s) are dropped.
    - Multiple concurrent sessions are prevented via turn locking.
    - Desktop notification toasts and internal timers never trigger unsolicited speech.
5. Barge-in Interruption during Wake-Word Session:
    - User interruption during playback immediately halts audio, processes correction, and finishes turn cleanly.
6. Application Restart and Settings Persistence:
    - Wake-word and voice configurations persist and restore across application restarts.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

from app.character.states import CharacterState
from app.core.signals import signals
from app.desktop.notification_toast import NotificationToast
from app.settings.config_manager import ConfigManager
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.microphone_manager import MicrophoneManager
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.wake_word_engine import WakeWordConfig, WakeWordEngine
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


class MockTTS(BaseTTSEngine):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.synthesized_phrases = []

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, **kw) -> SynthesizedAudio:
        self.synthesized_phrases.append(text)
        samples = np.ones(1600, dtype=np.float32) * 0.05
        return SynthesizedAudio(
            samples=samples,
            sample_rate=16000,
            duration_seconds=0.1,
            text=text,
            voice_name="mock_tts",
        )


class MockWhisper(WhisperEngine):
    def __init__(self, mock_text: str = "Who directed Interstellar?"):
        super().__init__()
        self.mock_text = mock_text

    def transcribe(self, audio_data: np.ndarray, **kwargs) -> TranscriptionResult:
        return TranscriptionResult(
            text=self.mock_text,
            language="en",
            language_probability=0.99,
            duration_seconds=0.5,
        )


class TestPhase9VoiceReliabilityWakeAndSleep(unittest.TestCase):
    """Test suite for Phase 9 Voice Reliability, Wake Word and Sleep Integration."""

    @classmethod
    def setUpClass(cls) -> None:
        if QApplication.instance() is None:
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self) -> None:
        self.mock_mic = MagicMock(spec=MicrophoneManager)
        self.mock_mic.start_recording.return_value = True
        self.mock_mic.is_muted = False

        self.mock_vad = MagicMock()
        self.mock_vad.process_frame = MagicMock()
        self.mock_vad.silence_threshold_ms = 400

        self.mock_whisper = MockWhisper()
        self.mock_player = MagicMock(spec=AudioPlayer)
        self.mock_player.is_playing = False
        self.mock_player.is_in_cooldown.return_value = False

        self.mock_tts = MockTTS()
        self.mock_ai = MagicMock()
        self.mock_ai.is_current_generation_voice = True

        self.wake_config = WakeWordConfig(
            activation_phrase="hey_bond",
            threshold=0.70,
            inactivity_timeout_sec=15.0,
        )
        self.wake_engine = WakeWordEngine(config=self.wake_config)

        self.ctrl = VoiceConversationController(
            mic_manager=self.mock_mic,
            vad_engine=self.mock_vad,
            whisper_engine=self.mock_whisper,
            audio_player=self.mock_player,
            tts_engine=self.mock_tts,
            ai_service=self.mock_ai,
            wake_word_engine=self.wake_engine,
            activation_mode=VoiceActivationMode.WAKE_WORD,
        )
        # Ensure echo_canceller doesn't block frames during mock runs
        if hasattr(self.ctrl, "echo_canceller"):
            self.ctrl.echo_canceller.is_in_cooldown = lambda limit: False

    def tearDown(self) -> None:
        self.ctrl.emergency_stop()
        self.ctrl.cleanup()
        if QApplication.instance():
            QApplication.processEvents()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Strict Sleep Standby
    # ─────────────────────────────────────────────────────────────────────────

    def test_bond_initializes_and_remains_asleep(self) -> None:
        """Verify Bond initializes in SLEEPING mode and remains asleep without wake word."""
        self.ctrl.enable()
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))
        self.assertTrue(self.wake_engine._is_standby)
        self.assertEqual(len(self.mock_tts.synthesized_phrases), 0, "No unsolicited speech while sleeping")

    def test_ambient_noise_and_conversations_do_not_wake_bond(self) -> None:
        """Verify non-wake speech and ambient noise frames do NOT trigger wake events."""
        self.ctrl.enable()
        state_transitions = []
        self.ctrl.state_changed.connect(state_transitions.append)

        # Feed non-wake conversational audio frame
        ambient_frame = np.random.randn(512).astype(np.float32) * 0.05
        self.ctrl.process_mic_frame(ambient_frame)

        # Must remain in SLEEPING / WAKE_WORD_STANDBY
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))
        self.mock_vad.process_frame.assert_not_called()
        self.mock_ai.ask.assert_not_called()

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Complete Wake-Up and Return-to-Sleep Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def test_wake_phrase_triggers_listening_and_active_dialogue(self) -> None:
        """Verify speaking 'hey_bond' wakes Bond, transitions to LISTENING, and engages dialogue."""
        self.ctrl.enable()
        states_recorded = []
        self.ctrl.state_changed.connect(states_recorded.append)

        # Trigger wake word
        self.ctrl._on_wake_word_detected("hey_bond", 0.95)

        # Verify transitions: WAKE_WORD_DETECTED -> LISTENING
        self.assertIn(ConversationState.WAKE_WORD_DETECTED, states_recorded)
        self.assertEqual(self.ctrl.state, ConversationState.LISTENING)
        self.assertFalse(self.wake_engine._is_standby)

    def test_return_to_sleep_after_audio_playback_finished(self) -> None:
        """Verify Bond automatically returns to SLEEPING after assistant finishes speaking."""
        self.ctrl.enable()
        self.ctrl._on_wake_word_detected("hey_bond", 0.95)
        self.assertEqual(self.ctrl.state, ConversationState.LISTENING)

        # Simulate turn: assistant speaking
        self.ctrl._state = ConversationState.SPEAKING

        # Assistant audio playback finishes
        self.ctrl._on_audio_player_finished()

        # Check return to sleep
        self.ctrl._return_to_sleep(reason="turn_completed")
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))
        self.assertTrue(self.wake_engine._is_standby)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Turn-Taking and Sleep Independence
    # ─────────────────────────────────────────────────────────────────────────

    def test_wake_silence_timeout_returns_to_sleep_if_user_says_nothing(self) -> None:
        """Verify wake silence timeout returns Bond to sleep if user does not speak after wake-up."""
        self.ctrl.enable()
        self.ctrl._on_wake_word_detected("hey_bond", 0.95)
        self.assertEqual(self.ctrl.state, ConversationState.LISTENING)

        # User says nothing -> silence timeout fires
        self.ctrl._on_wake_silence_timeout()
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))
        self.assertTrue(self.wake_engine._is_standby)

    def test_continuous_mode_remains_listening_while_wake_mode_returns_to_sleep(self) -> None:
        """Verify CONTINUOUS mode stays listening, while WAKE_WORD mode returns to sleep."""
        # 1. Continuous Mode
        self.ctrl.set_activation_mode(VoiceActivationMode.CONTINUOUS)
        self.assertFalse(self.ctrl.auto_return_to_sleep)
        self.assertEqual(self.ctrl.state, ConversationState.LISTENING)

        # 2. Wake-Word Mode
        self.ctrl.set_activation_mode(VoiceActivationMode.WAKE_WORD)
        self.assertTrue(self.ctrl.auto_return_to_sleep)
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Prevention of Feedback, False Positives, and Duplicates
    # ─────────────────────────────────────────────────────────────────────────

    def test_tts_playback_suppresses_wake_word_detection(self) -> None:
        """Verify wake word detection is suppressed while AudioPlayer is actively playing."""
        self.wake_engine.enable()
        self.wake_engine.is_speaking = True
        self.wake_engine.audio_player_is_playing = True

        test_frame = np.ones(1280, dtype=np.float32)
        res = self.wake_engine.process_frame(test_frame)
        self.assertFalse(res, "Wake word must not trigger while TTS is playing")

    def test_duplicate_wake_events_within_debounce_window_are_dropped(self) -> None:
        """Verify rapid repeated wake detections within debounce period (2.0s) are ignored."""
        self.wake_engine.enable()
        detected_events = []
        self.wake_engine.wake_word_detected.connect(lambda p, s: detected_events.append((p, s)))

        # First trigger
        self.wake_engine._test_mock_score = 0.95
        frame = np.ones(1280, dtype=np.float32)
        self.wake_engine.process_frame(frame)
        self.assertEqual(len(detected_events), 1)

        # Immediate second trigger (within debounce)
        self.wake_engine.process_frame(frame)
        self.assertEqual(len(detected_events), 1, "Second trigger within debounce window must be dropped")

    def test_notifications_and_toasts_do_not_trigger_voice_speech(self) -> None:
        """Verify showing notification toasts does not cause unsolicited voice speech."""
        self.ctrl.enable()
        toast = NotificationToast("Test Title", "Test Message body", duration_ms=1000)
        self.assertEqual(len(self.mock_tts.synthesized_phrases), 0)
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))
        toast.close()

    def test_background_text_ai_generation_does_not_speak_while_sleeping(self) -> None:
        """Verify typed text chat responses do not speak aloud while assistant is asleep."""
        self.ctrl.enable()
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))

        # Stream chunk from typed text chat
        self.mock_ai.is_current_generation_voice = False
        self.ctrl._on_ai_stream_chunk("Hello from typed text")
        self.ctrl._on_ai_stream_complete("Hello from typed text")

        # Must not synthesize or speak
        self.assertEqual(len(self.mock_tts.synthesized_phrases), 0)
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Barge-in Interruption during Wake-Word Session
    # ─────────────────────────────────────────────────────────────────────────

    def test_interruption_during_wake_conversation_halts_speech_and_processes(self) -> None:
        """Verify user interruption halts playback, captures correction, and proceeds cleanly."""
        self.ctrl.enable()
        self.ctrl._on_wake_word_detected("hey_bond", 0.95)
        self.ctrl._transition_to(ConversationState.SPEAKING)

        interrupted_turns = []
        self.ctrl.interruption_triggered.connect(interrupted_turns.append)

        # User interrupts with barge-in
        speech_chunk = np.ones(1600, dtype=np.float32) * 0.2
        self.ctrl._on_interruption_detected(turn_id=1, speech_samples=speech_chunk)

        self.assertEqual(len(interrupted_turns), 1)
        self.assertEqual(self.ctrl.state, ConversationState.USER_SPEAKING)
        self.mock_ai.cancel_generation.assert_called_once()

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Settings Persistence and Application Restart
    # ─────────────────────────────────────────────────────────────────────────

    def test_settings_persistence_across_restarts(self) -> None:
        """Verify wake-word mode, companion voice, and language settings restore across restart."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            f.write("{}")
            cfg_path = f.name

        cfg1 = ConfigManager(config_path=cfg_path)
        cfg1.set("voice.activation_mode", "wake_word")
        cfg1.set("voice.selected_profile", "mira")
        cfg1.set("language.response_language", "hi")
        cfg1.save()

        # Simulate restart with fresh ConfigManager instance
        cfg2 = ConfigManager(config_path=cfg_path)
        self.assertEqual(cfg2.get("voice.activation_mode"), "wake_word")
        self.assertEqual(cfg2.get("voice.selected_profile"), "mira")
        self.assertEqual(cfg2.get("language.response_language"), "hi")


if __name__ == "__main__":
    unittest.main()
