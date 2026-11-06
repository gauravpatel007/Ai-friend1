"""Phase 4 Automated Test Suite: Context-Aware Interruptions 2.0.

Tests over 20 interruption scenarios across all 4 interruption categories:
  - Type A: Correction (English, Hindi, Gujarati, Romanized)
  - Type B: Follow-up (English, Hindi, Gujarati, Romanized)
  - Type C: Topic change (English, Hindi, Gujarati, Romanized)
  - Type D: Brief acknowledgement / backchannel (English, Hindi, Gujarati, Romanized)

Verifies:
  1. Immediate Interruption: Playback stops, queued chunks cancel, in-flight speech aborted.
  2. Classification: 20+ scenarios correctly classified into Type A, B, C, or D.
  3. Context Preservation: Spoken portion vs unspoken portion tracked; previous query preserved.
  4. Partially Spoken Sentences: Accurate word-level truncations based on playback progress.
  5. Backchannel Non-cancellation: Short acknowledgements do not drop remaining speech.
  6. Acoustic Feedback Prevention: Output echo filtered without blocking genuine voice interruptions.
"""

from __future__ import annotations

from typing import Any
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PySide6.QtCore import QCoreApplication

from app.ai.conversation_context import ConversationContext
from app.ai.interruption_classifier import (
    InterruptionClassificationResult,
    InterruptionClassifier,
    InterruptionType,
)
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState
from app.voice.echo_suppressor import AcousticEchoSuppressor
from app.voice.streaming_audio_queue import (
    InterruptedTurnSnapshot,
    QueuedAudio,
    QueuedSentence,
    StreamingAudioQueue,
)
from app.voice.tts_base import SynthesizedAudio


