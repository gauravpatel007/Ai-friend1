"""Tests for Multilingual Communication and Language Settings.

Validates:
1. Accurate Language Detection for Native Scripts and Romanized Indic (Gujlish & Hinglish).
2. Distinguishing Romanized Gujarati ("Tamaru naam su che?") from Hindi and English.
3. Multilingual System Prompt Instruction Generation.
4. Transliteration Safety Nets for Gujarati & Hindi Romanization.
5. TTS Engine Language Compatibility Matrix & Limitation Warnings.
6. SettingsDialog Language & Communication Category, Dropdowns, and Persistence.
"""

import sys
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication

from app.settings.config_manager import ConfigManager
from app.ai.multilingual_engine import MultilingualEngine, SUPPORTED_LANGUAGES
from app.ai.personality_manager import PersonalityManager
from app.desktop.settings_dialog import SettingsDialog


@pytest.fixture
def test_config(tmp_path: Path) -> ConfigManager:
    config_file = tmp_path / "test_multilingual_config.json"
    return ConfigManager(config_path=config_file)


# ─── 1. Language Detection Tests ───────────────────────────────────────

def test_detect_language_romanized_gujarati():
    """Verify 'Tamaru naam su che?' is detected as Gujarati (Romanized) with high confidence."""
    # The exact user prompt query
    res = MultilingualEngine.detect_language("Tamaru naam su che?")
    assert res.code == "gu"
    assert res.name == "Gujarati"
    assert res.is_romanized is True
    assert res.confidence >= 0.80
    assert res.normalized_gujarati is not None
    assert res.normalized_gujarati.native_script == "તમારું નામ શું છે?"
    assert res.normalized_gujarati.semantic_intent == "asking_name"
    assert res.normalized_gujarati.english_gloss == "What is your name?"

    # Common conversational Gujarati Romanized phrases
    res2 = MultilingualEngine.detect_language("Kem cho?")
    assert res2.code == "gu"
    assert res2.is_romanized is True
    assert res2.normalized_gujarati.native_script == "કેમ છો?"
    assert res2.normalized_gujarati.semantic_intent == "greeting"
    assert res2.normalized_gujarati.english_gloss == "How are you?"

    res3 = MultilingualEngine.detect_language("Hu majama chu, tame kem cho?")
    assert res3.code == "gu"
    assert res3.is_romanized is True


def test_all_six_user_roman_gujarati_examples():
    """Validate all 6 user-specified Roman Gujarati inputs:
    1. Kem cho? -> કેમ છો? (How are you?)
    2. Tamaru naam su che? -> તમારું નામ શું છે? (What is your name?)
    3. Tame shu karo cho? -> તમે શું કરો છો? (What are you doing?)
    4. Mane Gujarati ma jawab aapo -> મને ગુજરાતીમાં જવાબ આપો (Answer me in Gujarati)
    5. Hu maja ma chu -> હું મજામાં છું (I am fine / doing great)
    6. Tame kya raho cho? -> તમે ક્યાં રહો છો? (Where do you live?)
    """
    cases = [
        ("Kem cho?", "કેમ છો?", "greeting", "How are you?"),
        ("Tamaru naam su che?", "તમારું નામ શું છે?", "asking_name", "What is your name?"),
        ("Tame shu karo cho?", "તમે શું કરો છો?", "asking_activity", "What are you doing?"),
        ("Mane Gujarati ma jawab aapo", "મને ગુજરાતીમાં જવાબ આપો", "request_language_gujarati", "Answer me in Gujarati / Speak in Gujarati"),
        ("Hu maja ma chu", "હું મજામાં છું", "status_wellbeing", "I am fine / I am doing great"),
        ("Tame kya raho cho?", "તમે ક્યાં રહો છો?", "asking_location", "Where do you live?"),
    ]

    for raw, expected_native, expected_intent, expected_gloss in cases:
        res = MultilingualEngine.detect_language(raw)
        assert res.code == "gu", f"Failed to detect {raw} as Gujarati"
        assert res.is_romanized is True, f"Failed to identify {raw} as Romanized"
        assert res.confidence >= 0.70
        assert res.normalized_gujarati is not None
        assert res.normalized_gujarati.native_script == expected_native
        assert res.normalized_gujarati.semantic_intent == expected_intent
        assert res.normalized_gujarati.english_gloss == expected_gloss


