"""Comprehensive Test Suite for Phase 10: Intelligent Memory, Personality & Emotion.

Validates:
- 10.1 & 10.2: Memory Architecture & Database Schema with SQLite FTS5.
- 10.3: Automatic Memory Extraction from Dialogue.
- 10.4: Memory & Conversation Summary Retrieval and Context Injection.
- 10.5: Intelligent Memory Update Logic (Contradiction Resolution).
- 10.6: Memory Management UI & Privacy Controls.
- 10.7: Personality Customization (all 5 profiles).
- 10.8: Text-based Emotion Classification & Dynamic Tone Adaptation.
- 10.9: Emotion-to-Animation Integration.
- 10.10: Context & Privacy Verification.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from app.ai.conversation_context import ConversationContext
from app.ai.emotion_classifier import EmotionClassifier, EmotionType
from app.ai.personality_manager import PRESET_PERSONALITIES, PersonalityManager
from app.character.states import CharacterState
from app.core.controller import ApplicationController
from app.core.signals import signals
from app.desktop.settings_dialog import SettingsDialog
from app.memory.database import init_db
from app.memory.memory_manager import MemoryManager
from app.memory.models import Memory
from app.settings.config_manager import ConfigManager


@pytest.fixture
def temp_db(tmp_path: Path):
    """Provide an isolated SQLite database path with initial schema."""
    db_path = str(tmp_path / "test_memory.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def memory_manager(temp_db: str):
    """Provide a MemoryManager instance backed by the temporary database."""
    return MemoryManager(db_path=temp_db)


# ─── 10.1 & 10.2: Database & CRUD Operations ──────────────────────────────────

def test_memory_crud_operations(memory_manager: MemoryManager):
    """Verify storing, retrieving, updating, and deleting memories."""
    # 1. Create
    mem = memory_manager.store_memory(
        category="preference",
        content="Prefers dark theme in code editor",
        source_conversation_id="conv-1",
    )
    assert mem.id is not None
    assert mem.category == "preference"
    assert "dark theme" in mem.content

    # 2. Read
    fetched = memory_manager.get_memory(mem.id)
    assert fetched is not None
    assert fetched.content == mem.content

    # 3. Update
    updated = memory_manager.update_memory(
        memory_id=mem.id,
        content="Prefers dark theme with high contrast",
        category="preference",
    )
    assert updated is not None
    assert "high contrast" in updated.content

    # 4. Delete
    assert memory_manager.delete_memory(mem.id) is True
    assert memory_manager.get_memory(mem.id) is None


def test_fts5_memory_search(memory_manager: MemoryManager):
    """Verify SQLite FTS5 search across stored memory content."""
    memory_manager.store_memory("project", "Building a quantum physics simulation engine")
    memory_manager.store_memory("learning", "Studying Rust async programming and Tokio")
    memory_manager.store_memory("preference", "Loves Italian espresso coffee")

    # Search project keyword
    results_quantum = memory_manager.search_memories("quantum")
    assert len(results_quantum) == 1
    assert "quantum physics" in results_quantum[0].content

    # Search programming keyword
    results_rust = memory_manager.search_memories("Rust Tokio")
    assert len(results_rust) >= 1
    assert "Rust async" in results_rust[0].content

    # Special characters & punctuation handling in FTS5
    safe_results = memory_manager.search_memories("espresso: 'coffee'*")
    assert len(safe_results) == 1
    assert "Italian espresso" in safe_results[0].content


def test_conversation_summaries_storage_and_search(memory_manager: MemoryManager):
    """Verify storing, retrieving, and searching conversation summaries."""
    summary1 = memory_manager.store_summary(
        conversation_id="conv-101",
        summary="User discussed neural network pruning techniques and quantization.",
    )
    assert summary1.id is not None

    summaries = memory_manager.get_summaries_for_conversation("conv-101")
    assert len(summaries) == 1
    assert "neural network" in summaries[0].summary

    # FTS5 search across summaries
    search_res = memory_manager.search_summaries("pruning quantization")
    assert len(search_res) == 1
    assert search_res[0].conversation_id == "conv-101"


# ─── 10.3: Memory Extraction ──────────────────────────────────────────────────

def test_heuristic_memory_extraction(memory_manager: MemoryManager):
    """Verify heuristic extraction identifies preferences, projects, learning, and remember directives."""
    text_sample = (
        "I am currently learning Go and Kubernetes. "
        "Also, my favorite food is spicy ramen. "
        "I am working on a new mobile app for fitness. "
        "Please remember that my server port is 8080."
    )

    extracted = memory_manager.extract_memories_from_text(text_sample)
    categories = [m.category for m in extracted]

    assert "learning" in categories or "goal" in categories
    assert "preference" in categories
    assert "project" in categories
    assert "fact" in categories

    # Casual non-salient text should yield nothing
    casual_text = "Good morning! Can you explain what a binary tree is?"
    assert len(memory_manager.extract_memories_from_text(casual_text)) == 0


# ─── 10.4: Retrieval & Context Injection ─────────────────────────────────────

def test_context_memory_and_summary_injection():
    """Verify conversation context properly formats memories and summaries into system prompt."""
    ctx = ConversationContext(system_prompt="You are Buddy, a friendly AI companion.")
    ctx.inject_memories(["[PREFERENCE] Prefers dark mode", "[PROJECT] Working on AI friend app"])
    ctx.inject_summaries(["User previously asked about PySide6 signal architecture."])
    ctx.add_user_message("Where should we continue?")

    messages = ctx.get_messages()
    assert len(messages) == 2
    system_content = messages[0]["content"]

    assert "memories about the user" in system_content.lower()
    assert "Prefers dark mode" in system_content
    assert "Working on AI friend app" in system_content
    assert "previous conversations" in system_content.lower()
    assert "PySide6 signal architecture" in system_content


# ─── 10.5: Contradiction Resolution / Memory Update Logic ────────────────────

def test_memory_contradiction_update_logic(memory_manager: MemoryManager):
    """Verify that updating a previously remembered fact modifies the existing entry instead of duplicating."""
    # 1. User says favorite color is blue
    initial_mem = memory_manager.store_or_update_memory(
        category="preference",
        content="My favorite color is blue",
    )
    assert memory_manager.get_memory_count() == 1
    assert "blue" in initial_mem.content

    # 2. User later corrects it: "My favorite color is actually green"
    updated_mem = memory_manager.store_or_update_memory(
        category="preference",
        content="My favorite color is green",
    )
    # Count should still be 1 because topic term overlap ('favorite', 'color') in 'preference' category was updated
    assert memory_manager.get_memory_count() == 1
    assert updated_mem.id == initial_mem.id
    assert "green" in updated_mem.content

    # 3. Completely distinct preference adds a new memory
    second_mem = memory_manager.store_or_update_memory(
        category="preference",
        content="I prefer dark mode IDE theme",
    )
    assert memory_manager.get_memory_count() == 2
    assert second_mem.id != initial_mem.id


# ─── 10.7: Personality Customization ──────────────────────────────────────────

def test_all_five_personality_profiles():
    """Verify that all 5 canonical personality profiles (Friendly, Funny, Calm, Energetic, Professional) exist and format correctly."""
    canonical_keys = ["friendly", "funny", "calm", "energetic", "professional"]
    for key in canonical_keys:
        assert key in PRESET_PERSONALITIES, f"Preset {key} missing from PRESET_PERSONALITIES"

    pm = PersonalityManager(companion_name="Buddy")

    # 1. Friendly
    pm.set_personality("friendly")
    p_friendly = pm.build_system_prompt()
    assert "warm" in p_friendly.lower() or "supportive" in p_friendly.lower()

    # 2. Funny
    pm.set_personality("funny")
    p_funny = pm.build_system_prompt()
    assert "humor" in p_funny.lower() or "playful" in p_funny.lower()

    # 3. Calm
    pm.set_personality("calm")
    p_calm = pm.build_system_prompt()
    assert "calm" in p_calm.lower() or "relaxed" in p_calm.lower()

    # 4. Energetic
    pm.set_personality("energetic")
    p_energetic = pm.build_system_prompt()
    assert "energetic" in p_energetic.lower() or "enthusiastic" in p_energetic.lower()

    # 5. Professional
    pm.set_personality("professional")
    p_prof = pm.build_system_prompt()
    assert "professional" in p_prof.lower() or "direct" in p_prof.lower()


# ─── 10.8: Emotion Classification & Tone Adaptation ──────────────────────────

def test_emotion_classification_categories():
    """Verify text emotion classification correctly tags emotions with confidence scoring."""
    # Happy
    emotion, score = EmotionClassifier.classify("I passed all my exams today! I am so happy and joyful!")
    assert emotion == EmotionType.HAPPY
    assert score >= 0.50

    # Excited
    emotion, score = EmotionClassifier.classify("OMG this is incredible! Absolutely fantastic and awesome!")
    assert emotion == EmotionType.EXCITED
    assert score >= 0.50

    # Sad
    emotion, score = EmotionClassifier.classify("I feel so depressed and heartbroken today. Everything went wrong.")
    assert emotion == EmotionType.SAD
    assert score >= 0.50

    # Frustrated
    emotion, score = EmotionClassifier.classify("I hate this stupid bug! It is so annoying and frustrating!")
    assert emotion == EmotionType.FRUSTRATED
    assert score >= 0.50

    # Neutral
    emotion, score = EmotionClassifier.classify("The train departs at 3:15 PM from platform two.")
    assert emotion == EmotionType.NEUTRAL


def test_emotion_dynamic_tone_instructions():
    """Verify dynamic tone instructions adapt based on detected emotion."""
    inst_sad = EmotionClassifier.get_tone_instruction(EmotionType.SAD)
    assert "empathetic" in inst_sad.lower() or "comfort" in inst_sad.lower()

    inst_frustrated = EmotionClassifier.get_tone_instruction(EmotionType.FRUSTRATED)
    assert "calm" in inst_frustrated.lower() or "solution" in inst_frustrated.lower()

    inst_excited = EmotionClassifier.get_tone_instruction(EmotionType.EXCITED)
    assert "enthusiasm" in inst_excited.lower() or "celebrate" in inst_excited.lower()

    inst_neutral = EmotionClassifier.get_tone_instruction(EmotionType.NEUTRAL)
    assert inst_neutral == ""


# ─── 10.9: Connect Emotion to Animation ───────────────────────────────────────

def test_emotion_triggers_happy_animation(qtbot):
    """Verify detecting happy/excited emotion signals triggers CharacterState.HAPPY on pet animation."""
    mock_app = MagicMock(spec=QApplication)
    ctrl = ApplicationController(app=mock_app)
    
    mock_anim_ctrl = MagicMock()
    mock_pet = MagicMock()
    mock_pet.anim_controller = mock_anim_ctrl
    ctrl.pet_window = mock_pet

    # Happy emotion with high confidence
    ctrl._on_user_emotion_detected("happy", 0.85)
    mock_anim_ctrl.request_state.assert_called_with(CharacterState.HAPPY)

    mock_anim_ctrl.reset_mock()

    # Excited emotion with high confidence
    ctrl._on_user_emotion_detected("excited", 0.75)
    mock_anim_ctrl.request_state.assert_called_with(CharacterState.HAPPY)

    mock_anim_ctrl.reset_mock()

    # Low confidence or neutral emotion should not trigger happy animation
    ctrl._on_user_emotion_detected("happy", 0.30)
    mock_anim_ctrl.request_state.assert_not_called()

    ctrl._on_user_emotion_detected("neutral", 0.90)
    mock_anim_ctrl.request_state.assert_not_called()


# ─── 10.6 & 10.10: Settings UI & Privacy Controls ─────────────────────────────

def test_settings_dialog_memory_management(qtbot, tmp_path: Path):
    """Verify SettingsDialog memory UI operations: listing, toggling, clearing."""
    db_path = str(tmp_path / "settings_mem.db")
    init_db(db_path)
    mem_mgr = MemoryManager(db_path=db_path)
    mem_mgr.store_memory("project", "Autonomous drone navigation")
    mem_mgr.store_memory("preference", "Prefers Vim keybindings")

    config_path = str(tmp_path / "settings.json")
    cfg_mgr = ConfigManager(config_path=config_path)

    dlg = SettingsDialog(
        config_manager=cfg_mgr,
        memory_manager=mem_mgr,
        parent=None,
    )
    qtbot.addWidget(dlg)

    # Verify table initialized with 2 memories
    assert dlg.mem_table.rowCount() == 2

    # Verify toggles
    dlg.cb_memory_enabled.setChecked(False)
    assert cfg_mgr.get("memory.enabled") is False

    dlg.cb_auto_extract.setChecked(False)
    assert cfg_mgr.get("memory.auto_extract_enabled") is False

    # Search filter
    dlg.search_input.setText("drone")
    assert dlg.mem_table.rowCount() == 1

    dlg.search_input.setText("")
    assert dlg.mem_table.rowCount() == 2

    # Clear all memories
    mem_mgr.clear_all_memories()
    dlg._refresh_memories()
    assert dlg.mem_table.rowCount() == 0


def test_privacy_memory_disabled_skips_retrieval(temp_db: str, tmp_path: Path):
    """Verify that when memory is disabled, context clears memories and retrieval is bypassed."""
    mem_mgr = MemoryManager(db_path=temp_db)
    mem_mgr.store_memory("preference", "Secret user preference")

    config_path = str(tmp_path / "privacy_settings.json")
    cfg_mgr = ConfigManager(config_path=config_path)
    cfg_mgr.set("memory.enabled", False)

    from app.ai.ai_service import AIService
    service = AIService(config_manager=cfg_mgr, memory_manager=mem_mgr)
    
    assert service.memory_enabled is False

    # Calling set_memory_enabled(False) ensures context has no injected memories
    service.context.inject_memories(["Stale memory"])
    service.set_memory_enabled(False)
    assert len(service.context._injected_memories) == 0
    assert len(service.context._injected_summaries) == 0
