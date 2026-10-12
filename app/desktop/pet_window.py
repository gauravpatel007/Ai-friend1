"""Desktop Pet Foundation Window.

Provides a frameless, transparent, draggable window for the AI character.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QPaintEvent, QPainter
from PySide6.QtWidgets import QWidget

from app.core.signals import signals
from app.settings.config_manager import ConfigManager
from app.utils.icon_utils import create_default_pet_pixmap
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DesktopPetWindow(QWidget):
    """Transparent, draggable desktop overlay window housing the pet."""

    def __init__(self, config_manager: ConfigManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self._drag_pos: Optional[QPoint] = None

        self._init_window()
        self._connect_signals()

    def _init_window(self) -> None:
        """Apply window flags, size, and position from configuration."""
        flags = Qt.FramelessWindowHint | Qt.SubWindow
        if self.config_manager.get("pet.always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        size = int(self.config_manager.get("pet.size", 120))
        self.setFixedSize(size, size)

        # Restore saved position or default to bottom-right corner
        pos_x = self.config_manager.get("pet.position_x", None)
        pos_y = self.config_manager.get("pet.position_y", None)

        if pos_x is not None and pos_y is not None:
            self.move(int(pos_x), int(pos_y))
        else:
            self._place_in_default_position()

    def _place_in_default_position(self) -> None:
        """Place character near the bottom-right corner of the primary screen."""
        screen = self.screen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = screen_geo.right() - self.width() - 40
            y = screen_geo.bottom() - self.height() - 60
            self.move(x, y)

    def _connect_signals(self) -> None:
        """Connect to central application signal bus."""
        signals.show_pet_requested.connect(self.show_pet)
        signals.hide_pet_requested.connect(self.hide_pet)
        signals.toggle_pet_requested.connect(self.toggle_pet)
        signals.activate_requested.connect(self.activate_and_highlight)

    def show_pet(self) -> None:
        """Display the pet window."""
        self.show()
        signals.pet_visibility_changed.emit(True)

    def hide_pet(self) -> None:
        """Hide the pet window."""
        self.hide()
        signals.pet_visibility_changed.emit(False)

    def toggle_pet(self) -> None:
        """Toggle visibility of the pet."""
        if self.isVisible():
            self.hide_pet()
        else:
            self.show_pet()

    def activate_and_highlight(self) -> None:
        """Bring pet to front and alert user."""
        self.show_pet()
        self.raise_()
        self.activateWindow()

    # --- Mouse Event Handlers for Dragging ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._drag_pos is not None:
            self._drag_pos = None
            # Persist new position
            self.config_manager.set("pet.position_x", self.x(), auto_save=False)
            self.config_manager.set("pet.position_y", self.y(), auto_save=True)
            signals.pet_moved.emit(self.x(), self.y())
            event.accept()

    # --- Paint Event ---

    def paintEvent(self, event: QPaintEvent) -> None:
        """Render the character sprite on the transparent canvas."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        pixmap = create_default_pet_pixmap(self.width())
        painter.drawPixmap(0, 0, self.width(), self.height(), pixmap)
        painter.end()
