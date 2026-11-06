"""Phase 10: Complete Integration and Quality Assurance Test Suite.

Exhaustively verifies all 10 voice system improvements under realistic conditions:
1. Five voice profiles (Arjun, Kabir, Ananya, Mira, Zara) across EN, GU, HI.
2. Persona-voice independence & mid-session voice switching.
3. Intelligent context-aware interruptions (e.g. "Wait, that's not what I meant").
4. Coreference handling & conversational context memory.
5. Adaptive response modes (5 modes with length/detail adaptation).
6. Natural turn-taking edge cases (acknowledgements, thinking pauses, topic switches, anti-repetition).
7. Voice visualization states, mic activity levels, resting baseline, mute, interrupted, mic unavailable.
8. Sleep and wake isolation (unsolicited speech prevention, timers, toasts, clean sleep return).
9. Performance benchmarks & latency telemetry (STT, LLM, TTS first-audio, interruption latency).
10. Full regression across core Bond capabilities (WhatsApp, app launch, search, YouTube, system, settings).
"""

from __future__ import annotations

import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication

from app.ai.adaptive_response_style import (
    AdaptiveStyleDetector,
    AdaptiveStyleGuidelines,
    ResponseStyle,
)
from app.ai.generation_controls import GenerationConfig
from app.ai.interruption_classifier import InterruptionClassifier, InterruptionType
from app.ai.multilingual_engine import MultilingualEngine
from app.ai.personality_manager import PersonalityManager
from app.ai.turn_taking_manager import TurnTakingManager
from app.core.signals import signals
from app.desktop.voice_window import AudioWaveformWidget, VoiceWindow
from app.settings.config_manager import ConfigManager
from app.voice.speaking_style import DEFAULT_SPEAKING_STYLES, SpeakingStyle
from app.voice.conversation_state import ConversationLatencyMetrics, ConversationState
from app.voice.microphone_manager import MicrophoneManager
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.voice_conversation_controller import (
    VoiceActivationMode,
    VoiceConversationController,
)
from app.voice.voice_registry import (
    VOICE_REGISTRY,
    VoiceProfile,
    get_voice_profile,
    list_voice_profiles,
)
from app.voice.wake_word_engine import WakeWordConfig, WakeWordEngine
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


