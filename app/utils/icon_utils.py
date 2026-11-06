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


def set_windows_app_user_model_id(app_id: str = "antigravity.bond.aidesktopfriend.v2") -> bool:
    """Set explicit Windows AppUserModelID so the taskbar groups and displays the custom icon instead of python.exe."""
    import sys
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        return True
    except Exception as e:
        logger.debug("Failed to set Windows AppUserModelID: %s", e)
        return False


def apply_windows_taskbar_icon(hwnd: int) -> bool:
    """Explicitly assign the high-res icon to the native Windows HWND via WM_SETICON."""
    import sys
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        icon_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"
        ico_path = icon_dir / "app_icon.ico"
        if not ico_path.exists():
            ico_path = icon_dir / "cyber_pet_squircle.ico"
        if not ico_path.exists():
            return False

        user32 = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE = 0x00000040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        # Query native monitor DPI icon metrics to ensure crystal-clear taskbar rendering
        cx_sm = user32.GetSystemMetrics(49) or 16  # SM_CXSMICON
        cy_sm = user32.GetSystemMetrics(50) or 16  # SM_CYSMICON
        cx_lg = user32.GetSystemMetrics(11) or 32  # SM_CXICON
        cy_lg = user32.GetSystemMetrics(12) or 32  # SM_CYICON

        # Taskbar icon (bottom opened app): buddy_avatar app_icon.ico
        # Window caption icon (top-left title bar): standing robot window_icon.ico
        win_ico_path = icon_dir / "window_icon.ico"
        if not win_ico_path.exists():
            win_ico_path = ico_path

        hicon_small = user32.LoadImageW(None, str(win_ico_path), IMAGE_ICON, cx_sm, cy_sm, LR_LOADFROMFILE)
        hicon_big = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, cx_lg, cy_lg, LR_LOADFROMFILE)
        if not hicon_big:
            hicon_big = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)

        if hicon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
        return True
    except Exception as e:
        logger.debug("Could not apply Win32 WM_SETICON: %s", e)
        return False


def get_window_title_icon() -> QIcon:
    """Return window title bar QIcon (top-left caption) from assets/icons/window_icon.*."""
    icon_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"
    win_ico = icon_dir / "window_icon.ico"
    win_png = icon_dir / "window_icon.png"

    icon = QIcon()
    if win_ico.exists():
        icon = QIcon(str(win_ico))

    if win_png.exists():
        pix = QPixmap(str(win_png))
        if not pix.isNull():
            icon.addPixmap(pix)
            for sz in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
                icon.addPixmap(pix.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    if not icon.isNull():
        return icon

    return get_application_icon()


def get_tray_icon() -> QIcon:
    """Return dedicated system tray icon, preserving the original companion icon."""
    icon_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"
    tray_ico = icon_dir / "tray_icon.ico"
    if tray_ico.exists():
        return QIcon(str(tray_ico))

    idle_png = Path(__file__).resolve().parent.parent.parent / "assets" / "characters" / "robot" / "idle.png"
    if idle_png.exists():
        return QIcon(str(idle_png))

    return get_application_icon()


def get_application_icon() -> QIcon:
    """Return application QIcon with all DPI resolutions from assets or generate programmatic fallback."""
    icon_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"
    ico_path = icon_dir / "app_icon.ico"
    png_path = icon_dir / "app_icon.png"

    icon = QIcon()
    if ico_path.exists():
        icon = QIcon(str(ico_path))

    if png_path.exists():
        pix = QPixmap(str(png_path))
        if not pix.isNull():
            icon.addPixmap(pix)
            for sz in (16, 24, 32, 48, 64, 128, 256):
                icon.addPixmap(pix.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    if not icon.isNull():
        return icon

    icon_fallback = icon_dir / "cyber_pet_squircle.png"
    if icon_fallback.exists():
        return QIcon(str(icon_fallback))

    # Generate and save default
    try:
        icon_dir.mkdir(parents=True, exist_ok=True)
        pixmap = create_default_pet_pixmap(128)
        pixmap.save(str(png_path), "PNG")
        return QIcon(pixmap)
    except Exception as e:
        logger.warning("Could not cache icon to disk: %s", e)
        return QIcon(create_default_pet_pixmap(64))
