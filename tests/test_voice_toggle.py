"""Unit and integration tests for Bug 11: Voice toggle endpoint without triple-toggle signal inversion."""

from typing import Any
import pytest
from fastapi.testclient import TestClient

from PySide6.QtCore import Qt
from app.api.server import app
from app.core.signals import signals
from app.settings.config_manager import ConfigManager
from app.voice.voice_service import VoiceMode


class DummyVoiceService:
    """Mock VoiceService supporting mode get/set and property semantics."""

    def __init__(self, initial_mode: Any = VoiceMode.OFF) -> None:
        self._mode = initial_mode
        self.tts_enabled = True
        self.is_muted = False

    @property
    def mode(self) -> Any:
        return self._mode

    def set_mode(self, mode: Any) -> None:
        if isinstance(mode, str):
            try:
                mode = VoiceMode(mode.lower().strip())
            except ValueError:
                mode = VoiceMode.OFF
        self._mode = mode


@pytest.fixture
def test_client(qapp_instance):
    """TestClient fixture with fresh state and config."""
    cfg = ConfigManager()
    app.state.config_manager = cfg
    app.state.voice_service = None
    app.state.controller = None
    client = TestClient(app)
    yield client
    # Teardown
    app.state.voice_service = None
    app.state.controller = None


def test_voice_toggle_with_signal_listener_no_inversion(test_client, qapp_instance):
    """Verify toggle does not invert state back to off when a Qt signal listener transitions the mode."""
    vs = DummyVoiceService(VoiceMode.OFF)
    app.state.voice_service = vs

    # Connect a listener simulating ApplicationController._on_voice_toggle
    def simulated_controller_toggle():
        if vs.mode == VoiceMode.OFF:
            vs.set_mode(VoiceMode.CONTINUOUS)
        else:
            vs.set_mode(VoiceMode.OFF)

    signals.voice_toggle_requested.connect(
        simulated_controller_toggle, Qt.ConnectionType.DirectConnection
    )
    try:
        # 1. Toggle ON: OFF -> CONTINUOUS
        resp1 = test_client.post("/api/voice/toggle")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "ok"
        assert data1["mode"] == "continuous"
        # Crucial: Voice must remain active, NOT inverted back to OFF!
        assert vs.mode == VoiceMode.CONTINUOUS

        # 2. Toggle OFF: CONTINUOUS -> OFF
        resp2 = test_client.post("/api/voice/toggle")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["status"] == "ok"
        assert data2["mode"] == "off"
        # Crucial: Voice must transition back to OFF, NOT inverted back to CONTINUOUS!
        assert vs.mode == VoiceMode.OFF
    finally:
        signals.voice_toggle_requested.disconnect(simulated_controller_toggle)


def test_voice_toggle_direct_fallback_no_listener(test_client):
    """Verify fallback direct toggle when no listener is connected to the Qt signal."""
    vs = DummyVoiceService(VoiceMode.OFF)
    app.state.voice_service = vs

    # 1. Toggle ON directly
    resp1 = test_client.post("/api/voice/toggle")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "ok"
    assert data1["mode"] == "continuous"
    assert vs.mode == VoiceMode.CONTINUOUS

    # 2. Toggle OFF directly
    resp2 = test_client.post("/api/voice/toggle")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "ok"
    assert data2["mode"] == "off"
    assert vs.mode == VoiceMode.OFF


def test_voice_toggle_controller_guard_in_main_api(test_client, qapp_instance):
    """Verify main_api.on_voice_toggle respects app.state.controller and does not double-toggle."""
    from main_api import setup_signal_bridges, teardown_signal_bridges
    from app.memory.conversation_repository import ConversationRepository

    repo = ConversationRepository()
    vs = DummyVoiceService(VoiceMode.OFF)
    app.state.voice_service = vs

    class DummyController:
        def __init__(self, voice_service):
            self.voice_service = voice_service
            signals.voice_toggle_requested.connect(
                self._on_voice_toggle, Qt.ConnectionType.DirectConnection
            )

        def _on_voice_toggle(self):
            if self.voice_service.mode == VoiceMode.OFF:
                self.voice_service.set_mode(VoiceMode.WAKE_WORD)
            else:
                self.voice_service.set_mode(VoiceMode.OFF)

    dummy_ctrl = DummyController(vs)
    app.state.controller = dummy_ctrl

    # setup_signal_bridges is called while controller is set
    setup_signal_bridges(qapp_instance, repo)

    try:
        # Toggle ON
        resp = test_client.post("/api/voice/toggle")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "wake_word"
        assert vs.mode == VoiceMode.WAKE_WORD

        # Toggle OFF
        resp2 = test_client.post("/api/voice/toggle")
        assert resp2.status_code == 200
        assert resp2.json()["mode"] == "off"
        assert vs.mode == VoiceMode.OFF
    finally:
        try:
            signals.voice_toggle_requested.disconnect(dummy_ctrl._on_voice_toggle)
        except Exception:
            pass
        teardown_signal_bridges()
        app.state.controller = None


def test_voice_toggle_service_none(test_client):
    """Verify toggle safely returns off when voice_service is None."""
    app.state.voice_service = None
    resp = test_client.post("/api/voice/toggle")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "mode": "off"}


def test_voice_status_endpoint_robustness(test_client):
    """Verify get_voice_status handles both Enum and string representations gracefully."""
    # 1. VoiceMode enum
    vs = DummyVoiceService(VoiceMode.CONTINUOUS)
    app.state.voice_service = vs
    resp1 = test_client.get("/api/voice/status")
    assert resp1.status_code == 200
    assert resp1.json()["mode"] == "continuous"

    # 2. String representation
    vs._mode = "wake_word"
    resp2 = test_client.get("/api/voice/status")
    assert resp2.status_code == 200
    assert resp2.json()["mode"] == "wake_word"

    # 3. None voice_service
    app.state.voice_service = None
    resp3 = test_client.get("/api/voice/status")
    assert resp3.status_code == 200
    assert resp3.json()["mode"] == "off"
