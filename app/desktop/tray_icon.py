"""System Tray Integration.

Manages the system tray icon, context menus, and tray notifications.
"""

from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QObject, Slot, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.core.signals import signals
from app.utils.icon_utils import get_application_icon, get_tray_icon
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SystemTrayManager(QObject):
    """System tray icon and context menu controller."""

    def __init__(self, config_manager: Optional[Any] = None, parent: Optional[QObject] = None) -> None:
        # Support passing parent as first positional argument for backward compatibility
        if isinstance(config_manager, QObject) and parent is None:
            parent = config_manager
            config_manager = None
        super().__init__(parent)
        self.config_manager = config_manager
        if self.config_manager is None:
            try:
                from app.settings.config_manager import get_config_manager
                self.config_manager = get_config_manager()
            except Exception:
                self.config_manager = None

        if self.config_manager:
            self.config_manager.setting_changed.connect(self._on_setting_changed)

        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._toggle_action: Optional[QAction] = None
        self._voice_action: Optional[QAction] = None
        self._active_toasts: list[Any] = []

    def _get_companion_name(self) -> str:
        if self.config_manager:
            return str(self.config_manager.get("ai.companion_name") or self.config_manager.get("companion.name") or "Buddy").strip()
        return "Buddy"

    def initialize(self) -> bool:
        """Create and display the system tray icon."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not supported on this platform.")
            return False

        icon = get_tray_icon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        name = self._get_companion_name()
        self.tray_icon.setToolTip(f"{name} — AI Desktop Friend")

        # Context Menu matching macOS Dark Glass Design
        menu = QMenu()
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint)
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(30, 31, 35, 0.96);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 10px;
                padding: 5px 4px;
                color: #F5F5F7;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
                font-size: 13px;
                font-weight: 400;
            }
            QMenu::item {
                padding: 5px 22px 5px 12px;
                border-radius: 5px;
                margin: 1px 2px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #007AFF;
                color: #FFFFFF;
                font-weight: 500;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 0.12);
                margin: 5px 8px;
            }
            QMenu::right-arrow {
                width: 8px;
                height: 8px;
                margin-right: 6px;
            }
        """)

        # 1. Open Chat
        chat_action = QAction("💬 Open Chat", menu)
        chat_action.triggered.connect(signals.open_chat_requested.emit)
        menu.addAction(chat_action)

        # 2. Voice Window (Dedicated Holographic Voice Portal)
        voice_win_action = QAction("🎙️ Voice Window", menu)
        voice_win_action.triggered.connect(signals.toggle_voice_window_requested.emit)
        menu.addAction(voice_win_action)

        self._toggle_action = QAction("👁️ Hide AI Friend", menu)
        self._toggle_action.triggered.connect(signals.toggle_pet_requested.emit)
        menu.addAction(self._toggle_action)

        self._voice_action = QAction("🎙️ Voice Active", menu)
        self._voice_action.setCheckable(True)
        self._voice_action.setChecked(False)
        self._voice_action.triggered.connect(lambda checked=False: signals.voice_toggle_requested.emit())
        menu.addAction(self._voice_action)

        # Voice Activation Modes Submenu (Phase 9.8)
        self.mode_menu = menu.addMenu("⚡ Activation Modes")
        self.mode_menu.setWindowFlags(self.mode_menu.windowFlags() | Qt.FramelessWindowHint)
        self.mode_menu.setAttribute(Qt.WA_TranslucentBackground, True)
        self.mode_menu.setStyleSheet("""
            QMenu {
                background-color: rgba(30, 31, 35, 0.96);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 10px;
                padding: 5px 4px;
                color: #F5F5F7;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
                font-size: 13px;
                font-weight: 400;
            }
            QMenu::item {
                padding: 5px 22px 5px 12px;
                border-radius: 5px;
                margin: 1px 2px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #007AFF;
                color: #FFFFFF;
                font-weight: 500;
            }
        """)
        self._mode_actions: dict[str, QAction] = {}
        for mode_key, mode_title in [
            ("continuous", "⚡ Continuous Dialogue"),
            ("wake_word", "👂 Wake Word ('Hey Buddy')"),
            ("push_to_talk", "🎙️ Push-to-Talk"),
            ("off", "🔇 Voice Off"),
        ]:
            action = QAction(mode_title, self.mode_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, m=mode_key: signals.activation_mode_changed.emit(m))
            self.mode_menu.addAction(action)
            self._mode_actions[mode_key] = action

        # Emergency Stop Action (Phase 9.9)
        emergency_action = QAction("🚨 Emergency Stop Listening", menu)
        emergency_action.triggered.connect(signals.emergency_stop_requested.emit)
        menu.addAction(emergency_action)

        self._sleep_action = QAction("🌙 Sleep Mode", menu)
        self._sleep_action.triggered.connect(self._toggle_sleep)
        menu.addAction(self._sleep_action)

        menu.addSeparator()

        settings_action = QAction("⚙️ Settings...", menu)
        settings_action.triggered.connect(signals.open_settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        exit_action = QAction("⏻ Exit AI Friend", menu)
        def _on_tray_exit():
            from app.core.lifecycle import get_lifecycle_manager
            get_lifecycle_manager().request_shutdown(source="system_tray_menu")
        exit_action.triggered.connect(_on_tray_exit)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)

        # Connect signals
        signals.pet_visibility_changed.connect(self._on_pet_visibility_changed)
        signals.activation_mode_changed.connect(self._on_mode_changed)
        signals.voice_state_changed.connect(self._on_mode_changed)

        self.tray_icon.show()
        logger.info("System tray initialized.")
        return True

    def _on_mode_changed(self, mode: str) -> None:
        """Update radio checkmarks in tray voice mode submenu."""
        for key, action in getattr(self, "_mode_actions", {}).items():
            action.setChecked(key == mode)
        if self._voice_action:
            self._voice_action.setChecked(mode not in ("off", "", "muted"))

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Triggered when the user interacts with the tray icon."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # Single click
            signals.toggle_pet_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            signals.show_pet_requested.emit()

    def _on_pet_visibility_changed(self, visible: bool) -> None:
        if self._toggle_action:
            self._toggle_action.setText("Hide AI Friend" if visible else "Show AI Friend")

    def _toggle_sleep(self) -> None:
        """Request application sleep mode toggle."""
        signals.sleep_requested.emit()

    def _on_voice_toggle(self, checked: bool = False) -> None:
        signals.voice_toggle_requested.emit()

    def show_message(self, title: str, message: str) -> None:
        """Display desktop notification card and tray message."""
        if self.config_manager:
            if not self.config_manager.get("general.show_tray_notifications", True):
                return
            if title == "No Speech Heard" and not self.config_manager.get("voice.notify_on_empty_speech", False):
                return

        try:
            from app.desktop.notification_toast import show_buddy_toast
            toast = show_buddy_toast(title=title, message=message)
            self._active_toasts = [t for t in self._active_toasts if t.isVisible()]
            self._active_toasts.append(toast)
        except Exception as e:
            logger.debug("Failed to spawn custom toast: %s", e)

        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def recover_tray_icon(self) -> None:
        """Recover tray icon when Windows Explorer restarts (Phase 11.7)."""
        logger.info("Recovering system tray icon after TaskbarCreated/Explorer restart...")
        if self.tray_icon:
            try:
                self.tray_icon.hide()
            except Exception:
                pass
            self.tray_icon.show()
        else:
            self.initialize()

    def ensure_tray_visible(self) -> None:
        """Ensure system tray icon is properly displayed and active in notification area."""
        if not self.tray_icon:
            self.initialize()
            return
        if not self.tray_icon.isVisible():
            self.tray_icon.show()
        self.tray_icon.setIcon(get_application_icon())
        name = self._get_companion_name()
        self.tray_icon.setToolTip(f"{name} — AI Desktop Friend")

    @Slot(str, object)
    def _on_setting_changed(self, key: str, val: Any) -> None:
        """Dynamically update system tray tooltip on companion name change."""
        if key in ("ai.companion_name", "companion.name", "character.name"):
            name = str(val).strip() if val else "Buddy"
            from PySide6.QtCore import QTimer
            if self.tray_icon:
                QTimer.singleShot(0, lambda: self.tray_icon.setToolTip(f"{name} — AI Desktop Friend") if self.tray_icon else None)

    def cleanup(self) -> None:
        """Clean up tray icon on shutdown."""
        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon = None
