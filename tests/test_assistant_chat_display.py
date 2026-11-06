"""Phase 7 Integration Tests: Assistant Chat Display & Message Lifecycle.

Verifies:
1. Assistant response is saved with role="assistant" and status="completed".
2. User message remains visible in repository with role="user".
3. Assistant message is associated with the correct conversation_id.
4. Assistant message is not stored as a user message.
5. Streaming chunks broadcast message_id, chunk, and conversation_id.
6. Completion resets active generation IDs without duplicate database entries.
7. Errors update the assistant message to status="error" with descriptive message.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.server import app
from app.core.controller import ApplicationController
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh isolated database."""
    db_file = tmp_path / "test_chat_display.db"
    return DatabaseManager(db_path=db_file)


@pytest.fixture
def repo(test_db):
    """Provides a fresh ConversationRepository."""
    return ConversationRepository(db_manager=test_db)


@pytest.fixture
def client(repo):
    """TestClient wired with real repo and mocked AI/voice services."""
    app.state.conv_repo = repo

    mock_ai = MagicMock()
    mock_ai.ask.return_value = 101
    mock_ai._is_generating = False
    mock_ai._last_user_prompt = ""
    app.state.ai_service = mock_ai

    mock_ctrl = MagicMock()
    mock_ctrl.current_assistant_msg_id = None
    mock_ctrl.current_conv_id = None
    app.state.controller = mock_ctrl

    return TestClient(app)


def test_user_and_assistant_message_association(client, repo):
    """Verify user message and assistant placeholder are correctly associated."""
    conv = repo.create_conversation("Phase 7 Test Conversation")

    with patch("app.api.websocket.ws_manager.broadcast_sync") as mock_broadcast:
        response = client.post(
            f"/api/conversations/{conv.id}/messages",
            json={"content": "What is the capital of France?", "is_voice": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "dispatched"
        user_msg_id = data["user_message_id"]
        assistant_msg_id = data["assistant_message_id"]

        # 1. User message checks
        user_msg = repo.get_message(user_msg_id)
        assert user_msg is not None
        assert user_msg.role == "user"
        assert user_msg.content == "What is the capital of France?"
        assert user_msg.conversation_id == conv.id
        assert user_msg.status == "completed"

        # 2. Assistant message checks
        assistant_msg = repo.get_message(assistant_msg_id)
        assert assistant_msg is not None
        assert assistant_msg.role == "assistant"
        assert assistant_msg.conversation_id == conv.id
        assert assistant_msg.status == "streaming"

        # Verify not confused with user message
        assert assistant_msg.role != "user"
        assert assistant_msg.id != user_msg.id

        # Verify broadcast of message_added for both
        broadcast_types = [call[0][0] for call in mock_broadcast.call_args_list]
        assert broadcast_types.count("message_added") == 2


def test_streaming_and_completion_lifecycle(repo):
    """Verify _on_ai_chunk and _on_ai_complete update DB and broadcast properly."""
    conv = repo.create_conversation("Streaming Lifecycle Chat")
    user_msg = repo.add_message(conv.id, "user", "Tell me a short joke", status="completed")
    assistant_msg = repo.add_message(conv.id, "assistant", "", status="streaming")

    controller = ApplicationController.__new__(ApplicationController)
    controller.conv_repo = repo
    controller.current_assistant_msg_id = assistant_msg.id
    controller.current_conv_id = conv.id

    recorded_states = []
    signals.character_state_changed.connect(recorded_states.append)

    try:
        with patch("app.api.websocket.ws_manager.broadcast_sync") as mock_broadcast:
            # 1. Simulate token chunk streaming
            controller._on_ai_chunk("Why did the chicken ")
            controller._on_ai_chunk("cross the road?")

            chunk_calls = [call for call in mock_broadcast.call_args_list if call[0][0] == "ai_chunk"]
            assert len(chunk_calls) == 2
            assert chunk_calls[0][0][1]["chunk"] == "Why did the chicken "
            assert chunk_calls[0][0][1]["message_id"] == assistant_msg.id
            assert chunk_calls[0][0][1]["conversation_id"] == conv.id

            # 2. Simulate completion
            full_response = "Why did the chicken cross the road? To get to the other side!"
            controller._on_ai_complete(full_response)

            # Verify DB updated
            updated_assistant = repo.get_message(assistant_msg.id)
            assert updated_assistant.role == "assistant"
            assert updated_assistant.content == full_response
            assert updated_assistant.status == "completed"

            # Verify user message untouched
            stored_user = repo.get_message(user_msg.id)
            assert stored_user.role == "user"
            assert stored_user.content == "Tell me a short joke"

            # Verify completion broadcast
            complete_calls = [call for call in mock_broadcast.call_args_list if call[0][0] == "ai_complete"]
            assert len(complete_calls) == 1
            assert complete_calls[0][0][1]["text"] == full_response
            assert complete_calls[0][0][1]["message_id"] == assistant_msg.id
            assert complete_calls[0][0][1]["conversation_id"] == conv.id

            # Verify controller state cleaned up
            assert controller.current_assistant_msg_id is None
            assert controller.current_conv_id is None
            assert "idle" in recorded_states
    finally:
        signals.character_state_changed.disconnect(recorded_states.append)


def test_ai_error_updates_message_status(repo):
    """Verify _on_ai_error updates DB status to 'error' and broadcasts actionable error."""
    conv = repo.create_conversation("Error Handling Chat")
    assistant_msg = repo.add_message(conv.id, "assistant", "", status="streaming")

    controller = ApplicationController.__new__(ApplicationController)
    controller.conv_repo = repo
    controller.current_assistant_msg_id = assistant_msg.id
    controller.current_conv_id = conv.id

    recorded_states = []
    signals.character_state_changed.connect(recorded_states.append)

    try:
        with patch("app.api.websocket.ws_manager.broadcast_sync") as mock_broadcast:
            error_msg = "Model 'llama3.2:latest' is not installed in Ollama. Pull it with: 'ollama pull llama3.2'."
            controller._on_ai_error(error_msg)

            # Verify DB updated to error
            updated = repo.get_message(assistant_msg.id)
            assert updated.role == "assistant"
            assert updated.content == error_msg
            assert updated.status == "error"

            # Verify broadcast
            error_calls = [call for call in mock_broadcast.call_args_list if call[0][0] == "ai_error"]
            assert len(error_calls) == 1
            assert error_calls[0][0][1]["message"] == error_msg
            assert error_calls[0][0][1]["message_id"] == assistant_msg.id
            assert error_calls[0][0][1]["conversation_id"] == conv.id

            # Verify state reset
            assert controller.current_assistant_msg_id is None
            assert controller.current_conv_id is None
            assert "idle" in recorded_states
    finally:
        signals.character_state_changed.disconnect(recorded_states.append)
