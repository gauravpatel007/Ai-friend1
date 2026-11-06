"""Phase 5 Automated Test Suite: Adaptive Response Length & Style.

Verifies:
1. 5.1 & 5.2 - All Five Response Styles & Intent Detection:
   - QUICK_ANSWER
   - NORMAL_CONVERSATION
   - DETAILED_EXPLANATION
   - STEP_BY_STEP
   - HANDS_FREE_SUMMARY
   Tested across English, Gujarati (script + Romanized), and Hindi (script + Romanized).
2. 5.3 - Voice-Specific Formatting & Behavior:
   - Stripping markdown tables, asterisks, raw URLs, code blocks, and emojis.
   - Spoken transitions and logical section chunking.
3. 5.4 - Direct User Overrides:
   - "Keep it short"
   - "Explain more"
   - "Give me an example"
   - "Continue"
   - "Summarize it"
   (Tested in English, Gujarati, and Hindi).
4. 5.5 - Language Settings Preservation:
   - Strict language rules maintained across all response styles for English, Gujarati, and Hindi.
5. Dynamic Token Budgeting:
   - Proportional token headroom allocated across voice and chat modalities.
6. AIService & Controller Integration:
   - State updating and signal emissions for text and voice modes.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication

from app.ai.adaptive_response_style import (
    AdaptiveStyleDetector,
    AdaptiveStyleGuidelines,
    ResponseStyle,
)
from app.ai.generation_controls import GenerationConfig
from app.ai.personality_manager import PersonalityManager
from app.voice.tts_base import clean_text_for_speech


class TestPhase5AdaptiveResponseLength(unittest.TestCase):
    """Automated tests for Phase 5 Adaptive Response Length."""

    @classmethod
    def setUpClass(cls) -> None:
        if QCoreApplication.instance() is None:
            cls.app = QCoreApplication([])
        else:
            cls.app = QCoreApplication.instance()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. FIVE RESPONSE STYLES ENUM & RESOLUTION
    # ─────────────────────────────────────────────────────────────────────────

    def test_response_style_enum_values_and_from_string(self) -> None:
        """Verify all five response styles exist and resolve correctly from strings."""
        self.assertEqual(ResponseStyle.QUICK_ANSWER.value, "quick_answer")
        self.assertEqual(ResponseStyle.NORMAL_CONVERSATION.value, "normal_conversation")
        self.assertEqual(ResponseStyle.DETAILED_EXPLANATION.value, "detailed_explanation")
        self.assertEqual(ResponseStyle.STEP_BY_STEP.value, "step_by_step")
        self.assertEqual(ResponseStyle.HANDS_FREE_SUMMARY.value, "hands_free_summary")

        # Fallback and alias resolutions
        self.assertEqual(ResponseStyle.from_string("quick"), ResponseStyle.QUICK_ANSWER)
        self.assertEqual(ResponseStyle.from_string("concise"), ResponseStyle.QUICK_ANSWER)
        self.assertEqual(ResponseStyle.from_string("normal"), ResponseStyle.NORMAL_CONVERSATION)
        self.assertEqual(ResponseStyle.from_string("detailed"), ResponseStyle.DETAILED_EXPLANATION)
        self.assertEqual(ResponseStyle.from_string("step-by-step"), ResponseStyle.STEP_BY_STEP)
        self.assertEqual(ResponseStyle.from_string("summary"), ResponseStyle.HANDS_FREE_SUMMARY)
        self.assertEqual(ResponseStyle.from_string("unknown"), ResponseStyle.NORMAL_CONVERSATION)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. USER INTENT DETECTION ACROSS EN, GU, HI (Section 5.2)
    # ─────────────────────────────────────────────────────────────────────────

    def test_detect_quick_answer_intent(self) -> None:
        """Verify Quick Answer intent is detected across EN, GU, HI."""
        # English
        style, is_override, _ = AdaptiveStyleDetector.detect_style("Just tell me the answer.")
        self.assertEqual(style, ResponseStyle.QUICK_ANSWER)

        style, _, _ = AdaptiveStyleDetector.detect_style("What is the capital of France? Yes or no.")
        self.assertEqual(style, ResponseStyle.QUICK_ANSWER)

        # Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("बस जवाब दो, मुझे जल्दी है।")
        self.assertEqual(style, ResponseStyle.QUICK_ANSWER)

        # Romanized Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("bas jawab do ek line me")
        self.assertEqual(style, ResponseStyle.QUICK_ANSWER)

        # Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("માત્ર જવાબ આપો, વધારાની વાત નહીં.")
        self.assertEqual(style, ResponseStyle.QUICK_ANSWER)

        # Romanized Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("matra jawab aapo ek litima")
        self.assertEqual(style, ResponseStyle.QUICK_ANSWER)

    def test_detect_normal_conversation_intent(self) -> None:
        """Verify Normal Conversation is the balanced default for standard queries."""
        # English
        style, is_override, _ = AdaptiveStyleDetector.detect_style("Explain machine learning.")
        self.assertEqual(style, ResponseStyle.NORMAL_CONVERSATION)
        self.assertFalse(is_override)

        style, _, _ = AdaptiveStyleDetector.detect_style("How does gravity work?")
        self.assertEqual(style, ResponseStyle.NORMAL_CONVERSATION)

        # Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("सौर मंडल क्या है?")
        self.assertEqual(style, ResponseStyle.NORMAL_CONVERSATION)

        # Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("તમે કેમ છો?")
        self.assertEqual(style, ResponseStyle.NORMAL_CONVERSATION)

    def test_detect_detailed_explanation_intent(self) -> None:
        """Verify Detailed Explanation intent is detected across EN, GU, HI."""
        # English
        style, _, _ = AdaptiveStyleDetector.detect_style("Explain this in complete detail with examples.")
        self.assertEqual(style, ResponseStyle.DETAILED_EXPLANATION)

        style, _, _ = AdaptiveStyleDetector.detect_style("Give me a deep dive into neural networks.")
        self.assertEqual(style, ResponseStyle.DETAILED_EXPLANATION)

        # Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("विस्तार से समझाइए उदाहरण सहित।")
        self.assertEqual(style, ResponseStyle.DETAILED_EXPLANATION)

        # Romanized Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("vistar se samjhao udaharan ke saath")
        self.assertEqual(style, ResponseStyle.DETAILED_EXPLANATION)

        # Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("આ વિષયને ઉદાહરણ સાથે વિસ્તારથી સમજાવો.")
        self.assertEqual(style, ResponseStyle.DETAILED_EXPLANATION)

        # Romanized Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("vigatvar janavo undanpurvak")
        self.assertEqual(style, ResponseStyle.DETAILED_EXPLANATION)

    def test_detect_step_by_step_intent(self) -> None:
        """Verify Step-by-Step Instructions intent is detected across EN, GU, HI."""
        # English
        style, _, _ = AdaptiveStyleDetector.detect_style("Guide me step by step.")
        self.assertEqual(style, ResponseStyle.STEP_BY_STEP)

        style, _, _ = AdaptiveStyleDetector.detect_style("How do I install python step by step?")
        self.assertEqual(style, ResponseStyle.STEP_BY_STEP)

        # Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("कदम दर कदम समझाओ कैसे करना है।")
        self.assertEqual(style, ResponseStyle.STEP_BY_STEP)

        # Romanized Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("step by step batao kaise install kare")
        self.assertEqual(style, ResponseStyle.STEP_BY_STEP)

        # Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("મને પગલાંવાર સમજાવો.")
        self.assertEqual(style, ResponseStyle.STEP_BY_STEP)

        # Romanized Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("paglavar janavo rit samjavo")
        self.assertEqual(style, ResponseStyle.STEP_BY_STEP)

    def test_detect_hands_free_summary_intent(self) -> None:
        """Verify Hands-Free Summary intent is detected across EN, GU, HI."""
        # English
        style, _, _ = AdaptiveStyleDetector.detect_style("Summarize this while I'm driving.")
        self.assertEqual(style, ResponseStyle.HANDS_FREE_SUMMARY)

        style, _, _ = AdaptiveStyleDetector.detect_style("Give me a hands-free summary with key takeaways.")
        self.assertEqual(style, ResponseStyle.HANDS_FREE_SUMMARY)

        # Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("ड्राइविंग करते हुए सारांश दो।")
        self.assertEqual(style, ResponseStyle.HANDS_FREE_SUMMARY)

        # Romanized Hindi
        style, _, _ = AdaptiveStyleDetector.detect_style("driving karte hue saransh do mukhya baatein")
        self.assertEqual(style, ResponseStyle.HANDS_FREE_SUMMARY)

        # Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("ડ્રાઇવિંગ કરતી વખતે સારાંશ આપો.")
        self.assertEqual(style, ResponseStyle.HANDS_FREE_SUMMARY)

        # Romanized Gujarati
        style, _, _ = AdaptiveStyleDetector.detect_style("driving karti vakhte saransh aapo")
        self.assertEqual(style, ResponseStyle.HANDS_FREE_SUMMARY)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. DIRECT USER OVERRIDES (Section 5.4)
    # ─────────────────────────────────────────────────────────────────────────

    def test_direct_user_override_keep_it_short(self) -> None:
        """Verify 'Keep it short' immediately overrides style to QUICK_ANSWER."""
        style, is_override, reason = AdaptiveStyleDetector.detect_style("Keep it short.")
        self.assertTrue(is_override)
        self.assertEqual(style, ResponseStyle.QUICK_ANSWER)

        # Hindi override
        style_hi, is_ov_hi, _ = AdaptiveStyleDetector.detect_style("छोटा बताओ")
        self.assertTrue(is_ov_hi)
        self.assertEqual(style_hi, ResponseStyle.QUICK_ANSWER)

        # Gujarati override
        style_gu, is_ov_gu, _ = AdaptiveStyleDetector.detect_style("ટૂંકમાં કહો")
        self.assertTrue(is_ov_gu)
        self.assertEqual(style_gu, ResponseStyle.QUICK_ANSWER)

    def test_direct_user_override_explain_more(self) -> None:
        """Verify 'Explain more' overrides style to DETAILED_EXPLANATION."""
        style, is_override, _ = AdaptiveStyleDetector.detect_style("Explain more.")
        self.assertTrue(is_override)
        self.assertEqual(style, ResponseStyle.DETAILED_EXPLANATION)

        # Hindi
        style_hi, is_ov_hi, _ = AdaptiveStyleDetector.detect_style("और बताओ")
        self.assertTrue(is_ov_hi)
        self.assertEqual(style_hi, ResponseStyle.DETAILED_EXPLANATION)

        # Gujarati
        style_gu, is_ov_gu, _ = AdaptiveStyleDetector.detect_style("વધુ સમજાવો")
        self.assertTrue(is_ov_gu)
        self.assertEqual(style_gu, ResponseStyle.DETAILED_EXPLANATION)

    def test_direct_user_override_give_me_an_example(self) -> None:
        """Verify 'Give me an example' triggers detailed explanation."""
        style, is_override, _ = AdaptiveStyleDetector.detect_style("Give me an example.")
        self.assertTrue(is_override)
        self.assertEqual(style, ResponseStyle.DETAILED_EXPLANATION)

        style_hi, is_ov_hi, _ = AdaptiveStyleDetector.detect_style("उदाहरण दो")
        self.assertTrue(is_ov_hi)
        self.assertEqual(style_hi, ResponseStyle.DETAILED_EXPLANATION)

        style_gu, is_ov_gu, _ = AdaptiveStyleDetector.detect_style("ઉદાહરણ આપો")
        self.assertTrue(is_ov_gu)
        self.assertEqual(style_gu, ResponseStyle.DETAILED_EXPLANATION)

    def test_direct_user_override_continue(self) -> None:
        """Verify 'Continue' carries on the explanation."""
        style, is_override, _ = AdaptiveStyleDetector.detect_style("Continue.")
        self.assertTrue(is_override)
        self.assertEqual(style, ResponseStyle.NORMAL_CONVERSATION)

        style_hi, is_ov_hi, _ = AdaptiveStyleDetector.detect_style("आगे बताओ")
        self.assertTrue(is_ov_hi)
        self.assertEqual(style_hi, ResponseStyle.NORMAL_CONVERSATION)

        style_gu, is_ov_gu, _ = AdaptiveStyleDetector.detect_style("આગળ બોલો")
        self.assertTrue(is_ov_gu)
        self.assertEqual(style_gu, ResponseStyle.NORMAL_CONVERSATION)

    def test_direct_user_override_summarize_it(self) -> None:
        """Verify 'Summarize it' triggers HANDS_FREE_SUMMARY."""
        style, is_override, _ = AdaptiveStyleDetector.detect_style("Summarize it.")
        self.assertTrue(is_override)
        self.assertEqual(style, ResponseStyle.HANDS_FREE_SUMMARY)

        style_hi, is_ov_hi, _ = AdaptiveStyleDetector.detect_style("सारांश दो")
        self.assertTrue(is_ov_hi)
        self.assertEqual(style_hi, ResponseStyle.HANDS_FREE_SUMMARY)

        style_gu, is_ov_gu, _ = AdaptiveStyleDetector.detect_style("સારાંશ આપો")
        self.assertTrue(is_ov_gu)
        self.assertEqual(style_gu, ResponseStyle.HANDS_FREE_SUMMARY)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. VOICE-SPECIFIC BEHAVIOR & FORMATTING CLEANUP (Section 5.3)
    # ─────────────────────────────────────────────────────────────────────────

    def test_clean_text_for_speech_removes_markdown_tables(self) -> None:
        """Verify markdown tables and separators are stripped from spoken audio text."""
        raw = (
            "Here is the comparison:\n\n"
            "| Item | Cost | Rating |\n"
            "| --- | --- | --- |\n"
            "| Apple | $1 | 5 stars |\n"
            "| Orange | $2 | 4 stars |\n\n"
            "In summary, apples are cheaper."
        )
        cleaned = clean_text_for_speech(raw)
        self.assertNotIn("|", cleaned)
        self.assertNotIn("---", cleaned)
        self.assertIn("In summary, apples are cheaper.", cleaned)

    def test_clean_text_for_speech_removes_formatting_symbols_and_emojis(self) -> None:
        """Verify asterisks, links, URLs, code blocks, and emojis are stripped."""
        raw = (
            "Look at **this bold word** and *italic word*! \U0001F680\n"
            "Check [Python docs](https://python.org) at `http://example.com`.\n"
            "```python\nprint('hello')\n```\n"
            "End of message."
        )
        cleaned = clean_text_for_speech(raw)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("*", cleaned)
        self.assertNotIn("\U0001F680", cleaned)
        self.assertNotIn("http://", cleaned)
        self.assertNotIn("https://", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertIn("this bold word and italic word", cleaned)
        self.assertIn("Python docs", cleaned)
        self.assertIn("End of message.", cleaned)

    def test_voice_prompt_directive_includes_formatting_constraints(self) -> None:
        """Verify system prompt directives for voice mode mandate no tables/asterisks/URLs."""
        directive = AdaptiveStyleGuidelines.build_style_directive(
            style=ResponseStyle.NORMAL_CONVERSATION,
            is_voice=True,
            response_language="en",
        )
        self.assertIn("CRITICAL VOICE FORMATTING CONSTRAINTS", directive)
        self.assertIn("NEVER use markdown tables", directive)
        self.assertIn("NEVER use asterisks", directive)
        self.assertIn("NEVER output raw web URLs", directive)

    def test_voice_prompt_detailed_explanation_guidelines(self) -> None:
        """Verify detailed explanation in voice mode instructs spoken sections and pauses."""
        directive = AdaptiveStyleGuidelines.build_style_directive(
            style=ResponseStyle.DETAILED_EXPLANATION,
            is_voice=True,
            response_language="en",
        )
        self.assertIn("Spoken Hands-Free", directive)
        self.assertIn("conversational sections", directive)
        self.assertIn("user can interrupt", directive)

    def test_voice_prompt_step_by_step_guidelines(self) -> None:
        """Verify step-by-step in voice mode instructs spoken transitions."""
        directive = AdaptiveStyleGuidelines.build_style_directive(
            style=ResponseStyle.STEP_BY_STEP,
            is_voice=True,
            response_language="en",
        )
        self.assertIn("First...", directive)
        self.assertIn("Next...", directive)
        self.assertIn("Finally...", directive)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. LANGUAGE PRESERVATION ACROSS RESPONSE STYLES (Section 5.5)
    # ─────────────────────────────────────────────────────────────────────────

    def test_language_preserved_for_all_styles_english(self) -> None:
        """Verify English response language directive is included regardless of style."""
        for style in ResponseStyle:
            directive = AdaptiveStyleGuidelines.build_style_directive(
                style=style,
                is_voice=False,
                response_language="en",
            )
            self.assertIn("STRICT RESPONSE LANGUAGE RULE", directive)
            self.assertIn("100% in English", directive)

    def test_language_preserved_for_all_styles_gujarati(self) -> None:
        """Verify Gujarati response language directive is included regardless of style."""
        for style in ResponseStyle:
            directive = AdaptiveStyleGuidelines.build_style_directive(
                style=style,
                is_voice=True,
                response_language="gu",
            )
            self.assertIn("STRICT RESPONSE LANGUAGE RULE", directive)
            self.assertIn("100% in Gujarati", directive)

    def test_language_preserved_for_all_styles_hindi(self) -> None:
        """Verify Hindi response language directive is included regardless of style."""
        for style in ResponseStyle:
            directive = AdaptiveStyleGuidelines.build_style_directive(
                style=style,
                is_voice=True,
                response_language="hi",
            )
            self.assertIn("STRICT RESPONSE LANGUAGE RULE", directive)
            self.assertIn("100% in Hindi", directive)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. DYNAMIC TOKEN BUDGETING ACROSS STYLES & MODES
    # ─────────────────────────────────────────────────────────────────────────

    def test_token_budgets_voice_vs_chat(self) -> None:
        """Verify token allocations match task complexity for voice and chat."""
        # Voice budgets
        q_v = GenerationConfig.estimate_task_token_budget("Just tell me the answer.", is_voice=True)
        norm_v = GenerationConfig.estimate_task_token_budget("Explain machine learning.", is_voice=True)
        det_v = GenerationConfig.estimate_task_token_budget("Explain this in complete detail with examples.", is_voice=True)
        step_v = GenerationConfig.estimate_task_token_budget("Guide me step by step.", is_voice=True)
        sum_v = GenerationConfig.estimate_task_token_budget("Summarize this while I'm driving.", is_voice=True)

        self.assertLess(q_v, norm_v)
        self.assertLess(norm_v, det_v)
        self.assertGreater(det_v, step_v)
        self.assertLess(sum_v, det_v)

        # Chat budgets
        q_c = GenerationConfig.estimate_task_token_budget("Just tell me the answer.", is_voice=False)
        det_c = GenerationConfig.estimate_task_token_budget("Explain this in complete detail with examples.", is_voice=False)
        self.assertGreater(det_c, q_c)
        self.assertGreaterEqual(det_c, 2500)

    # ─────────────────────────────────────────────────────────────────────────
    # 7. PERSONALITY MANAGER & AI SERVICE INTEGRATION
    # ─────────────────────────────────────────────────────────────────────────

    def test_personality_manager_integrates_adaptive_style_prompt(self) -> None:
        """Verify PersonalityManager injects adaptive style guidelines into system prompt."""
        pm = PersonalityManager()
        prompt_quick = pm.build_system_prompt(
            is_voice=True,
            response_style="quick_answer",
            user_input="Just the answer please",
            response_language="en",
        )
        self.assertIn("[ADAPTIVE RESPONSE STYLE: QUICK ANSWER]", prompt_quick)
        self.assertIn("1 or 2 concise sentences", prompt_quick)

        prompt_detailed = pm.build_system_prompt(
            is_voice=False,
            response_style="detailed_explanation",
            user_input="Explain in complete detail",
            response_language="gu",
        )
        self.assertIn("[ADAPTIVE RESPONSE STYLE: DETAILED EXPLANATION]", prompt_detailed)
        self.assertIn("100% in Gujarati", prompt_detailed)

    def test_ai_service_adaptive_style_state_and_override(self) -> None:
        """Verify AIService tracks adaptive response style and updates on override."""
        from app.ai.ai_service import AIService
        from app.settings.config_manager import ConfigManager

        cfg = ConfigManager()
        cfg.set("ai.response_style", "normal_conversation")
        service = AIService(config_manager=cfg)

        self.assertEqual(service.current_response_style, ResponseStyle.NORMAL_CONVERSATION)

        # Explicit setter
        service.set_response_style(ResponseStyle.DETAILED_EXPLANATION)
        self.assertEqual(service.current_response_style, ResponseStyle.DETAILED_EXPLANATION)

        # Mocking ask to verify override updates active style
        with patch.object(service, "cancel_generation"), \
             patch.object(service.model_manager, "is_available", return_value=True), \
             patch.object(service.model_manager, "select_active_model", return_value="llama3.2:latest"), \
             patch.object(service.thread_pool, "start"):

            # User sends direct override in chat: "Keep it short"
            service.ask("Keep it short.", is_voice=False)
            self.assertEqual(service.current_response_style, ResponseStyle.QUICK_ANSWER)

            # User sends direct override: "Explain more"
            service.ask("Explain more.", is_voice=True)
            self.assertEqual(service.current_response_style, ResponseStyle.DETAILED_EXPLANATION)

    # ─────────────────────────────────────────────────────────────────────────
    # 8. VOICE CONVERSATION CONTROLLER ADAPTIVE DISPATCH
    # ─────────────────────────────────────────────────────────────────────────

    def _create_mock_controller(self, service: Any = None) -> tuple[Any, Any]:
        """Create VoiceConversationController with mocked hardware."""
        from app.voice.voice_conversation_controller import VoiceConversationController
        from app.voice.whisper_engine import WhisperEngine
        from app.voice.vad_engine import VADEngine
        from app.voice.conversation_state import ConversationState

        mock_player = MagicMock()
        mock_tts = MagicMock()
        mock_whisper = MagicMock(spec=WhisperEngine)
        mock_vad = MagicMock(spec=VADEngine)
        mock_vad.silence_threshold_ms = 400

        mock_ai = service if service is not None else MagicMock()
        if service is None:
            mock_ai.ask.return_value = 1

        ctrl = VoiceConversationController(
            audio_player=mock_player,
            tts_engine=mock_tts,
            ai_service=mock_ai,
            whisper_engine=mock_whisper,
            vad_engine=mock_vad,
        )
        ctrl._turn_id = 1
        ctrl.audio_queue.start_new_turn(turn_id=1)
        ctrl._state = ConversationState.USER_SPEAKING
        # Ensure buddy is not sleeping
        if hasattr(ctrl, "command_dispatcher") and ctrl.command_dispatcher.buddy_state_manager:
            ctrl.command_dispatcher.buddy_state_manager.wake_up()
        return ctrl, mock_ai

    def test_voice_controller_dispatches_with_is_voice_true(self) -> None:
        """Verify VoiceConversationController dispatches user voice transcripts with is_voice=True."""
        from app.voice.whisper_engine import TranscriptionResult
        from app.voice.conversation_state import ConversationState

        ctrl, mock_ai = self._create_mock_controller()
        ctrl._state = ConversationState.USER_SPEAKING
        ctrl._transition_to(ConversationState.TRANSCRIBING)

        res = TranscriptionResult(
            text="Explain this in complete detail with examples.",
            language="en",
            language_probability=0.99,
            duration_seconds=1.5,
        )
        ctrl._on_transcription_completed(res, turn_id=1)

        mock_ai.ask.assert_called_once()
        _, kwargs = mock_ai.ask.call_args
        self.assertEqual(kwargs.get("user_prompt"), "Explain this in complete detail with examples.")
        self.assertTrue(kwargs.get("is_voice"))

    def test_voice_controller_with_real_ai_service_adapts_styles(self) -> None:
        """Verify voice interactions through VoiceConversationController correctly trigger adaptive styles."""
        from app.voice.whisper_engine import TranscriptionResult
        from app.voice.conversation_state import ConversationState
        from app.ai.ai_service import AIService
        from app.settings.config_manager import ConfigManager

        cfg = ConfigManager()
        cfg.set("ai.response_style", "normal_conversation")
        service = AIService(config_manager=cfg)

        ctrl, _ = self._create_mock_controller(service=service)

        with patch.object(service, "cancel_generation"), \
             patch.object(service.model_manager, "is_available", return_value=True), \
             patch.object(service.model_manager, "select_active_model", return_value="llama3.2:latest"), \
             patch.object(service.thread_pool, "start"):

            # Turn 1: Quick answer intent via voice
            ctrl._turn_id = 1
            ctrl.audio_queue.start_new_turn(turn_id=1)
            ctrl._state = ConversationState.USER_SPEAKING
            ctrl._transition_to(ConversationState.TRANSCRIBING)
            res1 = TranscriptionResult(
                text="Just tell me the answer.",
                language="en",
                language_probability=0.99,
                duration_seconds=1.0,
            )
            ctrl._on_transcription_completed(res1, turn_id=1)
            self.assertEqual(service.current_response_style, ResponseStyle.QUICK_ANSWER)

            # Turn 2: Step-by-step intent via voice
            ctrl._turn_id = 2
            ctrl.audio_queue.start_new_turn(turn_id=2)
            ctrl._state = ConversationState.USER_SPEAKING
            ctrl._transition_to(ConversationState.TRANSCRIBING)
            res2 = TranscriptionResult(
                text="Guide me step by step how to bake bread.",
                language="en",
                language_probability=0.99,
                duration_seconds=1.5,
            )
            ctrl._on_transcription_completed(res2, turn_id=2)
            self.assertEqual(service.current_response_style, ResponseStyle.STEP_BY_STEP)

            # Turn 3: Hands-free summary intent via voice in Hindi
            ctrl._turn_id = 3
            ctrl.audio_queue.start_new_turn(turn_id=3)
            ctrl._state = ConversationState.USER_SPEAKING
            ctrl._transition_to(ConversationState.TRANSCRIBING)
            res3 = TranscriptionResult(
                text="ड्राइविंग करते हुए सारांश दो।",
                language="hi",
                language_probability=0.99,
                duration_seconds=1.2,
            )
            ctrl._on_transcription_completed(res3, turn_id=3)
            self.assertEqual(service.current_response_style, ResponseStyle.HANDS_FREE_SUMMARY)

            # Turn 4: Detailed explanation intent via voice in Gujarati
            ctrl._turn_id = 4
            ctrl.audio_queue.start_new_turn(turn_id=4)
            ctrl._state = ConversationState.USER_SPEAKING
            ctrl._transition_to(ConversationState.TRANSCRIBING)
            res4 = TranscriptionResult(
                text="આ વિષયને ઉદાહરણ સાથે વિસ્તારથી સમજાવો.",
                language="gu",
                language_probability=0.99,
                duration_seconds=1.4,
            )
            ctrl._on_transcription_completed(res4, turn_id=4)
            self.assertEqual(service.current_response_style, ResponseStyle.DETAILED_EXPLANATION)
            self.assertEqual(service.current_response_style, ResponseStyle.DETAILED_EXPLANATION)


if __name__ == "__main__":
    unittest.main()
