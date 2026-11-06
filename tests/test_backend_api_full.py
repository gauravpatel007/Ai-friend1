"""Integration tests for all newly restored FastAPI endpoints and WebSocket signals."""

import pytest
from fastapi.testclient import TestClient
from PySide6.QtCore import QCoreApplication

from app.api.server import app
from app.memory.conversation_repository import ConversationRepository
from app.settings.config_manager import ConfigManager
from app.ai.ai_service import AIService
from main_api import setup_signal_bridges, teardown_signal_bridges


@pytest.fixture
def api_client(qapp_instance):
    cfg = ConfigManager()
    repo = ConversationRepository()
    ai = AIService(config_manager=cfg)

    app.state.config_manager = cfg
    app.state.conv_repo = repo
    app.state.ai_service = ai
    app.state.voice_service = None
    app.state.current_assistant_msg_id = None

    setup_signal_bridges(qapp_instance, repo)
    yield TestClient(app)
    teardown_signal_bridges()


def test_api_health_endpoint(api_client):
    res = api_client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["companion"] == "AI Desktop Friend"


def test_api_voice_endpoints(api_client):
    # Test voice status
    status_res = api_client.get("/api/voice/status")
    assert status_res.status_code == 200

    # Test voice toggle
    toggle_res = api_client.post("/api/voice/toggle")
    assert toggle_res.status_code == 200

    # Test voice speed
    speed_res = api_client.post("/api/voice/speed", json={"speed": 1.4})
    assert speed_res.status_code == 200
    assert speed_res.json()["speed"] == 1.4

    # Test voice volume
    vol_res = api_client.post("/api/voice/volume", json={"volume": 75})
    assert vol_res.status_code == 200
    assert vol_res.json()["volume"] == 0.75

    # Test voice engine selection
    engine_res = api_client.post("/api/voice/engine", json={"engine": "kokoro"})
    assert engine_res.status_code == 200
    assert engine_res.json()["engine"] == "kokoro"

    # Test audio devices list
    devices_res = api_client.get("/api/voice/devices")
    assert devices_res.status_code == 200
    assert "input_devices" in devices_res.json()


def test_api_offline_conversation_flow(api_client, qapp_instance):
    # Create conversation
    create_res = api_client.post("/api/conversations", json={"title": "Automated Offline Test"})
    assert create_res.status_code == 200
    conv_id = create_res.json()["id"]

    # Send message
    send_res = api_client.post(f"/api/conversations/{conv_id}/messages", json={"content": "Hello Buddy, how are you?"})
    assert send_res.status_code == 200
    assert send_res.json()["status"] == "dispatched"

    # Process events to allow streaming
    for _ in range(30):
        qapp_instance.processEvents()

    # Verify messages
    msgs_res = api_client.get(f"/api/conversations/{conv_id}/messages")
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()
    assert len(msgs) >= 2
    user_msg = msgs[0]
    assistant_msg = msgs[1]

    assert user_msg["role"] == "user"
    assert user_msg["status"] == "completed"
    assert assistant_msg["role"] == "assistant"


def test_api_rename_conversation(api_client):
    # 1. Create a conversation
    create_res = api_client.post("/api/conversations", json={"title": "Original Title"})
    assert create_res.status_code == 200
    conv_id = create_res.json()["id"]
    assert create_res.json()["title"] == "Original Title"

    # 2. Rename the conversation via /title
    rename_res = api_client.patch(f"/api/conversations/{conv_id}/title", json={"title": "Updated Modern Chat Title"})
    assert rename_res.status_code == 200
    data = rename_res.json()
    assert data["status"] == "ok"
    assert data["title"] == "Updated Modern Chat Title"

    # 2b. Rename the conversation via root PATCH /api/conversations/{conv_id}
    rename_root_res = api_client.patch(f"/api/conversations/{conv_id}", json={"title": "Rename"})
    assert rename_root_res.status_code == 200
    assert rename_root_res.json()["title"] == "Rename"

    # 3. Verify in conversation list
    list_res = api_client.get("/api/conversations")
    assert list_res.status_code == 200
    convs = {c["id"]: c["title"] for c in list_res.json()}
    assert convs[conv_id] == "Rename"

    # 4. Attempt rename non-existent conversation returns 404
    bad_res = api_client.patch("/api/conversations/non-existent-id/title", json={"title": "New Title"})
    assert bad_res.status_code == 404


def test_api_chat_export_endpoint(api_client):
    # 1. Create a conversation and add messages
    create_res = api_client.post("/api/conversations", json={"title": "Exportable Discussion"})
    assert create_res.status_code == 200
    conv_id = create_res.json()["id"]

    # 2. Export with valid conversation ID
    export_res = api_client.post("/api/chat/export", json={"conversation_id": conv_id})
    assert export_res.status_code == 200
    data = export_res.json()
    assert data["conversation_id"] == conv_id
    assert "Exportable Discussion" in data["title"]
    assert "# Exportable Discussion" in data["markdown"]

    # 3. Export with empty conversation_id falls back to the latest conversation
    empty_export = api_client.post("/api/chat/export", json={"conversation_id": ""})
    assert empty_export.status_code == 200
    assert "markdown" in empty_export.json()

    # 4. Export with unknown ID falls back gracefully without 404 or 500 error
    fallback_export = api_client.post("/api/chat/export", json={"conversation_id": "non_existent_conv"})
    assert fallback_export.status_code == 200
    assert "markdown" in fallback_export.json()


def test_api_pet_overlay_endpoints(api_client):
    # 1. Get status
    status_res = api_client.get("/api/pet/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert "always_on_top" in status_data
    assert "visible" in status_data

    # 2. Toggle always on top to True
    top_res1 = api_client.post("/api/pet/topmost", json={"always_on_top": True})
    assert top_res1.status_code == 200
    assert top_res1.json()["always_on_top"] is True

    # Check status
    assert api_client.get("/api/pet/status").json()["always_on_top"] is True

    # 3. Toggle always on top to False
    top_res2 = api_client.post("/api/pet/topmost", json={"always_on_top": False})
    assert top_res2.status_code == 200
    assert top_res2.json()["always_on_top"] is False
    assert api_client.get("/api/pet/status").json()["always_on_top"] is False

    # 4. Hide pet
    hide_res = api_client.post("/api/pet/hide")
    assert hide_res.status_code == 200
    assert hide_res.json()["visible"] is False
    assert api_client.get("/api/pet/status").json()["visible"] is False

    # 5. Show pet
    show_res = api_client.post("/api/pet/show")
    assert show_res.status_code == 200
    assert show_res.json()["visible"] is True
    assert api_client.get("/api/pet/status").json()["visible"] is True

    # 6. Reset position
    reset_res = api_client.post("/api/pet/reset_position")
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "ok"
    assert api_client.get("/api/pet/status").json()["visible"] is True

