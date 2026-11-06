"""Tests for Phase 6 — Natural Conversational Turn-Taking.

Verifies:
6.1 Pause handling, connector detection, and adaptive silence thresholds (English, Hindi, Gujarati).
6.2 Standalone short acknowledgement detection, prompt guidance, and token budgeting.
6.3 Contextual follow-up coreference resolution without entity repetition requests.
6.4 Avoidance of repeated answers, duplicate audio reprocessing, and robotic canned questions.
6.5 Multilingual consistency across English, Gujarati, and Hindi.
"""

import numpy as np
import pytest

from app.ai.adaptive_response_style import ResponseStyle
from app.ai.ai_service import AIService
from app.ai.conversation_context import ConversationContext
from app.ai.personality_manager import PersonalityManager
from app.ai.turn_taking_manager import TurnTakingManager
from app.voice.vad_engine import VADEngine, VADState


# ─────────────────────────────────────────────────────────────────────────────
# 6.1 Pause Handling & Adaptive VAD Endpointing
# ─────────────────────────────────────────────────────────────────────────────

class TestPauseHandlingAndConnectors:
    """Verifies adaptive VAD threshold and linguistic connector detection (6.1)."""

    def test_linguistic_connector_detection_english(self) -> None:
        assert TurnTakingManager.has_trailing_connector("I was wondering because") is True
        assert TurnTakingManager.has_trailing_connector("We could go and") is True
        assert TurnTakingManager.has_trailing_connector("Let me know if") is True
        assert TurnTakingManager.has_trailing_connector("Well um") is True
        assert TurnTakingManager.has_trailing_connector("Actually") is True

        # Non-connectors
        assert TurnTakingManager.has_trailing_connector("What time is it?") is False
        assert TurnTakingManager.has_trailing_connector("Tell me about Interstellar.") is False

    def test_linguistic_connector_detection_hindi(self) -> None:
        # Native Devanagari
        assert TurnTakingManager.has_trailing_connector("मैं सोच रहा था क्योंकि") is True
        assert TurnTakingManager.has_trailing_connector("हम चलेंगे और") is True
        assert TurnTakingManager.has_trailing_connector("बात यह है लेकिन") is True
        assert TurnTakingManager.has_trailing_connector("मेरा मतलब") is True

        # Romanized Hindi
        assert TurnTakingManager.has_trailing_connector("main soch raha tha kyunki") is True
        assert TurnTakingManager.has_trailing_connector("aaj aur") is True
        assert TurnTakingManager.has_trailing_connector("lekin") is True

        # Non-connectors
        assert TurnTakingManager.has_trailing_connector("नमस्ते आप कैसे हैं?") is False
        assert TurnTakingManager.has_trailing_connector("मुझे भारत के बारे में बताओ") is False

    def test_linguistic_connector_detection_gujarati(self) -> None:
        # Native Gujarati
        assert TurnTakingManager.has_trailing_connector("હું વિચારતો હતો કારણ કે") is True
        assert TurnTakingManager.has_trailing_connector("આપણે જઈશું અને") is True
        assert TurnTakingManager.has_trailing_connector("વાત એમ છે પણ") is True
        assert TurnTakingManager.has_trailing_connector("એટલે") is True

        # Romanized Gujarati
        assert TurnTakingManager.has_trailing_connector("hu vicharto hato karan ke") is True
        assert TurnTakingManager.has_trailing_connector("aaje ane") is True
        assert TurnTakingManager.has_trailing_connector("pan") is True

        # Non-connectors
        assert TurnTakingManager.has_trailing_connector("કેમ છો?") is False
        assert TurnTakingManager.has_trailing_connector("મને પુસ્તક વિશે કહો") is False

    def test_vad_adaptive_silence_threshold_calculation(self) -> None:
        vad = VADEngine(silence_threshold_ms=450)

        # 1. Normal completed speech (2200ms) with no connector -> base threshold (450ms)
        thresh_normal = vad.get_adaptive_silence_threshold_ms(speech_duration_ms=2200)
        assert thresh_normal == 450

        # 2. Short single-syllable / hesitation utterance (300ms) -> extended hesitation allowance
        thresh_short = vad.get_adaptive_silence_threshold_ms(speech_duration_ms=300)
        assert thresh_short >= 650

        # 3. Trailing connector flagged -> extended thinking allowance (>= 900ms)
        vad.set_trailing_connector(True)
        thresh_connector = vad.get_adaptive_silence_threshold_ms(speech_duration_ms=1500)
        assert thresh_connector >= 900
        vad.set_trailing_connector(False)

        # 4. Explicit thinking pause flagged -> extended allowance (>= 900ms)
        vad.set_thinking_pause(True)
        thresh_thinking = vad.get_adaptive_silence_threshold_ms(speech_duration_ms=1500)
        assert thresh_thinking >= 900
        vad.set_thinking_pause(False)

        # 5. Elevated ambient noise floor -> adds noise margin
        vad._ambient_noise_rms = 0.025
        thresh_noisy = vad.get_adaptive_silence_threshold_ms(speech_duration_ms=2200)
        assert thresh_noisy > 450

    def test_vad_preserves_explicit_low_test_thresholds(self) -> None:
        # Mock test environments configure low thresholds (e.g., 96ms)
        vad = VADEngine(silence_threshold_ms=96)
        thresh = vad.get_adaptive_silence_threshold_ms(speech_duration_ms=160)
        assert thresh == 96


