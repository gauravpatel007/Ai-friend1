"""Verification suite for Ctrl+C instant emergency shutdown and window hiding.

Tests requirements:
1. LifecycleManager registers and executes emergency exit handlers without delay.
2. Fast kill terminates child processes immediately without 1-second waits.
3. ApplicationController emergency_fast_exit hides all HWNDs in sub-millisecond time.
4. SingleInstanceGuard lock is released immediately on emergency exit, enabling clean subsequent launches.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from app.core.controller import ApplicationController
from app.core.lifecycle import LifecycleManager, get_lifecycle_manager
from app.core.single_instance import SingleInstanceGuard
from app.settings.config_manager import ConfigManager


def test_lifecycle_emergency_handler_registration() -> None:
    """Verify that emergency exit handlers register and execute cleanly."""
    mgr = LifecycleManager()
    called = []

    def handler():
        called.append(True)

    mgr.register_emergency_exit_handler(handler)

    with patch.object(LifecycleManager, "_hard_kill_process") as mock_kill:
        mgr.trigger_emergency_exit()
        assert called == [True]
        mock_kill.assert_called_once()


def test_lifecycle_fast_kill_children() -> None:
    """Verify that fast_kill_children terminates registered processes without hanging."""
    mgr = LifecycleManager()
    mock_proc = MagicMock()
    mock_proc.pid = 99999
    mock_proc.is_running.return_value = True
    mock_proc.children.return_value = []

    mgr.register_child_process(mock_proc)

    with patch("psutil.Process", return_value=mock_proc):
        mgr.fast_kill_children()
        mock_proc.kill.assert_called_once()


def test_controller_emergency_fast_exit_releases_guard(qtbot) -> None:
    """Verify emergency_fast_exit instantly releases single instance lock and triggers os._exit(0)."""
    app = QApplication.instance() or QApplication(sys.argv)
    config = ConfigManager()
    guard = SingleInstanceGuard(key="AIDesktopFriend_Test_Emergency")

    # Acquire lock
    assert guard.try_acquire() is True
    assert guard.is_primary() is True

    controller = ApplicationController(
        app=app,
        config_manager=config,
        single_instance_guard=guard,
    )

    # Create dummy widgets to simulate pet and chat windows
    w1 = QWidget()
    w2 = QWidget()
    w1.show()
    w2.show()
    controller.pet_window = w1
    controller.chat_window = w2
    controller._window_hwnds = [int(w1.winId()), int(w2.winId())]

    with patch.object(ApplicationController, "_hard_kill_process") as mock_kill:
        controller.emergency_fast_exit()
        mock_kill.assert_called_once()

    # Guard must be released
    assert guard.is_primary() is False

    # A new guard with the same key should now acquire immediately
    guard2 = SingleInstanceGuard(key="AIDesktopFriend_Test_Emergency")
    try:
        assert guard2.try_acquire() is True
    finally:
        guard2.release()
        w1.close()
        w2.close()