class TestPhase4ContextAwareInterruptions(unittest.TestCase):
    """Test suite for Phase 4 Context-Aware Interruptions 2.0."""

    @classmethod
    def setUpClass(cls) -> None:
        if QCoreApplication.instance() is None:
            cls.app = QCoreApplication([])
        else:
            cls.app = QCoreApplication.instance()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. CLASSIFICATION: 20+ Interruption Scenarios Across Types A, B, C, D
    # ─────────────────────────────────────────────────────────────────────────

    def test_01_type_a_correction_english_basic(self) -> None:
        """Type A Scenario 1: 'Wait, that's not what I meant.'"""
        res = InterruptionClassifier.classify("Wait, that's not what I meant.")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)
        self.assertEqual(res.suggested_action, "apply_correction")

    def test_02_type_a_correction_english_alternative(self) -> None:
        """Type A Scenario 2: 'No, I meant something else.'"""
        res = InterruptionClassifier.classify("No, I meant something else.")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)

    def test_03_type_a_correction_english_incorrect(self) -> None:
        """Type A Scenario 3: 'That's incorrect. I asked about airplanes.'"""
        res = InterruptionClassifier.classify("That's incorrect. I asked about airplanes.")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)

    def test_04_type_a_correction_english_explain_again(self) -> None:
        """Type A Scenario 4: 'Let me explain again.'"""
        res = InterruptionClassifier.classify("Let me explain again.")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)

    def test_05_type_a_correction_english_stop_wrong(self) -> None:
        """Type A Scenario 5: 'Stop, that is wrong.'"""
        res = InterruptionClassifier.classify("Stop, that is wrong.")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)

    def test_06_type_a_correction_gujarati_script(self) -> None:
        """Type A Scenario 6: Gujarati script correction 'ના, મારો મતલબ એ નહોતો'"""
        res = InterruptionClassifier.classify("ના, મારો મતલબ એ નહોતો")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)

    def test_07_type_a_correction_gujarati_romanized(self) -> None:
        """Type A Scenario 7: Romanized Gujarati 'Na, maro matlab e nahoto'"""
        res = InterruptionClassifier.classify("Na, maro matlab e nahoto")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)

    def test_08_type_a_correction_hindi_script(self) -> None:
        """Type A Scenario 8: Hindi script correction 'नहीं, मेरा मतलब यह नहीं था'"""
        res = InterruptionClassifier.classify("नहीं, मेरा मतलब यह नहीं था")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)

    def test_09_type_a_correction_hindi_romanized(self) -> None:
        """Type A Scenario 9: Romanized Hindi 'Nahi, mera matlab yeh nahi tha'"""
        res = InterruptionClassifier.classify("Nahi, mera matlab yeh nahi tha")
        self.assertEqual(res.interruption_type, InterruptionType.CORRECTION)

    def test_10_type_b_follow_up_english_why(self) -> None:
        """Type B Scenario 10: 'Why?'"""
        res = InterruptionClassifier.classify("Why?")
        self.assertEqual(res.interruption_type, InterruptionType.FOLLOW_UP)
        self.assertEqual(res.suggested_action, "elaborate_topic")

    def test_11_type_b_follow_up_english_what_happened_next(self) -> None:
        """Type B Scenario 11: 'What happened next?'"""
        res = InterruptionClassifier.classify("What happened next?")
        self.assertEqual(res.interruption_type, InterruptionType.FOLLOW_UP)

    def test_12_type_b_follow_up_english_tell_me_more(self) -> None:
        """Type B Scenario 12: 'Tell me more.'"""
        res = InterruptionClassifier.classify("Tell me more.")
        self.assertEqual(res.interruption_type, InterruptionType.FOLLOW_UP)

    def test_13_type_b_follow_up_english_really(self) -> None:
        """Type B Scenario 13: 'Really?'"""
        res = InterruptionClassifier.classify("Really?")
        self.assertEqual(res.interruption_type, InterruptionType.FOLLOW_UP)

    def test_14_type_b_follow_up_gujarati_script(self) -> None:
        """Type B Scenario 14: Gujarati script 'પછી શું થયું?'"""
        res = InterruptionClassifier.classify("પછી શું થયું?")
        self.assertEqual(res.interruption_type, InterruptionType.FOLLOW_UP)

    def test_15_type_b_follow_up_gujarati_romanized(self) -> None:
        """Type B Scenario 15: Romanized Gujarati 'Pachi shu thayu?'"""
        res = InterruptionClassifier.classify("Pachi shu thayu?")
        self.assertEqual(res.interruption_type, InterruptionType.FOLLOW_UP)

    def test_16_type_b_follow_up_hindi_script(self) -> None:
        """Type B Scenario 16: Hindi script 'फिर क्या हुआ?'"""
        res = InterruptionClassifier.classify("फिर क्या हुआ?")
        self.assertEqual(res.interruption_type, InterruptionType.FOLLOW_UP)

    def test_17_type_b_follow_up_hindi_romanized(self) -> None:
        """Type B Scenario 17: Romanized Hindi 'Fir kya hua?'"""
        res = InterruptionClassifier.classify("Fir kya hua?")
        self.assertEqual(res.interruption_type, InterruptionType.FOLLOW_UP)

    def test_18_type_c_topic_change_english_anyway(self) -> None:
        """Type C Scenario 18: 'Anyway, let's talk about something else.'"""
        res = InterruptionClassifier.classify("Anyway, let's talk about something else.")
        self.assertEqual(res.interruption_type, InterruptionType.TOPIC_CHANGE)
        self.assertEqual(res.suggested_action, "switch_topic")

    def test_19_type_c_topic_change_english_forget_that(self) -> None:
        """Type C Scenario 19: 'Forget that. I have another question.'"""
        res = InterruptionClassifier.classify("Forget that. I have another question.")
        self.assertEqual(res.interruption_type, InterruptionType.TOPIC_CHANGE)

    def test_20_type_c_topic_change_english_change_topic(self) -> None:
        """Type C Scenario 20: 'Change the topic.'"""
        res = InterruptionClassifier.classify("Change the topic.")
        self.assertEqual(res.interruption_type, InterruptionType.TOPIC_CHANGE)

    def test_21_type_c_topic_change_gujarati_script(self) -> None:
        """Type C Scenario 21: Gujarati script 'એ ભૂલી જાવ, મારો બીજો પ્રશ્ન છે'"""
        res = InterruptionClassifier.classify("એ ભૂલી જાવ, મારો બીજો પ્રશ્ન છે")
        self.assertEqual(res.interruption_type, InterruptionType.TOPIC_CHANGE)

    def test_22_type_c_topic_change_hindi_romanized(self) -> None:
        """Type C Scenario 22: Romanized Hindi 'Jane do, mujhe doosra sawal poochna hai'"""
        res = InterruptionClassifier.classify("Jane do, mujhe doosra sawal poochna hai")
        self.assertEqual(res.interruption_type, InterruptionType.TOPIC_CHANGE)

    def test_23_type_d_acknowledgement_english_hmm(self) -> None:
        """Type D Scenario 23: English 'Hmm' (Backchannel)"""
        res = InterruptionClassifier.classify("Hmm")
        self.assertEqual(res.interruption_type, InterruptionType.ACKNOWLEDGEMENT)
        self.assertEqual(res.suggested_action, "continue_playback")

    def test_24_type_d_acknowledgement_english_okay(self) -> None:
        """Type D Scenario 24: English 'Okay'"""
        res = InterruptionClassifier.classify("Okay")
        self.assertEqual(res.interruption_type, InterruptionType.ACKNOWLEDGEMENT)

    def test_25_type_d_acknowledgement_english_right(self) -> None:
        """Type D Scenario 25: English 'Right'"""
        res = InterruptionClassifier.classify("Right")
        self.assertEqual(res.interruption_type, InterruptionType.ACKNOWLEDGEMENT)

    def test_26_type_d_acknowledgement_english_yeah(self) -> None:
        """Type D Scenario 26: English 'Yeah'"""
        res = InterruptionClassifier.classify("Yeah")
        self.assertEqual(res.interruption_type, InterruptionType.ACKNOWLEDGEMENT)

    def test_27_type_d_acknowledgement_hindi_script_haan(self) -> None:
        """Type D Scenario 27: Hindi script 'हाँ'"""
        res = InterruptionClassifier.classify("हाँ")
        self.assertEqual(res.interruption_type, InterruptionType.ACKNOWLEDGEMENT)

    def test_28_type_d_acknowledgement_gujarati_romanized_barabar(self) -> None:
        """Type D Scenario 28: Gujarati Romanized 'Barabar'"""
        res = InterruptionClassifier.classify("Barabar")
        self.assertEqual(res.interruption_type, InterruptionType.ACKNOWLEDGEMENT)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. PARTIALLY SPOKEN SENTENCES & PROGRESS RATIO
    # ─────────────────────────────────────────────────────────────────────────

    def test_partially_spoken_sentence_truncation_50_percent(self) -> None:
        """Verify halfway interrupted sentence accurately truncates to ~50% words with ellipsis."""
        sentence = "Airplanes create aerodynamic lift through the curved shape of their wings."
        # 10 words total
        snapshot = InterruptedTurnSnapshot(
            turn_id=1,
            completed_sentences=["Yes, absolutely!"],
            interrupted_sentence=sentence,
            interrupted_progress_ratio=0.50,
            unspoken_sentences=["This is known as Bernoulli's principle."],
            all_sentences=["Yes, absolutely!", sentence, "This is known as Bernoulli's principle."],
        )

        actually_spoken = snapshot.actually_spoken_text
        self.assertTrue(actually_spoken.startswith("Yes, absolutely!"))
        # 50% of 11 words = 6 words ("Airplanes create aerodynamic lift through the...")
        self.assertIn("Airplanes create aerodynamic lift through the...", actually_spoken)
        # Unspoken tail must NOT be in actually_spoken
        self.assertNotIn("shape of their wings", actually_spoken)
        self.assertNotIn("Bernoulli", actually_spoken)

    def test_partially_spoken_sentence_early_onset_ignored(self) -> None:
        """Verify interruption under 8% progress doesn't claim any words were heard."""
        sentence = "Airplanes create aerodynamic lift through their wings."
        snapshot = InterruptedTurnSnapshot(
            turn_id=1,
            completed_sentences=["First sentence."],
            interrupted_sentence=sentence,
            interrupted_progress_ratio=0.04,  # Interrupted almost immediately
            unspoken_sentences=["Third sentence."],
            all_sentences=["First sentence.", sentence, "Third sentence."],
        )

        self.assertEqual(snapshot.actually_spoken_text, "First sentence.")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. STREAMING AUDIO QUEUE: IMMEDIATE STOP & SNAPSHOT CAPTURE
    # ─────────────────────────────────────────────────────────────────────────

    def test_streaming_audio_queue_stop_and_capture_interruption(self) -> None:
        """Verify stop_and_capture_interruption halts player, purges queues, and returns snapshot."""
        mock_player = MagicMock()
        mock_player.get_playback_progress.return_value = (1.5, 3.0, 0.50)
        mock_tts = MagicMock()

        queue = StreamingAudioQueue(audio_player=mock_player, tts_engine=mock_tts)
        queue.start_new_turn(turn_id=5)

        # Enqueue 3 sentences
        queue.enqueue_sentence("Sentence one.", turn_id=5)
        queue.enqueue_sentence("Sentence two.", turn_id=5)
        queue.enqueue_sentence("Sentence three.", turn_id=5)

        # Simulate sentence one finished
        audio1 = SynthesizedAudio(
            samples=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            duration_seconds=1.0,
            text="Sentence one.",
            voice_name="test",
        )
        queue._on_sentence_synthesized(
            QueuedSentence(turn_id=5, chunk_index=0, text="Sentence one."),
            audio1,
        )
        queue._on_player_chunk_finished()

        # Simulate sentence two currently playing
        audio2 = SynthesizedAudio(
            samples=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            duration_seconds=2.0,
            text="Sentence two.",
            voice_name="test",
        )
        queue._on_sentence_synthesized(
            QueuedSentence(turn_id=5, chunk_index=1, text="Sentence two."),
            audio2,
        )

        # User interrupts while sentence two is playing!
        snapshot = queue.stop_and_capture_interruption()

        # Audio player must be stopped immediately
        mock_player.stop.assert_called()

        # Snapshot checks
        self.assertEqual(snapshot.turn_id, 5)
        self.assertEqual(snapshot.completed_sentences, ["Sentence one."])
        self.assertEqual(snapshot.interrupted_sentence, "Sentence two.")
        self.assertEqual(snapshot.interrupted_progress_ratio, 0.50)
        self.assertEqual(snapshot.unspoken_sentences, ["Sentence three."])
        self.assertEqual(len(snapshot.all_sentences), 3)

        # Queue must be cleared immediately
        self.assertTrue(queue.is_empty)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. CONVERSATION CONTEXT: RECORDING INTERRUPTED TURN
    # ─────────────────────────────────────────────────────────────────────────

    def test_conversation_context_record_interrupted_turn(self) -> None:
        """Verify ConversationContext accurately marks interrupted assistant message."""
        ctx = ConversationContext()
        ctx.add_user_message("Tell me about Mars.")

        # Assistant was interrupted after speaking only part of the answer
        ctx.record_interrupted_turn("Mars is the fourth planet from the sun...")

        messages = ctx.get_messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Tell me about Mars.")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertIn("Mars is the fourth planet from the sun...", messages[1]["content"])
        self.assertIn("[interrupted]", messages[1]["content"])

    # ─────────────────────────────────────────────────────────────────────────
    # 5. ACOUSTIC ECHO SUPPRESSION: FEEDBACK PREVENTION
    # ─────────────────────────────────────────────────────────────────────────

    def test_acoustic_echo_suppressor_filters_assistant_playback(self) -> None:
        """Verify AcousticEchoSuppressor rejects microphone transcripts that echo assistant speech."""
        suppressor = AcousticEchoSuppressor()
        suppressor.record_assistant_speech("Airplanes create lift through the curved shape of their wings.")
        suppressor.mark_playback_started()

        # Speaker spillover transcript
        is_echo, reason, conf = suppressor.is_echo("create lift through the curved shape of their wings")
        self.assertTrue(is_echo, "Should detect microphone echo of assistant's own speech")

        # Genuine user interruption
        is_user_echo, _, _ = suppressor.is_echo("Wait, that's not what I asked about.")
        self.assertFalse(is_user_echo, "Genuine user correction must not be flagged as echo")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. CONTROLLER INTEGRATION: CONTEXT-AWARE INTERRUPTION FLOW
    # ─────────────────────────────────────────────────────────────────────────

    def _create_mock_controller(self) -> tuple[Any, MagicMock, MagicMock]:
        """Create a VoiceConversationController with mocked dependencies."""
        from app.voice.voice_conversation_controller import VoiceConversationController
        from app.voice.whisper_engine import WhisperEngine
        from app.voice.vad_engine import VADEngine

        mock_player = MagicMock()
        mock_player.is_playing = True
        mock_player.get_playback_progress.return_value = (1.0, 2.0, 0.5)

        mock_tts = MagicMock()
        mock_ai_service = MagicMock()
        mock_ai_service.ask.return_value = 1

        mock_whisper = MagicMock(spec=WhisperEngine)
        mock_vad = MagicMock(spec=VADEngine)
        mock_vad.silence_threshold_ms = 400
        mock_vad._active_utterance_frames = []

        ctrl = VoiceConversationController(
            audio_player=mock_player,
            tts_engine=mock_tts,
            ai_service=mock_ai_service,
            whisper_engine=mock_whisper,
            vad_engine=mock_vad,
        )
        ctrl._turn_id = 1
        ctrl.audio_queue.start_new_turn(turn_id=1)
        ctrl._current_turn_user_prompt = "How do planes fly?"
        return ctrl, mock_ai_service, mock_player

    def test_controller_interruption_correction_flow(self) -> None:
        """Verify Type A correction interruption triggers AI ask with correction context."""
        from app.voice.whisper_engine import TranscriptionResult
        ctrl, mock_ai, _ = self._create_mock_controller()

        ctrl._transition_to(ConversationState.AI_SPEAKING)
        ctrl.audio_queue.enqueue_sentence("Airplanes create lift through their wings.", turn_id=1)
        ctrl.audio_queue.enqueue_sentence("Air moves faster over the top.", turn_id=1)

        # User interrupts!
        ctrl._on_interruption_detected(turn_id=1, speech_samples=np.zeros(1600, dtype=np.float32))
        self.assertEqual(ctrl._state, ConversationState.USER_SPEAKING)
        self.assertIsNotNone(ctrl._active_interruption_snapshot)

        # STT delivers user correction (after VAD detects speech end & transitions to TRANSCRIBING)
        ctrl._transition_to(ConversationState.TRANSCRIBING)
        res = TranscriptionResult(
            text="Wait, that's not what I meant. I was asking about paper planes.",
            language="en",
            language_probability=0.99,
            duration_seconds=1.5,
        )
        ctrl._on_transcription_completed(res, turn_id=ctrl._turn_id)

        # Verify AI service was called with correction context
        mock_ai.ask.assert_called_once()
        _, kwargs = mock_ai.ask.call_args
        ctx = kwargs.get("interruption_context")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["type"], "correction")
        self.assertEqual(ctx["original_query"], "How do planes fly?")
        self.assertIn("Wait, that's not what I meant", ctx["interruption_text"])

    def test_controller_interruption_follow_up_flow(self) -> None:
        """Verify Type B follow-up interruption passes follow-up context without restart."""
        from app.voice.whisper_engine import TranscriptionResult
        ctrl, mock_ai, _ = self._create_mock_controller()

        ctrl._transition_to(ConversationState.AI_SPEAKING)
        ctrl.audio_queue.enqueue_sentence("Air moves faster over the top.", turn_id=1)

        ctrl._on_interruption_detected(turn_id=1, speech_samples=np.zeros(1600, dtype=np.float32))

        # STT delivers follow-up
        ctrl._transition_to(ConversationState.TRANSCRIBING)
        res = TranscriptionResult(
            text="Why does it move faster over the top?",
            language="en",
            language_probability=0.99,
            duration_seconds=1.0,
        )
        ctrl._on_transcription_completed(res, turn_id=ctrl._turn_id)

        mock_ai.ask.assert_called_once()
        _, kwargs = mock_ai.ask.call_args
        ctx = kwargs.get("interruption_context")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["type"], "follow_up")
        self.assertEqual(ctx["original_query"], "How do planes fly?")

    def test_controller_interruption_topic_change_flow(self) -> None:
        """Verify Type C topic change switches context cleanly."""
        from app.voice.whisper_engine import TranscriptionResult
        ctrl, mock_ai, _ = self._create_mock_controller()

        ctrl._transition_to(ConversationState.AI_SPEAKING)
        ctrl.audio_queue.enqueue_sentence("Sentence 1.", turn_id=1)
        ctrl._on_interruption_detected(turn_id=1, speech_samples=np.zeros(1600, dtype=np.float32))

        ctrl._transition_to(ConversationState.TRANSCRIBING)
        res = TranscriptionResult(
            text="Anyway, let's talk about something else. What is gravity?",
            language="en",
            language_probability=0.99,
            duration_seconds=1.8,
        )
        ctrl._on_transcription_completed(res, turn_id=ctrl._turn_id)

        mock_ai.ask.assert_called_once()
        _, kwargs = mock_ai.ask.call_args
        ctx = kwargs.get("interruption_context")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["type"], "topic_change")

    def test_controller_interruption_acknowledgement_resumes_playback(self) -> None:
        """Verify Type D acknowledgement does NOT cancel remaining sentences; resumes playback."""
        from app.voice.whisper_engine import TranscriptionResult
        ctrl, mock_ai, _ = self._create_mock_controller()

        ctrl._transition_to(ConversationState.AI_SPEAKING)
        ctrl.audio_queue.enqueue_sentence("First sentence.", turn_id=1)
        ctrl.audio_queue.enqueue_sentence("Second sentence.", turn_id=1)

        ctrl._on_interruption_detected(turn_id=1, speech_samples=np.zeros(1600, dtype=np.float32))

        # User simply backchannels "Okay"
        ctrl._transition_to(ConversationState.TRANSCRIBING)
        res = TranscriptionResult(
            text="Okay",
            language="en",
            language_probability=0.99,
            duration_seconds=0.4,
        )
        ctrl._on_transcription_completed(res, turn_id=ctrl._turn_id)

        # AI should NOT be asked for a new response
        mock_ai.ask.assert_not_called()

        # Controller state must return to AI_SPEAKING to continue remaining speech
        self.assertEqual(ctrl._state, ConversationState.AI_SPEAKING)


if __name__ == "__main__":
    unittest.main()
