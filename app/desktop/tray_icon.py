"""System Tray Integration.

Manages the system tray icon, context menus, and tray notifications.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.core.signals import signals
from app.utils.icon_utils import get_application_icon
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SystemTrayManager(QObject):
    """System tray icon and context menu controller."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._toggle_action: Optional[QAction] = None
        self._voice_action: Optional[QAction] = None

    def initialize(self) -> bool:
        """Create and display the system tray icon."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not supported on this platform.")
            return False

        icon = get_application_icon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("AI Desktop Friend")

        # Context Menu
        menu = QMenu()

        self._toggle_action = QAction("Hide AI Friend", menu)
        self._toggle_action.triggered.connect(signals.toggle_pet_requested.emit)
        menu.addAction(self._toggle_action)

        self._voice_action = QAction("Voice Active", menu)
        self._voice_action.setCheckable(True)
        self._voice_action.setChecked(False)
        self._voice_action.triggered.connect(self._on_voice_toggle)
        menu.addAction(self._voice_action)

        sleep_action = QAction("Sleep Mode", menu)
        sleep_action.triggered.connect(lambda: signals.character_state_changed.emit("sleeping"))
        menu.addAction(sleep_action)

        menu.addSeparator()

        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(lambda: logger.info("Settings requested from tray."))
        menu.addAction(settings_action)

        menu.addSeparator()

        exit_action = QAction("Exit AI Friend", menu)
        exit_action.triggered.connect(signals.shutdown_requested.emit)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)

        # Connect signals
        signals.pet_visibility_changed.connect(self._on_pet_visibility_changed)

        self.tray_icon.show()
        logger.info("System tray initialized.")
        return True

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Triggered when the user interacts with the tray icon."""
        if reason == QSystemTrayIcon.Trigger:  # Single click
            signals.toggle_pet_requested.emit()
        elif reason == QSystemTrayIcon.DoubleClick:
            signals.show_pet_requested.emit()

    def _on_pet_visibility_changed(self, visible: bool) -> None:
        if self._toggle_action:
            self._toggle_action.setText("Hide AI Friend" if visible else "Show AI Friend")

    def _on_voice_toggle(self, checked: bool) -> None:
        signals.voice_state_changed.emit("listening" if checked else "muted")

    def show_message(self, title: str, message: str) -> None:
        """Display native Windows desktop toast notification from the tray."""
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 3000)

    def cleanup(self) -> None:
        """Clean up tray icon on shutdown."""
        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon = None