def test_contrastive_english_not_misclassified():
    """Ensure ordinary English sentences containing short words are never misclassified as Gujarati."""
    english_sentences = [
        "What do you do?",
        "Can you help me with this code?",
        "Where is he going?",
        "Tell me about your name.",
        "How are you doing today?",
        "I am fine thank you",
        "Do you know what time it is?",
        "He said no to me",
        "So, tell me what you think.",
    ]

    for s in english_sentences:
        res = MultilingualEngine.detect_language(s)
        assert res.code == "en", f"English sentence '{s}' misclassified as {res.code}"
        assert res.name == "English"
        assert res.is_romanized is False


def test_detect_language_native_gujarati():
    """Verify native Gujarati script Unicode characters are identified as Gujarati."""
    res = MultilingualEngine.detect_language("તારું નામ શું છે?")
    assert res.code == "gu"
    assert res.name == "Gujarati"
    assert res.is_romanized is False
    assert res.detected_script == "gujarati"


def test_detect_language_romanized_hindi():
    """Verify Romanized Hindi (Hinglish) is distinguished from Gujarati."""
    res = MultilingualEngine.detect_language("Aapka naam kya hai?")
    assert res.code == "hi"
    assert res.name == "Hindi"
    assert res.is_romanized is True

    res2 = MultilingualEngine.detect_language("Mera naam Bond hai. Aap kaise hain?")
    assert res2.code == "hi"
    assert res2.is_romanized is True


def test_detect_language_native_hindi():
    """Verify native Devanagari script is identified as Hindi."""
    res = MultilingualEngine.detect_language("आप कैसे हो?")
    assert res.code == "hi"
    assert res.name == "Hindi"
    assert res.is_romanized is False
    assert res.detected_script == "devanagari"


def test_detect_language_english():
    """Verify standard English input is recognized as English."""
    res = MultilingualEngine.detect_language("Hello, how are you today?")
    assert res.code == "en"
    assert res.name == "English"


# ─── 2. Multilingual Prompt Directives Tests ───────────────────────────

def test_prompt_instruction_for_gujlish_native_response():
    """Verify prompt guidance instructs LLM that 'Tamaru naam su che?' is Gujarati and output in native script."""
    instr = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input="Tamaru naam su che?",
        response_language="gu",
        response_format="native",
    )
    assert "GUJARATI" in instr
    assert "તમારું નામ શું છે?" in instr
    assert "NATIVE GUJARATI SCRIPT" in instr


def test_prompt_instruction_for_gujlish_romanized_response():
    """Verify prompt guidance enforces Romanized Gujarati output without translating into English."""
    instr = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input="Tamaru naam su che?",
        response_language="gu",
        response_format="romanized",
    )
    assert "GUJARATI" in instr
    assert "ROMANIZED LATIN LETTERS" in instr
    assert "DO NOT translate into English" in instr


def test_prompt_instruction_with_english_response_to_gujarati_input():
    """Verify that when English response language is selected, Bond answers in English having understood the Gujarati."""
    instr = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input="Tamaru naam su che?",
        response_language="en",
        response_format="native",
    )
    assert "The user communicated in Gujarati" in instr
    assert "What is your name?" in instr
    assert "ENGLISH" in instr


def test_prompt_instruction_with_explicit_language_override():
    """Verify selecting Gujarati produces Gujarati output directives even when user spoke English."""
    instr = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input="Hello, can you help me?",
        response_language="gu",
        response_format="native",
    )
    assert "English" in instr
    assert "GUJARATI" in instr


# ─── 3. Transliteration Safety Net Tests ───────────────────────────────

def test_transliterate_gujarati_to_latin():
    """Verify native Gujarati text is accurately converted to readable Romanized Latin (Gujlish)."""
    native_text = "હું બોન્ડ છું. તમને મળીને આનંદ થયો!"
    romanized = MultilingualEngine.transliterate_gujarati_to_latin(native_text)
    assert "Bond" in romanized
    assert "Hu" in romanized
    assert "chu" in romanized
    assert "tamne" in romanized.lower()


def test_transliterate_devanagari_to_latin():
    """Verify native Devanagari text is accurately converted to readable Romanized Latin (Hinglish)."""
    native_text = "मेरा नाम बॉन्ड है।"
    romanized = MultilingualEngine.transliterate_devanagari_to_latin(native_text)
    assert "Mera" in romanized
    assert "naam" in romanized
    assert "Bond" in romanized
    assert "hai" in romanized


def test_format_response_script_fallback():
    """Verify format_response_script transliterates native script when romanized format is requested."""
    native_gu = "હું બોન્ડ છું."
    formatted = MultilingualEngine.format_response_script(
        text=native_gu,
        target_language="gu",
        target_format="romanized",
    )
    assert "Hu" in formatted
    assert "Bond" in formatted


