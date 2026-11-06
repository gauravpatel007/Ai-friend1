"""Tests for SettingsDialog Startup Integration (Bug 17)."""

from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtWidgets import QApplication

from app.core import startup_manager
from app.desktop.settings_dialog import SettingsDialog
from app.memory.memory_manager import MemoryManager
from app.settings.config_manager import ConfigManager


@pytest.fixture
def test_config(tmp_path):
    cfg_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=cfg_file)
    mgr.set("general.start_at_login", False)
    return mgr


@pytest.fixture
def mock_memory_mgr():
    mock = MagicMock(spec=MemoryManager)
    mock.get_memory_count.return_value = 0
    mock.get_all_memories.return_value = []
    mock.search_memories.return_value = []
    return mock


def test_startup_page_cb_autostart_initialization(qapp_instance, test_config, mock_memory_mgr):
    """Bug 17: Verify cb_autostart is stored on self, loaded from startup_manager, and updates config."""
    with patch("app.core.startup_manager.is_startup_enabled", return_value=True):
        dialog = SettingsDialog(
            config_manager=test_config,
            memory_manager=mock_memory_mgr,
        )

        assert hasattr(dialog, "cb_autostart")
        assert dialog.cb_autostart is not None
        # Should be checked because is_startup_enabled() returned True
        assert dialog.cb_autostart.isChecked() is True

    # Test toggling off
    with patch("app.core.startup_manager.set_startup_enabled", return_value=True) as mock_set:
        dialog.cb_autostart.setChecked(False)
        assert test_config.get("general.start_at_login") is False
        mock_set.assert_called_with(False)

    # Test toggling on
    with patch("app.core.startup_manager.set_startup_enabled", return_value=True) as mock_set:
        dialog.cb_autostart.setChecked(True)
        assert test_config.get("general.start_at_login") is True
        mock_set.assert_called_with(True)

    dialog.close()
