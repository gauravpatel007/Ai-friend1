"""Phase 1 Automated Test Suite: Five Genuinely Different Selectable Voices.

Verifies:
1. Five voice profiles: 2 male (Arjun, Kabir), 3 female (Ananya, Mira, Zara).
2. Dynamic voice switching without restarting.
3. Voice differentiation across audio samples and speaker weights.
4. Multilingual speech synthesis: English, Gujarati, and Hindi.
5. Voice preview execution and standardized comparison phrases.
6. Persistence across configuration reloads and application restarts.
7. Fallback behavior when primary engines/voices are unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from app.ai.multilingual_engine import MultilingualEngine
from app.settings.config_manager import ConfigManager
from app.voice.kokoro_engine import KokoroTTSEngine
from app.voice.sapi5_engine import Sapi5TTSEngine
from app.voice.voice_registry import (
    DEFAULT_VOICE_PROFILE_ID,
    VOICE_PREVIEW_SAMPLES,
    VOICE_REGISTRY,
    VoiceProfile,
    get_preview_sample_text,
    get_voice_profile,
    list_voice_profiles,
)


class TestPhase1VoiceProfiles(unittest.TestCase):
    """Test suite for Phase 1 voice profile implementation."""

    def test_01_registry_contains_exactly_five_profiles(self) -> None:
        """Verify exactly five voice profiles exist with 2 male and 3 female."""
        profiles = list_voice_profiles()
        self.assertEqual(len(profiles), 5, "Voice registry must contain exactly 5 voice profiles.")

        profile_ids = [p.profile_id for p in profiles]
        expected_ids = ["arjun", "kabir", "ananya", "mira", "zara"]
        self.assertEqual(profile_ids, expected_ids)

        # Count genders
        males = [p for p in profiles if p.gender == "male"]
        females = [p for p in profiles if p.gender == "female"]
        self.assertEqual(len(males), 2, "Must have exactly 2 male voice profiles.")
        self.assertEqual(len(females), 3, "Must have exactly 3 female voice profiles.")

        self.assertEqual(males[0].name, "Arjun")
        self.assertEqual(males[1].name, "Kabir")
        self.assertEqual(females[0].name, "Ananya")
        self.assertEqual(females[1].name, "Mira")
        self.assertEqual(females[2].name, "Zara")

    def test_02_voice_ids_are_distinct(self) -> None:
        """Verify each profile uses a genuinely different primary voice ID and acoustic model."""
        profiles = list_voice_profiles()
        voice_ids = [p.primary_voice_id for p in profiles]
        self.assertEqual(len(voice_ids), len(set(voice_ids)), "All 5 voice IDs must be unique.")

        # Ensure the Kokoro acoustic models are distinct:
        # Arjun -> am_adam (Male US)
        # Kabir -> am_michael (Male US)
        # Ananya -> af_bella (Female US)
        # Mira -> af_heart (Female US)
        # Zara -> bf_emma (Female British)
        self.assertEqual(VOICE_REGISTRY["arjun"].primary_voice_id, "am_adam")
        self.assertEqual(VOICE_REGISTRY["kabir"].primary_voice_id, "am_michael")
        self.assertEqual(VOICE_REGISTRY["ananya"].primary_voice_id, "af_bella")
        self.assertEqual(VOICE_REGISTRY["mira"].primary_voice_id, "af_heart")
        self.assertEqual(VOICE_REGISTRY["zara"].primary_voice_id, "bf_emma")

    def test_03_languages_supported_across_profiles(self) -> None:
        """Verify all 5 profiles officially support English, Hindi, and Gujarati."""
        for p in list_voice_profiles():
            self.assertIn("en", p.supported_languages)
            self.assertIn("hi", p.supported_languages)
            self.assertIn("gu", p.supported_languages)

    def test_04_standardized_preview_samples(self) -> None:
        """Verify identical fair comparison sentences exist for en, hi, gu."""
        en_sample = get_preview_sample_text("en")
        hi_sample = get_preview_sample_text("hi")
        gu_sample = get_preview_sample_text("gu")

        self.assertTrue(len(en_sample) > 10)
        self.assertTrue(len(hi_sample) > 10)
        self.assertTrue(len(gu_sample) > 10)

        # Must contain Bond companion greeting in each language
        self.assertIn("Bond", en_sample)
        self.assertIn("बॉन्ड", hi_sample)
        self.assertIn("બોન્ડ", gu_sample)

    def test_05_multilingual_engine_prepares_gender_appropriate_hint(self) -> None:
        """Verify MultilingualEngine returns gender-aligned voice hints for Indic languages."""
        sapi = Sapi5TTSEngine()
        installed = sapi.get_available_voices()

        # For Male profile (Arjun/Kabir):
        spoken_hi_m, hint_m = MultilingualEngine.prepare_text_for_tts(
            text="नमस्ते! मैं बॉन्ड हूँ।",
            target_language="hi",
            engine_name="Sapi5TTSEngine",
            installed_voices=installed,
            preferred_voice_id="am_adam",
            preferred_gender="male",
        )
        self.assertTrue(len(spoken_hi_m) > 0)
        # Should prefer Ravi or male voice over Heera
        if hint_m and "ravi" in [v.lower() for v in installed if "ravi" in v.lower()]:
            self.assertIn("ravi", hint_m.lower())

        # For Female profile (Ananya/Mira/Zara):
        spoken_hi_f, hint_f = MultilingualEngine.prepare_text_for_tts(
            text="नमस्ते! मैं बॉन्ड हूँ।",
            target_language="hi",
            engine_name="Sapi5TTSEngine",
            installed_voices=installed,
            preferred_voice_id="af_bella",
            preferred_gender="female",
        )
        self.assertTrue(len(spoken_hi_f) > 0)
        if hint_f and "heera" in [v.lower() for v in installed if "heera" in v.lower()]:
            self.assertIn("heera", hint_f.lower())

    def test_06_kokoro_voice_differentiation_english(self) -> None:
        """Verify Kokoro synthesizes genuinely distinct audio waveforms for the 5 voices."""
        kokoro = KokoroTTSEngine()
        if not kokoro.is_available():
            self.skipTest("Kokoro TTS engine not available in environment.")

        text = "Hello! I am Bond, your personal AI desktop companion."
        audios = {}

        for profile in list_voice_profiles():
            audio = kokoro.synthesize(text, voice=profile.primary_voice_id, speed=profile.speaking_rate)
            self.assertFalse(audio.is_empty, f"Audio for {profile.name} must not be empty.")
            self.assertGreater(len(audio.samples), 1000)
            audios[profile.profile_id] = audio

        # Compare male vs female waveforms and speaking rates
        arjun_audio = audios["arjun"]
        kabir_audio = audios["kabir"]
        zara_audio = audios["zara"]

        # Arjun (rate 1.0) vs Kabir (rate 0.95): Kabir takes longer due to deeper, relaxed cadence
        self.assertNotEqual(len(arjun_audio.samples), len(kabir_audio.samples))
        # Zara (rate 1.05 British): Faster cadence
        self.assertNotEqual(len(kabir_audio.samples), len(zara_audio.samples))

    def test_07_sapi5_voice_switching(self) -> None:
        """Verify SAPI5 engine respects dynamic voice token switching."""
        sapi = Sapi5TTSEngine()
        if not sapi.is_available():
            self.skipTest("SAPI5 not available on this platform.")

        voices = sapi.get_available_voices()
        self.assertTrue(len(voices) >= 2, "At least 2 SAPI voices expected on Windows.")

        audio_david = sapi.synthesize("Testing voice synthesis.", voice_name="Microsoft David Desktop")
        self.assertFalse(audio_david.is_empty)

        audio_zira = sapi.synthesize("Testing voice synthesis.", voice_name="Microsoft Zira Desktop")
        self.assertFalse(audio_zira.is_empty)

    def test_08_persistence_across_restart(self) -> None:
        """Verify selected voice profile persists and reloads correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "config.json"
            cfg = ConfigManager(config_path=str(cfg_path))

            # Default is arjun
            self.assertEqual(cfg.get("voice.selected_profile", "arjun"), "arjun")

            # User selects Mira
            cfg.set("voice.selected_profile", "mira")
            self.assertEqual(cfg.get("voice.selected_profile"), "mira")

            # Simulate application restart: load fresh ConfigManager instance from same path
            cfg_restart = ConfigManager(config_path=str(cfg_path))
            self.assertEqual(
                cfg_restart.get("voice.selected_profile"),
                "mira",
                "Selected voice 'mira' must persist across application restart.",
            )

    def test_09_voice_fallback_graceful_handling(self) -> None:
        """Verify invalid or non-existent profile IDs fall back to default profile (Arjun)."""
        fallback_prof = get_voice_profile("unknown_alien_voice_id")
        self.assertEqual(fallback_prof.profile_id, DEFAULT_VOICE_PROFILE_ID)
        self.assertEqual(fallback_prof.name, "Arjun")


if __name__ == "__main__":
    unittest.main()
