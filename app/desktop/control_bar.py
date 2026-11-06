"""Floating macOS Capsule Control Bar.

A sleek floating macOS Dynamic Island-style capsule dock anchored beneath Buddy:
- Rounded frosted dark glass capsule container (rgba(30, 31, 35, 0.94), hairline border)
- 4 Apple SF Vector Icon Actions:
    • Chat (Apple SF Message bubble, edge-to-edge left pill curve fill)
    • Voice (Apple SF Microphone)
    • Settings (Authentic Apple 6-tooth precision mechanical gear)
    • Hide (Apple SF Close mark, edge-to-edge right pill curve fill)
- Interactive hover retention: stays visible as long as cursor is over Pet or Control Bar
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QEnterEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.signals import signals
from app.utils.logger import get_logger

logger = get_logger(__name__)


def create_sf_icon(name: str, size: int = 18, color: QColor = QColor("#F5F5F7")) -> QPixmap:
    """Render resolution-independent Apple SF Symbol vector icon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    cx = size / 2.0
    cy = size / 2.0

    n = name.lower()
    if "chat" in n or "message" in n:
        pen = QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        w, h = 13.0, 9.5
        bx = cx - w / 2.0
        by = cy - h / 2.0 - 1.0
        path = QPainterPath()
        path.addRoundedRect(QRectF(bx, by, w, h), 3.8, 3.8)
        # Tail
        path.moveTo(cx - 2.5, by + h)
        path.lineTo(cx - 5.0, by + h + 3.0)
        path.lineTo(cx - 0.5, by + h)
        p.drawPath(path)

    elif "voice" in n or "mic" in n:
        pen = QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QBrush(color))
        cap_w, cap_h = 5.0, 9.0
        p.drawRoundedRect(QRectF(cx - cap_w / 2.0, cy - cap_h / 2.0 - 2.0, cap_w, cap_h), 2.5, 2.5)
        p.setBrush(Qt.NoBrush)
        cradle_r = 5.5
        cradle_rect = QRectF(cx - cradle_r, cy - cradle_r, cradle_r * 2.0, cradle_r * 2.0)
        path = QPainterPath()
        path.arcMoveTo(cradle_rect, 0)
        path.arcTo(cradle_rect, 0, -180)
        p.drawPath(path)
        p.drawLine(QPointF(cx, cy + cradle_r), QPointF(cx, cy + cradle_r + 3.0))
        p.drawLine(QPointF(cx - 3.5, cy + cradle_r + 3.0), QPointF(cx + 3.5, cy + cradle_r + 3.0))

    elif "settings" in n or "gear" in n:
        # Authentic Apple 6-tooth mechanical gear with rounded tooth profile and center circular hole
        path = QPainterPath()
        num_teeth = 6
        outer_r = 7.5
        root_r = 5.2
        inner_hole_r = 2.4

        for i in range(num_teeth):
            mid_angle = i * (2.0 * math.pi / num_teeth)
            span = 2.0 * math.pi / num_teeth
            a_v1 = mid_angle - span * 0.42
            a_t1 = mid_angle - span * 0.22
            a_t2 = mid_angle + span * 0.22
            a_v2 = mid_angle + span * 0.42

            p_v1 = QPointF(cx + root_r * math.cos(a_v1), cy + root_r * math.sin(a_v1))
            p_t1 = QPointF(cx + outer_r * math.cos(a_t1), cy + outer_r * math.sin(a_t1))
            p_t2 = QPointF(cx + outer_r * math.cos(a_t2), cy + outer_r * math.sin(a_t2))
            p_v2 = QPointF(cx + root_r * math.cos(a_v2), cy + root_r * math.sin(a_v2))

            if i == 0:
                path.moveTo(p_v1)
            else:
                path.lineTo(p_v1)
            path.lineTo(p_t1)
            path.lineTo(p_t2)
            path.lineTo(p_v2)

        path.closeSubpath()
        hole_path = QPainterPath()
        hole_path.addEllipse(QPointF(cx, cy), inner_hole_r, inner_hole_r)
        gear_path = path.subtracted(hole_path)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(gear_path)

    elif "hide" in n or "close" in n or "xmark" in n:
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        d = 4.0
        p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
        p.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))

    p.end()
    return pix


