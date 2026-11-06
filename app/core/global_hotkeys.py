"""Global System-Wide Windows Hotkeys & Low-Level Keyboard Hook (Bug 18).

Provides system-wide keyboard interception using the Windows Win32 API
(WH_KEYBOARD_LL low-level keyboard hook and RegisterHotKey).

Enables immediate Emergency Audio / AI Stop upon pressing Escape anywhere in Windows,
even when another application (browser, code editor, game) has foreground focus.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import time
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QObject, Signal, Slot

from app.core.signals import signals
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Windows Virtual Key Codes & Message Constants
VK_ESCAPE = 0x1B
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt key
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_HOTKEY = 0x0312

# Modifiers for RegisterHotKey
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """Win32 KBDLLHOOKSTRUCT structure for low-level keyboard hook events."""

    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


# Function pointer prototype for Windows Hook procedure (LRESULT is pointer-sized: c_ssize_t on 64-bit Windows)
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

if sys.platform == "win32":
    try:
        _user32 = ctypes.windll.user32
        _user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        _user32.CallNextHookEx.restype = ctypes.c_ssize_t
        _user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        _user32.SetWindowsHookExW.restype = wintypes.HHOOK
        _user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        _user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        _user32.GetAsyncKeyState.restype = ctypes.c_short
        _user32.GetForegroundWindow.argtypes = []
        _user32.GetForegroundWindow.restype = wintypes.HWND
        _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    except Exception as _e:
        logger.warning("Error configuring Win32 user32 hook API types: %s", _e)


class GlobalHotkeyManager(QObject):
    """System-wide global hotkey manager and keyboard hook coordinator."""

    # Qt Signal emitted when an emergency stop hotkey is detected
    emergency_stop_triggered = Signal()
    # Qt Signal emitted when a custom registered hotkey fires
    hotkey_triggered = Signal(str)  # hotkey_id

    def __init__(self, parent: Optional[QObject] = None, enable_hook: bool = True) -> None:
        super().__init__(parent)
        self._is_windows = sys.platform == "win32"
        self._hook_handle: Optional[int] = None
        self._hook_proc_ref: Optional[Any] = None
        self._last_escape_time: float = 0.0
        self._debounce_interval: float = 0.25  # seconds
        self._registered_hotkeys: Dict[int, str] = {}
        self._is_installed = False

        if self._is_windows and enable_hook:
            self.install()

    @property
    def is_installed(self) -> bool:
        """Check whether the global keyboard hook is active."""
        return self._is_installed

    def _is_app_window_focused(self) -> bool:
        """Check whether one of AI Friend's own windows (Chat, Pet, Settings, Movie Hub) has focus."""
        try:
            from PySide6.QtWidgets import QApplication
            if QApplication.activeWindow() is not None or QApplication.focusWidget() is not None:
                return True

            if self._is_windows:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                fg_hwnd = user32.GetForegroundWindow()
                if not fg_hwnd:
                    return False

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid))
                current_pid = kernel32.GetCurrentProcessId()
                if pid.value == current_pid:
                    return True
        except Exception as e:
            logger.debug("Error checking foreground window focus: %s", e)
        return False

    def install(self) -> bool:
        """Install the low-level Windows keyboard hook (WH_KEYBOARD_LL)."""
        if not self._is_windows:
            logger.debug("Global hotkeys: non-Windows environment; keyboard hook skipped.")
            return False

        if self._is_installed and self._hook_handle:
            return True

        try:
            user32 = ctypes.windll.user32

            @HOOKPROC
            def _low_level_keyboard_proc(nCode: int, wParam: int, lParam: int) -> int:
                try:
                    if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        try:
                            kbd = KBDLLHOOKSTRUCT.from_address(lParam)
                            vk = kbd.vkCode
                            if vk == VK_ESCAPE:
                                # Query physical modifier key states
                                ctrl_pressed = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                                alt_pressed = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                                shift_pressed = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)

                                # 1. System-wide emergency stop: requires dedicated modifier combo (Ctrl+Alt+Escape or Ctrl+Escape)
                                is_system_combo = (ctrl_pressed and alt_pressed) or (
                                    ctrl_pressed and not alt_pressed and not shift_pressed
                                )

                                # 2. Bare Escape: only allowed when an AI Friend window has active foreground focus
                                is_bare_escape = not (ctrl_pressed or alt_pressed or shift_pressed)
                                is_app_focused = self._is_app_window_focused() if is_bare_escape else False

                                if is_system_combo or (is_bare_escape and is_app_focused):
                                    now = time.time()
                                    if now - self._last_escape_time >= self._debounce_interval:
                                        self._last_escape_time = now
                                        trigger_reason = (
                                            "System-wide combo"
                                            if is_system_combo
                                            else "Bare Escape in AI Friend window"
                                        )
                                        logger.info("%s detected via WH_KEYBOARD_LL: firing Emergency Stop.", trigger_reason)
                                        self._dispatch_emergency_stop()
                                else:
                                    logger.debug(
                                        "Ignoring bare Escape outside AI Friend (ctrl=%s, alt=%s, app_focused=%s).",
                                        ctrl_pressed,
                                        alt_pressed,
                                        is_app_focused,
                                    )
                        except Exception as ex:
                            logger.debug("Error in low-level keyboard hook callback: %s", ex)

                    return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)
                except Exception as ex:
                    logger.debug("Error in _low_level_keyboard_proc CallNextHookEx: %s", ex)
                    return 0

            # Keep Python reference to prevent garbage collection of function pointer
            self._hook_proc_ref = _low_level_keyboard_proc
            h_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc_ref, None, 0)

            if not h_hook:
                err = ctypes.GetLastError()
                logger.warning("Failed to install WH_KEYBOARD_LL hook (Win32 error %d).", err)
                self._hook_handle = None
                self._is_installed = False
                return False

            self._hook_handle = h_hook
            self._is_installed = True
            logger.info("Global WH_KEYBOARD_LL keyboard hook installed successfully (handle=%s).", h_hook)
            return True

        except Exception as e:
            logger.error("Exception during global keyboard hook installation: %s", e)
            self._is_installed = False
            return False

    def uninstall(self) -> bool:
        """Uninstall the low-level keyboard hook."""
        if not self._is_windows or not self._hook_handle:
            self._is_installed = False
            return True

        try:
            user32 = ctypes.windll.user32
            res = user32.UnhookWindowsHookEx(self._hook_handle)
            logger.info("Global WH_KEYBOARD_LL keyboard hook uninstalled (result=%s).", res)
            self._hook_handle = None
            self._hook_proc_ref = None
            self._is_installed = False
            return bool(res)
        except Exception as e:
            logger.warning("Error during keyboard hook uninstall: %s", e)
            self._hook_handle = None
            self._is_installed = False
            return False

    def _dispatch_emergency_stop(self) -> None:
        """Safely emit emergency stop signals."""
        try:
            self.emergency_stop_triggered.emit()
        except RuntimeError:
            pass
        try:
            signals.emergency_stop_requested.emit()
        except RuntimeError:
            pass

    def simulate_hotkey(self, hotkey_name: str = "escape") -> None:
        """Simulate a global hotkey event for unit tests, diagnostics, and headless testing."""
        key_clean = hotkey_name.lower().strip()
        if key_clean in ("escape", "ctrl+escape", "ctrl+alt+escape"):
            logger.info("Simulating global Escape emergency stop hotkey (%s).", key_clean)
            self._dispatch_emergency_stop()
        else:
            self.hotkey_triggered.emit(hotkey_name)

    def cleanup(self) -> None:
        """Clean shutdown hook."""
        self.uninstall()

    def __del__(self) -> None:
        self.uninstall()
