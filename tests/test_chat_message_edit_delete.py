import pytest
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.memory.database import DatabaseManager
from app.memory.conversation_repository import ConversationRepository
from app.api.server import create_app


@pytest.fixture
def temp_repo(tmp_path: Path):
    db_mgr = DatabaseManager(db_path=tmp_path / "test_chat.db")
    repo = ConversationRepository(db_manager=db_mgr)
    return repo


def test_conversation_repo_delete_and_pair(temp_repo):
    conv = temp_repo.create_conversation("Test Conv")
    cid = conv.id

    # Add message pair 1
    u1 = temp_repo.add_message(cid, "user", "Hello there")
    a1 = temp_repo.add_message(cid, "assistant", "General Kenobi")

    # Add message pair 2
    u2 = temp_repo.add_message(cid, "user", "How are you?")
    a2 = temp_repo.add_message(cid, "assistant", "I am doing well!")

    # Verify pairing lookup
    assert temp_repo.get_paired_assistant_message(u1.id).id == a1.id
    assert temp_repo.get_paired_user_message(a1.id).id == u1.id
    assert temp_repo.get_paired_assistant_message(u2.id).id == a2.id
    assert temp_repo.get_paired_user_message(a2.id).id == u2.id

    # Delete pair 1 via user message
    deleted_ids = temp_repo.delete_message_pair(u1.id)
    assert set(deleted_ids) == {u1.id, a1.id}

    # Verify pair 1 is gone, pair 2 remains
    msgs = temp_repo.get_messages(cid)
    assert len(msgs) == 2
    assert msgs[0].id == u2.id
    assert msgs[1].id == a2.id

    # Delete pair 2 via assistant message
    deleted_ids2 = temp_repo.delete_message_pair(a2.id)
    assert set(deleted_ids2) == {u2.id, a2.id}
    assert len(temp_repo.get_messages(cid)) == 0


def test_conversation_repo_edit_content(temp_repo):
    conv = temp_repo.create_conversation("Test Edit")
    cid = conv.id
    u1 = temp_repo.add_message(cid, "user", "Original question")
    a1 = temp_repo.add_message(cid, "assistant", "Original answer")

    # Update content
    res1 = temp_repo.update_message_content(u1.id, "Edited question")
    assert res1 is True
    res2 = temp_repo.update_message_content(a1.id, "Edited answer", status="completed")
    assert res2 is True

    # Check updated messages
    updated_u = temp_repo.get_message(u1.id)
    assert updated_u.content == "Edited question"
    updated_a = temp_repo.get_message(a1.id)
    assert updated_a.content == "Edited answer"


def test_api_endpoints_delete_edit_retry(temp_repo):
    app = create_app()
    app.state.conv_repo = temp_repo

    mock_ai = MagicMock()
    mock_ai.ask.return_value = "gen-12345"
    mock_ai._last_user_prompt = "Last prompt"
    mock_ai.active_conversation_id = None
    app.state.ai_service = mock_ai

    client = TestClient(app)

    conv = temp_repo.create_conversation("API Test Conv")
    cid = conv.id
    u1 = temp_repo.add_message(cid, "user", "What is the capital of France?")
    a1 = temp_repo.add_message(cid, "assistant", "Paris is the capital of France.")
    u2 = temp_repo.add_message(cid, "user", "What is the capital of Germany?")
    a2 = temp_repo.add_message(cid, "assistant", "Berlin.")

    # 1. Edit a message via PATCH /api/messages/{id}
    edit_resp = client.patch(f"/api/messages/{a1.id}", json={"content": "Paris, France!"})
    assert edit_resp.status_code == 200
    assert edit_resp.json()["content"] == "Paris, France!"
    assert temp_repo.get_message(a1.id).content == "Paris, France!"

    # 2. Retry an assistant message via POST /api/messages/{id}/retry
    # Crucial constraint: must NOT delete or remove other messages!
    retry_resp = client.post(f"/api/messages/{a1.id}/retry", json={})
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "dispatched"
    assert retry_resp.json()["assistant_message_id"] == a1.id
    mock_ai.ask.assert_called_with(user_prompt="What is the capital of France?", is_voice=False)

    # Verify ALL 4 messages still exist in repository! None were truncated or removed
    all_msgs = temp_repo.get_messages(cid)
    assert len(all_msgs) == 4
    # The retried assistant message is set to empty streaming state
    retried_msg = temp_repo.get_message(a1.id)
    assert retried_msg.content == ""
    assert retried_msg.status == "streaming"
    # Other messages are intact
    assert temp_repo.get_message(u2.id).content == "What is the capital of Germany?"
    assert temp_repo.get_message(a2.id).content == "Berlin."

    # 3. Delete pair via DELETE /api/messages/{id}?pair=true
    del_resp = client.delete(f"/api/messages/{u2.id}?pair=true")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True
    assert set(del_resp.json()["message_ids"]) == {u2.id, a2.id}

    # Verify remaining messages
    remaining = temp_repo.get_messages(cid)
    assert len(remaining) == 2
    assert {m.id for m in remaining} == {u1.id, a1.id}


def test_user_delete_automatically_deletes_ai_response(temp_repo):
    """When a user deletes their message, any subsequent AI assistant message(s) are automatically deleted."""
    conv = temp_repo.create_conversation("Delete Test")
    cid = conv.id
    u1 = temp_repo.add_message(cid, "user", "My name is Gaurav")
    a1 = temp_repo.add_message(cid, "assistant", "Hello Gaurav!")
    u2 = temp_repo.add_message(cid, "user", "What's the weather?")
    a2 = temp_repo.add_message(cid, "assistant", "It is sunny.")

    # Delete user message u1
    deleted_ids = temp_repo.delete_message_pair(u1.id)
    assert set(deleted_ids) == {u1.id, a1.id}

    # Verify only turn 2 remains
    msgs = temp_repo.get_messages(cid)
    assert len(msgs) == 2
    assert [m.id for m in msgs] == [u2.id, a2.id]

