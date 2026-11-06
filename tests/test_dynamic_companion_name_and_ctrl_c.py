"""Verification test suite for dynamic companion name consistency and terminal Ctrl+C exit.

Tests:
1. Verification that dynamic companion name (e.g. 'Bond') is returned across all API endpoints:
   - GET /api/companion/state returns configured name.
   - GET /api/config returns configured name.
   - PUT /api/config updates name, saves config, and broadcasts companion_name_changed & companion_profile_updated.
   - POST /api/config/batch updates name atomically across all aliases ('ai.companion_name', 'companion.name', 'character.name').
2. Verification that SingleInstanceGuard.clean_lock_file() safely removes lock files from disk.
3. Verification that console control handler executes emergency exit immediately without deadlocking on cross-thread Qt calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PySide6.QtWidgets import QApplication

from app.api.server import app
from app.core.lifecycle import LifecycleManager, get_lifecycle_manager
from app.core.single_instance import SingleInstanceGuard
from app.settings.config_manager import ConfigManager


@pytest.fixture
def mock_config(tmp_path):
    """Provides an isolated ConfigManager for testing."""
    config_file = tmp_path / "test_config.json"
    cfg = ConfigManager(config_path=config_file)
    cfg.set("ai.companion_name", "Bond")
    cfg.set("companion.name", "Bond")
    app.state.config_manager = cfg
    return cfg


@pytest.fixture
def api_client(mock_config):
    """FastAPI TestClient with isolated ConfigManager."""
    return TestClient(app)


def test_companion_state_returns_dynamic_name(api_client, mock_config):
    """Verify GET /api/companion/state returns dynamic companion name from config."""
    res = api_client.get("/api/companion/state")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Bond"


def test_get_config_returns_dynamic_name(api_client, mock_config):
    """Verify GET /api/config returns configured companion name."""
    res = api_client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert data.get("ai", {}).get("companion_name") == "Bond" or data.get("ai.companion_name") == "Bond"


def test_update_config_broadcasts_and_persists_name(api_client, mock_config):
    """Verify PUT /api/config updates companion name and broadcasts updates to WebSockets."""
    with patch("app.api.websocket.ws_manager.broadcast_sync") as mock_broadcast:
        res = api_client.put("/api/config", json={"key": "ai.companion_name", "value": "Bond"})
        assert res.status_code == 200
        assert mock_config.get("ai.companion_name") == "Bond"
        assert mock_config.get("companion.name") == "Bond"

        # Verify broadcast events were sent
        broadcast_types = [call[0][0] for call in mock_broadcast.call_args_list]
        assert "companion_name_changed" in broadcast_types
        assert "companion_profile_updated" in broadcast_types


def test_batch_config_updates_all_companion_name_aliases(api_client, mock_config):
    """Verify POST /api/config/batch updates and normalizes all companion name keys."""
    with patch("app.api.websocket.ws_manager.broadcast_sync") as mock_broadcast:
        res = api_client.post(
            "/api/config/batch",
            json={"settings": {"ai.companion_name": "Agent Bond", "voice.speed": 1.0}},
        )
        assert res.status_code == 200
        assert mock_config.get("ai.companion_name") == "Agent Bond"
        assert mock_config.get("companion.name") == "Agent Bond"
        assert mock_config.get("character.name") == "Agent Bond"

        broadcast_types = [call[0][0] for call in mock_broadcast.call_args_list]
        assert "companion_name_changed" in broadcast_types
        assert "companion_profile_updated" in broadcast_types


def test_single_instance_clean_lock_file(tmp_path):
    """Verify clean_lock_file safely unlinks lock files without touching Qt server objects."""
    key = "Test_Lock_Clean_Verification"
    from platformdirs import user_data_dir
    lock_file = Path(user_data_dir("AI Desktop Friend", "Gaurav Patel")) / f"{key}.port"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text("8765", encoding="utf-8")
    assert lock_file.exists()

    SingleInstanceGuard.clean_lock_file(key)
    assert not lock_file.exists()


def test_emergency_fast_exit_executes_without_deadlock(qtbot):
    """Verify emergency_fast_exit releases the guard lock and terminates process instantly."""
    from app.core.controller import ApplicationController
    app_inst = QApplication.instance() or QApplication(sys.argv)
    cfg = ConfigManager()
    guard = SingleInstanceGuard(key="Test_Emergency_No_Deadlock")
    assert guard.try_acquire() is True

    controller = ApplicationController(app=app_inst, config_manager=cfg, single_instance_guard=guard)

    with patch.object(ApplicationController, "_hard_kill_process") as mock_kill:
        controller.emergency_fast_exit()
        mock_kill.assert_called_once()

    assert guard.is_primary() is False

