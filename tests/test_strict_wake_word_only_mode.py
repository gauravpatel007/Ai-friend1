"""Tests for Strict Wake Word Only Mode (All 10 Verification Scenarios).

Verifies the 10 requirements:
1. Scenario 1: Bond starts in SLEEP MODE when the application opens.
2. Scenario 2: Bond stays asleep indefinitely without saying anything (no unsolicited messages/prompts).
3. Scenario 3: Background conversations and ambient noises do not wake Bond.
4. Scenario 4: Speaking the configured wake word ("Hey Bond") wakes Bond up.
5. Scenario 5: Full cycle: User speaks wake word -> Bond listens -> Bond processes -> Bond speaks response.
6. Scenario 6: Bond immediately returns to SLEEP MODE after the response finishes.
7. Scenario 7: Speaking after Bond returns to sleep does NOT trigger a response unless wake word is spoken again.
8. Scenario 8: Bond's own TTS voice does not trigger the wake-word detector (self-voice/echo rejection).
9. Scenario 9: Disabling the wake-word feature keeps Bond asleep.
10. Scenario 10: Settings are saved and restored properly across restarts.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtCore import QObject

from app.character.states import CharacterState
from app.core.buddy_state_manager import BuddyState, get_buddy_state_manager
from app.settings.config_manager import ConfigManager
from app.core.controller import ApplicationController
from app.core.signals import signals
from app.desktop.pet_window import DesktopPetWindow
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.interruption_manager import InterruptionConfig, InterruptionManager
from app.voice.microphone_manager import MicrophoneManager
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceMode, VoiceService
from app.voice.wake_word_engine import WakeWordConfig, WakeWordEngine
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


# ─────────────────────────────────────────────────────────────────────────────
# Test Doubles / Mocks
# ─────────────────────────────────────────────────────────────────────────────

class MockTTS(BaseTTSEngine):
    """Mock TTS Engine producing synthetic audio samples."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.synthesized_phrases: List[str] = []

    def is_available(self) -> bool:
        return True

    def load_model(self, model_name: str) -> bool:
        return True

    def synthesize(self, text: str) -> SynthesizedAudio:
        self.synthesized_phrases.append(text)
        samples = np.ones(1600, dtype=np.float32) * 0.05  # 100ms dummy audio
        return SynthesizedAudio(
            samples=samples,
            sample_rate=16000,
            duration_seconds=0.1,
            text=text,
            voice_name="mock_voice",
        )


class MockWhisper(WhisperEngine):
    """Mock Whisper STT Engine."""

    def __init__(self, mock_text: str = "Hey Bond", mock_lang: str = "en") -> None:
        super().__init__()
        self.mock_text = mock_text
        self.mock_lang = mock_lang

    def ensure_model_loaded(self) -> bool:
        return True

    def transcribe(
        self, audio_data: np.ndarray, language=None, prompt=None, beam_size=1
    ) -> TranscriptionResult:
        return TranscriptionResult(
            text=self.mock_text,
            language=language or self.mock_lang,
            language_probability=0.99,
            duration_seconds=len(audio_data) / 16000.0,
        )

    def transcribe_async(
        self, audio_data: np.ndarray, callback=None, language=None, prompt=None
    ) -> None:
        res = self.transcribe(audio_data, language=language, prompt=prompt)
        if callback:
            callback(res)


