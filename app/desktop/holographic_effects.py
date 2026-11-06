"""Holographic and HUD visual effects for JARVIS interface.

Provides reusable QPainter routines and effect helpers for:
- Scan-line overlays
- Hexagonal and grid tessellations
- Sci-fi HUD corner brackets
- Radial energy rings and glow effects
- Drop shadow / glow widget enhancements
"""

from __future__ import annotations

import math
from typing import Optional, Union

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from app.desktop.jarvis_theme import COLORS, qcolor


def draw_scan_lines(
    painter: QPainter,
    rect: Union[QRect, QRectF],
    spacing: int = 4,
    opacity: float = 0.04,
    color: Optional[QColor] = None,
) -> None:
    """Draw subtle horizontal CRT/HUD scan-lines over a given rect."""
    painter.save()
    c = QColor(color) if color else qcolor("arc_bright")
    c.setAlphaF(max(0.0, min(1.0, opacity)))

    pen = QPen(c)
    pen.setWidth(1)
    painter.setPen(pen)

    top = int(rect.top())
    bottom = int(rect.bottom())
    left = float(rect.left())
    right = float(rect.right())

    # Draw every 'spacing' pixels
    for y in range(top, bottom, max(2, spacing)):
        painter.drawLine(QPointF(left, float(y)), QPointF(right, float(y)))

    painter.restore()


def draw_corner_brackets(
    painter: QPainter,
    rect: Union[QRect, QRectF],
    size: int = 14,
    color: Optional[QColor] = None,
    width: int = 2,
    offset: int = 2,
) -> None:
    """Draw HUD-style corner brackets [⌐ ¬ ⌙ ⌟] on the perimeter of a rect."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, False)

    c = QColor(color) if color else qcolor("arc_blue")
    pen = QPen(c)
    pen.setWidth(width)
    pen.setCapStyle(Qt.SquareCap)
    painter.setPen(pen)

    l = float(rect.left()) + offset
    r = float(rect.right()) - offset
    t = float(rect.top()) + offset
    b = float(rect.bottom()) - offset
    s = float(size)

    # Top-Left ┌
    painter.drawLine(QPointF(l, t), QPointF(l + s, t))
    painter.drawLine(QPointF(l, t), QPointF(l, t + s))

    # Top-Right ┐
    painter.drawLine(QPointF(r, t), QPointF(r - s, t))
    painter.drawLine(QPointF(r, t), QPointF(r, t + s))

    # Bottom-Left └
    painter.drawLine(QPointF(l, b), QPointF(l + s, b))
    painter.drawLine(QPointF(l, b), QPointF(l, b - s))

    # Bottom-Right ┘
    painter.drawLine(QPointF(r, b), QPointF(r - s, b))
    painter.drawLine(QPointF(r, b), QPointF(r, b - s))

    painter.restore()


def draw_hex_grid(
    painter: QPainter,
    rect: Union[QRect, QRectF],
    hex_size: float = 18.0,
    color: Optional[QColor] = None,
    opacity: float = 0.08,
) -> None:
    """Draw subtle hexagonal grid background across the rect."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    c = QColor(color) if color else qcolor("hud_border_bright")
    c.setAlphaF(max(0.0, min(1.0, opacity)))
    pen = QPen(c)
    pen.setWidthF(0.8)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # Hexagon geometry (pointy topped)
    # width = sqrt(3) * hex_size, height = 2 * hex_size
    # horizontal distance = width, vertical distance = 1.5 * hex_size
    w = math.sqrt(3) * hex_size
    h = 2 * hex_size
    h_dist = w
    v_dist = 1.5 * hex_size

    left = float(rect.left())
    top = float(rect.top())
    right = float(rect.right())
    bottom = float(rect.bottom())

    row = 0
    y = top
    while y <= bottom + hex_size:
        x_offset = (w / 2.0) if (row % 2 == 1) else 0.0
        x = left + x_offset - w
        while x <= right + w:
            path = QPainterPath()
            for i in range(6):
                angle_deg = 60 * i - 30
                angle_rad = math.radians(angle_deg)
                px = x + hex_size * math.cos(angle_rad)
                py = y + hex_size * math.sin(angle_rad)
                if i == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            path.closeSubpath()
            painter.drawPath(path)
            x += h_dist
        y += v_dist
        row += 1

    painter.restore()


def draw_glow_ring(
    painter: QPainter,
    center: Union[QPoint, QPointF],
    radius: float,
    color: Optional[QColor] = None,
    pulse_t: float = 0.0,
    width: float = 2.0,
    num_glow_passes: int = 4,
) -> None:
    """Draw a circular ring with soft radial glow bloom."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    cx = float(center.x())
    cy = float(center.y())
    base_color = QColor(color) if color else qcolor("arc_blue")

    # Dynamic breathing modulation based on pulse_t [0.0 .. 1.0]
    pulse_mod = 0.85 + 0.3 * math.sin(pulse_t * math.pi * 2.0)
    current_radius = radius * (1.0 + 0.03 * math.sin(pulse_t * math.pi * 2.0))

    # Draw outer glow halos
    for i in range(num_glow_passes, 0, -1):
        glow_c = QColor(base_color)
        alpha = (0.12 * pulse_mod) / (i * 1.2)
        glow_c.setAlphaF(min(1.0, max(0.0, alpha)))
        glow_pen = QPen(glow_c)
        glow_pen.setWidthF(width + i * 3.0)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), current_radius, current_radius)

    # Core bright ring
    core_c = QColor(base_color)
    core_c.setAlphaF(min(1.0, 0.9 * pulse_mod))
    core_pen = QPen(core_c)
    core_pen.setWidthF(width)
    painter.setPen(core_pen)
    painter.drawEllipse(QPointF(cx, cy), current_radius, current_radius)

    painter.restore()


def draw_hud_tech_box(
    painter: QPainter,
    rect: Union[QRect, QRectF],
    chamfer: float = 10.0,
    border_color: Optional[QColor] = None,
    fill_color: Optional[QColor] = None,
    border_width: float = 1.0,
) -> None:
    """Draw a sci-fi tech container with chamfered / angled top-right & bottom-left corners."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    b_col = QColor(border_color) if border_color else qcolor("hud_border")
    f_col = QColor(fill_color) if fill_color else qcolor("bg_card")

    pen = QPen(b_col)
    pen.setWidthF(border_width)
    painter.setPen(pen)
    painter.setBrush(QBrush(f_col))

    l = float(rect.left())
    t = float(rect.top())
    r = float(rect.right())
    b = float(rect.bottom())
    c = float(chamfer)

    path = QPainterPath()
    path.moveTo(l + c, t)
    path.lineTo(r - c, t)
    path.lineTo(r, t + c)
    path.lineTo(r, b - c)
    path.lineTo(r - c, b)
    path.lineTo(l + c, b)
    path.lineTo(l, b - c)
    path.lineTo(l, t + c)
    path.closeSubpath()

    painter.drawPath(path)
    painter.restore()


def apply_glow_effect(
    widget: QWidget,
    color: Union[str, QColor] = "#00BFFF",
    blur: int = 18,
    strength: float = 0.7,
) -> QGraphicsDropShadowEffect:
    """Attach a glowing drop-shadow effect to any QWidget."""
    glow = QGraphicsDropShadowEffect(widget)
    col = QColor(color) if isinstance(color, str) else color
    col.setAlphaF(min(1.0, max(0.0, strength)))
    glow.setColor(col)
    glow.setBlurRadius(blur)
    glow.setOffset(0, 0)
    widget.setGraphicsEffect(glow)
    return glow
