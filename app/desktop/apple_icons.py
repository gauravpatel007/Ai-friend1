"""Apple SF Symbols & Vector Graphics Engine for PySide6.

Renders crisp, resolution-independent Apple-style vector iconography
without any emojis or blurry bitmap assets.
"""

from __future__ import annotations

import math
from typing import Optional
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)


def create_pixmap(size: int = 24) -> tuple[QPixmap, QPainter]:
    """Helper to create an empty transparent pixmap and configured QPainter."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    return pix, painter


# ─── Core Apple SF Vector Drawing Routines ─────────────────────────────

def draw_mic(painter: QPainter, rect: QRectF, color: QColor, muted: bool = False) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    pen = QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)

    # Capsule
    cap_w = 6.0
    cap_h = 12.0
    cap_x = cx - cap_w / 2.0
    cap_y = cy - cap_h / 2.0 - 2.0
    painter.setBrush(QBrush(color) if not muted else Qt.NoBrush)
    painter.drawRoundedRect(QRectF(cap_x, cap_y, cap_w, cap_h), cap_w / 2.0, cap_w / 2.0)

    # Cradle Arc
    painter.setBrush(Qt.NoBrush)
    cradle_r = 7.0
    cradle_rect = QRectF(cx - cradle_r, cy - cradle_r + 1.0, cradle_r * 2.0, cradle_r * 2.0)
    path = QPainterPath()
    path.arcMoveTo(cradle_rect, 0)
    path.arcTo(cradle_rect, 0, -180)
    painter.drawPath(path)

    # Stem and Base
    stem_top = cy + cradle_r + 1.0
    painter.drawLine(QPointF(cx, stem_top), QPointF(cx, stem_top + 4.0))
    painter.drawLine(QPointF(cx - 5.0, stem_top + 4.0), QPointF(cx + 5.0, stem_top + 4.0))

    if muted:
        # Diagonal slash
        slash_pen = QPen(QColor(255, 69, 58), 2.0, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(slash_pen)
        painter.drawLine(QPointF(cx - 9.0, cy - 9.0), QPointF(cx + 9.0, cy + 9.0))


def draw_stop(painter: QPainter, rect: QRectF, color: QColor) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    s = 14.0
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawRoundedRect(QRectF(cx - s / 2.0, cy - s / 2.0, s, s), 3.0, 3.0)


def draw_gear(painter: QPainter, rect: QRectF, color: QColor) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    pen = QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # Center circle
    r = 3.8
    painter.drawEllipse(QPointF(cx, cy), r, r)

    # 6 subtle teeth spokes
    tooth_r1 = 5.6
    tooth_r2 = 8.4
    for i in range(6):
        angle = i * (math.pi / 3.0)
        p1 = QPointF(cx + math.cos(angle) * tooth_r1, cy + math.sin(angle) * tooth_r1)
        p2 = QPointF(cx + math.cos(angle) * tooth_r2, cy + math.sin(angle) * tooth_r2)
        painter.drawLine(p1, p2)


def draw_xmark(painter: QPainter, rect: QRectF, color: QColor) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    d = 4.5
    pen = QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
    painter.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))


def draw_search(painter: QPainter, rect: QRectF, color: QColor) -> None:
    cx = rect.center().x() - 1.5
    cy = rect.center().y() - 1.5
    pen = QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    r = 5.0
    painter.drawEllipse(QPointF(cx, cy), r, r)

    # Handle
    h_len = 4.5
    start_x = cx + r * math.cos(math.pi / 4.0)
    start_y = cy + r * math.sin(math.pi / 4.0)
    painter.drawLine(
        QPointF(start_x, start_y),
        QPointF(start_x + h_len, start_y + h_len),
    )


def draw_plus(painter: QPainter, rect: QRectF, color: QColor) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    d = 5.0
    pen = QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(cx - d, cy), QPointF(cx + d, cy))
    painter.drawLine(QPointF(cx, cy - d), QPointF(cx, cy + d))


def draw_pencil(painter: QPainter, rect: QRectF, color: QColor) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # Slanted pencil body
    path = QPainterPath()
    path.moveTo(cx - 5.0, cy + 5.0)
    path.lineTo(cx - 2.0, cy + 5.0)
    path.lineTo(cx + 5.0, cy - 2.0)
    path.lineTo(cx + 2.0, cy - 5.0)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(cx - 5.0, cy + 5.0), QPointF(cx - 6.0, cy + 6.0))


def draw_trash(painter: QPainter, rect: QRectF, color: QColor) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # Lid
    painter.drawLine(QPointF(cx - 6.0, cy - 4.5), QPointF(cx + 6.0, cy - 4.5))
    painter.drawLine(QPointF(cx - 2.0, cy - 6.5), QPointF(cx + 2.0, cy - 6.5))

    # Can
    path = QPainterPath()
    path.moveTo(cx - 4.5, cy - 4.5)
    path.lineTo(cx - 3.5, cy + 6.0)
    path.lineTo(cx + 3.5, cy + 6.0)
    path.lineTo(cx + 4.5, cy - 4.5)
    painter.drawPath(path)

    # Ribs
    painter.drawLine(QPointF(cx, cy - 2.0), QPointF(cx, cy + 4.0))


def draw_globe(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Draw crisp Apple SF Symbol Globe (for Language & Internationalization)."""
    cx = rect.center().x()
    cy = rect.center().y()
    pen = QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    r = 6.8
    # Outer sphere
    painter.drawEllipse(QPointF(cx, cy), r, r)

    # Equator line
    painter.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))

    # Central meridian ellipse
    painter.drawEllipse(QRectF(cx - 3.2, cy - r, 6.4, r * 2.0))