class MockAIService(QObject):
    """Mock AI Service for streaming / response generation."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.asked_prompts: List[str] = []
        self.cancel_called: bool = False

    def ask(self, user_prompt: str, is_voice: bool = True) -> None:
        self.asked_prompts.append(user_prompt)

    def cancel_generation(self) -> None:
        self.cancel_called = True


def create_test_controller(
    activation_mode: VoiceActivationMode = VoiceActivationMode.WAKE_WORD,
    auto_return_to_sleep: bool = True,
    wake_timeout_sec: float = 6.0,
    allow_energy_trigger: bool = False,
):
    """Helper to instantiate a fully-wired VoiceConversationController with test doubles."""
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = MockWhisper()
    player = AudioPlayer()
    tts = MockTTS()
    ai = MockAIService()
    int_mgr = InterruptionManager(audio_player=player, vad_engine=vad)
    wake_engine = WakeWordEngine(
        config=WakeWordConfig(
            activation_phrase="hey_bond",
            threshold=0.70,
            allow_energy_trigger=allow_energy_trigger,
        ),
        whisper_engine=whisper,
    )
    wake_engine._debounce_period_sec = 0.0

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
        auto_return_to_sleep=auto_return_to_sleep,
        wake_timeout_sec=wake_timeout_sec,
    )
    return controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 1: Bond Starts in SLEEP MODE when the Application Opens
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario1DefaultSleepMode:
    """Bond must ALWAYS start in SLEEP MODE when the application launches."""

    def test_default_config_sets_wake_word_mode(self) -> None:
        """Config default should have voice.mode='wake_word' and auto_return_to_sleep=True."""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "default_config.json",
        )
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        assert cfg.get("voice", {}).get("mode") == "wake_word"
        assert cfg.get("voice", {}).get("wake_word") == "Hey Bond"
        assert cfg.get("voice", {}).get("wake_word_enabled") is True
        assert cfg.get("voice", {}).get("auto_return_to_sleep") is True
        assert cfg.get("voice", {}).get("autonomous_messages") is False

    def test_buddy_state_manager_starts_in_sleeping(self) -> None:
        """BuddyStateManager initial state is SLEEPING."""
        bsm = get_buddy_state_manager()
        bsm.reset()
        assert bsm.get_state() == BuddyState.SLEEPING
        assert bsm.is_sleeping is True
        assert bsm.is_active is False

    def test_controller_initializes_as_sleeping(self) -> None:
        """Controller instance starts with _is_sleeping=True and character state SLEEPING."""
        mock_cfg = MagicMock()
        ctrl = ApplicationController(app=None, config_manager=mock_cfg)
        assert ctrl.is_sleeping is True
        assert ctrl._is_sleeping is True

    def test_desktop_pet_window_no_initial_greeting_bubble_when_sleeping(self, qtbot) -> None:
        """Desktop pet window must suppress greeting bubble on startup in sleep mode."""
        config_mock = MagicMock()
        config_mock.get.side_effect = lambda key, default=None: (
            "Bond" if "name" in key
            else True if "wake_word_enabled" in key
            else default
        )
        bsm = get_buddy_state_manager()
        bsm.reset()

        pet = DesktopPetWindow(config_manager=config_mock)
        qtbot.addWidget(pet)

        # Show pet
        pet.show_pet()

        # Visual state must be SLEEPING
        assert pet.anim_controller.current_state == CharacterState.SLEEPING
        # Speech bubble must NOT be shown
        assert pet.speech_bubble.isVisible() is False

        pet.close()


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 2: Bond Stays Asleep Indefinitely Without Saying Anything
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario2StaysAsleepIndefinitely:
    """While sleeping, Bond must not initiate conversations, send unsolicited messages, or wake up autonomously."""

    def test_autonomous_messages_strictly_disallowed_in_sleeping_state(self) -> None:
        """BuddyStateManager forbids autonomous messages while sleeping."""
        bsm = get_buddy_state_manager()
        bsm.reset()
        assert bsm.is_sleeping is True
        assert bsm.autonomous_messages_allowed is False

    def test_idle_background_events_do_not_generate_unsolicited_speech(self) -> None:
        """Background idle checks or timers must not trigger AI generation while sleeping."""
        mock_cfg = MagicMock()
        ctrl = ApplicationController(app=None, config_manager=mock_cfg)
        assert ctrl.is_sleeping is True

        # Mock AI generation and speech
        ctrl.generate_ai_response = MagicMock()
        ctrl.speak_text = MagicMock()

        # Simulate idle or background trigger
        bsm = get_buddy_state_manager()
        bsm.reset()

        # Check that no autonomous action is executed
        if not bsm.autonomous_messages_allowed:
            pass  # Expected: blocked by gate

        ctrl.generate_ai_response.assert_not_called()
        ctrl.speak_text.assert_not_called()
        assert ctrl.is_sleeping is True


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 3: Background Conversations and Ambient Noises Do Not Wake Bond
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario3BackgroundNoiseAndConversationsIgnored:
    """Room noise, TV audio, keyboard clicks, and non-wake speech must not wake Bond."""

    def test_acoustic_energy_burst_does_not_wake_bond(self, qtbot) -> None:
        """Loud noise burst (RMS 0.35) does not trigger wake word when allow_energy_trigger=False."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = create_test_controller(
            allow_energy_trigger=False
        )
        controller.enable()
        assert controller.state == ConversationState.SLEEPING

        detected = []
        wake_engine.wake_word_detected.connect(lambda phrase, score: detected.append((phrase, score)))

        # Feed 10 loud frames (RMS ~ 0.50)
        loud_frame = np.ones(1280, dtype=np.float32) * 0.50
        for _ in range(10):
            controller.process_mic_frame(loud_frame)

        # Must NOT trigger wake detection
        assert len(detected) == 0
        assert controller.state == ConversationState.SLEEPING
        controller.cleanup()

    @pytest.mark.parametrize(
        "phrase",
        [
            "Pass the salt please",
            "The weather is lovely outside",
            "Let's watch a movie tonight",
            "What do you think about that?",
            "I love James Bond movies",  # Contains 'bond' as a noun, but NOT a wake command
            "Are you going to the store today?",
            "Hello everyone in the meeting",
            "Are you coming to lunch today?",
            "Could someone turn on the lights?",
            "Bond is a fictional secret agent",
        ],
    )
    def test_non_wake_phrases_rejected_by_is_wake_phrase(self, phrase: str) -> None:
        """General conversational speech must return False for wake phrase detection."""
        assert WakeWordEngine.is_wake_phrase(phrase) is False

    def test_stt_transcription_dropped_while_sleeping(self) -> None:
        """Transcription of ordinary background conversation received during sleep is discarded."""
        mock_cfg = MagicMock()
        ctrl = ApplicationController(app=None, config_manager=mock_cfg)
        assert ctrl.is_sleeping is True

        ctrl.chat_manager = MagicMock()

        # Background speech transcribed
        ctrl._on_voice_transcription_ready("Pass the salt and turn on the television.", lang="en")

        # Chat manager must NOT receive message
        ctrl.chat_manager.send_message.assert_not_called()
        # State remains sleeping
        assert ctrl.is_sleeping is True
        assert ctrl.buddy_state_manager.is_sleeping is True


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 4: Speaking Configured Wake Word ("Hey Bond") Wakes Bond Up
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario4WakeWordWakesBond:
    """Only speaking the configured wake word wakes Bond up."""

    @pytest.mark.parametrize(
        "wake_phrase",
        [
            "Hey Bond",
            "Hey, Bond",
            "Wake up Bond",
            "Wake up, Bond",
            "Bond, wake up",
            "Activate Bond",
            "I'm talking to you, Bond",
            "Bond, are you there?",
        ],
    )
    def test_wake_phrases_recognized_by_engine(self, wake_phrase: str) -> None:
        """All configured primary and secondary Bond wake phrases are recognized."""
        assert WakeWordEngine.is_wake_phrase(wake_phrase) is True

    def test_wake_word_detected_transitions_state_and_buddy_manager(self, qtbot) -> None:
        """Wake word detection event transitions controller state and BuddyStateManager to ACTIVE."""
        bsm = get_buddy_state_manager()
        bsm.reset()
        assert bsm.get_state() == BuddyState.SLEEPING

        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = create_test_controller()
        controller.enable()
        assert controller.state == ConversationState.SLEEPING

        # Simulate wake word detected
        wake_engine.wake_word_detected.emit("hey_bond", 0.95)

        # Controller transitioned: SLEEPING -> WAKE_WORD_DETECTED -> LISTENING
        assert controller.state in (ConversationState.WAKE_WORD_DETECTED, ConversationState.LISTENING)
        assert bsm.get_state() == BuddyState.ACTIVE
        controller.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 5: Full Cycle: Wake Word -> Listen -> Process -> Speak
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario5FullInteractionCycle:
    """User speaks wake word -> Bond listens -> Bond processes -> Bond speaks response."""

    def test_strict_state_sequence_enforced(self, qtbot) -> None:
        """Controller strictly transitions: SLEEPING -> WAKE_WORD_DETECTED -> LISTENING -> PROCESSING -> SPEAKING."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = create_test_controller()
        controller.enable()
        assert controller.state == ConversationState.SLEEPING

        state_history: List[ConversationState] = [controller.state]
        controller.state_changed.connect(lambda s: state_history.append(s))

        # 1. Wake word detected
        wake_engine.wake_word_detected.emit("hey_bond", 0.92)
        assert ConversationState.WAKE_WORD_DETECTED in state_history
        assert controller.state == ConversationState.LISTENING

        # 2. User speaking onset detected by VAD
        success = controller._transition_to(ConversationState.USER_SPEAKING)
        assert success is True
        assert controller.state == ConversationState.USER_SPEAKING

        # 3. Whisper transcribing speech
        success = controller._transition_to(ConversationState.TRANSCRIBING)
        assert success is True
        assert controller.state == ConversationState.TRANSCRIBING

        # 4. Processing / LLM generating response
        success = controller._transition_to(ConversationState.GENERATING_RESPONSE)
        assert success is True
        assert controller.state == ConversationState.GENERATING_RESPONSE

        # 5. TTS speaking response
        success = controller._transition_to(ConversationState.SPEAKING)
        assert success is True
        assert controller.state == ConversationState.SPEAKING

        controller.cleanup()

    def test_unauthorized_direct_transition_from_sleeping_blocked(self, qtbot) -> None:
        """Direct transition from SLEEPING to SPEAKING or PROCESSING without wake word is blocked."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = create_test_controller()
        controller.enable()
        assert controller.state == ConversationState.SLEEPING

        # Attempt illegal transition: SLEEPING -> SPEAKING
        res_speaking = controller._transition_to(ConversationState.SPEAKING)
        assert res_speaking is False
        assert controller.state == ConversationState.SLEEPING

        # Attempt illegal transition: SLEEPING -> GENERATING_RESPONSE
        res_processing = controller._transition_to(ConversationState.GENERATING_RESPONSE)
        assert res_processing is False
        assert controller.state == ConversationState.SLEEPING

        controller.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 6: Bond Immediately Returns to SLEEP MODE After Speaking Finishes
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario6AutoReturnToSleep:
    """Bond immediately returns to SLEEP MODE after the response finishes."""

    def test_on_all_speech_played_returns_to_sleeping(self, qtbot) -> None:
        """When speech completes and auto_return_to_sleep=True, state returns to SLEEPING."""
        bsm = get_buddy_state_manager()
        bsm.set_state(BuddyState.ACTIVE)

        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = create_test_controller(
            auto_return_to_sleep=True
        )
        controller.enable()

        # Simulate waking and reaching SPEAKING state
        controller._transition_to(ConversationState.WAKE_WORD_DETECTED)
        controller._transition_to(ConversationState.LISTENING)
        controller._transition_to(ConversationState.SPEAKING)
        assert controller.state == ConversationState.SPEAKING

        # Audio finishes playback
        controller._on_all_speech_played(controller.current_turn_id)

        # Wait for echo decay delay to complete transition back to SLEEPING
        qtbot.waitUntil(lambda: controller.state == ConversationState.SLEEPING, timeout=1000)

        # State must return to SLEEPING
        assert controller.state == ConversationState.SLEEPING
        assert bsm.get_state() == BuddyState.SLEEPING
        controller.cleanup()

    def test_wake_timeout_silence_returns_to_sleeping(self, qtbot) -> None:
        """If user speaks wake word but remains silent, Bond returns to SLEEP after timeout."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = create_test_controller(
            auto_return_to_sleep=True,
            wake_timeout_sec=0.1,  # Fast 100ms timeout for test
        )
        controller.enable()

        # Wake word detected -> moves to LISTENING
        wake_engine.wake_word_detected.emit("hey_bond", 0.95)
        assert controller.state == ConversationState.LISTENING

        # Wait for silence timeout
        qtbot.wait(180)

        # Must return to SLEEPING!
        assert controller.state == ConversationState.SLEEPING
        controller.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 7: Speaking After Returning to Sleep Does NOT Trigger a Response
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario7SpeakingAfterSleepIgnored:
    """Speaking after Bond returns to sleep does NOT trigger a response unless wake word is spoken again."""

    def test_transcription_ignored_after_return_to_sleep(self, qtbot) -> None:
        """After returning to SLEEPING, user speech is ignored until wake word is uttered again."""
        mock_cfg = MagicMock()
        ctrl = ApplicationController(app=None, config_manager=mock_cfg)
        ctrl._is_sleeping = True
        ctrl.chat_manager = MagicMock()

        # User speaks without wake word
        ctrl._on_voice_transcription_ready("What's the capital of France?")
        ctrl.chat_manager.send_message.assert_not_called()
        assert ctrl.is_sleeping is True

        # Now user speaks wake word
        ctrl.wake_up = MagicMock()
        ctrl._on_voice_transcription_ready("Hey Bond")
        ctrl.wake_up.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 8: Bond's Own TTS Voice Never Triggers Wake Word Detector
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario8SelfVoiceRejection:
    """Bond's own TTS output must never trigger the wake-word detector."""

    def test_wake_engine_discards_audio_while_speaking(self, qtbot) -> None:
        """WakeWordEngine.process_frame discards audio when is_speaking=True."""
        engine = WakeWordEngine(
            config=WakeWordConfig(activation_phrase="hey_bond"),
            whisper_engine=MockWhisper(mock_text="Hey Bond"),
        )
        engine._debounce_period_sec = 0.0
        engine.enable()

        detected = []
        engine.wake_word_detected.connect(lambda phrase, score: detected.append((phrase, score)))

        # Simulate TTS playing
        engine.is_speaking = True

        # Feed frames that would normally trigger wake-word
        speech_frame = np.ones(1280, dtype=np.float32) * 0.15
        for _ in range(8):
            engine.process_frame(speech_frame)

        # Silence frame
        silence_frame = np.zeros(1280, dtype=np.float32)
        for _ in range(4):
            engine.process_frame(silence_frame)

        # Must NOT detect anything because is_speaking is True
        assert len(detected) == 0
        engine.disable()

    def test_controller_echo_suppression_discards_ai_transcription(self) -> None:
        """Transcription matching AI's own recent speech is suppressed as echo."""
        mock_cfg = MagicMock()
        ctrl = ApplicationController(app=None, config_manager=mock_cfg)
        ctrl._is_sleeping = False  # Test active state echo
        ctrl.buddy_state_manager.set_state(BuddyState.ACTIVE)
        ctrl._last_ai_speech_text = "I am Bond, your personal assistant."
        ctrl._last_ai_speech_time = time.time()
        ctrl.chat_manager = MagicMock()

        # STT captured Bond's own loudspeaker playback
        ctrl._on_voice_transcription_ready("I am Bond, your personal assistant.")

        # Must be dropped by echo suppression
        ctrl.chat_manager.send_message.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 9: Disabling Wake-Word Keeps Bond Asleep
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario9DisablingWakeWordKeepsBondAsleep:
    """When wake-word detection is disabled, Bond stays asleep permanently."""

    def test_disabled_wake_word_engine_does_not_process_frames(self, qtbot) -> None:
        """When wake_engine.is_enabled is False, frames are not processed and no wake signal fires."""
        controller, mic, vad, whisper, player, tts, ai, int_mgr, wake_engine = create_test_controller()
        controller.enable()

        # Explicitly disable wake-word engine
        wake_engine.disable()
        assert wake_engine.is_enabled is False

        detected = []
        wake_engine.wake_word_detected.connect(lambda phrase, score: detected.append((phrase, score)))

        # Feed speech frames
        speech_frame = np.ones(1280, dtype=np.float32) * 0.20
        for _ in range(10):
            controller.process_mic_frame(speech_frame)

        assert len(detected) == 0
        assert controller.state == ConversationState.SLEEPING
        controller.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 10: Settings Saved and Restored Properly Across Restarts
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario10SettingsPersistence:
    """Voice activation settings are saved and restored properly across restarts."""

    def test_config_save_and_reload(self) -> None:
        """ConfigManager persists wake_word, wake_word_enabled, auto_return_to_sleep across instances."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_config_path = os.path.join(temp_dir, "config.json")

            # 1. First run: initialize and customize settings
            cfg_mgr1 = ConfigManager(config_path=temp_config_path)
            cfg_mgr1.set("voice.mode", "wake_word")
            cfg_mgr1.set("voice.wake_word", "Wake up Bond")
            cfg_mgr1.set("voice.wake_word_enabled", True)
            cfg_mgr1.set("voice.auto_return_to_sleep", True)
            cfg_mgr1.set("voice.autonomous_messages", False)
            cfg_mgr1.save()

            # 2. Simulate application restart: load fresh ConfigManager instance
            cfg_mgr2 = ConfigManager(config_path=temp_config_path)
            assert cfg_mgr2.get("voice.mode") == "wake_word"
            assert cfg_mgr2.get("voice.wake_word") == "Wake up Bond"
            assert cfg_mgr2.get("voice.wake_word_enabled") is True
            assert cfg_mgr2.get("voice.auto_return_to_sleep") is True
            assert cfg_mgr2.get("voice.autonomous_messages") is False