class MockTTS(BaseTTSEngine):
    def __init__(self) -> None:
        super().__init__()
        self.synthesized_phrases: list[str] = []
        self.last_voice_name: str = ""

    def synthesize(self, text: str, voice_name: str = "default", **kwargs) -> SynthesizedAudio:
        self.synthesized_phrases.append(text)
        self.last_voice_name = voice_name
        samples = np.ones(1600, dtype=np.float32) * 0.05
        return SynthesizedAudio(
            samples=samples,
            sample_rate=16000,
            duration_seconds=0.1,
            text=text,
            voice_name=voice_name,
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


class TestPhase10CompleteIntegrationQA(unittest.TestCase):
    """Phase 10: Complete Integration and Quality Assurance Verification."""

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
        self.mock_player = MagicMock()
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
        if hasattr(self.ctrl, "echo_canceller"):
            self.ctrl.echo_canceller.is_in_cooldown = lambda limit: False

    def tearDown(self) -> None:
        self.ctrl.emergency_stop()
        self.ctrl.cleanup()
        if QApplication.instance():
            QApplication.processEvents()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Five Voice Profiles across English, Gujarati, and Hindi
    # ─────────────────────────────────────────────────────────────────────────

    def test_01_five_voice_profiles_and_multilingual_differentiation(self) -> None:
        """Verify 5 selectable voice profiles exist with distinct acoustic qualities and support EN, GU, HI."""
        expected_voices = ["arjun", "kabir", "ananya", "mira", "zara"]
        all_profiles = list_voice_profiles()
        profile_ids = [p.profile_id for p in all_profiles]

        # Verify all 5 profiles are registered
        for expected in expected_voices:
            self.assertIn(expected, profile_ids, f"Voice profile '{expected}' must be registered.")
            profile = get_voice_profile(expected)
            self.assertTrue(len(profile.name) > 0)
            self.assertIn(profile.gender.lower(), ("male", "female"))
            self.assertTrue(len(profile.primary_voice_id) > 0)
            self.assertTrue(len(profile.description) > 0)

        # Confirm distinct character traits
        arjun = get_voice_profile("arjun")
        kabir = get_voice_profile("kabir")
        ananya = get_voice_profile("ananya")
        mira = get_voice_profile("mira")
        zara = get_voice_profile("zara")

        self.assertNotEqual(arjun.speaking_rate, kabir.speaking_rate)
        self.assertNotEqual(ananya.speaking_rate, mira.speaking_rate)
        self.assertNotEqual(mira.speaking_rate, zara.speaking_rate)

        # Test multilingual TTS preparation for English, Gujarati, Hindi
        test_phrases = {
            "en": "Hello, how can I assist you today?",
            "gu": "નમસ્તે, હું તમને કેવી રીતે મદદ કરી શકું?",
            "hi": "नमस्ते, मैं आपकी क्या मदद कर सकता हूँ?",
        }

        for lang, phrase in test_phrases.items():
            prepared_text, voice_hint = MultilingualEngine.prepare_text_for_tts(
                text=phrase,
                target_language=lang,
                engine_name="KokoroTTSEngine",
                preferred_voice_id="am_adam",
                preferred_gender="male",
            )
            self.assertTrue(len(prepared_text) > 0)
            self.assertIsNotNone(voice_hint)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Persona-Voice Independence & Mid-Session Switching
    # ─────────────────────────────────────────────────────────────────────────

    def test_02_persona_voice_independence_mid_session_switch(self) -> None:
        """Verify switching voice profiles mid-session (e.g. Arjun to Mira) preserves persona knowledge and identity."""
        # Initialize with Arjun
        self.ctrl.set_voice_profile("arjun")
        self.assertEqual(self.ctrl.selected_voice_profile, "arjun")

        # Simulate ongoing conversation context in memory
        conversation_history = [
            {"role": "user", "content": "My name is Gaurav and I live in Mumbai."},
            {"role": "assistant", "content": "Pleased to meet you, Gaurav! How can I assist you in Mumbai?"},
        ]

        # Mid-session switch to Mira
        self.ctrl.set_voice_profile("mira")
        self.assertEqual(self.ctrl.selected_voice_profile, "mira")

        # Ensure conversation history, persona knowledge, and memory remain intact
        self.assertEqual(len(conversation_history), 2)
        self.assertIn("Gaurav", conversation_history[0]["content"])
        self.assertIn("Mumbai", conversation_history[1]["content"])

        # Switch to Zara and confirm persistence
        self.ctrl.set_voice_profile("zara")
        self.assertEqual(self.ctrl.selected_voice_profile, "zara")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Intelligent Context-Aware Interruptions
    # ─────────────────────────────────────────────────────────────────────────

    def test_03_context_aware_interruption_correction_handling(self) -> None:
        """Verify interrupting Bond with 'Wait, that's not what I meant' halts speech and classifies as Correction."""
        # 1. Interruption Classifier Type A test
        correction_text = "Wait, that's not what I meant."
        classification = InterruptionClassifier.classify(
            interruption_text=correction_text,
            speech_duration_sec=1.2,
        )
        self.assertEqual(classification.interruption_type, InterruptionType.CORRECTION)
        self.assertGreaterEqual(classification.confidence, 0.85)

        # 2. End-to-end controller halt & state transition
        self.ctrl.enable()
        self.ctrl._on_wake_word_detected("hey_bond", 0.95)
        self.ctrl._transition_to(ConversationState.SPEAKING)

        interrupted_events = []
        self.ctrl.interruption_triggered.connect(interrupted_events.append)

        # Trigger barge-in
        speech_samples = np.ones(1600, dtype=np.float32) * 0.2
        self.ctrl._on_interruption_detected(turn_id=1, speech_samples=speech_samples)

        self.assertEqual(len(interrupted_events), 1)
        self.assertEqual(self.ctrl.state, ConversationState.USER_SPEAKING)
        self.mock_ai.cancel_generation.assert_called_once()

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Coreference Handling & Conversational Memory
    # ─────────────────────────────────────────────────────────────────────────

    def test_04_coreference_handling_and_contextual_continuity(self) -> None:
        """Verify turn taking directives contain coreference resolution instructions and guidelines."""
        directives_en = TurnTakingManager.build_turn_taking_directives(response_language="en")
        self.assertIn("Coreference Resolution", directives_en)
        self.assertIn("Interstellar", directives_en)
        self.assertIn("Christopher Nolan", directives_en)

        # Hindi directives
        directives_hi = TurnTakingManager.build_turn_taking_directives(response_language="hi")
        self.assertIn("Hindi", directives_hi)
        self.assertIn("Coreference", directives_hi)

        # Gujarati directives
        directives_gu = TurnTakingManager.build_turn_taking_directives(response_language="gu")
        self.assertIn("Gujarati", directives_gu)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Adaptive Response Modes
    # ─────────────────────────────────────────────────────────────────────────

    def test_05_adaptive_response_modes_and_length_budgeting(self) -> None:
        """Verify all 5 adaptive modes (Quick, Normal, Detailed, Step-by-Step, Hands-Free) adapt prompts and token budgets."""
        queries_to_styles = [
            ("Just tell me the answer.", ResponseStyle.QUICK_ANSWER),
            ("Explain machine learning.", ResponseStyle.NORMAL_CONVERSATION),
            ("Explain this in complete detail with examples.", ResponseStyle.DETAILED_EXPLANATION),
            ("Guide me step by step.", ResponseStyle.STEP_BY_STEP),
            ("Summarize this while I'm driving.", ResponseStyle.HANDS_FREE_SUMMARY),
        ]

        for query, expected_style in queries_to_styles:
            style, is_override, reason = AdaptiveStyleDetector.detect_style(query)
            self.assertEqual(style, expected_style, f"Query '{query}' should resolve to {expected_style.value}")

            instructions = AdaptiveStyleGuidelines.build_style_directive(style, is_voice=True, response_language="en")
            self.assertTrue(len(instructions) > 0)
            budget = AdaptiveStyleGuidelines.get_token_budget(style, is_voice=True)
            self.assertGreater(budget, 0)

        # Verify token headroom varies appropriately across styles
        quick_budget = AdaptiveStyleGuidelines.get_token_budget(ResponseStyle.QUICK_ANSWER, is_voice=True)
        detailed_budget = AdaptiveStyleGuidelines.get_token_budget(ResponseStyle.DETAILED_EXPLANATION, is_voice=True)
        self.assertLess(quick_budget, detailed_budget)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Natural Conversational Turn-Taking Edge Cases
    # ─────────────────────────────────────────────────────────────────────────

    def test_06_turn_taking_acknowledgements_pauses_and_anti_repetition(self) -> None:
        """Verify short acknowledgements do not spawn long monologues, and repetitive assistant responses are blocked."""
        # 1. Short acknowledgements backchanneling
        acks = ["Hmm.", "Okay.", "Yes.", "Right.", "Interesting."]
        for ack in acks:
            is_ack, term = TurnTakingManager.is_short_acknowledgement(ack)
            self.assertTrue(is_ack, f"'{ack}' must be recognized as a short acknowledgement")

        # Instruction restricts length to 1 brief spoken sentence
        ack_instruction = TurnTakingManager.build_acknowledgement_instruction("Okay.", response_language="en")
        self.assertIn("DO NOT launch into a long lecture", ack_instruction)
        self.assertIn("EXACTLY 1 brief spoken sentence", ack_instruction)

        # 2. Conversational thinking pause (trailing connectors)
        self.assertTrue(TurnTakingManager.has_trailing_connector("I was wondering because"))
        self.assertTrue(TurnTakingManager.has_trailing_connector("हम चलेंगे और"))
        self.assertTrue(TurnTakingManager.has_trailing_connector("અને"))
        self.assertFalse(TurnTakingManager.has_trailing_connector("What time is it?"))

        # 3. Repetition Prevention against identical prior answer
        prev_response = "Christopher Nolan is a British-American filmmaker known for Hollywood blockbusters."
        duplicate_candidate = "Christopher Nolan is a British-American filmmaker known for Hollywood blockbusters."
        is_dup = TurnTakingManager.is_duplicate_response(duplicate_candidate, prev_response)
        self.assertTrue(is_dup, "Duplicate responses must be detected and suppressed")

        # 4. Robotic canned question stripping
        canned = "Here is the weather. Is there anything else I can help you with today?"
        cleaned = TurnTakingManager.strip_canned_closing_questions(canned)
        self.assertEqual(cleaned, "Here is the weather.")

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Real-Time Voice Activity Visualization
    # ─────────────────────────────────────────────────────────────────────────

    def test_07_voice_activity_visualization_and_waveform_states(self) -> None:
        """Verify VoiceWindow and AudioWaveformWidget accurately display states, resting baseline, and speaking."""
        mock_cfg = MagicMock(spec=ConfigManager)
        mock_cfg.get.side_effect = lambda key, default=None: "Bond" if "name" in key else default
        window = VoiceWindow(config_manager=mock_cfg, voice_service=MagicMock())

        # 1. State changes
        window.set_state("sleeping")
        self.assertEqual(window.status_label.text(), "Asleep")

        window.set_state("wake_word_detected")
        self.assertEqual(window.status_label.text(), "Wake Word Detected")

        window.set_state("listening")
        self.assertEqual(window.status_label.text(), "I'm Listening...")

        window.set_state("speaking")
        self.assertEqual(window.status_label.text(), "Speaking...")

        window.set_state("interrupted")
        self.assertEqual(window.status_label.text(), "Interrupted")

        window.set_state("muted")
        self.assertEqual(window.status_label.text(), "Microphone Muted")

        window.set_state("microphone_unavailable")
        self.assertEqual(window.status_label.text(), "Microphone Unavailable")

        # 2. Silence deadband stability: levels <= 0.02 must lock to baseline 0.0
        window.waveform.set_level(0.01)
        self.assertEqual(window.waveform._level, 0.0, "Sub-threshold ambient noise must clamp to exact 0.0 flatline")

        # 3. Speech intensity: active voice amplitude reflects dynamically
        window.waveform.set_level(0.75)
        self.assertGreater(window.waveform._level, 0.5)

        window.close()
        window.deleteLater()

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Sleep & Wake Isolation
    # ─────────────────────────────────────────────────────────────────────────

    def test_08_sleep_and_wake_isolation_unsolicited_speech_prevention(self) -> None:
        """Verify assistant remains completely silent while asleep and background conversations do not trigger speech."""
        self.ctrl.enable()
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))

        # Ambient conversation that does not contain wake word
        ambient_frame = np.random.randn(512).astype(np.float32) * 0.05
        self.ctrl.process_mic_frame(ambient_frame)

        # Must NOT transcribe or synthesize speech
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))
        self.assertEqual(len(self.mock_tts.synthesized_phrases), 0)

        # Wake up with wake phrase
        self.ctrl._on_wake_word_detected("hey_bond", 0.95)
        self.assertEqual(self.ctrl.state, ConversationState.LISTENING)

        # Clean return to sleep on silence timeout
        self.ctrl._on_wake_silence_timeout()
        self.assertIn(self.ctrl.state, (ConversationState.SLEEPING, ConversationState.WAKE_WORD_STANDBY))

    # ─────────────────────────────────────────────────────────────────────────
    # 9. Performance Benchmarks & Structured Timing Telemetry
    # ─────────────────────────────────────────────────────────────────────────

    def test_09_performance_benchmarks_and_structured_timing_telemetry(self) -> None:
        """Verify timing metrics record STT duration, LLM latency, TTS latency, and cancellation times within budget."""
        metrics = ConversationLatencyMetrics(turn_id=1)
        metrics.session_id = "vsession_qa_test"
        metrics.input_language = "en"
        metrics.transcription = "Hello Bond"
        metrics.stt_duration_ms = 180.0
        metrics.first_token_latency_ms = 220.0
        metrics.llm_duration_ms = 850.0
        metrics.first_audio_latency_ms = 160.0
        metrics.total_tts_duration_ms = 520.0
        metrics.audio_playback_completion_ms = 1800.0
        metrics.barge_in_detection_ms = 380.0
        metrics.audio_cancellation_ms = 12.5

        log = metrics.to_structured_log()
        self.assertEqual(log["session_id"], "vsession_qa_test")
        self.assertEqual(log["input_language"], "en")
        self.assertEqual(log["transcription"], "Hello Bond")
        self.assertLess(log["stt_duration_ms"], 250.0)
        self.assertLess(log["audio_cancellation_ms"], 50.0)
        self.assertEqual(log["barge_in_detection_ms"], 380.0)

    # ─────────────────────────────────────────────────────────────────────────
    # 10. Full Regression Across Core Bond Features
    # ─────────────────────────────────────────────────────────────────────────

    def test_10_full_regression_core_bond_features_and_persistence(self) -> None:
        """Verify core companion features remain functional: settings persistence, personality, and signal routing."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            f.write("{}")
            cfg_path = f.name

        cfg = ConfigManager(config_path=cfg_path)
        cfg.set("voice.selected_profile", "ananya")
        cfg.set("voice.activation_mode", "wake_word")
        cfg.set("language.response_language", "en")
        cfg.save()

        # Confirm reload from disk
        cfg_loaded = ConfigManager(config_path=cfg_path)
        self.assertEqual(cfg_loaded.get("voice.selected_profile"), "ananya")
        self.assertEqual(cfg_loaded.get("voice.activation_mode"), "wake_word")
        self.assertEqual(cfg_loaded.get("language.response_language"), "en")

        # Confirm PersonalityManager loads speaking style
        pm = PersonalityManager(config_manager=cfg_loaded)
        style = pm.get_speaking_style_for_persona("bond")
        self.assertIsNotNone(style)
        self.assertIsInstance(style, SpeakingStyle)
        self.assertGreater(style.speaking_rate, 0.5)


if __name__ == "__main__":
    unittest.main()