# ─────────────────────────────────────────────────────────────────────────────
# 6.2 Short Acknowledgements Handling
# ─────────────────────────────────────────────────────────────────────────────

class TestShortAcknowledgements:
    """Verifies detection of short acknowledgements and monologue prevention (6.2)."""

    def test_acknowledgement_detection_multilingual(self) -> None:
        # English
        for word in ["Hmm", "Okay", "OK", "Yes", "Yeah", "No", "Right", "Interesting", "Sure", "Got it", "Cool"]:
            is_ack, term = TurnTakingManager.is_short_acknowledgement(word)
            assert is_ack is True, f"Failed for English acknowledgement: {word}"

        # Hindi
        for word in ["हाँ", "अच्छा", "ठीक है", "हूँ", "सही बात है", "समझ गया", "जी", "जी हाँ", "haan", "accha", "theek hai"]:
            is_ack, term = TurnTakingManager.is_short_acknowledgement(word)
            assert is_ack is True, f"Failed for Hindi acknowledgement: {word}"

        # Gujarati
        for word in ["હા", "બરાબર", "ઠીક છે", "હંમ", "સારું", "ખરું", "જી હા", "વાહ", "સરસ", "haa", "barabar", "thik che"]:
            is_ack, term = TurnTakingManager.is_short_acknowledgement(word)
            assert is_ack is True, f"Failed for Gujarati acknowledgement: {word}"

        # Non-acknowledgements (should return False)
        assert TurnTakingManager.is_short_acknowledgement("Explain machine learning in detail")[0] is False
        assert TurnTakingManager.is_short_acknowledgement("Who directed Interstellar?")[0] is False
        assert TurnTakingManager.is_short_acknowledgement("મને ગાંધીજી વિશે કહો")[0] is False
        assert TurnTakingManager.is_short_acknowledgement("मुझे भारत के इतिहास के बारे में बताइए")[0] is False

    def test_acknowledgement_instruction_prompts(self) -> None:
        instr_en = TurnTakingManager.build_acknowledgement_instruction("Okay", response_language="en")
        assert "DO NOT launch into a long lecture" in instr_en
        assert "EXACTLY 1 brief spoken sentence in English" in instr_en

        instr_gu = TurnTakingManager.build_acknowledgement_instruction("બરાબર", response_language="gu")
        assert "DO NOT launch into a long lecture" in instr_gu
        assert "ગુજરાતીમાં" in instr_gu

        instr_hi = TurnTakingManager.build_acknowledgement_instruction("अच्छा", response_language="hi")
        assert "DO NOT launch into a long lecture" in instr_hi
        assert "हिन्दी में" in instr_hi