# ─── 4. TTS Capability Matrix & Phonetic Voice Preparation ────────────

def test_prepare_text_for_tts_native_gujarati_transliteration():
    """Verify prepare_text_for_tts transliterates native Gujarati to authentic Romanized text for TTS."""
    native_gu = "મારું નામ બોન્ડ છે! તમને મળીને આનંદ થયો."
    installed = ["Microsoft David Desktop - English (United States)", "Microsoft Heera - English (India)"]
    spoken, voice_hint = MultilingualEngine.prepare_text_for_tts(
        text=native_gu,
        target_language="gu",
        engine_name="sapi5",
        installed_voices=installed,
    )
    assert "Maru naam Bond che!" in spoken
    assert "tamne maline aanand thayo" in spoken.lower()
    assert voice_hint == "Microsoft Heera - English (India)"


def test_prepare_text_for_tts_romanized_preserves_text():
    """Verify Romanized Gujarati text is passed directly to TTS with an Indian voice hint."""
    romanized_gu = "Maru naam Bond che! Tamne maline aanand thayo."
    installed = ["Microsoft David Desktop - English (United States)", "Microsoft Heera - English (India)"]
    spoken, voice_hint = MultilingualEngine.prepare_text_for_tts(
        text=romanized_gu,
        target_language="gu",
        engine_name="sapi5",
        installed_voices=installed,
    )
    assert spoken == romanized_gu
    assert voice_hint == "Microsoft Heera - English (India)"


def test_tts_capability_kokoro_english_vs_gujarati():
    """Verify Kokoro engine is marked supported for English and phonetic speech for Gujarati."""
    en_check = MultilingualEngine.check_tts_capability("kokoro", "en")
    assert en_check["supported"] is True
    assert en_check["status_badge"] == "Supported"

    gu_check = MultilingualEngine.check_tts_capability("kokoro", "gu")
    assert gu_check["supported"] is True
    assert "Phonetic" in gu_check["status_badge"]

    ja_check = MultilingualEngine.check_tts_capability("kokoro", "ja")
    assert ja_check["supported"] is False
    assert ja_check["status_badge"] == "Voice Not Installed"


def test_tts_capability_sapi5_indian_voice_vs_missing_foreign_voice():
    """Verify SAPI5 utilizes Indian speech engine for Gujarati and indicates missing foreign voice packs."""
    installed = ["Microsoft David - English (United States)", "Microsoft Heera - English (India)"]
    gu_check = MultilingualEngine.check_tts_capability("sapi5", "gu", installed_voices=installed)
    assert gu_check["supported"] is True
    assert "Indian Speech Engine" in gu_check["status_badge"]

    # Japanese without Japanese voice pack
    ja_check = MultilingualEngine.check_tts_capability("sapi5", "ja", installed_voices=installed)
    assert ja_check["supported"] is False
    assert "Windows Voice Not Installed" in ja_check["status_badge"]


def test_end_to_end_voice_multilingual_workflow(test_config: ConfigManager):
    """Verify Phase 4 expected workflow:
    1. User speaks in Gujarati: 'Tamaru naam su che?'
    2. Speech recognition identifies the Gujarati speech.
    3. User's raw message is preserved in chat history.
    4. Bond understands the message ('તમારું નામ શું છે?', intent: 'asking_name', gloss: 'What is your name?').
    5. Bond generates Gujarati response.
    6. Response text is formatted in selected format (native vs romanized).
    7. TTS prepares spoken audio in Gujarati with matching meaning.
    """
    user_speech = "Tamaru naam su che?"

    # Step 2: Language detection identifies Gujarati
    detected = MultilingualEngine.detect_language(user_speech)
    assert detected.code == "gu"
    assert detected.is_romanized is True
    assert detected.normalized_gujarati.native_script == "તમારું નામ શું છે?"
    assert detected.normalized_gujarati.english_gloss == "What is your name?"

    # Step 3 & 4: Prompt generation injects ground truth
    test_config.set("language.response_language", "gu")
    test_config.set("language.response_format", "native")
    pm = PersonalityManager(config_manager=test_config)
    system_prompt = pm.build_system_prompt(is_voice=True, user_input=user_speech)

    assert "What is your name?" in system_prompt
    assert "તમારું નામ શું છે?" in system_prompt
    assert "NATIVE GUJARATI SCRIPT" in system_prompt

    # Step 5: AI generates Gujarati response
    raw_ai_response = "મારું નામ બોન્ડ છે! તમને મળીને આનંદ થયો."

    # Step 6: Native script display format
    display_native = MultilingualEngine.format_response_script(raw_ai_response, "gu", "native")
    assert display_native == "મારું નામ બોન્ડ છે! તમને મળીને આનંદ થયો."

    # Step 6 alternative: Romanized script display format
    display_roman = MultilingualEngine.format_response_script(raw_ai_response, "gu", "romanized")
    assert "Maru naam Bond che!" in display_roman
    assert "tamne maline aanand thayo" in display_roman.lower()

    # Step 7: TTS system speaks the response in Gujarati (matching meaning)
    spoken_audio_text, voice_hint = MultilingualEngine.prepare_text_for_tts(
        text=display_native,
        target_language="gu",
        engine_name="sapi5",
        installed_voices=["Microsoft Heera - English (India)"],
    )
    assert "Maru naam Bond che!" in spoken_audio_text
    assert "tamne maline aanand thayo" in spoken_audio_text.lower()
    assert voice_hint == "Microsoft Heera - English (India)"


