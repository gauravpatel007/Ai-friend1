"""Tests for Bug #10: Post-app.exec() processEvents() deadlock prevention & 1.5s grace exit watchdog.

Verifies:
1. main.py does not invoke app.processEvents() after app.exec() exits.
2. LifecycleManager.arm_exit_watchdog() starts an 'ExitGraceWatchdog' daemon thread.
3. The watchdog invokes _hard_kill_process() and os._exit() upon grace timeout expiration.
4. LifecycleManager._execute_shutdown() flushes deferred deletes without calling processEvents().
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from app.core.lifecycle import LifecycleManager, get_lifecycle_manager


def test_main_py_does_not_call_process_events_post_exec():
    """Verify that main.py does not contain app.processEvents() after app.exec()."""
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    with open(main_path, "r", encoding="utf-8") as f:
        source = f.read()

    # Parse AST to ensure no processEvents() call occurs in main()
    tree = ast.parse(source)
    process_events_calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check attribute calls like app.processEvents()
            if isinstance(node.func, ast.Attribute) and node.func.attr == "processEvents":
                process_events_calls.append(node.lineno)

    assert len(process_events_calls) == 0, (
        f"main.py must never call processEvents(); found on line(s): {process_events_calls}"
    )


def test_lifecycle_shutdown_does_not_call_process_events():
    """Verify that LifecycleManager._execute_shutdown does not call processEvents()."""
    source = inspect.getsource(LifecycleManager._execute_shutdown)
    code_lines = [l for l in source.splitlines() if not l.strip().startswith("#")]
    clean_code = "\n".join(code_lines)
    assert "processEvents" not in clean_code, (
        "LifecycleManager._execute_shutdown must not call processEvents() on a terminating event loop."
    )


def test_arm_exit_watchdog_starts_daemon_thread():
    """Verify arm_exit_watchdog creates a daemon thread that executes within timeout."""
    with patch.object(LifecycleManager, "_hard_kill_process") as mock_hard_kill, \
         patch("os._exit") as mock_os_exit:
        
        watchdog = LifecycleManager.arm_exit_watchdog(exit_code=42, timeout_sec=0.05)
        assert isinstance(watchdog, threading.Thread)
        assert watchdog.daemon is True
        assert watchdog.name == "ExitGraceWatchdog"

        # Wait for the short test timeout to trigger
        watchdog.join(timeout=1.0)
        assert not watchdog.is_alive()
        mock_hard_kill.assert_called_once()
        mock_os_exit.assert_called_once_with(42)


def test_main_returns_cleanly_with_exit_code():
    """Verify main() returns exit_code without hanging on processEvents."""
    import main as main_module

    mock_app = MagicMock()
    mock_app.exec.return_value = 0

    mock_controller = MagicMock()
    mock_controller.initialize.return_value = True

    mock_guard = MagicMock()
    mock_guard.try_acquire.return_value = True

    mock_cfg = MagicMock()
    mock_cfg.get.return_value = True  # general.setup_completed = True

    with patch("sys.argv", ["main.py", "--test-run"]), \
         patch("main.setup_logging"), \
         patch("app.desktop.jarvis_theme.load_jarvis_fonts"), \
         patch("app.desktop.jarvis_theme.get_global_stylesheet", return_value=""), \
         patch("main.get_application_icon"), \
         patch("main.QApplication") as mock_qapp_cls, \
         patch("main.SingleInstanceGuard", return_value=mock_guard), \
         patch("main.ConfigManager", return_value=mock_cfg), \
         patch("main.ApplicationController", return_value=mock_controller), \
         patch("app.core.lifecycle.LifecycleManager.arm_exit_watchdog") as mock_arm:
        
        mock_qapp_cls.instance.return_value = None
        mock_qapp_cls.return_value = mock_app

        exit_code = main_module.main()

        assert exit_code == 0
        mock_app.exec.assert_called_once()
        mock_arm.assert_called_once_with(exit_code=0, timeout_sec=1.5)
