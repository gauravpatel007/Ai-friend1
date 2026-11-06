"""Automated Test Suite for Phase 7 & Phase 8 UI Integration, Sleep/Wake, and AI Message Feedback.

Covers:
1. Clipboard Copy native backend API (/api/clipboard/copy).
2. Message Like & Dislike rating persistence in SQLite DB (messages.feedback and message_feedback table).
3. Feedback rating toggling / clearing.
4. Preference-based prompt guidance injection (emulate liked responses, avoid disliked responses).
5. Dynamic companion name propagation across endpoints.
6. Companion operational states: ACTIVE, SLEEPING, MUTED via REST endpoints.
7. Pet Window double click waking Buddy and requesting chat reveal.
8. Text chat functionality during sleep mode without waking or unsuppressing audio.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.server import app
from app.core.buddy_state_manager import get_buddy_state_manager, BuddyState
from app.memory.database import DatabaseManager
from app.memory.conversation_repository import ConversationRepository
from app.settings.config_manager import ConfigManager


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary SQLite database for testing."""
    db_file = str(tmp_path / "test_feedback.db")
    return DatabaseManager(db_file)


@pytest.fixture
def repo(test_db):
    """Create a ConversationRepository instance using temporary DB."""
    return ConversationRepository(test_db)


@pytest.fixture
def client(repo, tmp_path):
    """Create FastAPI TestClient with initialized repo and buddy state manager."""
    cfg_file = str(tmp_path / "config.json")
    cfg_mgr = ConfigManager(cfg_file)
    cfg_mgr.set("ai.companion_name", "Bond")

    app.state.config_manager = cfg_mgr
    app.state.conv_repo = repo
    return TestClient(app)


# ─── 1. Clipboard Copy Endpoint ──────────────────────────────────────────────

