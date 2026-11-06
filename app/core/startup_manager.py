"""Windows Startup Manager.

Manages registering / unregistering the application for automatic
launch when the current user logs in to Windows.

Uses the per-user Run registry key — no administrator privileges required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

_APP_NAME = "AIDesktopFriend"
_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_executable_path() -> str:
    """Return the path to the current executable or script.

    If running as a frozen PyInstaller/cx_Freeze bundle, uses sys.executable.
    Otherwise, constructs a `pythonw.exe main.py` command.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    # Development mode — point to pythonw inside the venv
    python = Path(sys.executable)
    pythonw = python.parent / "pythonw.exe"
    if pythonw.exists():
        exe = str(pythonw)
    else:
        exe = str(python)

    main_script = Path(__file__).resolve().parent.parent.parent / "main.py"
    return f'"{exe}" "{main_script}"'


def is_startup_enabled() -> bool:
    """Check whether the application is registered for Windows startup."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError as e:
        logger.warning("Could not read startup registry key: %s", e)
        return False


def enable_startup() -> bool:
    """Register the application for automatic startup on Windows login.

    Returns True on success, False on failure.
    """
    try:
        import winreg
        exe_path = _get_executable_path()
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, exe_path)
        logger.info("Startup entry registered: %s", exe_path)
        return True
    except (OSError, Exception) as e:
        logger.error("Failed to set startup registry entry: %s", e)
        return False


def disable_startup() -> bool:
    """Remove the application's Windows startup entry.

    Returns True on success, False on failure.
    """
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _APP_NAME)
        logger.info("Startup entry removed.")
        return True
    except FileNotFoundError:
        logger.info("Startup entry was not present; nothing to remove.")
        return True
    except (OSError, Exception) as e:
        logger.error("Failed to remove startup registry entry: %s", e)
        return False


def set_startup_enabled(enabled: bool) -> bool:
    """Enable or disable startup based on a boolean flag."""
    if enabled:
        return enable_startup()
    return disable_startup()
