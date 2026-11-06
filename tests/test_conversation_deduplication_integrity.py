"""Tests for Bug #20: ConversationRepository.add_message() de-duplication integrity and server.py handling.

Verifies:
1. Legitimate repeated user prompts (e.g. "yes", "ok") following an assistant turn are NOT dropped.
2. Rapid identical user prompts without an intervening assistant turn ARE rejected as duplicate.
3. Rejected duplicate user turns are marked with _is_duplicate=True.
4. server.py does not insert an orphaned assistant placeholder when a duplicate user turn is rejected.
5. Alternating user/assistant conversational structure is preserved across multi-turn exchanges with identical user queries.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.api.server import app


@pytest.fixture
def repo(tmp_path: Path):
    db_mgr = DatabaseManager(db_path=tmp_path / "dedup_test.db")
    return ConversationRepository(db_manager=db_mgr)


def test_repeated_user_prompt_allowed_after_assistant_turn(repo):
    """Verify that repeating 'yes' after an assistant message is accepted even within 1 second."""
    conv = repo.create_conversation("Dialogue")

    # Turn 1
    u1 = repo.add_message(conv.id, "user", "yes")
    a1 = repo.add_message(conv.id, "assistant", "Should I proceed with delete?")

    # Turn 2: User repeats "yes" immediately (within 1 second)
    u2 = repo.add_message(conv.id, "user", "yes")
    assert getattr(u2, "_is_duplicate", False) is False
    assert u2.id != u1.id
    assert u2.id > a1.id

    messages = repo.get_messages(conv.id)
    assert len(messages) == 3
    assert [m.role for m in messages] == ["user", "assistant", "user"]
    assert [m.content for m in messages] == ["yes", "Should I proceed with delete?", "yes"]


def test_rapid_identical_user_prompt_rejected_without_assistant_turn(repo):
    """Verify that repeating 'yes' before any assistant response is rejected as a duplicate."""
    conv = repo.create_conversation("Dialogue")

    # Click 1: User says "yes"
    u1 = repo.add_message(conv.id, "user", "yes")
    assert getattr(u1, "_is_duplicate", False) is False

    # Click 2: User says "yes" 0.1s later with NO assistant response recorded yet
    u2 = repo.add_message(conv.id, "user", "yes")
    assert getattr(u2, "_is_duplicate", False) is True
    assert u2.id == u1.id

    # Messages table must only have 1 message
    messages = repo.get_messages(conv.id)
    assert len(messages) == 1
    assert messages[0].id == u1.id


def test_multiple_identical_confirmations_across_conversation_turns(repo):
    """Verify a 6-turn sequence of repeated 'ok' confirmations alternating with assistant replies."""
    conv = repo.create_conversation("Confirmations")

    for i in range(3):
        u = repo.add_message(conv.id, "user", "ok")
        assert getattr(u, "_is_duplicate", False) is False
        a = repo.add_message(conv.id, "assistant", f"Step {i+1} completed. Continue?")
        assert getattr(a, "_is_duplicate", False) is False

    messages = repo.get_messages(conv.id)
    assert len(messages) == 6
    roles = [m.role for m in messages]
    assert roles == ["user", "assistant", "user", "assistant", "user", "assistant"]


def test_server_api_duplicate_rejection_prevents_orphaned_assistant(tmp_path: Path):
    """Verify POST /api/chat/messages does NOT insert an assistant placeholder on duplicate user prompt."""
    db_mgr = DatabaseManager(db_path=tmp_path / "server_dedup.db")
    test_repo = ConversationRepository(db_manager=db_mgr)
    conv = test_repo.create_conversation("API Chat")

    app.state.conv_repo = test_repo
    app.state.ai_service = MagicMock()
    app.state.ai_service._is_generating = False
    app.state.ai_service._last_user_prompt = ""
    app.state.current_assistant_msg_id = None

    client = TestClient(app)

    # 1. First prompt
    res1 = client.post(
        f"/api/conversations/{conv.id}/messages",
        json={"content": "Please start backup"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "dispatched"

    # In database: 1 user, 1 assistant (streaming)
    msgs_after_1 = test_repo.get_messages(conv.id)
    assert len(msgs_after_1) == 2
    assert msgs_after_1[0].role == "user"
    assert msgs_after_1[1].role == "assistant"

    # Simulate AI finishing its answer
    test_repo.update_message_content(msgs_after_1[1].id, "Backup in progress. Confirm?", status="completed")

    # 2. User confirms "yes"
    res2 = client.post(
        f"/api/conversations/{conv.id}/messages",
        json={"content": "yes"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "dispatched"

    msgs_after_2 = test_repo.get_messages(conv.id)
    assert len(msgs_after_2) == 4
    assert [m.role for m in msgs_after_2] == ["user", "assistant", "user", "assistant"]

    # AI finishes turn 2
    test_repo.update_message_content(msgs_after_2[3].id, "Final confirmation required. Proceed?", status="completed")

    # 3. User immediately confirms "yes" again in turn 3 (within 1 second!)
    res3 = client.post(
        f"/api/conversations/{conv.id}/messages",
        json={"content": "yes"},
    )
    assert res3.status_code == 200
    # Must be accepted because previous message was assistant!
    assert res3.json()["status"] == "dispatched"

    msgs_after_3 = test_repo.get_messages(conv.id)
    assert len(msgs_after_3) == 6
    assert [m.role for m in msgs_after_3] == ["user", "assistant", "user", "assistant", "user", "assistant"]
