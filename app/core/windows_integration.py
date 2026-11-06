"""Windows Integration Coordinator (Phase 11.7).

Handles deep Windows OS integration features:
- Explorer restart / TaskbarCreated detection for tray icon recovery.
- Windows power broadcast (WM_POWERBROADCAST) sleep/resume handling.
- Multi-monitor support and screen addition/removal repositioning.
- High-DPI display scaling compatibility.
- Windows Startup (Run registry) management.
- Post-resume audio device and background service revalidation.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from typing import Any, Callable, List, Optional, Tuple

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QCoreApplication,
    QObject,
    QPoint,
    QRect,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QApplication

from app.core import startup_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Windows Message Constants
WM_POWERBROADCAST = 0x0218
PBT_APMQUERYSUSPEND = 0x0000
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMECRITICAL = 0x0006
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012


class _WindowsNativeEventFilter(QAbstractNativeEventFilter):
    """Intercepts native Windows messages for system events."""

    def __init__(self, callback: Callable[[int, int, int], None]) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, eventType, message) -> Tuple[bool, int]:
        # On Windows, eventType is "windows_generic_MSG" or "windows_dispatcher_MSG"
        if eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                # MSG struct pointer
                msg = wintypes.MSG.from_address(int(message))
                self._callback(msg.message, msg.wParam, msg.lParam)
            except Exception:
                pass
        return False, 0


class WindowsIntegration(QObject):
    """Central coordinator for Windows OS integration and system events."""

    # Signal emitted when Windows Explorer restarts and TaskbarCreated is sent
    taskbar_created = Signal()
    # Signal emitted when Windows begins entering sleep / standby
    system_sleep_requested = Signal()
    # Signal emitted when Windows resumes from sleep / standby
    system_resumed = Signal()
    # Signal emitted when monitor resolution or screen configuration changes
    display_configuration_changed = Signal()

    def __init__(self, parent: Optional[QObject] = None, config_manager: Optional[object] = None) -> None:
        super().__init__(parent)
        self._config_manager = config_manager
        self._native_filter: Optional[_WindowsNativeEventFilter] = None
        self._taskbar_created_msg_id: int = 0
        self._is_windows = sys.platform == "win32"

        if self._is_windows:
            self._register_taskbar_created_message()
            self._install_native_event_filter()

        self._setup_monitor_listeners()

        # Global Windows Hotkeys & Keyboard Hook (Bug 18 / SEC-06)
        enable_escape_hook = True
        if self._config_manager and hasattr(self._config_manager, "get"):
            enable_escape_hook = bool(self._config_manager.get("general.enable_global_escape_hook", True))
        from app.core.global_hotkeys import GlobalHotkeyManager
        self.global_hotkeys = GlobalHotkeyManager(parent=self, enable_hook=enable_escape_hook)

    # -------------------------------------------------------------------------
    # High-DPI and Display Scaling
    # -------------------------------------------------------------------------

    @staticmethod
    def configure_high_dpi_scaling() -> None:
        """Configure Qt application attributes for crisp rendering across multi-DPI displays."""
        try:
            from PySide6.QtCore import Qt
            # Use fractional DPI pass-through if supported by Qt 6
            if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
                QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
                )
            logger.info("High DPI display scaling configured successfully.")
        except Exception as e:
            logger.warning("Could not set High DPI scale factor policy: %s", e)

    # -------------------------------------------------------------------------
    # Native Event Registration & Filter
    # -------------------------------------------------------------------------

    def _register_taskbar_created_message(self) -> None:
        """Register the Windows 'TaskbarCreated' broadcast message."""
        try:
            user32 = ctypes.windll.user32
            self._taskbar_created_msg_id = user32.RegisterWindowMessageW("TaskbarCreated")
            logger.debug("Registered Windows TaskbarCreated msg ID: 0x%X", self._taskbar_created_msg_id)
        except Exception as e:
            logger.warning("Failed to register TaskbarCreated message: %s", e)

    def _install_native_event_filter(self) -> None:
        """Install Qt native event filter on the global application instance."""
        app = QCoreApplication.instance()
        if app is not None:
            self._native_filter = _WindowsNativeEventFilter(self._handle_native_message)
            app.installNativeEventFilter(self._native_filter)
            logger.info("Windows native event filter installed.")

    def _handle_native_message(self, message: int, wparam: int, lparam: int) -> None:
        """Dispatch native Windows messages to high-level signals."""
        # 1. Explorer Crash / Restart Taskbar Recovery
        if self._taskbar_created_msg_id and message == self._taskbar_created_msg_id:
            logger.info("Received TaskbarCreated message from Windows Explorer.")
            self.taskbar_created.emit()

        # 2. Windows Power Events (Sleep / Resume)
        elif message == WM_POWERBROADCAST:
            if wparam in (PBT_APMSUSPEND, PBT_APMQUERYSUSPEND):
                logger.info("Windows entering sleep mode (PBT_APMSUSPEND, wParam=0x%X).", wparam)
                self.system_sleep_requested.emit()
            elif wparam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND, PBT_APMRESUMECRITICAL):
                logger.info("Windows resumed from sleep (wParam=0x%X). Triggering subsystem revalidation.", wparam)
                self.system_resumed.emit()

    def _on_native_windows_message(self, message: int, wparam: int, lparam: int) -> None:
        """Alias for _handle_native_message for programmatic/testing dispatch."""
        self._handle_native_message(message, wparam, lparam)

    def simulate_power_event(self, event_type: str) -> None:
        """Simulate power suspend or resume for unit tests or diagnostics."""
        if event_type == "suspend":
            self._handle_native_message(WM_POWERBROADCAST, PBT_APMSUSPEND, 0)
        elif event_type == "resume":
            self._handle_native_message(WM_POWERBROADCAST, PBT_APMRESUMEAUTOMATIC, 0)

    # -------------------------------------------------------------------------
    # Multi-Monitor Management
    # -------------------------------------------------------------------------

    def _setup_monitor_listeners(self) -> None:
        """Connect screen geometry change signals."""
        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)
            app.primaryScreenChanged.connect(self._on_screens_changed)

    @Slot(object)
    def _on_screens_changed(self, *args) -> None:
        """Triggered when monitors are connected, disconnected, or primary changes."""
        logger.info("Display/screen arrangement changed. Revalidating window bounds.")
        self.display_configuration_changed.emit()

    def validate_window_position(self, current_pos: QPoint, window_size: Tuple[int, int]) -> QPoint:
        """Ensure a window at current_pos is visibly positioned within an active screen.

        If the position is stranded off-screen (e.g. after monitor disconnect),
        returns a safe repositioned point on the primary monitor.
        """
        w, h = window_size
        target_rect = QRect(current_pos.x(), current_pos.y(), w, h)
        screens = QApplication.screens()

        # Check if rect intersects any available screen geometry by at least 40px
        is_visible = False
        for screen in screens:
            avail_geo = screen.availableGeometry()
            intersection = avail_geo.intersected(target_rect)
            if intersection.width() >= 40 and intersection.height() >= 40:
                is_visible = True
                break

        if is_visible:
            return current_pos

        # Off-screen — compute safe default position on primary screen
        primary = QApplication.primaryScreen()
        if primary:
            avail = primary.availableGeometry()
            safe_x = avail.right() - w - 40
            safe_y = avail.bottom() - h - 76
            logger.info("Repositioning stranded window to safe coords: (%d, %d)", safe_x, safe_y)
            return QPoint(safe_x, safe_y)

        return current_pos

    def ensure_rect_on_screen(self, rect: QRect) -> QPoint:
        """Alias for validate_window_position taking a QRect."""
        return self.validate_window_position(rect.topLeft(), (rect.width(), rect.height()))

    # -------------------------------------------------------------------------
    # Windows Startup Management
    # -------------------------------------------------------------------------

    @staticmethod
    def is_startup_enabled() -> bool:
        """Check if app is configured to launch on Windows startup."""
        return startup_manager.is_startup_enabled()

    @staticmethod
    def set_startup_enabled(enabled: bool) -> bool:
        """Enable or disable launch on Windows login."""
        return startup_manager.set_startup_enabled(enabled)

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def cleanup(self) -> None:
        """Uninstall native filter and global hotkey hooks on application shutdown."""
        if hasattr(self, "global_hotkeys") and self.global_hotkeys is not None:
            try:
                self.global_hotkeys.cleanup()
            except Exception:
                pass

        app = QCoreApplication.instance()
        if app is not None and self._native_filter is not None:
            try:
                app.removeNativeEventFilter(self._native_filter)
                self._native_filter = None
                logger.debug("Windows native event filter removed.")
            except Exception:
                pass
