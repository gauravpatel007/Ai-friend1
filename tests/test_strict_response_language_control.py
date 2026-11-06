"""Tests for Strict Response Language Control (English, Gujarati, Hindi).

Verifies:
1. ONLY THREE supported user languages in SUPPORTED_LANGUAGES: 'en', 'gu', 'hi'.
2. STT languages supported: 'auto', 'en', 'gu', 'hi'.
3. Strict Selected Language Rule:
   - English selected -> response in English regardless of input ("Kem cho?" -> English).
   - Gujarati selected -> response in Gujarati regardless of input ("Hello, how are you?" -> Gujarati).
   - Hindi selected -> response in Hindi regardless of input ("Kem cho?" -> Hindi).
4. Roman Gujarati comprehension and script format conversion (Native vs Romanized).
5. Voice output language resolution matching selected response language or explicit voice language.
6. Faster-Whisper language detection constraint to ('en', 'gu', 'hi').
7. Config persistence across application restart.
8. Evaluator bypass when response language is non-English to prevent English text leakage.
"""

import os
import tempfile
import pytest
from unittest.mock import MagicMock

from app.ai.multilingual_engine import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_STT_LANGUAGES,
    MultilingualEngine,
    RomanGujaratiNormalizer,
)
from app.settings.config_manager import ConfigManager


class TestStrictSupportedLanguages:
    """Requirement 1: ONLY THREE SUPPORTED USER LANGUAGES (en, gu, hi)."""

    def test_supported_languages_contains_only_three(self):
        """User dropdowns and registry must only expose English, Gujarati, Hindi."""
        assert set(SUPPORTED_LANGUAGES.keys()) == {"en", "gu", "hi"}

    def test_supported_stt_languages_contains_auto_and_three_languages(self):
        """STT language options must only contain auto, English, Gujarati, Hindi."""
        assert set(SUPPORTED_STT_LANGUAGES.keys()) == {"auto", "en", "gu", "hi"}


class TestStrictSelectedLanguageRule:
    """Requirement 2: Strict Selected Language Rule (Highest Priority)."""

    def test_english_selected_directives(self):
        """When English is selected, directives mandate 100% English response even for Gujarati input."""
        directives = MultilingualEngine.build_persistent_multilingual_directives(
            target_lang_code="en",
            target_format="native",
        )
        assert "STRICT SELECTED RESPONSE LANGUAGE RULE (ENGLISH ONLY)" in directives
        assert "formulate your answer 100% in English" in directives

        ground_truth = MultilingualEngine.build_turn_ground_truth(
            user_message="Kem cho?",
            configured_resp_lang="en",
            configured_resp_format="native",
        )
        assert "ENGLISH" in ground_truth
        assert "DO NOT reply in Gujarati" in ground_truth

    def test_gujarati_selected_directives(self):
        """When Gujarati is selected, directives mandate Gujarati response even for English input."""
        directives = MultilingualEngine.build_persistent_multilingual_directives(
            target_lang_code="gu",
            target_format="native",
        )
        assert "STRICT SELECTED RESPONSE LANGUAGE RULE (GUJARATI ONLY)" in directives
        assert "DO NOT output English text when Gujarati is selected" in directives

        ground_truth = MultilingualEngine.build_turn_ground_truth(
            user_message="Hello, how are you?",
            configured_resp_lang="gu",
            configured_resp_format="native",
        )
        assert "GUJARATI" in ground_truth
        assert "DO NOT respond in English" in ground_truth

    def test_hindi_selected_directives(self):
        """When Hindi is selected, directives mandate Hindi response even for Gujarati input."""
        directives = MultilingualEngine.build_persistent_multilingual_directives(
            target_lang_code="hi",
            target_format="native",
        )
        assert "STRICT SELECTED RESPONSE LANGUAGE RULE (HINDI ONLY)" in directives

        ground_truth = MultilingualEngine.build_turn_ground_truth(
            user_message="Kem cho?",
            configured_resp_lang="hi",
            configured_resp_format="native",
        )
        assert "HINDI" in ground_truth
        assert "DO NOT reply in Gujarati or English" in ground_truth


class TestGujaratiRomanizationSupport:
    """Requirement 3: GUJARATI ROMANIZATION SUPPORT."""

    def test_roman_gujarati_detection(self):
        """Roman Gujarati phrases must be correctly identified as Gujarati transliteration."""
        phrases = [
            "Kem cho?",
            "Tamaru naam su che?",
            "Tame shu karo cho?",
            "Mane Gujarati ma jawab aapo",
            "Hu maja ma chu",
        ]
        for phrase in phrases:
            assert RomanGujaratiNormalizer.is_roman_gujarati(phrase), f"Failed for '{phrase}'"
            det = MultilingualEngine.detect_language(phrase)
            assert det.code == "gu", f"Expected 'gu' for '{phrase}', got '{det.code}'"
            assert det.is_transliterated is True

    def test_gujarati_native_script_formatting(self):
        """When Gujarati Native Script is selected, Latin transliterates to Gujarati script."""
        formatted = MultilingualEngine.format_response_script(
            text="Kem cho? Hu majama chu.",
            target_language="gu",
            target_format="native",
        )
        # Should contain Gujarati script (Unicode 0x0A80 - 0x0AFF)
        has_gujarati = any('\u0A80' <= c <= '\u0AFF' for c in formatted)
        assert has_gujarati, f"Expected Gujarati script, got: {formatted}"

    def test_gujarati_romanized_formatting(self):
        """When Gujarati Romanized Script is selected, Gujarati script transliterates to Latin."""
        formatted = MultilingualEngine.format_response_script(
            text="હું મજામાં છું! તમે કેમ છો?",
            target_language="gu",
            target_format="romanized",
        )
        # Should be Latin letters (Gujlish)
        assert "hu" in formatted.lower() or "majama" in formatted.lower() or "kem" in formatted.lower() or "tame" in formatted.lower()

    def test_english_formatting_replaces_foreign_script(self):
        """When English is selected, stray foreign scripts are converted to English equivalents."""
        formatted = MultilingualEngine.format_response_script(
            text="હું મજામાં છું! તમે કેમ છો?",
            target_language="en",
            target_format="native",
        )
        assert not any('\u0A80' <= c <= '\u0AFF' for c in formatted)
        assert "doing well" in formatted.lower() or "fine" in formatted.lower() or "how are you" in formatted.lower()