def draw_symbol_by_name(name: str, painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Dispatch symbol drawer by name."""
    n = name.lower()
    if "gear" in n or "general" in n:
        draw_gear(painter, rect, color)
    elif "character" in n or "sparkle" in n:
        # Star / Sparkle
        cx = rect.center().x()
        cy = rect.center().y()
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        d = 6.0
        painter.drawLine(QPointF(cx, cy - d), QPointF(cx, cy + d))
        painter.drawLine(QPointF(cx - d, cy), QPointF(cx + d, cy))
        d2 = 3.5
        painter.drawLine(QPointF(cx - d2, cy - d2), QPointF(cx + d2, cy + d2))
        painter.drawLine(QPointF(cx - d2, cy + d2), QPointF(cx + d2, cy - d2))
    elif "model" in n or "brain" in n or "ai" in n:
        # Neural chip / processor symbol
        cx = rect.center().x()
        cy = rect.center().y()
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        s = 8.0
        painter.drawRoundedRect(QRectF(cx - s / 2.0, cy - s / 2.0, s, s), 2.0, 2.0)
        # Pins
        for offset in (-2.0, 2.0):
            painter.drawLine(QPointF(cx + offset, cy - 4.0), QPointF(cx + offset, cy - 6.5))
            painter.drawLine(QPointF(cx + offset, cy + 4.0), QPointF(cx + offset, cy + 6.5))
            painter.drawLine(QPointF(cx - 4.0, cy + offset), QPointF(cx - 6.5, cy + offset))
            painter.drawLine(QPointF(cx + 4.0, cy + offset), QPointF(cx + 6.5, cy + offset))
    elif "voice" in n or "mic" in n:
        draw_mic(painter, rect, color, muted=False)
    elif "personality" in n:
        # Sliders / Dial
        cx = rect.center().x()
        cy = rect.center().y()
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(cx - 6.0, cy - 3.0), QPointF(cx + 6.0, cy - 3.0))
        painter.drawLine(QPointF(cx - 6.0, cy + 3.0), QPointF(cx + 6.0, cy + 3.0))
        # Knobs
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(cx - 2.0, cy - 3.0), 2.0, 2.0)
        painter.drawEllipse(QPointF(cx + 2.0, cy + 3.0), 2.0, 2.0)
    elif "memory" in n:
        # Cylinder database / stacked disks
        cx = rect.center().x()
        cy = rect.center().y()
        pen = QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        w, h = 11.0, 4.0
        painter.drawEllipse(QRectF(cx - w / 2.0, cy - 6.0, w, h))
        painter.drawArc(QRectF(cx - w / 2.0, cy - 2.0, w, h), 0, -180 * 16)
        painter.drawArc(QRectF(cx - w / 2.0, cy + 2.0, w, h), 0, -180 * 16)
        painter.drawLine(QPointF(cx - w / 2.0, cy - 4.0), QPointF(cx - w / 2.0, cy + 4.0))
        painter.drawLine(QPointF(cx + w / 2.0, cy - 4.0), QPointF(cx + w / 2.0, cy + 4.0))
    elif "appearance" in n:
        # Paint palette
        cx = rect.center().x()
        cy = rect.center().y()
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), 6.5, 6.0)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(cx - 2.5, cy - 2.0), 1.2, 1.2)
        painter.drawEllipse(QPointF(cx + 2.0, cy - 2.0), 1.2, 1.2)
        painter.drawEllipse(QPointF(cx - 1.5, cy + 2.0), 1.2, 1.2)
    elif "hotkey" in n or "keyboard" in n:
        # Command ⌘ symbol or Keyboard
        cx = rect.center().x()
        cy = rect.center().y()
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(cx - 6.5, cy - 4.5, 13.0, 9.0), 2.0, 2.0)
        painter.drawLine(QPointF(cx - 3.5, cy + 2.0), QPointF(cx + 3.5, cy + 2.0))
    elif "startup" in n:
        # Rocket / Arrow Launch
        cx = rect.center().x()
        cy = rect.center().y()
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(cx, cy - 6.0), QPointF(cx, cy + 5.0))
        painter.drawLine(QPointF(cx, cy - 6.0), QPointF(cx - 4.0, cy - 2.0))
        painter.drawLine(QPointF(cx, cy - 6.0), QPointF(cx + 4.0, cy - 2.0))
        painter.drawLine(QPointF(cx - 5.0, cy + 5.0), QPointF(cx + 5.0, cy + 5.0))
    elif "advanced" in n:
        # Equalizer sliders
        cx = rect.center().x()
        cy = rect.center().y()
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for offset, knob_y in ((-4.0, -1.0), (0.0, 2.0), (4.0, -3.0)):
            painter.drawLine(QPointF(cx + offset, cy - 6.0), QPointF(cx + offset, cy + 6.0))
            painter.drawLine(QPointF(cx + offset - 1.5, cy + knob_y), QPointF(cx + offset + 1.5, cy + knob_y))
    elif "language" in n or "globe" in n or "communication" in n:
        draw_globe(painter, rect, color)
    else:
        draw_gear(painter, rect, color)


# ─── Sidebar Squircle Icon Generator ───────────────────────────────────

# Apple System Palette Gradients for Settings Categories
CATEGORY_GRADIENTS = {
    "general":                  ("#8E8E93", "#636366"),  # Apple System Gray
    "character":                ("#30B0C7", "#00839B"),  # Apple System Teal
    "ai model":                 ("#5E5CE6", "#3634A3"),  # Apple System Indigo
    "language & communication": ("#00C7BE", "#00839B"),  # Apple System Teal / Cyan
    "language":                 ("#00C7BE", "#00839B"),  # Apple System Teal / Cyan
    "voice":                    ("#BF5AF2", "#8944AB"),  # Apple System Purple
    "personality":              ("#FF9F0A", "#C97800"),  # Apple System Orange
    "memory":                   ("#32D74B", "#248A3D"),  # Apple System Green
    "appearance":               ("#0A84FF", "#0062D2"),  # Apple System Blue
    "hotkeys":                  ("#AF52DE", "#7D33A6"),  # Apple System Violet
    "startup":                  ("#FF375F", "#BF1538"),  # Apple System Red/Rose
    "advanced":                 ("#64748B", "#475569"),  # Apple System Slate
}


def create_apple_squircle_icon(category_name: str, size: int = 26) -> QIcon:
    """Create a pristine Apple macOS Settings squircle badge with vector symbol."""
    pix, painter = create_pixmap(size)

    key = category_name.lower().strip()
    c1_str, c2_str = CATEGORY_GRADIENTS.get(key, ("#64748B", "#475569"))

    # Squircle Background (Apple continuous smooth rounded rect)
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, QColor(c1_str))
    grad.setColorAt(1.0, QColor(c2_str))

    r = size * 0.26  # Apple squircle radius
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1.0, size - 1.0), r, r)

    # Subtle inner top highlight
    highlight_pen = QPen(QColor(255, 255, 255, 70), 0.8)
    painter.setPen(highlight_pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(1.0, 1.0, size - 2.0, size - 2.0), r - 0.5, r - 0.5)

    # Draw white vector symbol in center
    rect = QRectF(0, 0, size, size)
    draw_symbol_by_name(category_name, painter, rect, QColor(255, 255, 255))
    painter.end()

    return QIcon(pix)


def create_button_icon(name: str, size: int = 24, color: QColor = QColor(245, 245, 247)) -> QIcon:
    """Create a standalone monochrome vector icon for action buttons."""
    pix, painter = create_pixmap(size)
    rect = QRectF(0, 0, size, size)
    if name == "mic":
        draw_mic(painter, rect, color, muted=False)
    elif name == "mic_muted":
        draw_mic(painter, rect, color, muted=True)
    elif name == "stop":
        draw_stop(painter, rect, color)
    elif name == "gear":
        draw_gear(painter, rect, color)
    elif name == "close" or name == "x":
        draw_xmark(painter, rect, color)
    elif name == "search":
        draw_search(painter, rect, color)
    elif name == "plus":
        draw_plus(painter, rect, color)
    elif name == "pencil":
        draw_pencil(painter, rect, color)
    elif name == "trash":
        draw_trash(painter, rect, color)
    elif name in ("globe", "language"):
        draw_globe(painter, rect, color)
    else:
        draw_symbol_by_name(name, painter, rect, color)
    painter.end()
    return QIcon(pix)
