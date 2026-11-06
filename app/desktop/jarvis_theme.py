"""JARVIS HUD Theme System.

Central source of truth for the JARVIS aesthetic — colors, fonts,
stylesheets, and QFontDatabase registration.  Every UI component
references this module instead of hardcoding visual constants.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_FONTS_DIR = _PROJECT_ROOT / "assets" / "fonts"

# ─── JARVIS / Buddy Showcase Color Palette ────────────────────────────
COLORS: Dict[str, str] = {
    # Primary design tokens matching latest showcase reference
    "primary_bg":       "#080F20",
    "secondary_bg":     "#0D1930",
    "sidebar_bg":       "#101D35",
    "card_bg":          "#172540",
    "hover_bg":         "#203555",
    "primary_blue":     "#1674FF",
    "accent_cyan":      "#00D4FF",
    "accent_purple":    "#7558FF",
    "primary_text":     "#F4F7FF",
    "secondary_text":   "#9CAFCB",
    "borders":          "#263A5B",
    "success_indicator":"#00DC8C",

    # Deep slate backgrounds matching Showcase UI
    "bg_deep":          "#080F20",
    "bg_card":          "#172540",
    "bg_surface":       "#101D35",
    "bg_input":         "#0D1930",

    # Refined borders
    "hud_border":       "#263A5B",
    "hud_border_dim":   "#172540",
    "hud_border_bright":"#1674FF",

    # Vibrant Electric Blue & Cyan accents
    "arc_blue":         "#1674FF",
    "arc_bright":       "#00D4FF",
    "arc_dim":          "#0E5AD1",
    "accent_glow":      "#00D4FF",

    # Status
    "warn_orange":      "#F59E0B",
    "error_red":        "#EF4444",
    "success_green":    "#00DC8C",

    # Text
    "text_primary":     "#F4F7FF",
    "text_secondary":   "#9CAFCB",
    "text_dim":         "#64748B",
    "text_bright":      "#FFFFFF",

    # Message bubbles matching Showcase
    "user_msg_bg":      "#1674FF",
    "user_msg_border":  "#1674FF",
    "ai_msg_bg":        "#172540",
    "ai_msg_border":    "#263A5B",

    # Interactive
    "btn_hover":        "#203555",
    "btn_pressed":      "#0E5AD1",
    "btn_active":       "#1674FF",
    "scrollbar":        "rgba(156, 175, 203, 0.2)",
    "scrollbar_hover":  "rgba(156, 175, 203, 0.4)",
}


def qcolor(key: str) -> QColor:
    """Return a QColor for a named palette entry."""
    return QColor(COLORS[key])


# ─── Font Family Names ────────────────────────────────────────────────
FONTS: Dict[str, str] = {
    "display":    "Orbitron",
    "body":       "Rajdhani",
    "mono":       "Share Tech Mono",
    "fallback":   "Segoe UI",
}

_fonts_loaded = False


def load_jarvis_fonts() -> None:
    """Register embedded JARVIS fonts with QFontDatabase (call once at startup)."""
    global _fonts_loaded
    if _fonts_loaded:
        return

    font_files = [
        "Orbitron.ttf",
        "Rajdhani-Regular.ttf",
        "Rajdhani-SemiBold.ttf",
        "ShareTechMono-Regular.ttf",
    ]

    for fname in font_files:
        fpath = _FONTS_DIR / fname
        if fpath.exists():
            font_id = QFontDatabase.addApplicationFont(str(fpath))
            if font_id < 0:
                logger.warning("Failed to load font: %s", fpath)
            else:
                families = QFontDatabase.applicationFontFamilies(font_id)
                logger.info("Loaded font '%s' -> families: %s", fname, families)
        else:
            logger.debug("Font file not found (will use fallback): %s", fpath)

    _fonts_loaded = True


def font_family(role: str) -> str:
    """Return a CSS font-family string with fallbacks for a given role."""
    primary = FONTS.get(role, FONTS["fallback"])
    fallback = FONTS["fallback"]
    return f"'{primary}', '{fallback}', sans-serif"


# ─── Reusable Glow Effect ────────────────────────────────────────────

def apply_glow(
    widget: QWidget,
    color: str = "#00BFFF",
    blur: int = 20,
    offset_x: int = 0,
    offset_y: int = 0,
) -> QGraphicsDropShadowEffect:
    """Apply a cinematic glow drop-shadow to any widget."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setColor(QColor(color))
    effect.setBlurRadius(blur)
    effect.setOffset(offset_x, offset_y)
    widget.setGraphicsEffect(effect)
    return effect