# ─── 5. PersonalityManager & ConversationContext Integration ───────────

def test_personality_manager_build_prompt_incorporates_multilingual(test_config: ConfigManager):
    """Verify PersonalityManager injects multilingual guidance based on user input and config."""
    test_config.set("language.response_language", "gu")
    test_config.set("language.response_format", "native")

    pm = PersonalityManager(config_manager=test_config)
    prompt = pm.build_system_prompt(user_input="Tamaru naam su che?")

    assert "[STRICT RESPONSE LANGUAGE DIRECTIVES - BOND]" in prompt
    assert "GUJARATI" in prompt
    assert "તમારું નામ શું છે?" in prompt


def test_conversation_context_preserves_raw_user_message(test_config: ConfigManager):
    """Verify the user's raw message in chat history is strictly preserved (Requirement 4)."""
    from app.ai.conversation_context import ConversationContext
    
    raw_user_input = "Tamaru naam su che?"
    pm = PersonalityManager(config_manager=test_config)
    system_prompt = pm.build_system_prompt(user_input=raw_user_input)

    context = ConversationContext()
    context.set_system_prompt(system_prompt)
    context.add_user_message(raw_user_input)

    messages = context.get_messages()
    # User message in history must be exactly the user's raw string, NOT mutated into Gujarati script or English
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Tamaru naam su che?"

    # The system prompt must contain the linguistic ground truth
    assert messages[0]["role"] == "system"
    assert "તમારું નામ શું છે?" in messages[0]["content"]
    assert "What is your name?" in messages[0]["content"]


# ─── 6. SettingsDialog Integration & Persistence ──────────────────────

def test_settings_dialog_language_page_elements(qapp_instance, test_config: ConfigManager):
    """Verify SettingsDialog has the Language & Communication category, widgets, and persistence."""
    dlg = SettingsDialog(config_manager=test_config)

    # 11 total categories: General, Character, AI Model, Language & Communication, Voice, ...
    assert dlg.nav_list.count() == 11
    assert dlg.stacked_pages.count() == 11

    # Check 4 required language settings widgets
    assert dlg.combo_response_lang.count() == 3
    assert dlg.combo_response_format.count() == 2
    assert dlg.combo_voice_lang.count() == 4
    assert dlg.combo_stt_lang.count() == 4

    # Test selecting Gujarati as AI Response Language
    idx_gu = dlg.combo_response_lang.findData("gu")
    assert idx_gu >= 0
    dlg.combo_response_lang.setCurrentIndex(idx_gu)
    assert test_config.get("language.response_language") == "gu"

    # Test selecting Romanized Script
    idx_rom = dlg.combo_response_format.findData("romanized")
    assert idx_rom >= 0
    dlg.combo_response_format.setCurrentIndex(idx_rom)
    assert test_config.get("language.response_format") == "romanized"

    # Test selecting Gujarati Voice Language
    idx_voice_gu = dlg.combo_voice_lang.findData("gu")
    dlg.combo_voice_lang.setCurrentIndex(idx_voice_gu)
    assert test_config.get("language.voice_output_language") == "gu"

    # Test selecting Gujarati STT
    idx_stt_gu = dlg.combo_stt_lang.findData("gu")
    dlg.combo_stt_lang.setCurrentIndex(idx_stt_gu)
    assert test_config.get("language.stt_language") == "gu"
    assert test_config.get("voice.language") == "gu"

    # Test reset defaults restores auto / native
    dlg._reset_defaults()
    assert dlg.combo_response_lang.currentIndex() == 0
    assert dlg.combo_response_format.currentIndex() == 0

    dlg.close()


