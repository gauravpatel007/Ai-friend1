"""Test verifying off-thread wake and sleep dispatch fixes that prevent window hangs and deadlock."""

import threading
import time
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from app.core.controller import ApplicationController
from app.core.signals import signals
from app.settings.config_manager import ConfigManager


@pytest.fixture
def test_controller(qapp_instance, tmp_path):
    cfg_file = tmp_path / "test_config.json"
    cfg_mgr = ConfigManager(config_path=cfg_file)
    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg_mgr)
    signals.sleep_requested.connect(ctrl.enter_sleep_mode, Qt.ConnectionType.QueuedConnection)
    signals.wake_requested.connect(ctrl.wake_up, Qt.ConnectionType.QueuedConnection)
    ctrl.pet_window = MagicMock()
    ctrl.pet_window.isVisible.return_value = True
    ctrl.pet_window.speech_bubble = MagicMock()
    ctrl.pet_window.anim_controller = MagicMock()
    ctrl.voice_service = MagicMock()
    ctrl.voice_service.is_muted = False
    return ctrl


def test_offthread_wake_requested_no_deadlock(qapp_instance, test_controller):
    """Verify emitting signals.wake_requested from a worker thread safely schedules on GUI thread."""
    test_controller._is_sleeping = True
    executed_in_thread = []

    def background_wake_emitter():
        # Emulating FastAPI endpoint uvicorn worker thread
        signals.wake_requested.emit()
        executed_in_thread.append(True)

    t = threading.Thread(target=background_wake_emitter)
    t.start()
    t.join(timeout=2.0)
    assert not t.is_alive(), "Worker thread hung or deadlocked!"
    assert len(executed_in_thread) == 1

    # Process Qt event loop to let queued singleShot / QueuedConnection execute
    qapp_instance.processEvents()

    assert test_controller._is_sleeping is False, "Controller should have woken up safely"


def test_offthread_sleep_requested_no_deadlock(qapp_instance, test_controller):
    """Verify emitting signals.sleep_requested from a worker thread safely schedules on GUI thread."""
    test_controller._is_sleeping = False
    executed_in_thread = []

    def background_sleep_emitter():
        signals.sleep_requested.emit()
        executed_in_thread.append(True)

    t = threading.Thread(target=background_sleep_emitter)
    t.start()
    t.join(timeout=2.0)
    assert not t.is_alive(), "Worker thread hung or deadlocked!"
    assert len(executed_in_thread) == 1

    qapp_instance.processEvents()

    assert test_controller._is_sleeping is True, "Controller should have entered sleep mode safely"


def test_direct_offthread_wake_and_sleep_calls(qapp_instance, test_controller):
    """Verify calling ctrl.wake_up() directly off-thread dispatches safely via QTimer without deadlocking."""
    test_controller._is_sleeping = True

    def direct_caller():
        test_controller.wake_up(speak_ack=False)

    t = threading.Thread(target=direct_caller)
    t.start()
    t.join(timeout=2.0)
    assert not t.is_alive()

    qapp_instance.processEvents()
    assert test_controller._is_sleeping is False
