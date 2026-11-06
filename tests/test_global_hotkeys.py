"""Tests for Global Windows Hotkeys and Emergency Audio / AI Stop (Bug 18)."""

from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtCore import QObject

from app.core.global_hotkeys import GlobalHotkeyManager, VK_ESCAPE, WM_KEYDOWN
from app.core.signals import signals
from app.core.windows_integration import WindowsIntegration


def test_global_hotkey_manager_initialization(qapp_instance):
    """Bug 18: Verify GlobalHotkeyManager initializes and installs hook."""
    mgr = GlobalHotkeyManager()
    assert mgr is not None
    # Test simulate_hotkey
    events = []
    mgr.emergency_stop_triggered.connect(lambda: events.append("emergency"))

    mgr.simulate_hotkey("escape")
    assert len(events) == 1

    mgr.cleanup()
    assert mgr.is_installed is False


def test_global_hotkey_emergency_stop_signal_broadcasting(qapp_instance):
    """Bug 18: Verify emergency stop broadcast via signals bus."""
    mgr = GlobalHotkeyManager()
    signal_received = []

    def on_stop():
        signal_received.append(True)

    signals.emergency_stop_requested.connect(on_stop)
    try:
        mgr.simulate_hotkey("escape")
        assert len(signal_received) == 1
    finally:
        signals.emergency_stop_requested.disconnect(on_stop)
        mgr.cleanup()


def test_windows_integration_hotkey_lifecycle(qapp_instance):
    """Bug 18: Verify WindowsIntegration initializes and cleans up global hotkeys."""
    integration = WindowsIntegration()
    assert hasattr(integration, "global_hotkeys")
    assert integration.global_hotkeys is not None

    integration.cleanup()
    assert integration.global_hotkeys.is_installed is False


def test_application_controller_emergency_stop_handling(qapp_instance):
    """Bug 18: Verify ApplicationController._on_emergency_stop halts voice and AI."""
    from app.core.controller import ApplicationController
    from app.settings.config_manager import ConfigManager

    controller = ApplicationController(app=qapp_instance)
    controller.voice_service = MagicMock()
    controller.ai_service = MagicMock()
    controller.pet_window = MagicMock()

    # Trigger emergency stop
    controller._on_emergency_stop()

    controller.voice_service.emergency_stop.assert_called_once()
    controller.ai_service.cancel_generation.assert_called_once()
    controller.pet_window.anim_controller.request_state.assert_called_with("idle", force=True)


def test_bare_escape_ignored_when_external_app_focused(qapp_instance, monkeypatch):
    """Bug #4: Verify bare Escape is ignored when third-party app is in the foreground."""
    import ctypes
    from app.core.global_hotkeys import KBDLLHOOKSTRUCT, VK_ESCAPE, VK_CONTROL, VK_MENU, VK_SHIFT, WM_KEYDOWN

    mgr = GlobalHotkeyManager(enable_hook=False)
    # Mock non-focused app
    monkeypatch.setattr(mgr, "_is_app_window_focused", lambda: False)

    dispatched = []
    mgr.emergency_stop_triggered.connect(lambda: dispatched.append(True))

    # Mock user32
    mock_user32 = MagicMock()
    # No modifiers held
    mock_user32.GetAsyncKeyState.return_value = 0
    mock_user32.CallNextHookEx.return_value = 0
    monkeypatch.setattr(ctypes.windll, "user32", mock_user32)

    # Install hook with mocked user32
    mgr.install()
    assert mgr._hook_proc_ref is not None

    # Simulate bare Escape keydown from external app
    kbd = KBDLLHOOKSTRUCT(vkCode=VK_ESCAPE, scanCode=1, flags=0, time=100, dwExtraInfo=0)
    lParam = ctypes.addressof(kbd)

    res = mgr._hook_proc_ref(0, WM_KEYDOWN, lParam)
    assert len(dispatched) == 0
    mock_user32.CallNextHookEx.assert_called_once()

    mgr.cleanup()


def test_bare_escape_triggers_when_app_focused(qapp_instance, monkeypatch):
    """Bug #4: Verify bare Escape triggers emergency stop when AI Friend window is focused."""
    import ctypes
    from app.core.global_hotkeys import KBDLLHOOKSTRUCT, VK_ESCAPE, WM_KEYDOWN

    mgr = GlobalHotkeyManager(enable_hook=False)
    # Mock AI Friend window has active focus
    monkeypatch.setattr(mgr, "_is_app_window_focused", lambda: True)

    dispatched = []
    mgr.emergency_stop_triggered.connect(lambda: dispatched.append(True))

    mock_user32 = MagicMock()
    mock_user32.GetAsyncKeyState.return_value = 0
    mock_user32.CallNextHookEx.return_value = 0
    monkeypatch.setattr(ctypes.windll, "user32", mock_user32)

    mgr.install()
    kbd = KBDLLHOOKSTRUCT(vkCode=VK_ESCAPE, scanCode=1, flags=0, time=100, dwExtraInfo=0)
    lParam = ctypes.addressof(kbd)

    res = mgr._hook_proc_ref(0, WM_KEYDOWN, lParam)
    assert len(dispatched) == 1

    mgr.cleanup()


def test_system_combo_triggers_regardless_of_focus(qapp_instance, monkeypatch):
    """Bug #4: Verify Ctrl+Alt+Escape triggers system-wide emergency stop even when external app is focused."""
    import ctypes
    from app.core.global_hotkeys import KBDLLHOOKSTRUCT, VK_ESCAPE, VK_CONTROL, VK_MENU, WM_KEYDOWN

    mgr = GlobalHotkeyManager(enable_hook=False)
    # External app has focus
    monkeypatch.setattr(mgr, "_is_app_window_focused", lambda: False)

    dispatched = []
    mgr.emergency_stop_triggered.connect(lambda: dispatched.append(True))

    mock_user32 = MagicMock()
    # Return 0x8000 for VK_CONTROL and VK_MENU
    def mock_get_async_key_state(vkey):
        if vkey in (VK_CONTROL, VK_MENU):
            return 0x8000
        return 0

    mock_user32.GetAsyncKeyState.side_effect = mock_get_async_key_state
    mock_user32.CallNextHookEx.return_value = 0
    monkeypatch.setattr(ctypes.windll, "user32", mock_user32)

    mgr.install()
    kbd = KBDLLHOOKSTRUCT(vkCode=VK_ESCAPE, scanCode=1, flags=0, time=100, dwExtraInfo=0)
    lParam = ctypes.addressof(kbd)

    res = mgr._hook_proc_ref(0, WM_KEYDOWN, lParam)
    assert len(dispatched) == 1

    mgr.cleanup()