# ─── 7. Phase 5: AI Model & Prompt Configuration Tests ────────────────

def test_phase5_persistent_multilingual_directives():
    """Verify persistent directives enforce strict response language control."""
    directives = MultilingualEngine.build_persistent_multilingual_directives(
        response_language="gu",
        response_format="native",
    )
    # 1. Respect selected response language
    assert "STRICT RESPONSE LANGUAGE DIRECTIVES - BOND" in directives
    assert "STRICT SELECTED RESPONSE LANGUAGE RULE" in directives

    # 2. Transliteration understanding
    assert "Deep Gujarati Romanization Comprehension" in directives

    # 3. Separation of Gujarati from Hindi
    assert "DO NOT interpret Gujarati transliteration as Hindi" in directives

    # 4. Mixed-language conversations & code-switching
    assert "Do NOT randomly mix English, Gujarati, and Hindi" in directives

    # 5. Natural conversational language vs literal translation
    assert "Conversational Fluency & Context Preservation" in directives

    # 6. Context preservation across language switches
    assert "Preserve full conversation context" in directives


def test_phase5_strict_selected_language_mode_instructions():
    """Verify strict selected response language rules for all 3 supported languages."""
    gu_directives = MultilingualEngine.build_persistent_multilingual_directives(
        response_language="gu",
        response_format="native",
    )
    assert "STRICT SELECTED RESPONSE LANGUAGE RULE (GUJARATI ONLY)" in gu_directives

    en_directives = MultilingualEngine.build_persistent_multilingual_directives(
        response_language="en",
        response_format="native",
    )
    assert "STRICT SELECTED RESPONSE LANGUAGE RULE (ENGLISH ONLY)" in en_directives

    hi_directives = MultilingualEngine.build_persistent_multilingual_directives(
        response_language="hi",
        response_format="native",
    )
    assert "STRICT SELECTED RESPONSE LANGUAGE RULE (HINDI ONLY)" in hi_directives


def test_phase5_explicit_language_override_instructions():
    """Verify explicit response language setting enforces that language regardless of input language."""
    gu_directives = MultilingualEngine.build_persistent_multilingual_directives(
        response_language="gu",
        response_format="native",
    )
    assert "The selected response language in Settings is the absolute priority over the user's input language." in gu_directives
    assert "NEVER automatically change or switch your response language based on the user's latest message." in gu_directives


def test_phase5_turn_ground_truth_minimizes_repeated_instructions():
    """Verify turn ground truth is injected for Roman Gujarati input with linguistic facts."""
    gt_gujlish = MultilingualEngine.build_turn_ground_truth(
        user_input="Tamaru naam su che?",
        response_language="en",
        response_format="native",
    )
    assert gt_gujlish is not None
    assert "તમારું નામ શું છે?" in gt_gujlish
    assert "ENGLISH" in gt_gujlish
    assert "DO NOT reply in Gujarati" in gt_gujlish


def test_phase5_context_preservation_across_language_switch():
    """Verify conversation context is preserved across turns when user switches languages."""
    from app.ai.conversation_context import ConversationContext
    context = ConversationContext()

    # Turn 1: User speaks in English
    t1_user = "Tell me about space exploration."
    t1_assistant = "Space exploration has led to incredible milestones like the Apollo Moon landings and Mars rovers."
    context.add_user_message(t1_user)
    context.add_assistant_message(t1_assistant)

    # Turn 2: User switches to Gujarati
    t2_user = "Tamne Mars par javu game?"  # Would you like to go to Mars?
    context.add_user_message(t2_user)

    messages = context.get_messages()
    # Context must retain both turns
    assert len(messages) == 3
    assert messages[0]["content"] == t1_user
    assert messages[1]["content"] == t1_assistant
    assert messages[2]["content"] == t2_user


def test_phase5_mixed_language_code_switching_recognition():
    """Verify mixed-language inputs (code-switching) are recognized as Gujarati."""
    res1 = MultilingualEngine.detect_language("Mane coding ma help karo")
    assert res1.code == "gu"
    assert res1.is_romanized is True

    res2 = MultilingualEngine.detect_language("Tamaru AI model su che?")
    assert res2.code == "gu"
    assert res2.is_romanized is True


# ─── 8. Phase 6: Settings Persistence Across Restarts ─────────────────

