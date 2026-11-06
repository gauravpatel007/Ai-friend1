"""Tests for DesktopPetWindow closeEvent lifecycle integration (Bug #23).

Verifies that closing the primary desktop pet window initiates centralized
LifecycleManager shutdown, and respects idempotency when shutdown is already active.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from app.core.lifecycle import LifecycleState, get_lifecycle_manager
from app.desktop.pet_window import DesktopPetWindow
from app.settings.config_manager import ConfigManager


@pytest.fixture
def pet_window(qapp_instance, tmp_path: Path):
    cfg_file = tmp_path / "pet_test_config.json"
    cfg = ConfigManager(config_path=cfg_file)
    window = DesktopPetWindow(config_manager=cfg)
    yield window
    # Ensure window is closed cleanly
    try:
        window._request_shutdown_on_close = False
        window.close()
    except Exception:
        pass


def test_pet_window_close_event_requests_lifecycle_shutdown(pet_window: DesktopPetWindow):
    """Bug #23: When user closes the pet window, central lifecycle shutdown must be requested."""
    lm = get_lifecycle_manager()
    lm._shutdown_initiated = False

    pet_window._force_shutdown_in_test = True

    with patch.object(lm, "request_shutdown") as mock_shutdown:
        close_event = QCloseEvent()
        pet_window.closeEvent(close_event)

        mock_shutdown.assert_called_once_with(source="pet_window_close")


def test_pet_window_close_event_idempotent_during_active_shutdown(pet_window: DesktopPetWindow):
    """Bug #23: If shutdown is already initiated, closeEvent does NOT issue another shutdown request."""
    lm = get_lifecycle_manager()
    lm._shutdown_initiated = True

    pet_window._force_shutdown_in_test = True

    with patch.object(lm, "request_shutdown") as mock_shutdown:
        close_event = QCloseEvent()
        pet_window.closeEvent(close_event)

        mock_shutdown.assert_not_called()


def test_pet_window_close_event_respects_request_shutdown_flag(pet_window: DesktopPetWindow):
    """Bug #23: When _request_shutdown_on_close is False, shutdown is not requested."""
    lm = get_lifecycle_manager()
    lm._shutdown_initiated = False

    pet_window._request_shutdown_on_close = False
    pet_window._force_shutdown_in_test = True

    with patch.object(lm, "request_shutdown") as mock_shutdown:
        close_event = QCloseEvent()
        pet_window.closeEvent(close_event)

        mock_shutdown.assert_not_called()


def test_pet_window_close_cleans_up_children(pet_window: DesktopPetWindow):
    """Verify child widgets and timers are properly cleaned up on close."""
    assert hasattr(pet_window, "anim_controller")
    assert hasattr(pet_window, "control_bar")

    pet_window._request_shutdown_on_close = False
    pet_window.close()

    assert not pet_window._anim_timer.isActive()
    assert pet_window._signal_connections == []