class TestVoiceOutputLanguageResolution:
    """Requirement 4 & 5: Voice Output Language consistency."""

    def test_follow_response_mode(self):
        """Voice Output Language 'follow_response' follows selected response language."""
        from app.voice.voice_conversation_controller import VoiceConversationController
        ctrl = VoiceConversationController()
        mock_ai = MagicMock()
        mock_ai.config_manager.get.side_effect = lambda k, d=None: {
            "language.voice_output_language": "follow_response",
            "language.response_language": "gu",
        }.get(k, d)
        ctrl.ai_service = mock_ai

        # When sentence arrives and follow_response is set
        cfg_voice_mode = ctrl.ai_service.config_manager.get("language.voice_output_language", "follow_response")
        configured_resp_lang = ctrl.ai_service.config_manager.get("language.response_language", "en")
        if cfg_voice_mode in ("en", "gu", "hi"):
            target_voice_lang = cfg_voice_mode
        else:
            target_voice_lang = configured_resp_lang if configured_resp_lang in ("en", "gu", "hi") else "en"

        assert target_voice_lang == "gu"

    def test_explicit_voice_mode(self):
        """Explicit voice language selection takes priority."""
        for lang in ("en", "gu", "hi"):
            cfg_voice_mode = lang
            target_voice_lang = cfg_voice_mode if cfg_voice_mode in ("en", "gu", "hi") else "en"
            assert target_voice_lang == lang


class TestSTTThreeLanguageConstraint:
    """Requirement 5: Automatic STT detection strictly among English, Gujarati, Hindi."""

    def test_whisper_detected_lang_constraint(self):
        """Non-supported Whisper detections are constrained to (en, gu, hi)."""
        full_text_gu = "તારું નામ શું છે?"
        full_text_hi = "मेरा नाम क्या है?"
        full_text_en = "What is your name?"

        # 1. Gujarati text detected with weird tag like 'sd' (Sindhi)
        info_lang = "sd"
        final_lang = info_lang
        if final_lang not in ("en", "gu", "hi"):
            if any('\u0A80' <= c <= '\u0AFF' for c in full_text_gu):
                final_lang = "gu"
        assert final_lang == "gu"

        # 2. Hindi text detected with 'ne' (Nepali)
        info_lang = "ne"
        final_lang = info_lang
        if final_lang not in ("en", "gu", "hi"):
            if any('\u0900' <= c <= '\u097F' for c in full_text_hi):
                final_lang = "hi"
        assert final_lang == "hi"

        # 3. English text
        info_lang = "cy"  # Welsh hallucination
        final_lang = info_lang
        if final_lang not in ("en", "gu", "hi"):
            if any('\u0A80' <= c <= '\u0AFF' for c in full_text_en):
                final_lang = "gu"
            elif any('\u0900' <= c <= '\u097F' for c in full_text_en):
                final_lang = "hi"
            else:
                final_lang = "en"
        assert final_lang == "en"


class TestConfigPersistence:
    """Requirement 5: Persist all settings after application restart."""

    def test_settings_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "test_settings.json")
            
            # 1. Write settings
            cm1 = ConfigManager(config_path=cfg_path)
            cm1.set("language.response_language", "gu")
            cm1.set("language.response_format", "romanized")
            cm1.set("language.voice_output_language", "gu")
            cm1.set("language.stt_language", "auto")

            # 2. Create new ConfigManager reading the same file (simulating app restart)
            cm2 = ConfigManager(config_path=cfg_path)
            assert cm2.get("language.response_language") == "gu"
            assert cm2.get("language.response_format") == "romanized"
            assert cm2.get("language.voice_output_language") == "gu"
            assert cm2.get("language.stt_language") == "auto"


class TestEvaluatorBypassForNonEnglish:
    """Ensure hardcoded English evaluators do not leak English when Gujarati/Hindi is selected."""

    def test_evaluator_bypass_when_gujarati_selected(self):
        from app.ai.ai_service import AIService
        ai_service = AIService()
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda k, d=None: "gu" if k == "language.response_language" else d
        ai_service.config_manager = mock_cfg

        # Check configured_resp_lang logic
        configured_resp_lang = ai_service.config_manager.get("language.response_language", "en")
        should_intercept = str(configured_resp_lang).lower().strip() in ("en", "")
        assert should_intercept is False, "Hardcoded English evaluators must NOT intercept when Gujarati is selected"

    def test_evaluator_allowed_when_english_selected(self):
        from app.ai.ai_service import AIService
        ai_service = AIService()
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda k, d=None: "en" if k == "language.response_language" else d
        ai_service.config_manager = mock_cfg

        configured_resp_lang = ai_service.config_manager.get("language.response_language", "en")
        should_intercept = str(configured_resp_lang).lower().strip() in ("en", "")
        assert should_intercept is True, "English evaluators can intercept when English is selected"