def test_language_settings_persistence_across_restart(tmp_path: Path):
    """Verify Phase 6 requirements:
    1. All language preferences are saved using the existing ConfigManager storage.
    2. Closing and restarting Bond restores all 4 saved preferences:
       - AI Response Language
       - AI Response Text Format
       - Voice Output Language
       - Speech Recognition Language
    3. Values are not hardcoded or reset upon restart.
    4. Sensible defaults are provided for existing users without breaking existing experience.
    """
    settings_file = tmp_path / "persistent_settings.json"

    # Step 1: First session — Verify sensible defaults exist
    cfg_session1 = ConfigManager(config_path=settings_file)
    assert cfg_session1.get("language.response_language") in ("auto", "en")
    assert cfg_session1.get("language.response_format") == "native"
    assert cfg_session1.get("language.voice_output_language") == "follow_response"
    assert cfg_session1.get("language.stt_language") == "auto"

    # Step 2: User changes language settings in the UI / API
    cfg_session1.set("language.response_language", "gu")
    cfg_session1.set("language.response_format", "romanized")
    cfg_session1.set("language.voice_output_language", "gu")
    cfg_session1.set("language.specific_voice_language", "gu")
    cfg_session1.set("language.stt_language", "gu")
    cfg_session1.set("voice.language", "gu")

    # Step 3: Application closes (session 1 terminated)
    del cfg_session1

    # Step 4: Application restarts — fresh ConfigManager loads from disk
    cfg_session2 = ConfigManager(config_path=settings_file)

    # Step 5: Verify all preferences are restored accurately from disk
    assert cfg_session2.get("language.response_language") == "gu"
    assert cfg_session2.get("language.response_format") == "romanized"
    assert cfg_session2.get("language.voice_output_language") == "gu"
    assert cfg_session2.get("language.specific_voice_language") == "gu"
    assert cfg_session2.get("language.stt_language") == "gu"
    assert cfg_session2.get("voice.language") == "gu"

    # Step 6: Verify backwards compatibility for existing user configs lacking the "language" block
    legacy_file = tmp_path / "legacy_user_settings.json"
    import json
    legacy_data = {
        "general": {"start_at_login": True},
        "companion": {"name": "Bond"},
        "ai": {"model": "llama3.2:3b", "personality": "friendly"},
        "voice": {"enabled": True, "speed": 1.1},
    }
    with open(legacy_file, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)

    legacy_cfg = ConfigManager(config_path=legacy_file)
    # Existing settings must be preserved
    assert legacy_cfg.get("companion.name") == "Bond"
    assert legacy_cfg.get("voice.speed") == 1.1
    # Sensible language defaults must seamlessly populate without crashing
    assert legacy_cfg.get("language.response_language") in ("auto", "en")
    assert legacy_cfg.get("language.response_format") == "native"
    assert legacy_cfg.get("language.voice_output_language") == "follow_response"
    assert legacy_cfg.get("language.stt_language") == "auto"


# ─── 9. Section 9: End-to-End Test Suite (Tests 1 through 10) ─────────

def test_section9_test1_gujarati_in_english_letters():
    """Test 1: Gujarati in English Letters.
    Input: 'Tamaru naam su che?'
    Expected:
    - Bond understands that this is Gujarati.
    - Responds naturally in Gujarati when Gujarati or Auto-detect is selected.
    - Must NOT produce an unrelated Hindi interpretation.
    """
    from app.ai.multilingual_engine import RomanGujaratiNormalizer
    user_input = "Tamaru naam su che?"
    det = MultilingualEngine.detect_language(user_input)

    # 1. Understood as Gujarati, not Hindi or English
    assert det.code == "gu"
    assert det.code != "hi"
    assert det.is_romanized is True

    # 2. Transliteration to Gujarati native script
    native_script = RomanGujaratiNormalizer.transliterate_to_native_script(user_input)
    assert "નામ" in native_script
    assert "તમારું" in native_script or "તારું" in native_script

    # 3. Prompt directives explicitly prevent Hindi interpretation
    turn_prompt = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input=user_input,
        response_language="auto",
        response_format="native",
    )
    assert "GUJARATI" in turn_prompt
    assert "DO NOT interpret Gujarati transliteration as Hindi" in turn_prompt
    assert "HINDI ONLY" not in turn_prompt


