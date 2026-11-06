"""Tests for ApplicationController."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.controller import ApplicationController
from app.core.signals import signals
from app.settings.config_manager import ConfigManager


import uuid

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


def test_controller_initialization_and_shutdown(qapp_instance):
    """Test full ApplicationController lifecycle: init, window creation, clean shutdown."""
    config_file = SCRATCH_DIR / f"test_settings_{uuid.uuid4().hex}.json"
    config_manager = ConfigManager(config_path=config_file)

    controller = ApplicationController(
        app=qapp_instance,
        config_manager=config_manager,
    )

    with patch("app.desktop.modern_chat_window.ModernChatWindow", return_value=MagicMock()):
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
