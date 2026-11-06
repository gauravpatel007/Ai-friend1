"""Phase 7 Automated Test Suite: Per-Persona Speaking Styles.

Verifies:
7.1 Speaking style configuration: Speaking rate, pitch, expressiveness, energy,
    pause duration, sentence delivery, and conversational style.
7.2 Voice style presets:
    - Arjun: Friendly, confident, natural pace, warm delivery.
    - Kabir: Calm, mature, measured pace, composed delivery.
    - Ananya: Warm, expressive, friendly, natural conversational pace.
    - Mira: Gentle, calm, softer delivery, relaxed pace.
    - Zara: Energetic, confident, expressive, lively delivery.
7.3 Persona independence: Voice, speaking style, and persona prompt remain
    independently configurable and persistent without mutating AI memory or context.
7.4 Natural speech guardrails: Clamping prevents robotic delivery, excessive pauses,
    or artificial pitch distortions; audio DSP maintains volume stability.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from app.ai.personality_manager import PersonalityManager
from app.settings.config_manager import ConfigManager
from app.voice.speaking_style import (
    DEFAULT_SPEAKING_STYLES,
    MAX_PAUSE_MS,
    MAX_PITCH_SEMITONES,
    MAX_SPEAKING_RATE,
    MIN_PAUSE_MS,
    MIN_PITCH_SEMITONES,
    MIN_SPEAKING_RATE,
    SpeakingStyle,
    SpeakingStyleManager,
    apply_speaking_style_dsp,
)


class TestPhase7PersonaSpeakingStyles(unittest.TestCase):
    """Test suite for Phase 7: Per-Persona Speaking Styles."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "test_speaking_style_settings.json"
        self.config = ConfigManager(config_path=str(self.config_path))
        self.personality_mgr = PersonalityManager(config_manager=self.config)
        self.style_mgr = SpeakingStyleManager(config_manager=self.config)

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ─── 7.1 Speaking Style Configuration ─────────────────────────────────────

    def test_01_speaking_style_dimensions_present_and_configurable(self) -> None:
        """Verify all seven required speaking style dimensions exist and can be set."""
        style = SpeakingStyle(
            style_id="test_custom",
            name="Test Style",
            speaking_rate=1.05,
            pitch=-0.5,
            expressiveness=0.75,
            energy=0.70,
            pause_duration_ms=130,
            sentence_delivery="Warm delivery",
            conversational_style="Friendly and confident",
        )

        self.assertEqual(style.style_id, "test_custom")
        self.assertEqual(style.name, "Test Style")
        self.assertEqual(style.speaking_rate, 1.05)
        self.assertEqual(style.pitch, -0.5)
        self.assertEqual(style.expressiveness, 0.75)
        self.assertEqual(style.energy, 0.70)
        self.assertEqual(style.pause_duration_ms, 130)
        self.assertEqual(style.sentence_delivery, "Warm delivery")
        self.assertEqual(style.conversational_style, "Friendly and confident")

    def test_02_serialization_and_deserialization(self) -> None:
        """Verify dictionary serialization preserves all speaking style properties."""
        original = SpeakingStyle(
            style_id="kabir_custom",
            name="Custom Kabir",
            speaking_rate=0.90,
            pitch=-1.2,
            expressiveness=0.40,
            energy=0.50,
            pause_duration_ms=190,
            sentence_delivery="Composed delivery",
            conversational_style="Calm and mature",
        )

        d = original.to_dict()
        restored = SpeakingStyle.from_dict(d)

        self.assertEqual(restored.style_id, original.style_id)
        self.assertEqual(restored.speaking_rate, original.speaking_rate)
        self.assertEqual(restored.pitch, original.pitch)
        self.assertEqual(restored.expressiveness, original.expressiveness)
        self.assertEqual(restored.energy, original.energy)
        self.assertEqual(restored.pause_duration_ms, original.pause_duration_ms)
        self.assertEqual(restored.sentence_delivery, original.sentence_delivery)
        self.assertEqual(restored.conversational_style, original.conversational_style)

    # ─── 7.2 Example Voice Styles ─────────────────────────────────────────────

    def test_03_baseline_presets_match_specification(self) -> None:
        """Verify the 5 default voice styles match the specifications in Section 7.2."""
        # 1. Arjun: Friendly, confident, natural pace, warm delivery
        arjun = DEFAULT_SPEAKING_STYLES["arjun"]
        self.assertEqual(arjun.speaking_rate, 1.00)
        self.assertIn("Warm", arjun.sentence_delivery)
        self.assertIn("Friendly", arjun.conversational_style)

        # 2. Kabir: Calm, mature, measured speaking pace, composed delivery
        kabir = DEFAULT_SPEAKING_STYLES["kabir"]
        self.assertLess(kabir.speaking_rate, 1.00)  # Measured pace
        self.assertLess(kabir.pitch, 0.0)          # Slightly deeper
        self.assertIn("Composed", kabir.sentence_delivery)
        self.assertIn("Calm", kabir.conversational_style)
        self.assertGreater(kabir.pause_duration_ms, arjun.pause_duration_ms)

        # 3. Ananya: Warm, expressive, friendly, natural conversational pace
        ananya = DEFAULT_SPEAKING_STYLES["ananya"]
        self.assertEqual(ananya.speaking_rate, 1.00)
        self.assertGreaterEqual(ananya.expressiveness, 0.75)
        self.assertIn("Warm", ananya.conversational_style)

        # 4. Mira: Gentle, calm, softer delivery, relaxed pace
        mira = DEFAULT_SPEAKING_STYLES["mira"]
        self.assertLess(mira.speaking_rate, 1.00)  # Relaxed pace
        self.assertLess(mira.energy, arjun.energy) # Softer delivery
        self.assertIn("Softer", mira.sentence_delivery)
        self.assertIn("Gentle", mira.conversational_style)

        # 5. Zara: Energetic, confident, expressive, lively delivery
        zara = DEFAULT_SPEAKING_STYLES["zara"]
        self.assertGreater(zara.speaking_rate, 1.00) # Energetic pace
        self.assertGreater(zara.energy, arjun.energy) # High energy
        self.assertGreaterEqual(zara.expressiveness, 0.80)
        self.assertIn("Lively", zara.sentence_delivery)
        self.assertIn("Energetic", zara.conversational_style)
        self.assertLess(zara.pause_duration_ms, arjun.pause_duration_ms)

    def test_04_default_persona_to_style_mappings(self) -> None:
        """Verify initial default persona mappings resolve correctly."""
        style_friendly = self.style_mgr.get_style_for_persona("friendly")
        self.assertEqual(style_friendly.style_id, "arjun")

        style_calm = self.style_mgr.get_style_for_persona("calm")
        self.assertEqual(style_calm.style_id, "kabir")

        style_creative = self.style_mgr.get_style_for_persona("creative")
        self.assertEqual(style_creative.style_id, "ananya")

        style_energetic = self.style_mgr.get_style_for_persona("energetic")
        self.assertEqual(style_energetic.style_id, "zara")

        style_professional = self.style_mgr.get_style_for_persona("professional")
        self.assertEqual(style_professional.style_id, "kabir")

    # ─── 7.3 Persona Independence ─────────────────────────────────────────────

    def test_05_style_change_does_not_mutate_persona_prompt_or_knowledge(self) -> None:
        """Verify modifying speaking style modifies TTS delivery without changing system prompt (7.3)."""
        prompt_before = self.personality_mgr.build_system_prompt(personality="friendly")

        # Customize friendly persona speaking style to Zara's energetic style
        success = self.personality_mgr.set_speaking_style_for_persona("friendly", "zara")
        self.assertTrue(success)

        style_after = self.personality_mgr.get_speaking_style_for_persona("friendly")
        self.assertEqual(style_after.style_id, "zara")
        self.assertEqual(style_after.speaking_rate, 1.08)

        # Persona prompt must remain identical in character/persona identity
        prompt_after = self.personality_mgr.build_system_prompt(personality="friendly")
        self.assertEqual(prompt_before, prompt_after)

    def test_06_independent_voice_and_speaking_style_customization(self) -> None:
        """Verify user can set Arjun voice but Kabir's calm measured speaking style for a persona."""
        # Friendly persona uses Arjun voice by default
        self.assertEqual(self.personality_mgr.get_voice_for_persona("friendly"), "arjun")

        # Set Kabir's calm delivery for friendly persona
        self.personality_mgr.set_speaking_style_for_persona("friendly", "kabir")
        style = self.personality_mgr.get_speaking_style_for_persona("friendly")
        self.assertEqual(style.style_id, "kabir")
        self.assertEqual(style.speaking_rate, 0.92)

        # Voice profile remains Arjun
        self.assertEqual(self.personality_mgr.get_voice_for_persona("friendly"), "arjun")

        # Switch voice profile to Ananya, speaking style remains Kabir
        self.personality_mgr.set_voice_for_persona("friendly", "ananya")
        self.assertEqual(self.personality_mgr.get_voice_for_persona("friendly"), "ananya")
        self.assertEqual(self.personality_mgr.get_speaking_style_for_persona("friendly").style_id, "kabir")

    def test_07_persistence_across_manager_restarts(self) -> None:
        """Verify configured speaking styles are persisted and restored from config."""
        custom_style = SpeakingStyle(
            style_id="custom_calm",
            name="Personal Calm",
            speaking_rate=0.88,
            pitch=-1.0,
            expressiveness=0.5,
            energy=0.4,
            pause_duration_ms=200,
            sentence_delivery="Composed delivery",
            conversational_style="Calm and mature",
        )

        self.style_mgr.set_style_for_persona("calm", custom_style)

        # Create new manager pointing to the same config path
        restored_mgr = SpeakingStyleManager(config_manager=self.config)
        restored_style = restored_mgr.get_style_for_persona("calm")

        self.assertEqual(restored_style.speaking_rate, 0.88)
        self.assertEqual(restored_style.pitch, -1.0)
        self.assertEqual(restored_style.pause_duration_ms, 200)

    # ─── 7.4 Natural Speech & Audio Guardrails ─────────────────────────────────

    def test_08_natural_speech_boundary_clamping(self) -> None:
        """Verify parameters outside natural bounds are safely clamped (7.4)."""
        # Unnatural rate: 2.5x -> clamped to 1.35x
        # Unnatural pitch: +8 semitones -> clamped to +2.0 semitones
        # Unnatural pause: 1500ms -> clamped to 260ms
        extreme_style = SpeakingStyle(
            style_id="extreme",
            name="Extreme",
            speaking_rate=2.5,
            pitch=8.0,
            expressiveness=5.0,
            energy=3.0,
            pause_duration_ms=1500,
        )

        self.assertEqual(extreme_style.speaking_rate, MAX_SPEAKING_RATE)
        self.assertEqual(extreme_style.pitch, MAX_PITCH_SEMITONES)
        self.assertEqual(extreme_style.pause_duration_ms, MAX_PAUSE_MS)
        self.assertEqual(extreme_style.expressiveness, 1.0)
        self.assertEqual(extreme_style.energy, 1.0)

        # Lower boundary clamping
        slow_style = SpeakingStyle(
            style_id="too_slow",
            name="Too Slow",
            speaking_rate=0.2,
            pitch=-10.0,
            pause_duration_ms=10,
        )
        self.assertEqual(slow_style.speaking_rate, MIN_SPEAKING_RATE)
        self.assertEqual(slow_style.pitch, MIN_PITCH_SEMITONES)
        self.assertEqual(slow_style.pause_duration_ms, MIN_PAUSE_MS)

    def test_09_audio_dsp_processing_stability(self) -> None:
        """Verify audio DSP applies pitch shift, volume scaling, and pause padding safely."""
        sr = 24000
        duration = 0.5
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
        raw_samples = (0.5 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)

        # Test Zara style (energetic, pitch +0.8, pause 85ms)
        zara_style = DEFAULT_SPEAKING_STYLES["zara"]
        processed_zara = apply_speaking_style_dsp(raw_samples, sr, zara_style, is_inter_sentence=True)

        self.assertTrue(len(processed_zara) > len(raw_samples))
        self.assertFalse(np.isnan(processed_zara).any())
        self.assertFalse(np.isinf(processed_zara).any())
        # Volume soft limiting prevents clipping > 1.0
        self.assertLessEqual(np.max(np.abs(processed_zara)), 1.0)

        # Test Mira style (gentle, softer delivery, pause 160ms)
        mira_style = DEFAULT_SPEAKING_STYLES["mira"]
        processed_mira = apply_speaking_style_dsp(raw_samples, sr, mira_style, is_inter_sentence=True)

        self.assertTrue(len(processed_mira) > len(raw_samples))
        # Mira inter-sentence pause (160ms) should be longer than Zara (85ms)
        self.assertGreater(len(processed_mira), len(processed_zara))
        self.assertFalse(np.isnan(processed_mira).any())


if __name__ == "__main__":
    unittest.main()
