"""Windows 10/11 Foreground Window Elevation Helper.

Provides reliable window elevation and focus handling across PowerShell,
CMD, Windows Terminal, and background process launches.
"""

from __future__ import annotations

import sys
from typing import Optional


def elevate_window_to_front(hwnd_int: int, keep_topmost: bool = False) -> bool:
    """Elevates a Win32 window cleanly to the foreground without causing screen flicker or menu flashes.
    
    1. Checks if already the active foreground window to avoid redundant DWM layout resets.
    2. Unlocks SetForegroundWindow permissions via AllowSetForegroundWindow.
    3. Attempts standard SetForegroundWindow directly.
    4. If locked by the OS, attaches thread input queues gently using non-destructive SWP flags
       (SWP_NOREDRAW | SWP_NOSENDCHANGING) without flashing Alt menu keys or triggering SWP_SHOWWINDOW.
    """
    if sys.platform != "win32":
        return False

    try:
        import ctypes
        from ctypes import wintypes, c_void_p, c_int, c_uint

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = c_void_p(hwnd_int)
        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd == hwnd_int:
            return True  # Already foreground window, no action needed

        # 1. Allow this process and any child to set foreground window
        user32.AllowSetForegroundWindow(-1)

        # 2. Try clean foreground activation first
        if user32.SetForegroundWindow(hwnd):
            user32.BringWindowToTop(hwnd)
            return True

        # 3. If OS foreground lock is active, bridge console and GUI input queues
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        cur_thread = kernel32.GetCurrentThreadId()

        attached = False
        if fg_thread and fg_thread != cur_thread:
            try:
                attached = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))
            except Exception:
                attached = False

        # Non-destructive SWP flags: Never pass SWP_SHOWWINDOW (0x0040) to prevent DWM composition flashing
        HWND_TOPMOST = c_void_p(-1)
        HWND_NOTOPMOST = c_void_p(-2)
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        SWP_NOREDRAW = 0x0008
        SWP_NOSENDCHANGING = 0x0400
        SWP_NOOWNERZORDER = 0x0200
        swp_flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOREDRAW | SWP_NOSENDCHANGING | SWP_NOOWNERZORDER

        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, swp_flags)
        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)

        # Release topmost unless keep_topmost is requested
        if not keep_topmost:
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, swp_flags)

        if attached:
            try:
                user32.AttachThreadInput(cur_thread, fg_thread, False)
            except Exception:
                pass

        return True
    except Exception:
        return False


def minimize_console_window() -> bool:
    """Minimizes the active console terminal if running interactively.
    
    This clears the display so desktop pet and chat window are immediately visible,
    while keeping the terminal running in the taskbar for log monitoring or Ctrl+C exit.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        console_hwnd = kernel32.GetConsoleWindow()
        if console_hwnd:
            SW_MINIMIZE = 6
            return bool(user32.ShowWindow(console_hwnd, SW_MINIMIZE))
    except Exception:
        pass
    return False
