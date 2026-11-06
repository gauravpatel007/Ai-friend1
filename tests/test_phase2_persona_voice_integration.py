"""Phase 2 Automated Test Suite: Voice Settings and Persona Integration.

Verifies:
1. Centralized voice configuration: Every persona uses one of the five distinct voice profiles.
2. Persona and voice independence: Personas are not permanently locked to a voice; users can
   reassign any of the 5 voices to any persona.
3. Decoupling: Changing voice or persona preserves conversation context, history, and memory.
4. Language consistency: Response language (English, Gujarati, Hindi) is preserved regardless
   of voice or persona changes; voice never forces a language switch.
5. Settings persistence: Persona-to-voice mappings are persisted to config and restored upon restart.
6. Acceptance criteria: Switching personas or voices does not break ongoing conversations.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from app.ai.ai_service import AIService
from app.ai.conversation_context import ConversationContext
from app.ai.personality_manager import (
    DEFAULT_PERSONA_VOICE_MAP,
    PRESET_PERSONALITIES,
    PersonalityManager,
    PersonalityPreset,
)
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.memory.memory_manager import MemoryManager
from app.settings.config_manager import ConfigManager
from app.voice.voice_registry import (
    DEFAULT_VOICE_PROFILE_ID,
    VOICE_REGISTRY,
    VoiceProfile,
    get_voice_profile,
    list_voice_profiles,
)


class TestPhase2PersonaVoiceIntegration(unittest.TestCase):
    """Automated test suite for Phase 2: Persona and Voice Integration."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "test_settings.json"
        self.config = ConfigManager(config_path=str(self.config_path))
        self.personality_mgr = PersonalityManager(config_manager=self.config)

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ─── 2.1 Centralized Voice Configuration ─────────────────────────

    def test_01_all_personas_mapped_to_valid_profiles(self) -> None:
        """Verify every defined persona preset is mapped to a valid 5-voice profile."""
        valid_profile_ids = {p.profile_id for p in list_voice_profiles()}
        self.assertEqual(valid_profile_ids, {"arjun", "kabir", "ananya", "mira", "zara"})

        for preset_key, preset in PRESET_PERSONALITIES.items():
            mapped_voice = self.personality_mgr.get_voice_for_persona(preset_key)
            self.assertIn(
                mapped_voice,
                valid_profile_ids,
                f"Persona '{preset_key}' mapped to invalid voice profile '{mapped_voice}'",
            )
            # Verify preset metadata
            self.assertTrue(hasattr(preset, "default_voice"))
            self.assertTrue(hasattr(preset, "speaking_character"))

    def test_02_default_voice_persona_characteristics(self) -> None:
        """Verify baseline persona-voice pairings match design specs."""
        self.assertEqual(self.personality_mgr.get_voice_for_persona("friendly"), "arjun")
        self.assertEqual(self.personality_mgr.get_voice_for_persona("calm"), "kabir")
        self.assertEqual(self.personality_mgr.get_voice_for_persona("funny"), "zara")
        self.assertEqual(self.personality_mgr.get_voice_for_persona("energetic"), "zara")
        self.assertEqual(self.personality_mgr.get_voice_for_persona("professional"), "kabir")
        self.assertEqual(self.personality_mgr.get_voice_for_persona("creative"), "ananya")

    def test_03_available_personalities_metadata(self) -> None:
        """Verify discovery API returns default voice and speaking character."""
        available = PersonalityManager.get_available_personalities()
        self.assertTrue(len(available) >= 5)
        for item in available:
            self.assertIn("key", item)
            self.assertIn("title", item)
            self.assertIn("description", item)
            self.assertIn("default_voice", item)
            self.assertIn("speaking_character", item)

    # ─── 2.2 Persona and Voice Independence ──────────────────────────

    def test_04_reassign_voice_for_persona(self) -> None:
        """Verify user can assign any of the 5 voices to any persona."""
        all_profiles = ["arjun", "kabir", "ananya", "mira", "zara"]

        for voice_id in all_profiles:
            ok = self.personality_mgr.set_voice_for_persona("calm", voice_id)
            self.assertTrue(ok)
            self.assertEqual(self.personality_mgr.get_voice_for_persona("calm"), voice_id)

        # Test rejecting invalid voice ID
        self.assertFalse(self.personality_mgr.set_voice_for_persona("calm", "unknown_robot_voice"))

    def test_05_voice_change_does_not_mutate_persona_identity(self) -> None:
        """Verify changing voice does NOT modify persona knowledge, prompt, or identity."""
        original_prompt = PRESET_PERSONALITIES["friendly"].base_prompt
        original_title = PRESET_PERSONALITIES["friendly"].title

        # Switch voice to Mira
        self.personality_mgr.set_voice_for_persona("friendly", "mira")

        # Identity remains identical
        self.assertEqual(PRESET_PERSONALITIES["friendly"].base_prompt, original_prompt)
        self.assertEqual(PRESET_PERSONALITIES["friendly"].title, original_title)
        self.assertEqual(self.personality_mgr.companion_name, "Buddy")

    def test_06_persona_switch_activates_mapped_voice_signal(self) -> None:
        """Verify switching persona emits voice_profile_changed with the mapped voice."""
        received_profiles = []

        def on_voice_changed(profile_id: str) -> None:
            received_profiles.append(profile_id)

        signals.voice_profile_changed.connect(on_voice_changed)
        try:
            # Switch to calm -> should emit kabir
            self.personality_mgr.set_personality("calm")
            self.assertEqual(self.config.get("voice.selected_profile"), "kabir")
            self.assertIn("kabir", received_profiles)

            # Reassign calm to mira and switch back and forth
            self.personality_mgr.set_voice_for_persona("calm", "mira")
            self.personality_mgr.set_personality("friendly")
            self.assertEqual(self.config.get("voice.selected_profile"), "arjun")

            self.personality_mgr.set_personality("calm")
            self.assertEqual(self.config.get("voice.selected_profile"), "mira")
            self.assertEqual(received_profiles[-1], "mira")
        finally:
            signals.voice_profile_changed.disconnect(on_voice_changed)

    # ─── 2.3 Language Consistency ────────────────────────────────────

    def test_07_language_remains_consistent_on_voice_switch(self) -> None:
        """Verify configured response language (gu, hi, en) is never altered by voice switch."""
        for test_lang in ["gu", "hi", "en"]:
            self.config.set("language.response_language", test_lang)

            # Switch across all 5 voices
            for voice_id in ["arjun", "kabir", "ananya", "mira", "zara"]:
                self.personality_mgr.set_voice_for_persona(self.personality_mgr.active_personality, voice_id)
                current_lang = self.config.get("language.response_language")
                self.assertEqual(
                    current_lang,
                    test_lang,
                    f"Voice switch to '{voice_id}' modified response language from '{test_lang}' to '{current_lang}'",
                )

    def test_08_language_remains_consistent_on_persona_switch(self) -> None:
        """Verify configured response language is never altered by persona switch."""
        self.config.set("language.response_language", "gu")

        for persona_key in ["friendly", "calm", "funny", "energetic", "professional", "creative"]:
            self.personality_mgr.set_personality(persona_key)
            self.assertEqual(
                self.config.get("language.response_language"),
                "gu",
                f"Persona switch to '{persona_key}' changed response language!",
            )

    # ─── 2.4 Settings Persistence ────────────────────────────────────

    def test_09_persona_voice_mappings_persist_across_restart(self) -> None:
        """Verify customized persona-to-voice mappings persist to disk and reload."""
        # Customize mappings
        self.personality_mgr.set_voice_for_persona("friendly", "zara")
        self.personality_mgr.set_voice_for_persona("calm", "mira")
        self.personality_mgr.set_voice_for_persona("creative", "kabir")

        # Simulate fresh application launch with a new ConfigManager and PersonalityManager
        reloaded_config = ConfigManager(config_path=str(self.config_path))
        reloaded_mgr = PersonalityManager(config_manager=reloaded_config)

        self.assertEqual(reloaded_mgr.get_voice_for_persona("friendly"), "zara")
        self.assertEqual(reloaded_mgr.get_voice_for_persona("calm"), "mira")
        self.assertEqual(reloaded_mgr.get_voice_for_persona("creative"), "kabir")
        # Untouched preset maintains default
        self.assertEqual(reloaded_mgr.get_voice_for_persona("energetic"), "zara")

    # ─── Acceptance Criteria: Conversation Preservation ─────────────

    def test_10_conversation_and_memory_preserved_across_voice_and_persona_changes(self) -> None:
        """Verify ongoing multi-turn conversations and memories are 100% intact after voice & persona switches."""
        db_path = Path(self.temp_dir.name) / "test_memory.db"
        db_mgr = DatabaseManager(db_path=str(db_path))
        repo = ConversationRepository(db_manager=db_mgr)
        mem_mgr = MemoryManager(db_manager=db_mgr)

        # 1. Establish an ongoing conversation session
        conv = repo.create_conversation("Project Brainstorm")
        repo.add_message(conv.id, "user", "What are the latest updates on our AI friend project?")
        repo.add_message(conv.id, "assistant", "We have upgraded the multi-tier voice pipeline!")
        mem_mgr.add_memory("User is working on AI Desktop Companion.", category="project")

        initial_messages = repo.get_messages(conv.id)
        self.assertEqual(len(initial_messages), 2)
        initial_memories = mem_mgr.get_all_memories()
        self.assertEqual(len(initial_memories), 1)

        # 2. Change active voice
        self.personality_mgr.set_voice_for_persona("friendly", "mira")

        # Messages and memories must be completely untouched
        messages_after_voice = repo.get_messages(conv.id)
        self.assertEqual(len(messages_after_voice), 2)
        self.assertEqual(messages_after_voice[0].content, initial_messages[0].content)
        self.assertEqual(messages_after_voice[1].content, initial_messages[1].content)
        self.assertEqual(len(mem_mgr.get_all_memories()), 1)

        # 3. Change persona to 'calm'
        self.personality_mgr.set_personality("calm")

        # Messages and memories must remain completely untouched
        messages_after_persona = repo.get_messages(conv.id)
        self.assertEqual(len(messages_after_persona), 2)
        self.assertEqual(messages_after_persona[0].content, initial_messages[0].content)
        self.assertEqual(messages_after_persona[1].content, initial_messages[1].content)
        self.assertEqual(len(mem_mgr.get_all_memories()), 1)

        # 4. Multi-turn dialogue can continue seamlessly
        repo.add_message(conv.id, "user", "Awesome, what should we test next?")
        repo.add_message(conv.id, "assistant", "Let's verify natural interruptions and responsive audio.")
        updated_messages = repo.get_messages(conv.id)
        self.assertEqual(len(updated_messages), 4)


if __name__ == "__main__":
    unittest.main()
