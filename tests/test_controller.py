"""Tests for ApplicationController."""

from pathlib import Path
import pytest

from app.core.controller import ApplicationController
from app.core.signals import signals
from app.settings.config_manager import ConfigManager


def test_controller_initialization_and_shutdown(qapp_instance, tmp_path: Path):
    """Test full ApplicationController lifecycle: init, window creation, clean shutdown."""
    config_file = tmp_path / "test_settings.json"
    config_manager = ConfigManager(config_path=config_file)

    controller = ApplicationController(
        app=qapp_instance,
        config_manager=config_manager,
    )

    init_fired = []
    shutdown_fired = []
    controller.initialized.connect(lambda: init_fired.append(True))
    controller.shutting_down.connect(lambda: shutdown_fired.append(True))

    assert controller.initialize() is True
    assert len(init_fired) == 1
    assert controller.pet_window is not None
    assert controller.tray_manager is not None

    # Test toggling pet visibility
    signals.toggle_pet_requested.emit()
    qapp_instance.processEvents()
    assert controller.pet_window.isVisible() is False

    signals.toggle_pet_requested.emit()
    qapp_instance.processEvents()
    assert controller.pet_window.isVisible() is True

    # Test shutdown
    controller.shutdown()
    assert len(shutdown_fired) == 1
    assert controller.pet_window is None
    assert controller.tray_manager is None
