"""Icon generation and loading utilities."""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush

from app.utils.logger import get_logger

logger = get_logger(__name__)


def create_default_pet_pixmap(size: int = 64) -> QPixmap:
    """Programmatically generate a crisp, cute robot companion icon.
    
    Draws a rounded robot head with glowing visor eyes and antenna.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    scale = size / 64.0

    # Colors
    head_color = QColor(41, 128, 185)       # Calm modern cyan-blue
    visor_color = QColor(24, 30, 42)        # Dark visor
    eye_color = QColor(46, 204, 113)        # Glowing green eyes
    antenna_color = QColor(241, 196, 15)    # Warm yellow tip

    # Antenna
    painter.setPen(QPen(QColor(100, 110, 130), 2.5 * scale))
    painter.drawLine(int(32 * scale), int(16 * scale), int(32 * scale), int(6 * scale))

    # Antenna bulb
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(antenna_color))
    painter.drawEllipse(QRectF(29 * scale, 3 * scale, 6 * scale, 6 * scale))

    # Robot Head body (rounded rect)
    painter.setBrush(QBrush(head_color))
    painter.setPen(QPen(QColor(25, 42, 60), 2 * scale))
    painter.drawRoundedRect(
        QRectF(8 * scale, 14 * scale, 48 * scale, 42 * scale),
        10 * scale,
        10 * scale,
    )

    # Face Visor
    painter.setBrush(QBrush(visor_color))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(
        QRectF(14 * scale, 24 * scale, 36 * scale, 22 * scale),
        6 * scale,
        6 * scale,
    )

    # Glowing eyes
    painter.setBrush(QBrush(eye_color))
    painter.drawEllipse(QRectF(20 * scale, 30 * scale, 8 * scale, 9 * scale))
    painter.drawEllipse(QRectF(36 * scale, 30 * scale, 8 * scale, 9 * scale))

    # Cheeks
    cheek_color = QColor(231, 76, 60, 180)
    painter.setBrush(QBrush(cheek_color))
    painter.drawEllipse(QRectF(16 * scale, 40 * scale, 4 * scale, 3 * scale))
    painter.drawEllipse(QRectF(44 * scale, 40 * scale, 4 * scale, 3 * scale))

    painter.end()
    return pixmap


def get_application_icon() -> QIcon:
    """Return application QIcon from assets or generate programmatic fallback."""
    icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icons" / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    # Generate and save default
    try:
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        pixmap = create_default_pet_pixmap(128)
        pixmap.save(str(icon_path), "PNG")
        return QIcon(pixmap)
    except Exception as e:
        logger.warning("Could not cache icon to disk: %s", e)
        return QIcon(create_default_pet_pixmap(64))
