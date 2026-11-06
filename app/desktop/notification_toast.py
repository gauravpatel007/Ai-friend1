"""Desktop Notification Toast — Glassmorphic Floating Card (Showcase Section 9).

Provides a premium desktop toast card matching the JARVIS showcase design:
- Sleek dark slate glass styling (#0B1120, border #1E293B) with cyan drop shadow.
- Header with circular Buddy avatar, 'Buddy' title, 'now' timestamp, and close button.
- Clean notification body text.
- Smooth positioning in the lower-right screen corner.
- Auto-dismiss timer with mouse hover pause support.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Set

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QFont, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from app.core.signals import signals
from app.utils.logger import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_AVATAR_PATH = _PROJECT_ROOT / "assets" / "icons" / "buddy_avatar.png"

# Module-level registry holding strong references to prevent premature GC destruction (Bug 20)
_active_toasts: Set[NotificationToast] = set()


def get_active_toasts() -> Set[NotificationToast]:
    """Return the set of currently active notification toasts."""
    return set(_active_toasts)


def clear_all_toasts() -> None:
    """Close and clear all currently active notification toasts."""
    for toast in list(_active_toasts):
        try:
            toast.close()
        except Exception:
            pass
    _active_toasts.clear()


class NotificationToast(QWidget):
    """Floating desktop toast notification matching Showcase Section 9."""

    def __init__(
        self,
        title: str = "Buddy",
        message: str = "",
        duration_ms: int = 4500,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.duration_ms = duration_ms
        self._is_closing = False
        self._fade_anim: Optional[QPropertyAnimation] = None
        self._fade_in_anim: Optional[QPropertyAnimation] = None

        self._init_window()
        self._init_ui(title, message)
        self._setup_timer()

        # Retain strong reference to prevent garbage collection destruction
        _active_toasts.add(self)
        self.destroyed.connect(self._on_destroyed)

    def _init_window(self) -> None:
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(320, 92)

    def _init_ui(self, title: str, message: str) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)

        self.bg_frame = QFrame(self)
        self.bg_frame.setStyleSheet("""
            QFrame {
                background-color: #0B1120;
                border: 1px solid #1E293B;
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(14, 165, 233, 90))
        self.bg_frame.setGraphicsEffect(shadow)

        frame_layout = QVBoxLayout(self.bg_frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(6)

        # Header Row: Avatar + Title + "now" + Close button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        # Avatar
        self.avatar_lbl = QLabel(self.bg_frame)
        self.avatar_lbl.setFixedSize(22, 22)
        if _AVATAR_PATH.exists():
            pix = QPixmap(str(_AVATAR_PATH)).scaled(
                22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.avatar_lbl.setPixmap(pix)
        else:
            self.avatar_lbl.setText("🤖")
        header_row.addWidget(self.avatar_lbl)

        # Title
        self.title_lbl = QLabel(title, self.bg_frame)
        self.title_lbl.setStyleSheet("""
            color: #F8FAFC;
            font-family: 'Segoe UI', sans-serif;
            font-size: 13px;
            font-weight: 700;
        """)
        header_row.addWidget(self.title_lbl)

        # Timestamp "now"
        self.time_lbl = QLabel("now", self.bg_frame)
        self.time_lbl.setStyleSheet("""
            color: #64748B;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: 500;
        """)
        header_row.addWidget(self.time_lbl)

        header_row.addStretch()

        # Close button
        self.btn_close = QPushButton("✕", self.bg_frame)
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748B;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #EF4444;
            }
        """)
        self.btn_close.clicked.connect(self.dismiss)
        header_row.addWidget(self.btn_close)

        frame_layout.addLayout(header_row)

        # Body Message
        self.msg_lbl = QLabel(message, self.bg_frame)
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setStyleSheet("""
            color: #94A3B8;
            font-family: 'Segoe UI', sans-serif;
            font-size: 12px;
            font-weight: 400;
        """)
        frame_layout.addWidget(self.msg_lbl)

        outer_layout.addWidget(self.bg_frame)

    def _setup_timer(self) -> None:
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(self.duration_ms)
        self._dismiss_timer.timeout.connect(self.dismiss)
        self._dismiss_timer.start()

    @Slot()
    def _on_destroyed(self) -> None:
        _active_toasts.discard(self)

    def closeEvent(self, event) -> None:
        _active_toasts.discard(self)
        super().closeEvent(event)

    @Slot()
    def dismiss(self) -> None:
        """Smoothly dismiss the toast with a fade-out animation."""
        if self._is_closing:
            return
        self._is_closing = True
        self._dismiss_timer.stop()

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(180)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self._finish_close)
        self._fade_anim.start()

    def _finish_close(self) -> None:
        _active_toasts.discard(self)
        self.close()

    def show_toast(self) -> None:
        """Position in bottom-right corner, stack neatly, and display with fade-in."""
        _active_toasts.add(self)

        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            target_x = avail.right() - self.width() - 16

            # Dynamically calculate offset to stack nicely above already active visible toasts
            visible_others = [t for t in _active_toasts if t is not self and t.isVisible()]
            offset_y = len(visible_others) * (self.height() + 10)
            target_y = avail.bottom() - self.height() - 16 - offset_y
            if target_y < avail.top() + 16:
                target_y = avail.bottom() - self.height() - 16

            self.move(target_x, target_y)

        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        # Smooth fade-in
        self._fade_in_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in_anim.setDuration(180)
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)
        self._fade_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in_anim.start()

    def enterEvent(self, event) -> None:
        """Pause dismiss on mouse hover."""
        self._dismiss_timer.stop()
        if self._is_closing and self._fade_anim:
            self._fade_anim.stop()
            self.setWindowOpacity(1.0)
            self._is_closing = False
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Resume dismiss timer on leave."""
        self._dismiss_timer.start(1800)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            signals.open_chat_requested.emit()
            self.dismiss()
        super().mousePressEvent(event)


def show_buddy_toast(title: str, message: str, duration_ms: int = 4500) -> NotificationToast:
    """Convenience helper to spawn a desktop toast."""
    toast = NotificationToast(title=title, message=message, duration_ms=duration_ms)
    toast.show_toast()
    return toast