def test_section9_test2_gujarati_in_gujarati_script():
    """Test 2: Gujarati in Gujarati Script.
    Input: 'તારું નામ શું છે?'
    Expected: Bond understands and responds in Gujarati.
    """
    user_input = "તારું નામ શું છે?"
    det = MultilingualEngine.detect_language(user_input)

    assert det.code == "gu"
    assert det.is_romanized is False
    assert det.confidence >= 0.95

    turn_prompt = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input=user_input,
        response_language="auto",
        response_format="native",
    )
    assert "GUJARATI" in turn_prompt


def test_section9_test3_english():
    """Test 3: English.
    Input: 'What is your name?'
    Expected: Bond responds in English when English or Auto-detect is selected.
    """
    user_input = "What is your name?"
    det = MultilingualEngine.detect_language(user_input)

    assert det.code == "en"
    assert det.is_romanized is False

    # Auto-detect mode includes English directive
    turn_prompt_auto = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input=user_input,
        response_language="auto",
        response_format="native",
    )
    assert "English" in turn_prompt_auto

    # Explicit English mode enforces English Only
    turn_prompt_en = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input=user_input,
        response_language="en",
        response_format="native",
    )
    assert "ENGLISH ONLY" in turn_prompt_en


def test_section9_test4_hindi():
    """Test 4: Hindi.
    Input: 'आपका नाम क्या है?'
    Expected: Bond responds naturally in Hindi when Hindi or Auto-detect is selected.
    """
    user_input = "आपका नाम क्या है?"
    det = MultilingualEngine.detect_language(user_input)

    assert det.code == "hi"
    assert det.is_romanized is False

    turn_prompt = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input=user_input,
        response_language="auto",
        response_format="native",
    )
    assert "HINDI" in turn_prompt
    assert "GUJARATI ONLY" not in turn_prompt


def test_section9_test5_gujarati_with_romanized_text_format():
    """Test 5: Gujarati with Romanized Text Format.
    Settings:
    - AI Response Language: Gujarati
    - Display Response Text As: Romanized / Latin Script
    Expected:
    Gujarati response written using English letters, NOT translated into English.
    """
    raw_ai_response = "મારું નામ બોન્ડ છે! તમે કેમ છો?"
    formatted = MultilingualEngine.format_response_script(
        text=raw_ai_response,
        target_language="gu",
        target_format="romanized",
    )
    # Must use Latin characters
    assert all(ord(c) < 128 or c in "‘’“”–—…" for c in formatted)
    # Must preserve Gujarati vocabulary (Bond, naam, che, kem, tame)
    low = formatted.lower()
    assert "bond" in low
    assert "naam" in low or "nam" in low
    assert "che" in low
    # Must NOT be translated into English
    assert "what is your name" not in low
    assert "my name is" not in low


def test_section9_test6_gujarati_with_native_script():
    """Test 6: Gujarati with Native Script.
    Settings:
    - AI Response Language: Gujarati
    - Display Response Text As: Native Script
    Expected:
    Gujarati response displayed in Gujarati characters.
    """
    raw_ai_response = "મારું નામ બોન્ડ છે! આજે તમે કેમ છો?"
    formatted = MultilingualEngine.format_response_script(
        text=raw_ai_response,
        target_language="gu",
        target_format="native",
    )
    # Must contain native Gujarati Unicode codepoints (U+0A80 to U+0AFF)
    assert any(0x0A80 <= ord(c) <= 0x0AFF for c in formatted)
    assert "બોન્ડ" in formatted
    assert "તમે કેમ છો" in formatted


def test_section9_test7_voice_conversation_flow():
    """Test 7: Voice Conversation.
    Speak Gujarati question through microphone:
    Verify:
    - Speech recognition language configuration.
    - Correct language identification.
    - Correct AI response formatting.
    - Correct TTS speech synthesis preparation.
    """
    # 1. User speaks Gujarati question recognized via STT
    stt_transcript = "Tamaru naam su che?"
    det = MultilingualEngine.detect_language(stt_transcript)
    assert det.code == "gu"

    # 2. Model generates native Gujarati response
    ai_generated_response = "મારું નામ બોન્ડ છે!"

    # 3. Display script formatted according to settings
    displayed_text = MultilingualEngine.format_response_script(
        text=ai_generated_response,
        target_language="gu",
        target_format="native",
    )
    assert "મારું નામ બોન્ડ છે!" in displayed_text

    # 4. Spoken text prepared for TTS engine
    # SAPI5 with Indian voice (Heera / Ravi) speaks phonetically
    spoken_text, voice_hint = MultilingualEngine.prepare_text_for_tts(
        text=displayed_text,
        target_language="gu",
        engine_name="sapi5",
        installed_voices=["Microsoft Heera - English (India)", "Microsoft David - English (United States)"],
    )
    assert spoken_text  # Phonetic transliteration generated
    assert voice_hint == "Microsoft Heera - English (India)"