# ─── Global QApplication Stylesheet ──────────────────────────────────

def get_global_stylesheet() -> str:
    """Return the app-wide JARVIS dark stylesheet."""
    return f"""
        /* ── Global Reset ── */
        QWidget {{
            background-color: {COLORS['bg_deep']};
            color: {COLORS['text_primary']};
            font-family: {font_family('body')};
            font-size: 13px;
        }}

        /* ── Scrollbars ── */
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {COLORS['scrollbar']};
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {COLORS['scrollbar_hover']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 6px;
        }}
        QScrollBar::handle:horizontal {{
            background: {COLORS['scrollbar']};
            border-radius: 3px;
            min-width: 20px;
        }}

        /* ── Tooltips ── */
        QToolTip {{
            background-color: {COLORS['bg_card']};
            color: {COLORS['arc_bright']};
            border: 1px solid {COLORS['hud_border']};
            padding: 4px 8px;
            font-family: {font_family('mono')};
            font-size: 11px;
        }}

        /* ── Context menus ── */
        QMenu {{
            background-color: {COLORS['bg_card']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['hud_border']};
            padding: 4px;
            font-family: {font_family('body')};
        }}
        QMenu::item {{
            padding: 6px 24px 6px 12px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: {COLORS['btn_hover']};
            color: {COLORS['arc_bright']};
        }}
        QMenu::separator {{
            height: 1px;
            background: {COLORS['hud_border']};
            margin: 4px 8px;
        }}
    """


# ─── Component Stylesheets ───────────────────────────────────────────

def chat_panel_stylesheet() -> str:
    """Stylesheet for the main chat panel frame."""
    return f"""
        QFrame#JarvisPanel {{
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['hud_border']};
            border-radius: 16px;
        }}
    """


def header_stylesheet() -> str:
    """Stylesheet for the chat panel header."""
    return f"""
        QFrame#JarvisHeader {{
            background-color: {COLORS['bg_card']};
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
            border-bottom: 1px solid {COLORS['hud_border_dim']};
        }}
    """


def header_button_stylesheet() -> str:
    """Stylesheet for header action buttons."""
    return f"""
        QPushButton {{
            background: transparent;
            color: {COLORS['text_secondary']};
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: bold;
            padding: 4px 8px;
        }}
        QPushButton:hover {{
            background-color: rgba(255, 255, 255, 0.08);
            color: #FFFFFF;
        }}
        QPushButton:pressed {{
            background-color: rgba(255, 255, 255, 0.04);
        }}
    """


def input_field_stylesheet() -> str:
    """Stylesheet for the chat input text edit."""
    return f"""
        QPlainTextEdit {{
            background-color: {COLORS['bg_surface']};
            color: #FFFFFF;
            border: 1px solid {COLORS['hud_border']};
            border-radius: 20px;
            padding: 8px 14px;
            font-size: 13px;
            font-family: {font_family('body')};
            selection-background-color: rgba(37, 99, 235, 0.4);
        }}
        QPlainTextEdit:focus {{
            border: 1px solid {COLORS['arc_blue']};
            background-color: {COLORS['bg_surface']};
        }}
    """


