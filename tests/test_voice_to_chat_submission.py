"""Tests verifying that transcribed voice text appears in chat and reaches the backend."""

from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from app.api.server import app
from app.api.websocket import ws_manager
from app.core.controller import ApplicationController
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager


@pytest.fixture
def api_client(tmp_path):
    """TestClient setup with initialized DB repository and mock AI service."""
    db_file = tmp_path / "voice_chat_test.db"
    db_manager = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_manager)

    mock_ai = MagicMock()
    mock_ai._is_generating = False
    mock_ai._last_user_prompt = ""
    mock_ai.ask.return_value = 101

    app.state.conv_repo = repo
    app.state.ai_service = mock_ai
    app.state.config_manager = None
    app.state.current_assistant_msg_id = None
    app.state.active_conversation_id = None

    client = TestClient(app)
    return client, repo, mock_ai


def test_empty_transcription_does_not_submit_and_broadcasts_error():
    """Verify empty or whitespace-only transcription triggers voice_error and no ask()."""
    mock_ai = MagicMock()
    mock_voice = MagicMock()
    mock_repo = MagicMock()

    controller = ApplicationController.__new__(ApplicationController)
    controller.ai_service = mock_ai
    controller.voice_service = mock_voice
    controller.conv_repo = mock_repo

    with patch.object(ws_manager, "broadcast_sync") as mock_broadcast:
        controller._on_voice_transcription_ready("   ", "en")

        # Must NOT call AI or add message
        mock_ai.ask.assert_not_called()
        mock_repo.add_message.assert_not_called()

        # Must broadcast voice_error
        mock_broadcast.assert_called_once()
        event_type, payload = mock_broadcast.call_args[0]
        assert event_type == "voice_error"
        assert "No speech was detected" in payload["message"] or "No clear speech detected" in payload["message"]


def test_finalized_transcription_broadcasts_to_connected_ui():
    """Verify that when UI is connected via WebSocket, controller broadcasts transcription event."""
    mock_ai = MagicMock()
    mock_voice = MagicMock()
    mock_voice.command_dispatcher.dispatch.return_value = False
    mock_repo = MagicMock()

    controller = ApplicationController.__new__(ApplicationController)
    controller.ai_service = mock_ai
    controller.voice_service = mock_voice
    controller.conv_repo = mock_repo

    dummy_client = MagicMock()
    ws_manager.active_connections.add(dummy_client)

    try:
        with patch.object(ws_manager, "broadcast_sync") as mock_broadcast:
            controller._on_voice_transcription_ready("Hello, how are you?", "en")

            # Must broadcast 'transcription' to UI so UI reuses standard sendMessage path
            mock_broadcast.assert_called_once_with(
                "transcription",
                {"text": "Hello, how are you?", "language": "en"}
            )
            # Controller does not directly duplicate DB message when UI is active
            mock_ai.ask.assert_not_called()
    finally:
        ws_manager.active_connections.discard(dummy_client)


def test_voice_message_submission_to_backend_endpoint(api_client):
    """Verify that posting voice text to /api/conversations/{conv_id}/messages persists USER message."""
    client, repo, mock_ai = api_client

    conv = repo.create_conversation("Voice Turn Test")
    spoken_text = "Hello, how are you?"

    with patch.object(ws_manager, "broadcast_sync") as mock_broadcast:
        response = client.post(
            f"/api/conversations/{conv.id}/messages",
            json={"content": spoken_text, "is_voice": True},
        )

        assert response.status_code == 200
        res_data = response.json()
        assert res_data["status"] == "dispatched"
        assert res_data["user_message_id"] is not None
        assert res_data["assistant_message_id"] is not None

        # Verify DB contents
        messages = repo.get_messages(conv.id)
        assert len(messages) == 2

        user_msg = messages[0]
        assert user_msg.role == "user"
        assert user_msg.content == "Hello, how are you?"
        assert user_msg.status == "completed"

        assistant_msg = messages[1]
        assert assistant_msg.role == "assistant"
        assert assistant_msg.status == "streaming"

        # Verify AI service received exact prompt with is_voice=True
        mock_ai.ask.assert_called_once_with(
            user_prompt="Hello, how are you?",
            is_voice=True,
            response_style=None,
        )

        # Verify message_added broadcast was emitted for both
        broadcast_events = [call[0][0] for call in mock_broadcast.call_args_list]
        assert broadcast_events.count("message_added") == 2