class CapsuleDockButton(QPushButton):
    """macOS styled action button with vector icon above, text label below, and capsule-matching pill curve fills."""

    def __init__(
        self,
        icon_name: str,
        label_text: str,
        is_accent: bool = True,
        is_destructive: bool = False,
        position_mode: str = "middle",  # 'left', 'middle', 'right'
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.position_mode = position_mode

        btn_width = 54 if position_mode == "left" else (48 if position_mode == "right" else 50)
        self.setFixedSize(btn_width, 46)

        layout = QVBoxLayout(self)
        if position_mode == "left":
            layout.setContentsMargins(6, 4, 2, 4)
        elif position_mode == "right":
            layout.setContentsMargins(2, 4, 6, 4)
        else:
            layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(2)

        self.icon_label = QLabel(self)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")

        icon_color = QColor("#F5F5F7") if not is_destructive else QColor("#D1D1D6")
        self.icon_label.setPixmap(create_sf_icon(icon_name, size=18, color=icon_color))

        self.text_label = QLabel(label_text, self)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet(f"""
            QLabel {{
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, sans-serif;
                font-size: 10.5px;
                font-weight: 500;
                color: {'#A1A1A6' if is_destructive else '#C7C7CC'};
                background: transparent;
            }}
        """)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)

        if position_mode == "left":
            # Completely fill left capsule curve on hover
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-top-left-radius: 23px;
                    border-bottom-left-radius: 23px;
                    border-top-right-radius: 6px;
                    border-bottom-right-radius: 6px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.16);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.24);
                }
            """)
        elif position_mode == "right":
            # Completely fill right capsule curve on hover with macOS system red
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-top-right-radius: 23px;
                    border-bottom-right-radius: 23px;
                    border-top-left-radius: 6px;
                    border-bottom-left-radius: 6px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 69, 58, 0.35);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 69, 58, 0.48);
                }
            """)
        else:
            # Middle buttons
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.14);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.22);
                }
            """)


class FloatingControlBar(QWidget):
    """Floating macOS dark frosted glass capsule dock anchored near the pet character."""

    def __init__(self, parent: Optional[QWidget] = None, pet_window: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pet_window = pet_window
        self._opacity_value = 0.0
        self._target_visible = False
        self._pet_rect: Optional[QRect] = None

        self._init_ui()
        self._init_animation()
        self._connect_signals()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._begin_hide)

    def set_pet_window(self, pet_window: QWidget) -> None:
        """Associate parent pet window for unified hover coordinate tracking."""
        self._pet_window = pet_window

    def _init_ui(self) -> None:
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(1)

        # 4 macOS Action Buttons
        self.btn_chat = CapsuleDockButton("chat", "Chat", is_accent=True, position_mode="left")
        self.btn_voice = CapsuleDockButton("voice", "Voice", is_accent=True, position_mode="middle")
        self.btn_settings = CapsuleDockButton("settings", "Settings", is_accent=False, position_mode="middle")

        # Subtle vertical separator before hide action
        self.sep = QFrame(self)
        self.sep.setFixedWidth(1)
        self.sep.setFixedHeight(24)
        self.sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.14); margin: 0 1px;")

        self.btn_hide = CapsuleDockButton("hide", "Hide", is_accent=False, is_destructive=True, position_mode="right")

        layout.addWidget(self.btn_chat)
        layout.addWidget(self.btn_voice)
        layout.addWidget(self.btn_settings)
        layout.addWidget(self.sep)
        layout.addWidget(self.btn_hide)

        self.setLayout(layout)
        self.adjustSize()

    def _init_animation(self) -> None:
        self._fade_anim = QPropertyAnimation(self, b"bar_opacity", self)
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

    def _connect_signals(self) -> None:
        self.btn_chat.clicked.connect(signals.open_chat_requested.emit)
        self.btn_voice.clicked.connect(signals.open_voice_window_requested.emit)
        self.btn_settings.clicked.connect(signals.open_settings_requested.emit)
        self.btn_hide.clicked.connect(signals.hide_pet_requested.emit)

    def _get_bar_opacity(self) -> float:
        return self._opacity_value

    def _set_bar_opacity(self, value: float) -> None:
        self._opacity_value = value
        self.setWindowOpacity(value)
        if value <= 0.01 and not self._target_visible:
            self.hide()

    bar_opacity = Property(float, _get_bar_opacity, _set_bar_opacity)

    def show_bar(self, pet_rect: QRect) -> None:
        """Display control bar and keep it visible while mouse interacts with pet or bar."""
        self._pet_rect = pet_rect
        self._target_visible = True
        self._reposition(pet_rect)
        self.show()
        # Do NOT auto-hide after fixed seconds! Stays visible as long as user is hovering.
        self._hide_timer.stop()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity_value)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def hide_bar(self) -> None:
        self._target_visible = False
        self._hide_timer.stop()
        self._begin_hide()

    def _begin_hide(self) -> None:
        # Before fading out, verify cursor is NOT over the bar or pet
        cursor_pos = QCursor.pos()
        bar_rect = self.frameGeometry().adjusted(-10, -10, 10, 10)
        if bar_rect.contains(cursor_pos):
            # Cursor is still on the control bar: keep visible!
            return

        if self._pet_window:
            pet_rect = self._pet_window.frameGeometry().adjusted(-10, -10, 10, 10)
            if pet_rect.contains(cursor_pos):
                # Cursor is still on the pet: keep visible!
                return

        self._target_visible = False
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity_value)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _reposition(self, pet_rect: QRect) -> None:
        bar_width = self.sizeHint().width()
        bar_height = self.sizeHint().height()
        gap = 8

        screen = (
            QApplication.screenAt(pet_rect.center())
            or QApplication.screenAt(pet_rect.topLeft())
            or self.screen()
            or QApplication.primaryScreen()
        )
        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        bar_x = pet_rect.center().x() - bar_width // 2

        # Keep dock cleanly separated from pet — zero overlap
        if pet_rect.bottom() + gap + bar_height <= screen_geo.bottom():
            bar_y = pet_rect.bottom() + gap
        elif pet_rect.left() - gap - bar_width >= screen_geo.left():
            bar_x = pet_rect.left() - gap - bar_width
            bar_y = pet_rect.bottom() - bar_height
        else:
            bar_x = pet_rect.right() + gap
            bar_y = pet_rect.bottom() - bar_height

        bar_x = max(screen_geo.left() + 4, min(bar_x, screen_geo.right() - bar_width - 4))
        bar_y = max(screen_geo.top() + 4, min(bar_y, screen_geo.bottom() - bar_height - 4))

        self.move(bar_x, bar_y)

    def update_position(self, pet_rect: QRect) -> None:
        self._pet_rect = pet_rect
        if self.isVisible():
            self._reposition(pet_rect)

    def enterEvent(self, event: QEnterEvent) -> None:
        # Cursor entered control bar: stop any hide timer on bar and on pet
        self._hide_timer.stop()
        if self._pet_window and hasattr(self._pet_window, "_hover_hide_timer"):
            self._pet_window._hover_hide_timer.stop()

        if self._opacity_value < 1.0:
            self._fade_anim.stop()
            self._fade_anim.setStartValue(self._opacity_value)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        # Check if cursor moved directly up into the pet window
        cursor_pos = QCursor.pos()
        if self._pet_window:
            pet_rect = self._pet_window.frameGeometry().adjusted(-10, -10, 10, 10)
            if pet_rect.contains(cursor_pos):
                # Cursor moved back to pet: stay visible!
                return

        # Cursor left both: start graceful hide timer (700ms grace period)
        self._hide_timer.start(700)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(1, 1, -1, -1)
        r_float = QRectF(rect)

        # macOS Dark Frosted Glass Capsule
        path = QPainterPath()
        radius = r_float.height() / 2.0
        path.addRoundedRect(r_float, radius, radius)
        painter.fillPath(path, QColor(30, 31, 35, 240))

        # Delicate frosted hairline border
        pen = QPen(QColor(255, 255, 255, 36))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.end()