def send_button_stylesheet() -> str:
    """Stylesheet for the send button."""
    return f"""
        QPushButton {{
            background-color: {COLORS['arc_blue']};
            color: #FFFFFF;
            border: none;
            border-radius: 18px;
            font-family: {font_family('body')};
            font-weight: bold;
            font-size: 14px;
            padding: 0px;
        }}
        QPushButton:hover {{
            background-color: {COLORS['arc_bright']};
        }}
        QPushButton:pressed {{
            background-color: {COLORS['arc_dim']};
        }}
        QPushButton:disabled {{
            background-color: {COLORS['hud_border']};
            color: {COLORS['text_dim']};
        }}
    """


def mode_button_stylesheet(active: bool = False) -> str:
    """Stylesheet for voice mode selector buttons."""
    if active:
        return f"""
            QPushButton {{
                background-color: {COLORS['arc_blue']};
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 12px;
            }}
        """
    return f"""
        QPushButton {{
            background-color: rgba(255, 255, 255, 0.05);
            color: {COLORS['text_secondary']};
            border: 1px solid {COLORS['hud_border']};
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            padding: 4px 12px;
        }}
        QPushButton:hover {{
            background-color: rgba(255, 255, 255, 0.1);
            color: #FFFFFF;
        }}
    """


def user_bubble_stylesheet() -> str:
    """Stylesheet for user message bubbles."""
    return f"""
        QFrame {{
            background-color: {COLORS['user_msg_bg']};
            border: none;
            border-radius: 16px;
            border-bottom-right-radius: 4px;
        }}
    """


def ai_bubble_stylesheet() -> str:
    """Stylesheet for AI message bubbles."""
    return f"""
        QFrame {{
            background-color: {COLORS['ai_msg_bg']};
            border: 1px solid {COLORS['hud_border']};
            border-radius: 16px;
            border-bottom-left-radius: 4px;
        }}
    """


def error_bubble_stylesheet() -> str:
    """Stylesheet for error message bubbles."""
    return f"""
        QFrame {{
            background-color: rgba(255, 68, 68, 0.08);
            border: 1px solid rgba(255, 68, 68, 0.3);
            border-left: 2px solid {COLORS['error_red']};
            border-radius: 10px;
            border-top-left-radius: 2px;
        }}
    """


def settings_sidebar_stylesheet() -> str:
    """Stylesheet for settings sidebar navigation."""
    return f"""
        QFrame#SettingsSidebar {{
            background-color: {COLORS['bg_deep']};
            border-right: 1px solid {COLORS['hud_border']};
        }}
    """


def settings_nav_button_stylesheet(active: bool = False) -> str:
    """Stylesheet for sidebar nav buttons."""
    if active:
        return f"""
            QPushButton {{
                background-color: rgba(0, 191, 255, 0.1);
                color: {COLORS['arc_bright']};
                border: none;
                border-left: 2px solid {COLORS['arc_blue']};
                text-align: left;
                padding: 10px 14px;
                font-family: {font_family('mono')};
                font-size: 12px;
            }}
        """
    return f"""
        QPushButton {{
            background: transparent;
            color: {COLORS['text_dim']};
            border: none;
            border-left: 2px solid transparent;
            text-align: left;
            padding: 10px 14px;
            font-family: {font_family('mono')};
            font-size: 12px;
        }}
        QPushButton:hover {{
            background-color: {COLORS['btn_hover']};
            color: {COLORS['text_primary']};
            border-left: 2px solid {COLORS['hud_border']};
        }}
    """


def control_bar_button_stylesheet() -> str:
    """Stylesheet for HUD control bar buttons."""
    return f"""
        QPushButton {{
            background: transparent;
            color: {COLORS['text_dim']};
            border: 1px solid {COLORS['hud_border']};
            border-radius: 4px;
            font-family: {font_family('mono')};
            font-size: 11px;
            padding: 4px 12px;
        }}
        QPushButton:hover {{
            background-color: {COLORS['btn_hover']};
            color: {COLORS['arc_bright']};
            border: 1px solid {COLORS['arc_blue']};
        }}
        QPushButton:pressed {{
            background-color: {COLORS['btn_pressed']};
        }}
    """