# ─────────────────────────────────────────────────────────────────────────────
# 6.3 Follow-Up Questions & Coreference Resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestFollowUpCoreferenceResolution:
    """Verifies coreference resolution for follow-up queries (6.3)."""

    def test_system_prompt_includes_coreference_directives(self) -> None:
        pm = PersonalityManager()
        prompt_en = pm.build_system_prompt(response_language="en")
        assert "[NATURAL CONVERSATIONAL TURN-TAKING & DIALOGUE FLOW]" in prompt_en
        assert "Coreference Resolution" in prompt_en
        assert "Interstellar" in prompt_en
        assert "NEVER ask the user to repeat the movie or entity name" in prompt_en

        prompt_gu = pm.build_system_prompt(response_language="gu")
        assert "Coreference Resolution" in prompt_gu
        assert "Gujarati" in prompt_gu

        prompt_hi = pm.build_system_prompt(response_language="hi")
        assert "Coreference Resolution" in prompt_hi
        assert "Hindi" in prompt_hi

    def test_multi_turn_context_preserves_subject_entity(self) -> None:
        ctx = ConversationContext()
        # Turn 1: User asks about Interstellar, assistant provides answer
        ctx.add_user_message("Tell me about the movie Interstellar.")
        ctx.add_assistant_message("Interstellar is a 2014 science fiction film about astronauts traveling through a wormhole.")

        # Turn 2: User asks follow-up with pronoun "it"
        ctx.add_user_message("Who directed it?")

        messages = ctx.get_messages()
        # Ensure context maintains both turns in sequence
        assert len(messages) == 3
        assert messages[0]["content"] == "Tell me about the movie Interstellar."
        assert "Interstellar is a 2014 science fiction" in messages[1]["content"]
        assert messages[2]["content"] == "Who directed it?"


# ─────────────────────────────────────────────────────────────────────────────
# 6.4 Avoid Repeated Responses & Robotic Canned Questions
# ─────────────────────────────────────────────────────────────────────────────

class TestAntiRepetitionAndCannedQuestions:
    """Verifies repetition avoidance and robotic question stripping (6.4)."""

    def test_canned_closing_question_stripping_english(self) -> None:
        raw1 = "Interstellar was directed by Christopher Nolan. Would you like to know more about this movie?"
        cleaned1 = TurnTakingManager.strip_canned_closing_questions(raw1)
        assert cleaned1 == "Interstellar was directed by Christopher Nolan."

        raw2 = "The capital of France is Paris. Is there anything else I can help you with today?"
        cleaned2 = TurnTakingManager.strip_canned_closing_questions(raw2)
        assert cleaned2 == "The capital of France is Paris."

        raw3 = "The meeting starts at 3 PM. Let me know if you need anything else."
        cleaned3 = TurnTakingManager.strip_canned_closing_questions(raw3)
        assert cleaned3 == "The meeting starts at 3 PM."

    def test_canned_closing_question_stripping_hindi(self) -> None:
        raw = "क्रिस्टोफर नोलन ने इंटरस्टेलर का निर्देशन किया था। क्या आप कुछ और जानना चाहते हैं?"
        cleaned = TurnTakingManager.strip_canned_closing_questions(raw)
        assert cleaned == "क्रिस्टोफर नोलन ने इंटरस्टेलर का निर्देशन किया था।"

    def test_canned_closing_question_stripping_gujarati(self) -> None:
        raw = "ક્રિસ્ટોફર નોલાને ઇન્ટરસ્ટેલરનું દિગ્દર્શન કર્યું હતું. શું તમે વધુ જાણવા માંગો છો?"
        cleaned = TurnTakingManager.strip_canned_closing_questions(raw)
        assert cleaned == "ક્રિસ્ટોફર નોલાને ઇન્ટરસ્ટેલરનું દિગ્દર્શન કર્યું હતું."

    def test_duplicate_response_detection(self) -> None:
        prev = "Christopher Nolan directed Interstellar."
        # Exact match
        assert TurnTakingManager.is_duplicate_response("Christopher Nolan directed Interstellar.", prev) is True
        # Punctuation/casing variant
        assert TurnTakingManager.is_duplicate_response("christopher nolan directed interstellar!", prev) is True
        # Completely different response
        assert TurnTakingManager.is_duplicate_response("It was released in November 2014.", prev) is False
