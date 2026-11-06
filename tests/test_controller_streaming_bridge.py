"""Tests for Bug 12: WebSocket Streaming Bridge in ApplicationController.

Verifies that ApplicationController natively bridges:
1. signals.ai_response_chunk -> WebSocket "ai_chunk" event with message_id and text chunk
2. signals.ai_response_complete -> SQLite repository status="completed" update + WebSocket "ai_complete"
3. signals.ai_error_occurred -> SQLite repository status="error" update + WebSocket "ai_error"
4. signals.ai_generation_cancelled -> SQLite repository status="cancelled" update + WebSocket "ai_cancelled"
5. Character state, voice state, and emotion WebSocket bridges
6. Deduplication: setup_signal_bridges skips duplicate listeners when ApplicationController is active
7. REST endpoint POST /api/conversations/{id}/messages synchronizes current_assistant_msg_id to controller
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.server import app as fastapi_app
from app.api.websocket import ws_manager
from app.core.controller import ApplicationController
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.settings.config_manager import ConfigManager
from main_api import setup_signal_bridges, teardown_signal_bridges


SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def controller_fixture(qapp_instance):
    """Fixture providing initialized ApplicationController with mocked windows and in-memory repo."""
    teardown_signal_bridges()
    config_file = SCRATCH_DIR / "test_ctrl_streaming_cfg.json"
    cfg = ConfigManager(config_path=config_file)
    mock_repo = MagicMock(spec=ConversationRepository)

    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)
    ctrl.conv_repo = mock_repo

    mock_ai = MagicMock()
    mock_voice = MagicMock()
    mock_voice.mode = "off"
    mock_voice.tts_enabled = False

    with patch("app.ai.ai_service.AIService", return_value=mock_ai), \
         patch("app.voice.voice_service.VoiceService", return_value=mock_voice), \
         patch("app.desktop.modern_chat_window.ModernChatWindow", return_value=MagicMock()), \
         patch("app.desktop.voice_window.VoiceWindow", return_value=MagicMock()), \
         patch.object(ctrl, "_start_api_server"):
        init_ok = ctrl.initialize()
        assert init_ok is True

    fastapi_app.state.controller = ctrl
    fastapi_app.state.conv_repo = mock_repo
    fastapi_app.state.config_manager = cfg

    yield ctrl, mock_repo

    ctrl.shutdown()
    teardown_signal_bridges()
    fastapi_app.state.controller = None
    fastapi_app.state.current_assistant_msg_id = None


def test_controller_ai_chunk_streaming(controller_fixture, qapp_instance):
    """Verify ApplicationController routes ai_response_chunk to WebSocket with message_id."""
    ctrl, _ = controller_fixture
    events = []

    with patch.object(ws_manager, "broadcast_sync", side_effect=lambda t, d=None: events.append((t, d))):
        ctrl.current_assistant_msg_id = 101

        signals.ai_response_chunk.emit("Hello ")
        qapp_instance.processEvents()

        signals.ai_response_chunk.emit("World!")
        qapp_instance.processEvents()

        chunk_events = [e for e in events if e[0] == "ai_chunk"]
        assert len(chunk_events) == 2
        assert chunk_events[0][1] == {"chunk": "Hello ", "message_id": 101, "conversation_id": None}
        assert chunk_events[1][1] == {"chunk": "World!", "message_id": 101, "conversation_id": None}


def test_controller_ai_complete_flow(controller_fixture, qapp_instance):
    """Verify ai_response_complete updates SQLite message to completed and broadcasts ai_complete."""
    ctrl, mock_repo = controller_fixture
    events = []

    with patch.object(ws_manager, "broadcast_sync", side_effect=lambda t, d=None: events.append((t, d))):
        ctrl.current_assistant_msg_id = 202
        fastapi_app.state.current_assistant_msg_id = 202

        signals.ai_response_complete.emit("Complete answer text")
        qapp_instance.processEvents()

        # Check repository was updated
        mock_repo.update_message_content.assert_called_once_with(202, "Complete answer text", status="completed")

        # Check WebSocket broadcast
        complete_events = [e for e in events if e[0] == "ai_complete"]
        assert len(complete_events) == 1
        assert complete_events[0][1] == {"text": "Complete answer text", "message_id": 202, "conversation_id": None}

        # Check active message IDs reset
        assert ctrl.current_assistant_msg_id is None
        assert fastapi_app.state.current_assistant_msg_id is None


def test_controller_ai_error_flow(controller_fixture, qapp_instance):
    """Verify ai_error_occurred updates SQLite message to error and broadcasts ai_error."""
    ctrl, mock_repo = controller_fixture
    events = []

    with patch.object(ws_manager, "broadcast_sync", side_effect=lambda t, d=None: events.append((t, d))):
        ctrl.current_assistant_msg_id = 303
        fastapi_app.state.current_assistant_msg_id = 303

        signals.ai_error_occurred.emit("Inference failure: OOM")
        qapp_instance.processEvents()

        # Check repository was updated
        mock_repo.update_message_content.assert_called_once_with(303, "Inference failure: OOM", status="error")

        # Check WebSocket broadcast
        error_events = [e for e in events if e[0] == "ai_error"]
        assert len(error_events) == 1
        assert error_events[0][1] == {"message": "Inference failure: OOM", "message_id": 303, "conversation_id": None}

        # Check active message IDs reset
        assert ctrl.current_assistant_msg_id is None
        assert fastapi_app.state.current_assistant_msg_id is None


def test_controller_ai_cancelled_flow(controller_fixture, qapp_instance):
    """Verify ai_generation_cancelled updates SQLite message to cancelled and broadcasts ai_cancelled."""
    ctrl, mock_repo = controller_fixture
    events = []

    with patch.object(ws_manager, "broadcast_sync", side_effect=lambda t, d=None: events.append((t, d))):
        ctrl.current_assistant_msg_id = 404
        fastapi_app.state.current_assistant_msg_id = 404

        signals.ai_generation_cancelled.emit()
        qapp_instance.processEvents()

        # Check repository was updated
        mock_repo.update_message_content.assert_called_once_with(404, "[Cancelled by user]", status="cancelled")

        # Check WebSocket broadcast
        cancel_events = [e for e in events if e[0] == "ai_cancelled"]
        assert len(cancel_events) == 1
        assert cancel_events[0][1] == {"message_id": 404, "conversation_id": None}

        # Check active message IDs reset
        assert ctrl.current_assistant_msg_id is None
        assert fastapi_app.state.current_assistant_msg_id is None


def test_controller_ui_state_bridges(controller_fixture, qapp_instance):
    """Verify character_state_changed, voice_state_changed, and emotion events are broadcast."""
    _, _ = controller_fixture
    events = []

    with patch.object(ws_manager, "broadcast_sync", side_effect=lambda t, d=None: events.append((t, d))):
        signals.character_state_changed.emit("thinking")
        qapp_instance.processEvents()
        assert ("char_state", {"state": "thinking"}) in events

        signals.voice_state_changed.emit("continuous")
        qapp_instance.processEvents()
        assert ("voice_state", {"state": "continuous"}) in events

        signals.user_emotion_detected.emit("happy", 0.88)
        qapp_instance.processEvents()
        assert ("user_emotion", {"emotion": "happy", "confidence": 0.88}) in events


def test_setup_signal_bridges_skips_when_controller_active(controller_fixture, qapp_instance):
    """Verify setup_signal_bridges does not register duplicate listeners when controller is active."""
    ctrl, mock_repo = controller_fixture
    events = []

    with patch.object(ws_manager, "broadcast_sync", side_effect=lambda t, d=None: events.append((t, d))):
        # Call setup_signal_bridges while controller is attached to fastapi_app.state
        setup_signal_bridges(qapp_instance, mock_repo)

        ctrl.current_assistant_msg_id = 505
        signals.ai_response_chunk.emit("No duplicates")
        qapp_instance.processEvents()

        chunk_events = [e for e in events if e[0] == "ai_chunk"]
        # Must be exactly 1 event (from ApplicationController), NOT 2 events
        assert len(chunk_events) == 1


def test_post_message_syncs_controller_assistant_msg_id(controller_fixture):
    """Verify sending a message via POST endpoint sets ctrl.current_assistant_msg_id."""
    ctrl, mock_repo = controller_fixture

    dummy_user_msg = MagicMock(id=601, conversation_id="conv_1", role="user", content="Hi", created_at=1.0, status="completed")
    dummy_asst_msg = MagicMock(id=602, conversation_id="conv_1", role="assistant", content="", created_at=1.0, status="streaming")
    mock_repo.add_message.side_effect = [dummy_user_msg, dummy_asst_msg]

    mock_ai = MagicMock()
    mock_ai.ask.return_value = 1
    fastapi_app.state.ai_service = mock_ai

    client = TestClient(fastapi_app)
    resp = client.post("/api/conversations/conv_1/messages", json={"content": "Hi"})
    assert resp.status_code == 200

    assert ctrl.current_assistant_msg_id == 602
    assert fastapi_app.state.current_assistant_msg_id == 602