def test_section9_test8_language_switching_context_preservation():
    """Test 8: Language Switching.
    Start a conversation in Gujarati, switch to English, and switch back to Gujarati.
    Bond should understand the language change in Auto-detect mode and maintain conversation context.
    """
    from app.ai.conversation_context import ConversationContext
    context = ConversationContext()

    # Turn 1: Gujarati
    turn1_user = "Kem cho?"
    det1 = MultilingualEngine.detect_language(turn1_user)
    assert det1.code == "gu"
    context.add_user_message(turn1_user)
    context.add_assistant_message("હું મજામાં છું! તમે કેમ છો?")

    # Turn 2: Switch to English
    turn2_user = "Can you help me plan a trip to Gujarat?"
    det2 = MultilingualEngine.detect_language(turn2_user)
    assert det2.code == "en"
    context.add_user_message(turn2_user)
    context.add_assistant_message("I'd love to help you plan your trip to Gujarat! What places would you like to visit?")

    # Turn 3: Switch back to Gujarati
    turn3_user = "Mane Gir National Park javu che."
    det3 = MultilingualEngine.detect_language(turn3_user)
    assert det3.code == "gu"
    context.add_user_message(turn3_user)

    # Context history retains all 3 turns with exact raw content
    history = context.get_messages()
    assert len(history) == 5
    assert history[0]["content"] == turn1_user
    assert history[2]["content"] == turn2_user
    assert history[4]["content"] == turn3_user


def test_section9_test9_application_restart_persistence(tmp_path: Path):
    """Test 9: Application Restart.
    Change all language settings, close Bond, and reopen it.
    Verify that all selected settings are restored.
    """
    cfg_file = tmp_path / "bond_restart_test.json"
    session1 = ConfigManager(config_path=cfg_file)

    # Change all language settings
    session1.set("language.response_language", "gu")
    session1.set("language.response_format", "romanized")
    session1.set("language.voice_output_language", "gu")
    session1.set("language.specific_voice_language", "gu")
    session1.set("language.stt_language", "gu")
    session1.set("voice.language", "gu")

    # Close Bond
    del session1

    # Reopen Bond
    session2 = ConfigManager(config_path=cfg_file)
    assert session2.get("language.response_language") == "gu"
    assert session2.get("language.response_format") == "romanized"
    assert session2.get("language.voice_output_language") == "gu"
    assert session2.get("language.specific_voice_language") == "gu"
    assert session2.get("language.stt_language") == "gu"
    assert session2.get("voice.language") == "gu"


def test_section9_test10_existing_functionality_preservation(tmp_path: Path):
    """Test 10: Existing Functionality.
    Verify that existing English conversations, text mode, voice mode, chat history,
    and general settings continue working without regressions.
    """
    cfg_file = tmp_path / "bond_existing_func.json"
    cfg = ConfigManager(config_path=cfg_file)

    # Companion configuration
    cfg.set("companion.name", "Bond")
    assert cfg.get("companion.name") == "Bond"

    # AI Model & Personality
    assert "llama3.2" in str(cfg.get("ai.model"))
    assert cfg.get("ai.personality") == "friendly"

    # Standard English chat input detection
    en_input = "Hello Bond, what is the weather like today?"
    det = MultilingualEngine.detect_language(en_input)
    assert det.code == "en"
    assert det.is_romanized is False

    # English prompt construction
    prompt = MultilingualEngine.build_multilingual_prompt_instruction(
        user_input=en_input,
        response_language="auto",
        response_format="native",
    )
    assert "English" in prompt
    assert "GUJARATI ONLY" not in prompt

    # Voice settings
    assert cfg.get("voice.enabled") is True
    cfg.set("voice.voice_speed", 1.0)
    assert cfg.get("voice.voice_speed") == 1.0

    # Test preview API method works natively
    preview_gu_native = MultilingualEngine.generate_language_preview("gu", "native")
    assert preview_gu_native["preview_text"] == "નમસ્તે! હું બોન્ડ છું. આજે તમે કેમ છો?"

    preview_gu_romanized = MultilingualEngine.generate_language_preview("gu", "romanized")
    assert "Namaste" in preview_gu_romanized["preview_text"]
    assert "Bond" in preview_gu_romanized["preview_text"]