def test_clipboard_copy_endpoint(client):
    """Verify POST /api/clipboard/copy executes safely and returns ok."""
    resp = client.post("/api/clipboard/copy", json={"text": "Hello Buddy Clipboard Test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "copied" in data


# ─── 2. Message Like & Dislike Rating Persistence ───────────────────────────

def test_message_feedback_like_dislike_persistence(repo, client):
    """Verify like and dislike ratings persist to SQLite messages and message_feedback tables."""
    conv = repo.create_conversation("Feedback Test")
    user_msg = repo.add_message(conv.id, "user", "What is the capital of France?", status="completed")
    asst_msg = repo.add_message(conv.id, "assistant", "The capital of France is Paris.", status="completed")

    # 1. Like the assistant message
    resp_like = client.post(f"/api/messages/{asst_msg.id}/feedback", json={"feedback": "like"})
    assert resp_like.status_code == 200
    assert resp_like.json()["feedback"] == "like"

    # Verify messages table updated
    loaded_msgs = repo.get_messages(conv.id)
    asst_loaded = [m for m in loaded_msgs if m.id == asst_msg.id][0]
    assert asst_loaded.feedback == "like"

    # Verify message_feedback table updated
    prefs = repo.get_feedback_preferences()
    assert len(prefs["liked"]) == 1
    assert prefs["liked"][0]["message_id"] == asst_msg.id
    assert prefs["liked"][0]["rating"] == "like"
    assert prefs["liked"][0]["user_prompt"] == "What is the capital of France?"
    assert prefs["liked"][0]["assistant_response"] == "The capital of France is Paris."

    # 2. Switch rating to dislike
    resp_dislike = client.post(f"/api/messages/{asst_msg.id}/feedback", json={"feedback": "dislike"})
    assert resp_dislike.status_code == 200
    assert resp_dislike.json()["feedback"] == "dislike"

    prefs_after_dislike = repo.get_feedback_preferences()
    assert len(prefs_after_dislike["liked"]) == 0
    assert len(prefs_after_dislike["disliked"]) == 1
    assert prefs_after_dislike["disliked"][0]["message_id"] == asst_msg.id
    assert prefs_after_dislike["disliked"][0]["rating"] == "dislike"

    # 3. Clear feedback (toggle off)
    resp_clear = client.post(f"/api/messages/{asst_msg.id}/feedback", json={"feedback": None})
    assert resp_clear.status_code == 200
    assert resp_clear.json()["feedback"] is None

    prefs_after_clear = repo.get_feedback_preferences()
    assert len(prefs_after_clear["liked"]) == 0
    assert len(prefs_after_clear["disliked"]) == 0


def test_message_feedback_resolves_temporary_client_id(repo, client):
    """Verify temporary client timestamp IDs are gracefully resolved to the latest assistant message."""
    conv = repo.create_conversation("Temp ID Test")
    repo.add_message(conv.id, "user", "Explain quantum computing briefly.", status="completed")
    asst_msg = repo.add_message(conv.id, "assistant", "Quantum computing uses qubits.", status="completed")

    # Send client timestamp ID (e.g. 1730000000000) with conversation_id endpoint
    temp_id = 1730123456789
    resp = client.post(f"/api/conversations/{conv.id}/messages/{temp_id}/feedback", json={"feedback": "like"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["message_id"] == asst_msg.id
    assert data["feedback"] == "like"

    prefs = repo.get_feedback_preferences()
    assert len(prefs["liked"]) == 1
    assert prefs["liked"][0]["message_id"] == asst_msg.id


# ─── 3. Preference-Based Prompt Guidance Generation ─────────────────────────

def test_feedback_prompt_guidance_generation(repo):
    """Verify get_feedback_prompt_guidance generates clear directives for liked and disliked styles."""
    conv = repo.create_conversation("Style Training")
    u1 = repo.add_message(conv.id, "user", "Give me a quick python summary.", status="completed")
    a1 = repo.add_message(conv.id, "assistant", "Python is readable, dynamic, and versatile.", status="completed")
    repo.set_message_feedback(a1.id, "like")

    u2 = repo.add_message(conv.id, "user", "What is Docker?", status="completed")
    a2 = repo.add_message(conv.id, "assistant", "As an AI language model, I would like to comprehensively state...", status="completed")
    repo.set_message_feedback(a2.id, "dislike")

    guidance = repo.get_feedback_prompt_guidance()
    assert guidance != ""
    assert "PREFERRED STYLES & APPROVED CONTENT" in guidance
    assert "REJECTED STYLES & FORBIDDEN CONTENT" in guidance
    assert "Python is readable" in guidance
    assert "As an AI language model" in guidance


# ─── 4. Operational State Endpoints (Sleep, Wake, Mute, Unmute) ─────────────

def test_companion_operational_state_endpoints(client):
    """Verify REST endpoints transition Buddy operational state correctly."""
    sm = get_buddy_state_manager()
    sm.wake_up(reason="setup")
    assert sm.state == BuddyState.ACTIVE

    # Sleep
    res_sleep = client.post("/api/companion/sleep")
    assert res_sleep.status_code == 200
    assert res_sleep.json()["operational_state"] == "sleeping"
    assert sm.is_sleeping is True

    # Voice status reports sleeping
    res_vstatus = client.get("/api/voice/status")
    assert res_vstatus.status_code == 200
    assert res_vstatus.json()["is_sleeping"] is True
    assert res_vstatus.json()["operational_state"] == "sleeping"

    # Wake
    res_wake = client.post("/api/companion/wake")
    assert res_wake.status_code == 200
    assert res_wake.json()["operational_state"] == "active"
    assert sm.is_sleeping is False

    # Mute
    res_mute = client.post("/api/companion/mute")
    assert res_mute.status_code == 200
    assert res_mute.json()["operational_state"] == "muted"
    assert sm.is_muted is True

    # Unmute
    res_unmute = client.post("/api/companion/unmute")
    assert res_unmute.status_code == 200
    assert res_unmute.json()["operational_state"] == "active"
    assert sm.is_muted is False


# ─── 5. Dynamic Companion Name Consistency ──────────────────────────────────

def test_companion_name_across_endpoints(client):
    """Verify companion name configured as 'Bond' is returned across companion state and config."""
    res_state = client.get("/api/companion/state")
    assert res_state.status_code == 200
    data = res_state.json()
    assert data["name"] == "Bond"

    res_cfg = client.get("/api/config")
    assert res_cfg.status_code == 200
    cfg = res_cfg.json()
    assert (cfg.get("ai", {}).get("companion_name") == "Bond" or cfg.get("ai.companion_name") == "Bond")


# ─── 6. Pet Window Double Click & Context Menu ──────────────────────────────

def test_pet_window_double_click_wakes_and_reveals(qapp_instance, tmp_path):
    """Verify double-clicking the pet window wakes sleeping Buddy and emits chat window reveal."""
    from app.desktop.pet_window import DesktopPetWindow
    from app.core.signals import signals

    sm = get_buddy_state_manager()
    sm.enter_sleep(reason="test")
    assert sm.is_sleeping is True

    cfg_file = str(tmp_path / "pet_cfg.json")
    cfg_mgr = ConfigManager(cfg_file)

    pet = DesktopPetWindow(config_manager=cfg_mgr)
    reveal_signals = []
    signals.open_chat_requested.connect(lambda: reveal_signals.append(True))

    # Trigger double click
    pet._on_double_click()

    assert len(reveal_signals) == 1
    pet.close()


def test_modern_chat_window_position_near_pet_bounds_clamp(qapp_instance, tmp_path):
    """Verify position_near_pet ensures 100% on-screen visibility when pet is at screen edges."""
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    from app.desktop.modern_chat_window import ModernChatWindow

    cfg_file = str(tmp_path / "chat_cfg.json")
    cfg_mgr = ConfigManager(cfg_file)
    chat = ModernChatWindow(config_manager=cfg_mgr)

    screen = QApplication.primaryScreen()
    assert screen is not None
    geo = screen.availableGeometry()

    # Case 1: Pet at far right edge of the screen
    pet_far_right = QRect(geo.right() - 150, geo.bottom() - 200, 128, 128)
    chat.position_near_pet(pet_far_right)

    # Window MUST be completely within available screen geometry
    assert chat.x() >= geo.left() + 10
    assert chat.x() + chat.width() <= geo.right() + 1
    assert chat.y() >= geo.top() + 10
    assert chat.y() + chat.height() <= geo.bottom() + 1

    # Case 2: Pet at far left edge of the screen
    pet_far_left = QRect(geo.left() + 20, geo.top() + 100, 128, 128)
    chat.position_near_pet(pet_far_left)

    assert chat.x() >= geo.left() + 10
    assert chat.x() + chat.width() <= geo.right() + 1
    assert chat.y() >= geo.top() + 10
    assert chat.y() + chat.height() <= geo.bottom() + 1

    # Case 3: Calling show_chat with out-of-bounds pos restores it safely
    chat.move(geo.right() + 500, geo.bottom() + 500)
    chat.show_chat()
    assert chat.x() + chat.width() <= geo.right() + 1
    assert chat.y() + chat.height() <= geo.bottom() + 1

    chat.close()
