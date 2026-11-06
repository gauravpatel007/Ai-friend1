"""Settings & System Configuration Modal — Apple HIG macOS Settings Design.

Provides an authentic Apple macOS System Settings interface:
- macOS frosted glass modal window with authentic Traffic Light controls.
- 10-category left sidebar with Apple Squircle Icon Badges (NO EMOJIS).
- Inset Grouped card containers for all configuration sections.
- Authentic iOS / macOS animated toggle switches (Apple Green #34C759).
- Clean SF Pro typography and resolution-independent vector icons.
- Full long-term memory management with SQLite FTS5 search and table actions.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from app.ai.ai_service import AIService

from app.ai.personality_manager import PRESET_PERSONALITIES
from app.core.signals import signals
from app.desktop.apple_icons import (
    create_apple_squircle_icon,
    create_button_icon,
)
from app.memory.memory_manager import MemoryManager
from app.memory.models import Memory
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_AVATAR_PATH = _PROJECT_ROOT / "assets" / "icons" / "buddy_avatar.png"
_SPRITE_IDLE_PATH = _PROJECT_ROOT / "assets" / "characters" / "robot" / "idle.png"

MEMORY_CATEGORIES = ["preference", "project", "learning", "interest", "fact", "general"]

# Apple System Palette Accent Colors for Category Badges
CATEGORY_COLORS = {
    "preference": "#34C759",  # Apple Green
    "project":    "#0A84FF",  # Apple Blue
    "learning":   "#00E5FF",  # Apple Cyan
    "interest":   "#FF9F0A",  # Apple Amber
    "fact":       "#BF5AF2",  # Apple Purple
    "general":    "#8E8E93",  # Apple Slate Gray
}


class AnimatedToggleSwitch(QCheckBox):
    """Authentic Apple iOS / macOS style animated toggle switch."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(28)
        self.setContentsMargins(0, 0, 0, 0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Apple Switch Track (Pill)
        pill_w = 42
        pill_h = 24
        pill_y = (self.height() - pill_h) // 2

        checked = self.isChecked()
        track_color = QColor(52, 199, 89) if checked else QColor(58, 58, 60)  # Apple Green vs Dark Fill
        painter.setBrush(QBrush(track_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, pill_y, pill_w, pill_h, pill_h / 2.0, pill_h / 2.0)

        # Switch Thumb (Crisp White Circle with subtle shadow)
        thumb_dia = 20
        thumb_y = pill_y + 2
        thumb_x = (pill_w - thumb_dia - 2) if checked else 2

        # Thumb drop shadow
        painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
        painter.drawEllipse(thumb_x, thumb_y + 1, thumb_dia, thumb_dia)

        # Thumb fill
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(thumb_x, thumb_y, thumb_dia, thumb_dia)

        # Label text
        text = self.text()
        if text:
            painter.setPen(QPen(QColor(245, 245, 247)))
            font = QFont("-apple-system", 10)
            font.setStyleHint(QFont.SansSerif)
            painter.setFont(font)
            painter.drawText(
                QRect(pill_w + 12, 0, self.width() - pill_w - 12, self.height()),
                Qt.AlignVCenter | Qt.AlignLeft,
                text,
            )


class AddEditMemoryDialog(QDialog):
    """Modal dialog to add or edit a long-term memory with Apple styling."""

    def __init__(
        self,
        memory: Optional[Memory] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.memory = memory
        self.is_edit = memory is not None
        self.setWindowTitle("Edit Memory" if self.is_edit else "Add Memory")
        self.setFixedSize(460, 310)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #181B21;
                color: #F5F5F7;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
            }
            QLabel {
                color: #F5F5F7;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: 600;
            }
            QComboBox, QTextEdit {
                background-color: rgba(0, 0, 0, 0.25);
                color: #F5F5F7;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 8px 12px;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QComboBox:focus, QTextEdit:focus {
                border-color: #0A84FF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.category_combo = QComboBox(self)
        for cat in MEMORY_CATEGORIES:
            self.category_combo.addItem(cat.capitalize(), cat)
        if self.is_edit and self.memory:
            idx = self.category_combo.findData(self.memory.category.lower())
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
        form.addRow("Category:", self.category_combo)

        self.content_edit = QTextEdit(self)
        self.content_edit.setPlaceholderText("Enter the key fact or preference to remember...")
        if self.is_edit and self.memory:
            self.content_edit.setText(self.memory.content)
        form.addRow("Memory Content:", self.content_edit)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #E5E5EA;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 16px;
                font-family: -apple-system, sans-serif;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Memory", self)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0A84FF, stop:1 #0071E3);
                color: #FFFFFF;
                font-family: -apple-system, sans-serif;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 6px 20px;
            }
            QPushButton:hover {
                background: #0071E3;
            }
        """)
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _on_save(self) -> None:
        text = self.content_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Invalid Content", "Memory content cannot be empty.")
            return
        self.accept()

    def get_data(self) -> tuple[str, str]:
        category = str(self.category_combo.currentData())
        content = self.content_edit.toPlainText().strip()
        return category, content


class SizePresetCard(QFrame):
    """Interactive character size preset card with Buddy thumbnail (Apple Segmented Picker)."""

    clicked = Signal(int)

    def __init__(
        self,
        title: str,
        pixel_size: int,
        dimension_text: str,
        is_active: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.pixel_size = pixel_size
        self._is_active = is_active
        self.setFixedSize(130, 130)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._init_ui(title, dimension_text)
        self._update_style()

    def _init_ui(self, title: str, dimension_text: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        # Thumbnail image
        self.img_lbl = QLabel(self)
        self.img_lbl.setAlignment(Qt.AlignCenter)
        if _SPRITE_IDLE_PATH.exists():
            pix = QPixmap(str(_SPRITE_IDLE_PATH)).scaled(
                48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.img_lbl.setPixmap(pix)
        else:
            # Clean vector icon fallback (NO EMOJI)
            self.img_lbl.setPixmap(create_button_icon("character", size=32, color=QColor(10, 132, 255)).pixmap(32, 32))
        layout.addWidget(self.img_lbl)

        # Title
        self.title_lbl = QLabel(title, self)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet("""
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
            font-size: 13px;
            font-weight: 700;
            color: #FFFFFF;
        """)
        layout.addWidget(self.title_lbl)

        # Dimension subtext
        self.sub_lbl = QLabel(dimension_text, self)
        self.sub_lbl.setAlignment(Qt.AlignCenter)
        self.sub_lbl.setStyleSheet("""
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
            font-size: 11px;
            color: #8E8E93;
        """)
        layout.addWidget(self.sub_lbl)

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self._update_style()

    def _update_style(self) -> None:
        if self._is_active:
            self.setStyleSheet("""
                QFrame {
                    background-color: rgba(10, 132, 255, 0.12);
                    border: 2px solid #0A84FF;
                    border-radius: 14px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: rgba(255, 255, 255, 0.035);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 14px;
                }
                QFrame:hover {
                    border-color: rgba(255, 255, 255, 0.16);
                    background-color: rgba(255, 255, 255, 0.06);
                }
            """)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.pixel_size)
        super().mousePressEvent(event)


class VoiceProfileCard(QFrame):
    """Interactive companion voice profile card matching Apple Inset Grouped design (Phase 1)."""

    selected = Signal(str)               # profile_id
    preview_requested = Signal(str, str) # profile_id, language

    def __init__(
        self,
        profile,
        is_selected: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self._is_selected = is_selected
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._init_ui()
        self.set_selected(is_selected)

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignVCenter)

        # Radio / Checkmark Indicator
        self.radio_lbl = QLabel(self)
        self.radio_lbl.setFixedSize(18, 18)
        self.radio_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.radio_lbl)

        # Content container
        content_box = QWidget(self)
        content_box.setStyleSheet("background: transparent; border: none;")
        c_layout = QVBoxLayout(content_box)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(3)

        # Top row: Name + Gender pill + Languages
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.setAlignment(Qt.AlignVCenter)

        self.name_lbl = QLabel(self.profile.name, content_box)
        self.name_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #FFFFFF;")
        top_row.addWidget(self.name_lbl)

        # Gender Pill
        is_male = (self.profile.gender == "male")
        gender_color = "#0A84FF" if is_male else "#FF375F"
        gender_bg = "rgba(10, 132, 255, 0.15)" if is_male else "rgba(255, 55, 95, 0.15)"
        gender_pill = QLabel(self.profile.gender.title(), content_box)
        gender_pill.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 700;
            color: {gender_color};
            background-color: {gender_bg};
            border: 1px solid {gender_color}55;
            border-radius: 4px;
            padding: 1px 6px;
        """)
        top_row.addWidget(gender_pill)

        # Multilingual support pill
        lang_pill = QLabel("EN · HI · GU", content_box)
        lang_pill.setStyleSheet("""
            font-size: 10px;
            font-weight: 600;
            color: #8E8E93;
            background-color: rgba(255, 255, 255, 0.06);
            border-radius: 4px;
            padding: 1px 5px;
        """)
        top_row.addWidget(lang_pill)
        top_row.addStretch()
        c_layout.addLayout(top_row)

        # Description
        self.desc_lbl = QLabel(self.profile.description, content_box)
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setStyleSheet("font-size: 11px; color: #8E8E93; line-height: 1.3;")
        c_layout.addWidget(self.desc_lbl)

        layout.addWidget(content_box, 1)

        # Right box: Language dropdown + Play Preview button
        action_box = QWidget(self)
        action_box.setStyleSheet("background: transparent; border: none;")
        ab_layout = QHBoxLayout(action_box)
        ab_layout.setContentsMargins(0, 0, 0, 0)
        ab_layout.setSpacing(6)
        ab_layout.setAlignment(Qt.AlignVCenter)

        self.lang_combo = QComboBox(action_box)
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("हिन्दी", "hi")
        self.lang_combo.addItem("ગુજરાતી", "gu")
        self.lang_combo.setFixedWidth(84)
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 6px;
                padding: 2px 4px;
                font-size: 11px;
                font-weight: 600;
                color: #FFFFFF;
            }
        """)
        ab_layout.addWidget(self.lang_combo)

        self.btn_preview = QPushButton("▶ Preview", action_box)
        self.btn_preview.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_preview.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #F5F5F7;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: rgba(10, 132, 255, 0.25);
                border-color: #0A84FF;
                color: #0A84FF;
            }
            QPushButton:pressed {
                background-color: rgba(10, 132, 255, 0.4);
            }
        """)
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        ab_layout.addWidget(self.btn_preview)

        layout.addWidget(action_box)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.profile.profile_id)
        super().mousePressEvent(event)

    def _on_preview_clicked(self) -> None:
        selected_lang = str(self.lang_combo.currentData() or "en")
        self.preview_requested.emit(self.profile.profile_id, selected_lang)

    def set_selected(self, is_selected: bool) -> None:
        self._is_selected = is_selected
        if is_selected:
            self.setStyleSheet("""
                QFrame {
                    background-color: rgba(10, 132, 255, 0.08);
                    border: 1.5px solid #0A84FF;
                    border-radius: 10px;
                }
            """)
            self.radio_lbl.setStyleSheet("""
                background-color: #0A84FF;
                border: 2px solid #FFFFFF;
                border-radius: 9px;
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: rgba(255, 255, 255, 0.025);
                    border: 1px solid rgba(255, 255, 255, 0.07);
                    border-radius: 10px;
                }
                QFrame:hover {
                    background-color: rgba(255, 255, 255, 0.05);
                    border-color: rgba(255, 255, 255, 0.12);
                }
            """)
            self.radio_lbl.setStyleSheet("""
                background-color: transparent;
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 9px;
            """)


class SettingsDialog(QDialog):
    """Central configuration modal with Apple HIG 11-category left sidebar (NO EMOJIS)."""

    def __init__(
        self,
        config_manager: ConfigManager,
        memory_manager: Optional[MemoryManager] = None,
        ai_service: Optional[AIService] = None,
        voice_service: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.memory_manager = memory_manager or MemoryManager()
        self.ai_service = ai_service

        if voice_service is None and parent is not None:
            voice_service = getattr(parent, "voice_service", None)
        if voice_service is None:
            try:
                from app.api.server import fastapi_app
                voice_service = getattr(fastapi_app.state, "voice_service", None)
            except Exception:
                pass
        self.voice_service = voice_service

        self._is_drag_active = False
        self._drag_pos = QPoint()
        self._current_memories: List[Memory] = []
        self._size_cards: list[SizePresetCard] = []

        self._init_window()
        self._init_ui()
        self._load_settings()
        self._refresh_memories()

    def _init_window(self) -> None:
        self.setWindowTitle("Settings")
        self.resize(800, 600)
        self.setMinimumSize(680, 500)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)

        # Background Frame (Apple macOS Frosted Container)
        self.bg_frame = QFrame(self)
        self.bg_frame.setObjectName("settingsBgFrame")
        self.bg_frame.setStyleSheet("""
            QFrame#settingsBgFrame {
                background-color: #16181D;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 20px;
            }
            QLabel {
                color: #F5F5F7;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QComboBox, QLineEdit, QTextEdit {
                background-color: rgba(0, 0, 0, 0.25);
                color: #F5F5F7;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 7px 12px;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 13px;
                selection-background-color: #0A84FF;
            }
            QComboBox:focus, QLineEdit:focus, QTextEdit:focus {
                border-color: #0A84FF;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #F5F5F7;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 14px;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
                border-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)

        # Soft Multi-layer Apple Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.bg_frame.setGraphicsEffect(shadow)

        frame_layout = QVBoxLayout(self.bg_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # 1. Apple macOS Titlebar
        self._init_header(frame_layout)

        # 2. Split Body (Left Nav Sidebar + Right Content Stack)
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._init_nav_sidebar(body_layout)
        self._init_pages_stack(body_layout)

        frame_layout.addLayout(body_layout, 1)

        # 3. Bottom Action Bar
        bottom_bar = QFrame(self.bg_frame)
        bottom_bar.setFixedHeight(54)
        bottom_bar.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 22, 28, 0.98);
                border-top: 1px solid rgba(255, 255, 255, 0.07);
                border-bottom-left-radius: 20px;
                border-bottom-right-radius: 20px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 0, 20, 0)

        btn_defaults = QPushButton("Reset Defaults", bottom_bar)
        btn_defaults.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #8E8E93;
                border-radius: 8px;
                padding: 7px 16px;
                font-family: -apple-system, sans-serif;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
            }
        """)
        btn_defaults.clicked.connect(self._reset_defaults)
        bottom_layout.addWidget(btn_defaults)

        bottom_layout.addStretch()

        self.btn_done = QPushButton("Save & Close", bottom_bar)
        self.btn_done.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0A84FF, stop:1 #0071E3);
                color: #FFFFFF;
                border: none;
                font-family: -apple-system, sans-serif;
                font-weight: 600;
                border-radius: 8px;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background: #0071E3;
            }
            QPushButton:pressed {
                background: #005BB5;
            }
        """)
        self.btn_done.clicked.connect(self.close)
        bottom_layout.addWidget(self.btn_done)

        frame_layout.addWidget(bottom_bar)
        outer_layout.addWidget(self.bg_frame)

    def _init_header(self, parent_layout: QVBoxLayout) -> None:
        self.header_frame = QFrame(self.bg_frame)
        self.header_frame.setFixedHeight(48)
        self.header_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.02);
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.07);
            }
        """)

        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(12)

        # Authentic macOS Traffic Light controls (Close, Minimize, Zoom)
        tl_frame = QFrame(self.header_frame)
        tl_frame.setStyleSheet("background: transparent; border: none;")
        tl_layout = QHBoxLayout(tl_frame)
        tl_layout.setContentsMargins(0, 0, 0, 0)
        tl_layout.setSpacing(8)

        btn_close = QPushButton("", tl_frame)
        btn_close.setFixedSize(12, 12)
        btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        btn_close.setToolTip("Close")
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #FF5F56;
                border: 1px solid rgba(0, 0, 0, 0.2);
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #E0443E;
            }
        """)
        btn_close.clicked.connect(self.close)
        tl_layout.addWidget(btn_close)

        btn_min = QPushButton("", tl_frame)
        btn_min.setFixedSize(12, 12)
        btn_min.setCursor(QCursor(Qt.PointingHandCursor))
        btn_min.setToolTip("Minimize")
        btn_min.setStyleSheet("""
            QPushButton {
                background-color: #FFBD2E;
                border: 1px solid rgba(0, 0, 0, 0.2);
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #DEA123;
            }
        """)
        btn_min.clicked.connect(self.showMinimized)
        tl_layout.addWidget(btn_min)

        btn_zoom = QPushButton("", tl_frame)
        btn_zoom.setFixedSize(12, 12)
        btn_zoom.setEnabled(False)
        btn_zoom.setStyleSheet("""
            QPushButton {
                background-color: #27C93F;
                border: 1px solid rgba(0, 0, 0, 0.2);
                border-radius: 6px;
                opacity: 0.5;
            }
        """)
        tl_layout.addWidget(btn_zoom)

        header_layout.addWidget(tl_frame)

        # Title Box with pure Apple typography (NO EMOJIS)
        title_box = QWidget(self.header_frame)
        title_box.setStyleSheet("background: transparent; border: none;")
        tb_layout = QHBoxLayout(title_box)
        tb_layout.setContentsMargins(10, 0, 0, 0)
        tb_layout.setSpacing(8)

        title_lbl = QLabel("Settings", title_box)
        title_lbl.setStyleSheet("""
            color: #FFFFFF;
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 14px;
            font-weight: 700;
        """)
        tb_layout.addWidget(title_lbl)

        sub_pill = QLabel("System Preferences", title_box)
        sub_pill.setStyleSheet("""
            color: #8E8E93;
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
            font-size: 11px;
            font-weight: 500;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 6px;
            padding: 2px 7px;
        """)
        tb_layout.addWidget(sub_pill)

        header_layout.addWidget(title_box)
        header_layout.addStretch()

        parent_layout.addWidget(self.header_frame)

    def _init_nav_sidebar(self, parent_layout: QHBoxLayout) -> None:
        """Left navigation menu with 10 categories using Apple Squircle Icon Badges (NO EMOJIS)."""
        self.nav_frame = QFrame(self.bg_frame)
        self.nav_frame.setFixedWidth(210)
        self.nav_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 20, 25, 0.96);
                border-right: 1px solid rgba(255, 255, 255, 0.07);
            }
        """)

        nav_layout = QVBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(8, 12, 8, 12)
        nav_layout.setSpacing(4)

        self.nav_list = QListWidget(self.nav_frame)
        self.nav_list.setIconSize(QSize(22, 22))
        self.nav_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                color: #A1A1A6;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: 500;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-radius: 8px;
                margin-bottom: 3px;
                color: #E5E5EA;
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.06);
                color: #FFFFFF;
            }
            QListWidget::item:selected {
                background-color: #0A84FF;
                color: #FFFFFF;
                font-weight: 600;
            }
        """)

        categories = [
            ("General", 0),
            ("Character", 1),
            ("AI Model", 2),
            ("Language & Communication", 3),
            ("Voice", 4),
            ("Personality", 5),
            ("Memory", 6),
            ("Appearance", 7),
            ("Hotkeys", 8),
            ("Startup", 9),
            ("Advanced", 10),
        ]

        for name, idx in categories:
            # Pristine Apple Squircle Icon Badge with vector symbol (NO EMOJIS)
            icon = create_apple_squircle_icon(name, size=24)
            item = QListWidgetItem(icon, name)
            item.setData(Qt.UserRole, idx)
            self.nav_list.addItem(item)

        self.nav_list.currentRowChanged.connect(self._on_category_changed)
        nav_layout.addWidget(self.nav_list)

        parent_layout.addWidget(self.nav_frame)

    def _init_pages_stack(self, parent_layout: QHBoxLayout) -> None:
        """Right content area with stacked category pages."""
        self.stacked_pages = QStackedWidget(self.bg_frame)
        self.stacked_pages.setStyleSheet("background: transparent;")

        # Page 0: General
        self._page_general = self._create_general_page()
        self.stacked_pages.addWidget(self._page_general)

        # Page 1: Character (Showcase Section 6 size presets)
        self._page_character = self._create_character_page()
        self.stacked_pages.addWidget(self._page_character)

        # Page 2: AI Model
        self._page_model = self._create_model_page()
        self.stacked_pages.addWidget(self._page_model)

        # Page 3: Language & Communication
        self._page_language = self._create_language_page()
        self.stacked_pages.addWidget(self._page_language)

        # Page 4: Voice
        self._page_voice = self._create_voice_page()
        self.stacked_pages.addWidget(self._page_voice)

        # Page 5: Personality
        self._page_personality = self._create_personality_page()
        self.stacked_pages.addWidget(self._page_personality)

        # Page 6: Memory (Full Phase 10 management)
        self._page_memory = self._create_memory_page()
        self.stacked_pages.addWidget(self._page_memory)

        # Page 7: Appearance
        self._page_appearance = self._create_appearance_page()
        self.stacked_pages.addWidget(self._page_appearance)

        # Page 8: Hotkeys
        self._page_hotkeys = self._create_hotkeys_page()
        self.stacked_pages.addWidget(self._page_hotkeys)

        # Page 9: Startup
        self._page_startup = self._create_startup_page()
        self.stacked_pages.addWidget(self._page_startup)

        # Page 10: Advanced
        self._page_advanced = self._create_advanced_page()
        self.stacked_pages.addWidget(self._page_advanced)

        parent_layout.addWidget(self.stacked_pages, 1)

        # Select first category by default
        self.nav_list.setCurrentRow(0)

    def _on_category_changed(self, row: int) -> None:
        if 0 <= row < self.stacked_pages.count():
            self.stacked_pages.setCurrentIndex(row)

    def _make_apple_card(self) -> tuple[QFrame, QVBoxLayout]:
        """Helper to create an Apple Inset Grouped card container."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        return card, layout

    # ─── Category Pages ────────────────────────────────────────────────

    def _create_general_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("General", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Configure desktop presentation and companion identity.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        card, card_layout = self._make_apple_card()

        form = QFormLayout()
        form.setSpacing(14)

        self.name_input = QLineEdit(page)
        self.name_input.textChanged.connect(self._on_name_changed)
        form.addRow("Companion Name:", self.name_input)

        self.cb_always_on_top = AnimatedToggleSwitch("Keep Pet Always on Top", page)
        self.cb_always_on_top.setChecked(True)
        form.addRow(self.cb_always_on_top)

        self.cb_start_minimized = AnimatedToggleSwitch("Start Minimized to System Tray", page)
        form.addRow(self.cb_start_minimized)

        card_layout.addLayout(form)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _create_character_page(self) -> QWidget:
        """Character page matching Apple Inset Grouped design."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("Character & Appearance", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Customize character dimensions, presets, and fluid animation effects.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        # Card 1: Size & Presets
        card1, c1_layout = self._make_apple_card()

        slider_row = QHBoxLayout()
        slider_lbl = QLabel("Character Size:", page)
        slider_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #F5F5F7;")
        slider_row.addWidget(slider_lbl)

        self.lbl_size_val = QLabel("120 px", page)
        self.lbl_size_val.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            color: #0A84FF;
            background: rgba(10, 132, 255, 0.12);
            padding: 2px 8px;
            border-radius: 6px;
        """)
        slider_row.addWidget(self.lbl_size_val)
        slider_row.addStretch()
        c1_layout.addLayout(slider_row)

        self.size_slider = QSlider(Qt.Horizontal, page)
        self.size_slider.setRange(70, 180)
        self.size_slider.setValue(120)
        self.size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.12);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #0A84FF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.2);
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
        """)
        self.size_slider.valueChanged.connect(self._on_slider_size_changed)
        c1_layout.addWidget(self.size_slider)

        presets_lbl = QLabel("Presets:", page)
        presets_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #8E8E93; margin-top: 6px;")
        c1_layout.addWidget(presets_lbl)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_small = SizePresetCard("Small", 80, "80 × 80 px", is_active=False, parent=page)
        self.card_small.clicked.connect(self._select_size_preset)
        cards_layout.addWidget(self.card_small)

        self.card_med = SizePresetCard("Medium", 120, "120 × 120 px", is_active=True, parent=page)
        self.card_med.clicked.connect(self._select_size_preset)
        cards_layout.addWidget(self.card_med)

        self.card_large = SizePresetCard("Large", 160, "160 × 160 px", is_active=False, parent=page)
        self.card_large.clicked.connect(self._select_size_preset)
        cards_layout.addWidget(self.card_large)

        cards_layout.addStretch()
        c1_layout.addLayout(cards_layout)
        layout.addWidget(card1)

        self._size_cards = [self.card_small, self.card_med, self.card_large]

        # Card 2: Animation & Glow
        card2, c2_layout = self._make_apple_card()
        self.cb_floor_shadow = AnimatedToggleSwitch("Enable Holographic Floor Glow", page)
        self.cb_floor_shadow.setChecked(True)
        c2_layout.addWidget(self.cb_floor_shadow)

        self.cb_breathing = AnimatedToggleSwitch("Enable Idle Bobbing & Breathing Animation", page)
        self.cb_breathing.setChecked(True)
        c2_layout.addWidget(self.cb_breathing)

        layout.addWidget(card2)
        layout.addStretch()
        return page

    def _select_size_preset(self, size_val: int) -> None:
        self.size_slider.setValue(size_val)
        self._on_slider_size_changed(size_val)

    def _on_slider_size_changed(self, size_val: int) -> None:
        self.lbl_size_val.setText(f"{size_val} px")
        self.config_manager.set("pet.size", size_val)
        signals.character_size_changed.emit(size_val)

        for card in self._size_cards:
            card.set_active(abs(card.pixel_size - size_val) <= 10)

    def _create_model_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("AI Model & Inference", scroll_content)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Zero cloud APIs. Configure local Ollama daemon, automatic routing, and task preferences.", scroll_content)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        # ─── Card 1: Selection Mode & Manual Model ─────────────────────
        card_mode, cm_layout = self._make_apple_card()
        form_mode = QFormLayout()
        form_mode.setSpacing(14)

        self.combo_model_mode = QComboBox(scroll_content)
        self.combo_model_mode.addItem("Automatic (Intelligent Router)", "auto")
        self.combo_model_mode.addItem("Manual (Strict Model Selection)", "manual")
        self.combo_model_mode.currentIndexChanged.connect(self._on_model_mode_changed)
        form_mode.addRow("Selection Mode:", self.combo_model_mode)

        self.endpoint_input = QLineEdit(scroll_content)
        self.endpoint_input.setText("http://127.0.0.1:11434")
        self.endpoint_input.textChanged.connect(self._on_endpoint_changed)
        form_mode.addRow("Ollama Endpoint:", self.endpoint_input)

        cm_layout.addLayout(form_mode)

        # Manual Model Selector Container
        self.manual_model_container = QWidget(scroll_content)
        mm_layout = QVBoxLayout(self.manual_model_container)
        mm_layout.setContentsMargins(0, 8, 0, 0)
        mm_layout.setSpacing(8)

        mm_form = QFormLayout()
        mm_form.setSpacing(10)
        self.combo_manual_model = QComboBox(self.manual_model_container)
        self.combo_manual_model.setEditable(True)
        self.combo_manual_model.currentIndexChanged.connect(self._on_manual_model_changed)
        self.combo_manual_model.currentTextChanged.connect(self._on_manual_model_text_changed)
        mm_form.addRow("Active Model:", self.combo_manual_model)
        mm_layout.addLayout(mm_form)

        # Hidden QLineEdit for backward compatibility with existing tests
        self.model_input = QLineEdit(scroll_content)
        self.model_input.setVisible(False)
        self.model_input.textChanged.connect(self._on_model_changed)

        self.lbl_manual_model_warning = QLabel(
            "Selected model is not installed locally in Ollama. Run 'ollama pull' or select an installed model.",
            self.manual_model_container
        )
        self.lbl_manual_model_warning.setStyleSheet("color: #FF9F0A; font-size: 11px; font-weight: 600;")
        self.lbl_manual_model_warning.setVisible(False)
        mm_layout.addWidget(self.lbl_manual_model_warning)

        cm_layout.addWidget(self.manual_model_container)
        layout.addWidget(card_mode)

        # ─── Card 2: Response Priority (Auto Mode) ─────────────────────
        self.card_priority, cp_layout = self._make_apple_card()
        cp_header = QLabel("Response Priority", scroll_content)
        cp_header.setStyleSheet("font-size: 14px; font-weight: 600; color: #FFFFFF;")
        cp_layout.addWidget(cp_header)

        form_prio = QFormLayout()
        form_prio.setSpacing(10)
        self.combo_response_priority = QComboBox(scroll_content)
        self.combo_response_priority.addItem("Balanced (Default — Speed & Accuracy)", "balanced")
        self.combo_response_priority.addItem("Fastest Response (Low Latency, Compact Models)", "fastest")
        self.combo_response_priority.addItem("Best Available Quality (Deep Reasoning & Detailed)", "quality")
        self.combo_response_priority.currentIndexChanged.connect(self._on_response_priority_changed)
        form_prio.addRow("Priority Profile:", self.combo_response_priority)
        cp_layout.addLayout(form_prio)
        layout.addWidget(self.card_priority)

        # ─── Card 3: Task-Specific Preferences (Auto Mode) ─────────────
        self.card_tasks, ct_layout = self._make_apple_card()
        ct_header = QLabel("Task-Specific Preferences", scroll_content)
        ct_header.setStyleSheet("font-size: 14px; font-weight: 600; color: #FFFFFF;")
        ct_layout.addWidget(ct_header)
        ct_sub = QLabel("Assign preferred models for specific tasks. Only verified compatible models are listed.", scroll_content)
        ct_sub.setStyleSheet("font-size: 11px; color: #8E8E93; margin-top: -4px; margin-bottom: 8px;")
        ct_layout.addWidget(ct_sub)

        form_tasks = QFormLayout()
        form_tasks.setSpacing(10)

        self.combo_pref_general = QComboBox(scroll_content)
        self.combo_pref_reasoning = QComboBox(scroll_content)
        self.combo_pref_coding = QComboBox(scroll_content)
        self.combo_pref_summarization = QComboBox(scroll_content)
        self.combo_pref_vision = QComboBox(scroll_content)

        self.combo_pref_general.currentIndexChanged.connect(lambda: self._on_task_pref_changed("general_conversation", self.combo_pref_general))
        self.combo_pref_reasoning.currentIndexChanged.connect(lambda: self._on_task_pref_changed("complex_reasoning", self.combo_pref_reasoning))
        self.combo_pref_coding.currentIndexChanged.connect(lambda: self._on_task_pref_changed("coding", self.combo_pref_coding))
        self.combo_pref_summarization.currentIndexChanged.connect(lambda: self._on_task_pref_changed("document_summarization", self.combo_pref_summarization))
        self.combo_pref_vision.currentIndexChanged.connect(lambda: self._on_task_pref_changed("vision", self.combo_pref_vision))

        form_tasks.addRow("General Conversation:", self.combo_pref_general)
        form_tasks.addRow("Complex Reasoning:", self.combo_pref_reasoning)
        form_tasks.addRow("Coding & Debugging:", self.combo_pref_coding)
        form_tasks.addRow("Document Summarization:", self.combo_pref_summarization)
        form_tasks.addRow("Vision & Image Analysis:", self.combo_pref_vision)
        ct_layout.addLayout(form_tasks)
        layout.addWidget(self.card_tasks)

        layout.addStretch()
        scroll.setWidget(scroll_content)

        main_page_layout = QVBoxLayout(page)
        main_page_layout.setContentsMargins(0, 0, 0, 0)
        main_page_layout.addWidget(scroll)
        return page

    def _create_language_page(self) -> QWidget:
        """Language & Communication page matching Apple Inset Grouped design."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("Language & Communication", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Configure multilingual input understanding, response language, script display, and voice output.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        # ─── Card 1: AI Response Language & Text Format ────────────────
        card1, c1_layout = self._make_apple_card()

        c1_title = QLabel("AI Response Generation & Display", page)
        c1_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #00C7BE;")
        c1_layout.addWidget(c1_title)

        form1 = QFormLayout()
        form1.setSpacing(14)

        # A. AI Response Language Dropdown
        self.combo_response_lang = QComboBox(page)
        from app.ai.multilingual_engine import SUPPORTED_LANGUAGES, SUPPORTED_STT_LANGUAGES, MultilingualEngine
        for code, meta in SUPPORTED_LANGUAGES.items():
            display_name = meta["name"]
            if meta.get("native_name") and meta["native_name"] != meta["name"]:
                display_name = f"{meta['name']} ({meta['native_name']})"
            self.combo_response_lang.addItem(display_name, code)
        self.combo_response_lang.currentIndexChanged.connect(self._on_response_lang_changed)
        form1.addRow("AI Response Language:", self.combo_response_lang)

        desc_response_lang = QLabel(
            "Bond will ALWAYS respond in the selected language, regardless of whether you speak or type in English, Gujarati, or Hindi.",
            page,
        )
        desc_response_lang.setWordWrap(True)
        desc_response_lang.setStyleSheet("font-size: 11px; color: #8E8E93; margin-top: -6px;")
        form1.addRow("", desc_response_lang)

        # B. AI Response Text Format Dropdown
        self.combo_response_format = QComboBox(page)
        self.combo_response_format.addItem("Native Script (Recommended) — e.g. તારું નામ શું છે?", "native")
        self.combo_response_format.addItem("Romanized / Latin Script — e.g. Tamaru naam su che?", "romanized")
        self.combo_response_format.currentIndexChanged.connect(self._on_response_format_changed)
        form1.addRow("Display Response Text As:", self.combo_response_format)

        desc_format = QLabel(
            "Native Script displays text using standard regional scripts (ગુજરાતી, देवनागरी). "
            "Romanized Script displays the same regional words using English letters without translating into English.",
            page,
        )
        desc_format.setWordWrap(True)
        desc_format.setStyleSheet("font-size: 11px; color: #8E8E93; margin-top: -6px;")
        form1.addRow("", desc_format)

        c1_layout.addLayout(form1)

        # Live Script & Language Preview Box
        self.preview_box = QFrame(page)
        self.preview_box.setStyleSheet("""
            QFrame {
                background: rgba(10, 132, 255, 0.08);
                border: 1px solid rgba(10, 132, 255, 0.2);
                border-radius: 8px;
            }
        """)
        preview_layout = QVBoxLayout(self.preview_box)
        preview_layout.setContentsMargins(12, 8, 12, 8)
        preview_layout.setSpacing(4)

        lbl_preview_title = QLabel("LIVE SCRIPT & LANGUAGE PREVIEW", self.preview_box)
        lbl_preview_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #0A84FF;")
        preview_layout.addWidget(lbl_preview_title)

        self.lbl_script_preview = QLabel(self.preview_box)
        self.lbl_script_preview.setStyleSheet("font-size: 12px; color: #F5F5F7;")
        self.lbl_script_preview.setWordWrap(True)
        preview_layout.addWidget(self.lbl_script_preview)
        c1_layout.addWidget(self.preview_box)

        layout.addWidget(card1)

        # ─── Card 2: Voice Output Language & Live TTS Limitation Check ─
        card2, c2_layout = self._make_apple_card()

        c2_title = QLabel("Voice Output Language & Speech Synthesis", page)
        c2_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #BF5AF2;")
        c2_layout.addWidget(c2_title)

        form2 = QFormLayout()
        form2.setSpacing(14)

        # C. Voice Output Language Dropdown
        self.combo_voice_lang = QComboBox(page)
        self.combo_voice_lang.addItem("Follow AI Response Language (Recommended)", "follow_response")
        self.combo_voice_lang.addItem("English", "en")
        self.combo_voice_lang.addItem("Gujarati (ગુજરાતી)", "gu")
        self.combo_voice_lang.addItem("Hindi (हिन्दी)", "hi")
        self.combo_voice_lang.currentIndexChanged.connect(self._on_voice_lang_changed)
        form2.addRow("Voice Output Language:", self.combo_voice_lang)

        # Legacy / hidden specific voice lang for backwards compatibility
        self.combo_specific_voice_lang = QComboBox(page)
        self.combo_specific_voice_lang.setVisible(False)

        c2_layout.addLayout(form2)

        # Live TTS Voice Capability & Limitation Indicator Box
        self.tts_cap_box = QFrame(page)
        self.tts_cap_box.setStyleSheet("""
            QFrame {
                background: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
        """)
        tts_box_layout = QVBoxLayout(self.tts_cap_box)
        tts_box_layout.setContentsMargins(12, 10, 12, 10)
        tts_box_layout.setSpacing(6)

        tts_badge_row = QHBoxLayout()
        tts_lbl_title = QLabel("TTS Voice Compatibility Status:", self.tts_cap_box)
        tts_lbl_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #F5F5F7;")
        tts_badge_row.addWidget(tts_lbl_title)

        self.lbl_tts_badge = QLabel("Supported", self.tts_cap_box)
        self.lbl_tts_badge.setStyleSheet("""
            font-size: 11px;
            font-weight: 700;
            color: #32D74B;
            background: rgba(50, 215, 75, 0.12);
            border-radius: 4px;
            padding: 2px 8px;
        """)
        tts_badge_row.addWidget(self.lbl_tts_badge)
        tts_badge_row.addStretch()
        tts_box_layout.addLayout(tts_badge_row)

        self.lbl_tts_cap_desc = QLabel(
            "Verifying voice compatibility with the active speech synthesis engine...",
            self.tts_cap_box,
        )
        self.lbl_tts_cap_desc.setWordWrap(True)
        self.lbl_tts_cap_desc.setStyleSheet("font-size: 11px; color: #8E8E93; line-height: 1.4;")
        tts_box_layout.addWidget(self.lbl_tts_cap_desc)

        c2_layout.addWidget(self.tts_cap_box)
        layout.addWidget(card2)

        # ─── Card 3: Speech Recognition Language ───────────────────────
        card3, c3_layout = self._make_apple_card()

        c3_title = QLabel("Speech Recognition (STT)", page)
        c3_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #32ADE6;")
        c3_layout.addWidget(c3_title)

        form3 = QFormLayout()
        form3.setSpacing(14)

        # D. Speech Recognition Language Dropdown
        self.combo_stt_lang = QComboBox(page)
        for code, meta in SUPPORTED_STT_LANGUAGES.items():
            display_name = meta["name"]
            if meta.get("native_name") and meta["native_name"] != meta["name"] and code != "auto":
                display_name = f"{meta['name']} ({meta['native_name']})"
            self.combo_stt_lang.addItem(display_name, code)
        self.combo_stt_lang.currentIndexChanged.connect(self._on_stt_lang_changed)
        form3.addRow("Speech Recognition Language:", self.combo_stt_lang)

        desc_stt = QLabel(
            "Automatic detection accurately recognizes speech across English, Gujarati, and Hindi. "
            "Selecting a specific language locks speech recognition to that language only.",
            page,
        )
        desc_stt.setWordWrap(True)
        desc_stt.setStyleSheet("font-size: 11px; color: #8E8E93; margin-top: -6px;")
        form3.addRow("", desc_stt)

        c3_layout.addLayout(form3)
        layout.addWidget(card3)

        layout.addStretch()
        return page

    def _update_tts_capability_display(self) -> None:
        """Update live status badge and limitation advisory for speech synthesis."""
        if not hasattr(self, "lbl_tts_badge") or not hasattr(self, "lbl_tts_cap_desc"):
            return

        from app.ai.multilingual_engine import MultilingualEngine

        active_engine = self.config_manager.get("voice.engine") or self.config_manager.get("voice.tts_engine") or "kokoro"
        voice_mode = self.combo_voice_lang.currentData() if hasattr(self, "combo_voice_lang") else "follow_response"

        target_lang = "en"
        if voice_mode in ("en", "gu", "hi"):
            target_lang = voice_mode
        elif voice_mode == "specific" and hasattr(self, "combo_specific_voice_lang"):
            target_lang = self.combo_specific_voice_lang.currentData() or "en"
        elif voice_mode in ("follow_response", "follow_input") and hasattr(self, "combo_response_lang"):
            resp_lang = self.combo_response_lang.currentData()
            target_lang = "en" if resp_lang in ("auto", "", None) else resp_lang

        # Query installed voices from voice_service if available
        installed_voices = None
        if hasattr(self, "voice_service") and self.voice_service:
            try:
                if hasattr(self.voice_service, "get_available_voices"):
                    installed_voices = self.voice_service.get_available_voices()
            except Exception:
                pass

        check = MultilingualEngine.check_tts_capability(
            engine_name=str(active_engine),
            target_language=str(target_lang),
            installed_voices=installed_voices,
        )

        badge_text = check["status_badge"]
        badge_color = check["badge_color"]
        msg = check["message"]

        self.lbl_tts_badge.setText(badge_text)
        self.lbl_tts_badge.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 700;
            color: {badge_color};
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid {badge_color};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        self.lbl_tts_cap_desc.setText(msg)

    def _update_script_preview(self) -> None:
        if not hasattr(self, "lbl_script_preview"):
            return
        lang = str(self.combo_response_lang.currentData()) if hasattr(self, "combo_response_lang") else "auto"
        fmt = str(self.combo_response_format.currentData()) if hasattr(self, "combo_response_format") else "native"

        if lang == "gu":
            if fmt == "romanized":
                user_ex = "Tamaru naam su che?"
                bond_ex = "Maru naam Bond che! Tamne maline khub aanand thayo."
            else:
                user_ex = "તમારું નામ શું છે?"
                bond_ex = "મારું નામ બોન્ડ છે! તમને મળીને ખૂબ આનંદ થયો."
        elif lang == "hi":
            if fmt == "romanized":
                user_ex = "Aapka naam kya hai?"
                bond_ex = "Mera naam Bond hai! Aap kaise hain?"
            else:
                user_ex = "आपका नाम क्या है?"
                bond_ex = "मेरा नाम बॉन्ड है! आप कैसे हैं?"
        elif lang == "auto":
            if fmt == "romanized":
                user_ex = "Kem cho? / Tamaru naam su che?"
                bond_ex = "Hu majama chu! (Auto-detect mirrors your input in Latin script)"
            else:
                user_ex = "Kem cho? / કેમ છો?"
                bond_ex = "હું મજામાં છું! (Auto-detect mirrors your input in native script)"
        else:
            user_ex = "What is your name?"
            bond_ex = "My name is Bond! Pleased to meet you."

        self.lbl_script_preview.setText(
            f"<b>You:</b> {user_ex}<br>"
            f"<b>Bond:</b> <span style='color: #32D74B; font-weight: 600;'>{bond_ex}</span>"
        )

    def _create_voice_page(self) -> QWidget:
        """Voice page matching Apple Inset Grouped design with 5 genuine voice profiles (Phase 1)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        header = QLabel("Voice & Speech", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Select Bond's conversational voice profile across genuine male and female speakers.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        # ─── Card 1: 5 Selectable Voice Profiles ───────────────────────────
        card_voices, cv_layout = self._make_apple_card()

        cv_title = QLabel("Companion Voice Selection", page)
        cv_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #00C7BE;")
        cv_layout.addWidget(cv_title)

        cv_desc = QLabel(
            "Bond features five genuinely distinct voices. Select a companion voice profile below, "
            "or press Preview to listen to identical test sentences across English, Hindi, and Gujarati.",
            page,
        )
        cv_desc.setWordWrap(True)
        cv_desc.setStyleSheet("font-size: 11px; color: #8E8E93; margin-top: -4px; margin-bottom: 6px;")
        cv_layout.addWidget(cv_desc)

        from app.voice.voice_registry import list_voice_profiles
        self._voice_cards: list[VoiceProfileCard] = []
        active_prof = self.config_manager.get("voice.selected_profile", "arjun")

        for profile in list_voice_profiles():
            vcard = VoiceProfileCard(
                profile=profile,
                is_selected=(profile.profile_id == active_prof),
                parent=page,
            )
            vcard.selected.connect(self._on_voice_profile_selected)
            vcard.preview_requested.connect(self._on_voice_profile_preview_requested)
            self._voice_cards.append(vcard)
            cv_layout.addWidget(vcard)

        layout.addWidget(card_voices)

        # ─── Card 2: Speech Triggers & Audio Configuration ─────────────────
        card_trigger, ct_layout = self._make_apple_card()

        ct_title = QLabel("Speech Triggers & Audio Settings", page)
        ct_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #32ADE6;")
        ct_layout.addWidget(ct_title)

        form = QFormLayout()
        form.setSpacing(14)

        self.voice_mode_combo = QComboBox(page)
        self.voice_mode_combo.addItem("Continuous Dialogue", "continuous")
        self.voice_mode_combo.addItem("Wake Word ('Hey Buddy')", "wake_word")
        self.voice_mode_combo.addItem("Push-to-Talk", "push_to_talk")
        self.voice_mode_combo.addItem("Voice Off", "off")
        self.voice_mode_combo.currentIndexChanged.connect(self._on_voice_mode_changed)
        form.addRow("Voice Mode:", self.voice_mode_combo)

        self.tts_engine_combo = QComboBox(page)
        self.tts_engine_combo.addItem("Kokoro-82M (Neural High Quality)", "kokoro")
        self.tts_engine_combo.addItem("Piper (Fast Neural ONNX)", "piper")
        self.tts_engine_combo.addItem("Windows SAPI5 (Native Offline)", "sapi5")
        self.tts_engine_combo.currentIndexChanged.connect(self._on_tts_engine_changed)
        form.addRow("TTS Voice Engine:", self.tts_engine_combo)

        self.voice_speed_slider = QSlider(Qt.Horizontal, page)
        self.voice_speed_slider.setRange(50, 200)
        self.voice_speed_slider.setValue(100)
        self.lbl_voice_speed = QLabel("1.00x", page)
        self.lbl_voice_speed.setStyleSheet("color: #0A84FF; font-weight: 600; min-width: 45px;")
        speed_row = QHBoxLayout()
        speed_row.addWidget(self.voice_speed_slider)
        speed_row.addWidget(self.lbl_voice_speed)
        self.voice_speed_slider.valueChanged.connect(self._on_voice_speed_changed)
        form.addRow("Speech Speed:", speed_row)

        self.wake_word_enabled_cb = QCheckBox("Enable Wake-Word Activation", page)
        self.wake_word_enabled_cb.toggled.connect(self._on_wake_word_enabled_toggled)
        form.addRow("Wake Word Status:", self.wake_word_enabled_cb)

        self.wake_word_input = QLineEdit(page)
        self.wake_word_input.textChanged.connect(self._on_wake_word_changed)
        form.addRow("Wake Word Phrase:", self.wake_word_input)

        self.auto_return_to_sleep_cb = QCheckBox("Auto Return to Sleep (Single interaction cycle)", page)
        self.auto_return_to_sleep_cb.toggled.connect(self._on_auto_return_to_sleep_toggled)
        form.addRow("Sleep Management:", self.auto_return_to_sleep_cb)

        self.autonomous_messages_cb = QCheckBox("Allow Autonomous Messages & Checks", page)
        self.autonomous_messages_cb.toggled.connect(self._on_autonomous_messages_toggled)
        form.addRow("Autonomous Actions:", self.autonomous_messages_cb)

        ct_layout.addLayout(form)
        layout.addWidget(card_trigger)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _on_voice_profile_selected(self, profile_id: str) -> None:
        """Handle user selection of one of the 5 companion voice profiles (Phase 1.3, 2.2)."""
        logger.info("Voice profile selected: %s", profile_id)
        self.config_manager.set("voice.selected_profile", profile_id)
        for card in getattr(self, "_voice_cards", []):
            card.set_selected(card.profile.profile_id == profile_id)

        # Keep persona-to-voice mapping synchronized with active persona
        active_persona = self.config_manager.get("ai.personality", "friendly")
        if self.ai_service and hasattr(self.ai_service, "personality_manager"):
            self.ai_service.personality_manager.set_voice_for_persona(active_persona, profile_id, emit_signal=False)
        else:
            pmap = self.config_manager.get("ai.persona_voice_map", {})
            if isinstance(pmap, dict):
                pmap[active_persona] = profile_id
                self.config_manager.set("ai.persona_voice_map", pmap)

        if hasattr(self, "persona_voice_combo"):
            self.persona_voice_combo.blockSignals(True)
            v_idx = self.persona_voice_combo.findData(profile_id)
            if v_idx >= 0:
                self.persona_voice_combo.setCurrentIndex(v_idx)
            self.persona_voice_combo.blockSignals(False)

        if hasattr(self, "voice_service") and self.voice_service:
            self.voice_service.set_voice_profile(profile_id)
        signals.voice_profile_changed.emit(profile_id)
        self._update_tts_capability_display()

    def _on_voice_profile_preview_requested(self, profile_id: str, language: str) -> None:
        """Handle user request to preview a voice profile in the selected language (Phase 1.4)."""
        logger.info("Playing preview for voice '%s' in language '%s'", profile_id, language)
        vs = getattr(self, "voice_service", None)
        if vs is None:
            try:
                from app.api.server import fastapi_app
                vs = getattr(fastapi_app.state, "voice_service", None)
                if vs:
                    self.voice_service = vs
            except Exception:
                pass
        if vs and hasattr(vs, "play_voice_preview"):
            vs.play_voice_preview(profile_id, language=language)
        else:
            logger.warning("VoiceService unavailable for voice preview: %s", profile_id)

    def _create_personality_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("AI Personality & Style", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Choose tone of voice, empathy level, and response conciseness.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        card, card_layout = self._make_apple_card()

        form = QFormLayout()
        form.setSpacing(14)

        self.personality_combo = QComboBox(page)
        profiles = [
            ("friendly", "Friendly (Casual & supportive)"),
            ("funny", "Funny (Playful & humorous)"),
            ("calm", "Calm (Relaxed & mindful)"),
            ("energetic", "Energetic (Enthusiastic & vibrant)"),
            ("professional", "Professional (Direct & informative)"),
        ]
        for key, label in profiles:
            self.personality_combo.addItem(label, key)
        self.personality_combo.currentIndexChanged.connect(self._on_personality_changed)
        form.addRow("Personality Profile:", self.personality_combo)

        self.lbl_profile_desc = QLabel("", page)
        self.lbl_profile_desc.setWordWrap(True)
        self.lbl_profile_desc.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 10px;
                color: #8E8E93;
                font-size: 12px;
                line-height: 18px;
            }
        """)
        form.addRow("Profile Behavior:", self.lbl_profile_desc)

        # Assigned Voice Profile selector (Phase 2.1, 2.2)
        voice_row = QWidget(page)
        voice_layout = QHBoxLayout(voice_row)
        voice_layout.setContentsMargins(0, 0, 0, 0)
        voice_layout.setSpacing(8)

        self.persona_voice_combo = QComboBox(voice_row)
        voice_options = [
            ("arjun", "Arjun – Male (Friendly & Confident)"),
            ("kabir", "Kabir – Male (Calm & Mature)"),
            ("ananya", "Ananya – Female (Warm & Expressive)"),
            ("mira", "Mira – Female (Gentle & Composed)"),
            ("zara", "Zara – Female (Energetic & Lively)"),
        ]
        for v_id, v_label in voice_options:
            self.persona_voice_combo.addItem(v_label, v_id)
        self.persona_voice_combo.currentIndexChanged.connect(self._on_persona_voice_changed)
        voice_layout.addWidget(self.persona_voice_combo, 1)

        self.btn_preview_persona_voice = QPushButton("Test Voice", voice_row)
        self.btn_preview_persona_voice.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_preview_persona_voice.setStyleSheet("""
            QPushButton {
                background: #0A84FF;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #0071E3;
            }
        """)
        self.btn_preview_persona_voice.clicked.connect(self._on_preview_persona_voice_clicked)
        voice_layout.addWidget(self.btn_preview_persona_voice)

        form.addRow("Assigned Voice:", voice_row)

        self.style_combo = QComboBox(page)
        self.style_combo.addItem("Concise (1-3 sentences)", "concise")
        self.style_combo.addItem("Casual (Conversational)", "casual")
        self.style_combo.addItem("Detailed (Comprehensive)", "detailed")
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)
        form.addRow("Response Style:", self.style_combo)

        card_layout.addLayout(form)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _create_memory_page(self) -> QWidget:
        """Full memory management tab maintaining 100% test compatibility (NO EMOJIS)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QLabel("Long-Term Memory", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Persistent SQLite context recall and auto-extracted memory points.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 4px;")
        layout.addWidget(sub)

        # Card 1: Toggles
        card_toggles, ct_layout = self._make_apple_card()
        toggles_layout = QHBoxLayout()
        self.cb_memory_enabled = AnimatedToggleSwitch("Enable Long-Term Memory", page)
        self.cb_memory_enabled.toggled.connect(self._on_memory_enabled_toggled)
        toggles_layout.addWidget(self.cb_memory_enabled)

        self.cb_auto_extract = AnimatedToggleSwitch("Auto-Extract Memories From Chats", page)
        self.cb_auto_extract.toggled.connect(self._on_auto_extract_toggled)
        toggles_layout.addWidget(self.cb_auto_extract)
        ct_layout.addLayout(toggles_layout)
        layout.addWidget(card_toggles)

        # Card 2: Search & Table
        card_table, ctab_layout = self._make_apple_card()

        # Search Bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit(page)
        self.search_input.setPlaceholderText("Search stored memories (FTS5 search)...")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input)

        self.lbl_stats = QLabel("0 memories", page)
        self.lbl_stats.setStyleSheet("""
            color: #8E8E93;
            font-size: 12px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 6px;
            padding: 3px 8px;
        """)
        search_layout.addWidget(self.lbl_stats)
        ctab_layout.addLayout(search_layout)

        # Memory Table
        self.mem_table = QTableWidget(0, 3, page)
        self.mem_table.setHorizontalHeaderLabels(["Category", "Content", "Date"])
        self.mem_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.mem_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.mem_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.mem_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mem_table.setSelectionMode(QTableWidget.SingleSelection)
        self.mem_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mem_table.doubleClicked.connect(self._on_edit_memory)
        self.mem_table.setStyleSheet("""
            QTableWidget {
                background-color: rgba(0, 0, 0, 0.2);
                color: #F5F5F7;
                gridline-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                selection-background-color: rgba(10, 132, 255, 0.35);
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
            }
            QHeaderView::section {
                background-color: rgba(255, 255, 255, 0.04);
                color: #8E8E93;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
                font-size: 11px;
                font-weight: 600;
                border: none;
                padding: 6px;
            }
        """)
        ctab_layout.addWidget(self.mem_table)

        # Action Buttons with Apple Vector Icons (NO EMOJIS)
        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add Memory", page)
        btn_add.setIcon(create_button_icon("plus", size=14, color=QColor(245, 245, 247)))
        btn_add.clicked.connect(self._on_add_memory)
        btn_row.addWidget(btn_add)

        btn_edit = QPushButton("Edit", page)
        btn_edit.setIcon(create_button_icon("pencil", size=14, color=QColor(245, 245, 247)))
        btn_edit.clicked.connect(self._on_edit_memory)
        btn_row.addWidget(btn_edit)

        btn_del = QPushButton("Delete", page)
        btn_del.setIcon(create_button_icon("trash", size=14, color=QColor(255, 69, 58)))
        btn_del.clicked.connect(self._on_delete_memory)
        btn_row.addWidget(btn_del)

        btn_clear = QPushButton("Clear All", page)
        btn_clear.clicked.connect(self._on_clear_all_memories)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()
        ctab_layout.addLayout(btn_row)

        layout.addWidget(card_table)
        return page

    def _create_appearance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("Appearance", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Interface theme and glassmorphic vibrancy appearance.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        card, c_layout = self._make_apple_card()
        theme_lbl = QLabel("Color Palette: Apple macOS Sequoia Dark Space Gray & System Blue", page)
        theme_lbl.setStyleSheet("color: #E5E5EA; font-size: 13px;")
        c_layout.addWidget(theme_lbl)

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _create_hotkeys_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("Keyboard Hotkeys", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Quick system-wide hotkeys and interaction controls.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        card, c_layout = self._make_apple_card()
        info = QLabel(
            "• Escape: Immediate Emergency Audio / AI Stop\n"
            "• Enter: Transmit message in chat\n"
            "• Shift + Enter: Insert newline in message input",
            page,
        )
        info.setStyleSheet("color: #E5E5EA; line-height: 24px; font-size: 13px;")
        c_layout.addWidget(info)

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _create_startup_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("Startup & Integration", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Configure launch behavior when logging into your desktop.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        card, c_layout = self._make_apple_card()
        self.cb_autostart = AnimatedToggleSwitch("Launch on Windows Startup", page)
        self.cb_autostart.toggled.connect(self._on_autostart_toggled)
        c_layout.addWidget(self.cb_autostart)

        info = QLabel(
            "When enabled, AI Desktop Friend will automatically launch quietly in the background when you sign in.",
            page,
        )
        info.setStyleSheet("color: #8E8E93; font-size: 12px; margin-top: 4px;")
        info.setWordWrap(True)
        c_layout.addWidget(info)

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _create_advanced_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("Advanced Performance", page)
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(header)

        sub = QLabel("Fine-tune resource throttling, hardware acceleration, and telemetry.", page)
        sub.setStyleSheet("font-size: 12px; color: #8E8E93; margin-top: -8px; margin-bottom: 6px;")
        layout.addWidget(sub)

        card, c_layout = self._make_apple_card()
        info = QLabel("Performance Mode: Balanced (Intelligent CPU / RAM allocation)", page)
        info.setStyleSheet("color: #E5E5EA; font-size: 13px;")
        c_layout.addWidget(info)

        layout.addWidget(card)
        layout.addStretch()
        return page

    # ─── Settings Loading & Saving ─────────────────────────────────────

    def _load_settings(self) -> None:
        mem_enabled = bool(self.config_manager.get("memory.enabled", True))
        self.cb_memory_enabled.setChecked(mem_enabled)

        auto_extract = bool(self.config_manager.get("memory.auto_extract_enabled", True))
        self.cb_auto_extract.setChecked(auto_extract)

        companion_name = self.config_manager.get("ai.companion_name", "Buddy")
        self.name_input.setText(companion_name)

        active_pers = self.config_manager.get("ai.personality", "friendly")
        idx = self.personality_combo.findData(active_pers)
        if idx >= 0:
            self.personality_combo.setCurrentIndex(idx)
        self._update_personality_description(active_pers)

        # Synchronize persona assigned voice (Phase 2.1)
        if hasattr(self, "persona_voice_combo"):
            mapped_voice = "arjun"
            if self.ai_service and hasattr(self.ai_service, "personality_manager"):
                mapped_voice = self.ai_service.personality_manager.get_voice_for_persona(active_pers)
            else:
                pmap = self.config_manager.get("ai.persona_voice_map", {})
                if isinstance(pmap, dict):
                    mapped_voice = pmap.get(active_pers, "arjun")
            v_idx = self.persona_voice_combo.findData(mapped_voice)
            if v_idx >= 0:
                self.persona_voice_combo.blockSignals(True)
                self.persona_voice_combo.setCurrentIndex(v_idx)
                self.persona_voice_combo.blockSignals(False)

        resp_style = self.config_manager.get("ai.response_style", "concise")
        idx = self.style_combo.findData(resp_style)
        if idx >= 0:
            self.style_combo.setCurrentIndex(idx)

        voice_mode = self.config_manager.get("voice.mode", "push_to_talk")
        idx = self.voice_mode_combo.findData(voice_mode)
        if idx >= 0:
            self.voice_mode_combo.setCurrentIndex(idx)

        active_engine = self.config_manager.get("voice.engine") or self.config_manager.get("voice.tts_engine") or "kokoro"
        idx = self.tts_engine_combo.findData(active_engine)
        if idx >= 0:
            self.tts_engine_combo.setCurrentIndex(idx)

        active_prof = self.config_manager.get("voice.selected_profile", "arjun")
        for card in getattr(self, "_voice_cards", []):
            card.set_selected(card.profile.profile_id == active_prof)

        speed_val = float(self.config_manager.get("voice.speed") or self.config_manager.get("voice.voice_speed") or 1.0)
        self.voice_speed_slider.blockSignals(True)
        self.voice_speed_slider.setValue(int(round(speed_val * 100)))
        self.lbl_voice_speed.setText(f"{speed_val:.2f}x")
        self.voice_speed_slider.blockSignals(False)

        wake_enabled = bool(self.config_manager.get("voice.wake_word_enabled", True))
        if hasattr(self, "wake_word_enabled_cb"):
            self.wake_word_enabled_cb.blockSignals(True)
            self.wake_word_enabled_cb.setChecked(wake_enabled)
            self.wake_word_enabled_cb.blockSignals(False)

        wake_word = self.config_manager.get("voice.wake_word", "Hey Bond")
        self.wake_word_input.setText(wake_word)

        auto_sleep = bool(self.config_manager.get("voice.auto_return_to_sleep", True))
        if hasattr(self, "auto_return_to_sleep_cb"):
            self.auto_return_to_sleep_cb.blockSignals(True)
            self.auto_return_to_sleep_cb.setChecked(auto_sleep)
            self.auto_return_to_sleep_cb.blockSignals(False)

        auto_msgs = bool(self.config_manager.get("voice.autonomous_messages", False))
        if hasattr(self, "autonomous_messages_cb"):
            self.autonomous_messages_cb.blockSignals(True)
            self.autonomous_messages_cb.setChecked(auto_msgs)
            self.autonomous_messages_cb.blockSignals(False)

        endpoint = self.config_manager.get("ai.ollama_host", "http://127.0.0.1:11434")
        self.endpoint_input.blockSignals(True)
        self.endpoint_input.setText(endpoint)
        self.endpoint_input.blockSignals(False)

        # AI Model Settings (Phase 5)
        self._populate_model_preferences_ui()

        mode = self.config_manager.get("ai.model_selection_mode", "auto")
        mode_idx = self.combo_model_mode.findData(mode)
        if mode_idx >= 0:
            self.combo_model_mode.blockSignals(True)
            self.combo_model_mode.setCurrentIndex(mode_idx)
            self.combo_model_mode.blockSignals(False)

        priority = self.config_manager.get("ai.response_priority", "balanced")
        prio_idx = self.combo_response_priority.findData(priority)
        if prio_idx >= 0:
            self.combo_response_priority.blockSignals(True)
            self.combo_response_priority.setCurrentIndex(prio_idx)
            self.combo_response_priority.blockSignals(False)

        model = self.config_manager.get("ai.model", "llama3.2:3b")
        self.model_input.blockSignals(True)
        self.model_input.setText(model)
        self.model_input.blockSignals(False)
        man_idx = self.combo_manual_model.findText(model)
        self.combo_manual_model.blockSignals(True)
        if man_idx >= 0:
            self.combo_manual_model.setCurrentIndex(man_idx)
        else:
            self.combo_manual_model.setEditText(model)
        self.combo_manual_model.blockSignals(False)

        task_prefs = self.config_manager.get("ai.task_preferred_models", {})
        task_combos = {
            "general_conversation": self.combo_pref_general,
            "complex_reasoning": self.combo_pref_reasoning,
            "coding": self.combo_pref_coding,
            "document_summarization": self.combo_pref_summarization,
            "vision": self.combo_pref_vision,
        }
        for task_key, combo in task_combos.items():
            pref_val = task_prefs.get(task_key, "auto") if isinstance(task_prefs, dict) else "auto"
            t_idx = combo.findData(pref_val)
            if t_idx >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(t_idx)
                combo.blockSignals(False)

        self._update_model_ui_state(mode)
        self._check_manual_model_availability(model)

        pet_size = int(self.config_manager.get("pet.size", 120))
        self.size_slider.setValue(pet_size)
        self.lbl_size_val.setText(f"{pet_size} px")
        for card in self._size_cards:
            card.set_active(abs(card.pixel_size - pet_size) <= 10)

        if hasattr(self, "cb_autostart"):
            from app.core import startup_manager
            is_enabled = startup_manager.is_startup_enabled()
            cfg_autostart = bool(self.config_manager.get("general.start_at_login", False))
            self.cb_autostart.blockSignals(True)
            self.cb_autostart.setChecked(is_enabled or cfg_autostart)
            self.cb_autostart.blockSignals(False)

        # Language & Communication Settings
        if hasattr(self, "combo_response_lang"):
            resp_lang = self.config_manager.get("language.response_language", "auto")
            idx = self.combo_response_lang.findData(resp_lang)
            if idx >= 0:
                self.combo_response_lang.blockSignals(True)
                self.combo_response_lang.setCurrentIndex(idx)
                self.combo_response_lang.blockSignals(False)

        if hasattr(self, "combo_response_format"):
            resp_fmt = self.config_manager.get("language.response_format", "native")
            idx = self.combo_response_format.findData(resp_fmt)
            if idx >= 0:
                self.combo_response_format.blockSignals(True)
                self.combo_response_format.setCurrentIndex(idx)
                self.combo_response_format.blockSignals(False)

        if hasattr(self, "combo_voice_lang"):
            voice_lang = self.config_manager.get("language.voice_output_language", "follow_response")
            idx = self.combo_voice_lang.findData(voice_lang)
            if idx >= 0:
                self.combo_voice_lang.blockSignals(True)
                self.combo_voice_lang.setCurrentIndex(idx)
                self.combo_voice_lang.blockSignals(False)
            if hasattr(self, "combo_specific_voice_lang"):
                self.combo_specific_voice_lang.setEnabled(voice_lang == "specific")

        if hasattr(self, "combo_specific_voice_lang"):
            spec_lang = self.config_manager.get("language.specific_voice_language", "en")
            idx = self.combo_specific_voice_lang.findData(spec_lang)
            if idx >= 0:
                self.combo_specific_voice_lang.blockSignals(True)
                self.combo_specific_voice_lang.setCurrentIndex(idx)
                self.combo_specific_voice_lang.blockSignals(False)

        if hasattr(self, "combo_stt_lang"):
            stt_lang = self.config_manager.get("language.stt_language") or self.config_manager.get("voice.language", "auto")
            idx = self.combo_stt_lang.findData(stt_lang)
            if idx >= 0:
                self.combo_stt_lang.blockSignals(True)
                self.combo_stt_lang.setCurrentIndex(idx)
                self.combo_stt_lang.blockSignals(False)

        self._update_tts_capability_display()
        self._update_script_preview()

    def _update_personality_description(self, pers_key: str) -> None:
        pers_cfg = PRESET_PERSONALITIES.get(pers_key)
        if pers_cfg:
            char_desc = getattr(pers_cfg, "speaking_character", "Companion")
            self.lbl_profile_desc.setText(
                f"{pers_cfg.title}: {pers_cfg.description}\nTone: {char_desc}\n\nPersona Guide:\n{pers_cfg.base_prompt[:160]}..."
            )
        else:
            self.lbl_profile_desc.setText(f"Active personality: {pers_key}")

    def _reset_defaults(self) -> None:
        self.size_slider.setValue(120)
        self.name_input.setText("Buddy")
        self.personality_combo.setCurrentIndex(0)
        if hasattr(self, "combo_response_lang"):
            self.combo_response_lang.setCurrentIndex(0)
        if hasattr(self, "combo_response_format"):
            self.combo_response_format.setCurrentIndex(0)
        if hasattr(self, "combo_voice_lang"):
            self.combo_voice_lang.setCurrentIndex(0)
        if hasattr(self, "combo_specific_voice_lang"):
            self.combo_specific_voice_lang.setCurrentIndex(0)
        if hasattr(self, "combo_stt_lang"):
            self.combo_stt_lang.setCurrentIndex(0)
        self._update_tts_capability_display()
        self._update_script_preview()

    # ─── Memory Operations ─────────────────────────────────────────────

    def _refresh_memories(self, query: str = "") -> None:
        if query.strip():
            self._current_memories = self.memory_manager.search_memories(query, limit=50)
        else:
            self._current_memories = self.memory_manager.get_all_memories(limit=100)

        total_count = self.memory_manager.get_memory_count()
        self.lbl_stats.setText(f"{total_count} memories")

        self.mem_table.setRowCount(0)
        self.mem_table.setRowCount(len(self._current_memories))

        for row, mem in enumerate(self._current_memories):
            cat_item = QTableWidgetItem(mem.category.capitalize())
            cat_item.setTextAlignment(Qt.AlignCenter)
            cat_color = CATEGORY_COLORS.get(mem.category.lower(), "#8E8E93")
            cat_item.setForeground(QColor(cat_color))

            content_item = QTableWidgetItem(mem.content)
            content_item.setToolTip(mem.content)

            date_str = mem.created_at[:10] if mem.created_at else ""
            date_item = QTableWidgetItem(date_str)
            date_item.setTextAlignment(Qt.AlignCenter)
            date_item.setForeground(QColor("#8E8E93"))

            self.mem_table.setItem(row, 0, cat_item)
            self.mem_table.setItem(row, 1, content_item)
            self.mem_table.setItem(row, 2, date_item)

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        self._refresh_memories(text)

    @Slot()
    def _on_add_memory(self) -> None:
        dlg = AddEditMemoryDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            category, content = dlg.get_data()
            mem = self.memory_manager.store_memory(category=category, content=content)
            signals.memory_stored.emit(mem)
            self._refresh_memories(self.search_input.text())

    @Slot()
    def _on_edit_memory(self) -> None:
        row = self.mem_table.currentRow()
        if row < 0 or row >= len(self._current_memories):
            QMessageBox.information(self, "No Selection", "Please select a memory to edit.")
            return

        target_mem = self._current_memories[row]
        dlg = AddEditMemoryDialog(memory=target_mem, parent=self)
        if dlg.exec() == QDialog.Accepted:
            category, content = dlg.get_data()
            updated = self.memory_manager.update_memory(
                memory_id=target_mem.id,
                content=content,
                category=category,
            )
            if updated:
                signals.memory_updated.emit(updated)
            self._refresh_memories(self.search_input.text())

    @Slot()
    def _on_delete_memory(self) -> None:
        row = self.mem_table.currentRow()
        if row < 0 or row >= len(self._current_memories):
            QMessageBox.information(self, "No Selection", "Please select a memory to delete.")
            return

        target_mem = self._current_memories[row]
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete this memory?\n\n\"{target_mem.content}\"",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.memory_manager.delete_memory(target_mem.id)
            signals.memory_deleted.emit(target_mem.id)
            self._refresh_memories(self.search_input.text())

    @Slot()
    def _on_clear_all_memories(self) -> None:
        reply = QMessageBox.warning(
            self,
            "Clear All Memories",
            "Are you sure you want to delete ALL stored memories? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.memory_manager.clear_all_memories()
            self._refresh_memories(self.search_input.text())

    @Slot(bool)
    def _on_memory_enabled_toggled(self, checked: bool) -> None:
        self.config_manager.set("memory.enabled", checked)
        if self.ai_service:
            self.ai_service.set_memory_enabled(checked)

    @Slot(bool)
    def _on_auto_extract_toggled(self, checked: bool) -> None:
        self.config_manager.set("memory.auto_extract_enabled", checked)
        if self.ai_service:
            self.ai_service.set_auto_extract_memory(checked)

    # ─── Personality & AI Slots ────────────────────────────────────────

    @Slot(int)
    def _on_personality_changed(self, index: int) -> None:
        key = str(self.personality_combo.currentData())
        self.config_manager.set("ai.personality", key)
        if self.ai_service:
            self.ai_service.set_personality(key)
        self._update_personality_description(key)

        # Synchronize persona voice dropdown to mapped voice (Phase 2.1)
        mapped_voice = "arjun"
        if self.ai_service and hasattr(self.ai_service, "personality_manager"):
            mapped_voice = self.ai_service.personality_manager.get_voice_for_persona(key)
        else:
            pmap = self.config_manager.get("ai.persona_voice_map", {})
            if isinstance(pmap, dict):
                mapped_voice = pmap.get(key, "arjun")

        if hasattr(self, "persona_voice_combo"):
            self.persona_voice_combo.blockSignals(True)
            v_idx = self.persona_voice_combo.findData(mapped_voice)
            if v_idx >= 0:
                self.persona_voice_combo.setCurrentIndex(v_idx)
            self.persona_voice_combo.blockSignals(False)

        # Update Voice tab cards to reflect the active voice profile
        for card in getattr(self, "_voice_cards", []):
            card.set_selected(card.profile.profile_id == mapped_voice)
        self._update_tts_capability_display()

    @Slot(int)
    def _on_persona_voice_changed(self, index: int) -> None:
        """Handle user changing the assigned voice for the selected persona (Phase 2.2)."""
        voice_id = str(self.persona_voice_combo.currentData())
        if not voice_id:
            return
        current_persona = str(self.personality_combo.currentData()) or "friendly"
        logger.info("Persona '%s' voice assigned to '%s'", current_persona, voice_id)

        # Update personality manager
        if self.ai_service and hasattr(self.ai_service, "personality_manager"):
            self.ai_service.personality_manager.set_voice_for_persona(current_persona, voice_id, emit_signal=False)
        else:
            pmap = self.config_manager.get("ai.persona_voice_map", {})
            if not isinstance(pmap, dict):
                pmap = {}
            pmap[current_persona] = voice_id
            self.config_manager.set("ai.persona_voice_map", pmap)

        # Update active selected profile and notify
        self.config_manager.set("voice.selected_profile", voice_id)
        if hasattr(self, "voice_service") and self.voice_service:
            self.voice_service.set_voice_profile(voice_id)
        signals.voice_profile_changed.emit(voice_id)

        # Synchronize voice cards in Voice tab
        for card in getattr(self, "_voice_cards", []):
            card.set_selected(card.profile.profile_id == voice_id)
        self._update_tts_capability_display()

    def _on_preview_persona_voice_clicked(self) -> None:
        """Preview the persona's assigned voice in the configured AI response language (Phase 2.3)."""
        voice_id = str(self.persona_voice_combo.currentData()) if hasattr(self, "persona_voice_combo") else "arjun"
        resp_lang = self.config_manager.get("language.voice_output_language", "en")
        if resp_lang == "follow_response":
            resp_lang = self.config_manager.get("language.response_language", "en")
        if resp_lang not in ("en", "hi", "gu"):
            resp_lang = "en"
        logger.info("Previewing persona voice '%s' in language '%s'", voice_id, resp_lang)
        vs = getattr(self, "voice_service", None)
        if vs is None:
            try:
                from app.api.server import fastapi_app
                vs = getattr(fastapi_app.state, "voice_service", None)
                if vs:
                    self.voice_service = vs
            except Exception:
                pass
        if vs and hasattr(vs, "play_voice_preview"):
            vs.play_voice_preview(voice_id, language=resp_lang)
        else:
            logger.warning("VoiceService unavailable for persona voice preview: %s", voice_id)

    @Slot(str)
    def _on_name_changed(self, text: str) -> None:
        cleaned = text.strip() or "Buddy"
        self.config_manager.set("ai.companion_name", cleaned)
        self.config_manager.set("companion.name", cleaned)
        if self.ai_service and hasattr(self.ai_service, "personality_manager"):
            self.ai_service.personality_manager.set_companion_name(cleaned)

    @Slot(int)
    def _on_style_changed(self, index: int) -> None:
        style = str(self.style_combo.currentData())
        self.config_manager.set("ai.response_style", style)
        if self.ai_service:
            self.ai_service.config.response_style = style

    @Slot(int)
    def _on_voice_mode_changed(self, index: int) -> None:
        mode = str(self.voice_mode_combo.currentData())
        self.config_manager.set("voice.mode", mode)
        signals.activation_mode_changed.emit(mode)

    @Slot(bool)
    def _on_wake_word_enabled_toggled(self, checked: bool) -> None:
        self.config_manager.set("voice.wake_word_enabled", checked)
        if hasattr(self, "voice_service") and self.voice_service and hasattr(self.voice_service, "conversation_controller"):
            ctrl = self.voice_service.conversation_controller
            if ctrl and hasattr(ctrl, "wake_word_engine"):
                if checked:
                    ctrl.wake_word_engine.enable()
                else:
                    ctrl.wake_word_engine.disable()

    @Slot(str)
    def _on_wake_word_changed(self, text: str) -> None:
        cleaned = text.strip() or "Hey Bond"
        self.config_manager.set("voice.wake_word", cleaned)
        if hasattr(self, "voice_service") and self.voice_service and hasattr(self.voice_service, "conversation_controller"):
            ctrl = self.voice_service.conversation_controller
            if ctrl and hasattr(ctrl, "wake_word_engine"):
                ctrl.wake_word_engine.set_activation_phrase(cleaned)

    @Slot(bool)
    def _on_auto_return_to_sleep_toggled(self, checked: bool) -> None:
        self.config_manager.set("voice.auto_return_to_sleep", checked)
        if hasattr(self, "voice_service") and self.voice_service and hasattr(self.voice_service, "conversation_controller"):
            ctrl = self.voice_service.conversation_controller
            if ctrl:
                ctrl.auto_return_to_sleep = checked

    @Slot(bool)
    def _on_autonomous_messages_toggled(self, checked: bool) -> None:
        self.config_manager.set("voice.autonomous_messages", checked)

    @Slot(str)
    def _on_model_changed(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            self.config_manager.set("ai.model", cleaned)
            if self.ai_service:
                self.ai_service.model_manager.set_active_model(cleaned)

    # ─── Model Preferences & Fallbacks Slots (Phase 5) ─────────────────

    def _populate_model_preferences_ui(self) -> None:
        """Populate model dropdowns with installed and compatible models (Phase 5)."""
        installed = []
        if self.ai_service and hasattr(self.ai_service, "model_manager"):
            installed = self.ai_service.model_manager.get_installed_models()
        if not installed:
            try:
                from app.ai.model_capability_registry import get_model_capability_registry
                installed = [p.model_id for p in get_model_capability_registry().get_installed_models()]
            except Exception:
                installed = []

        self.combo_manual_model.blockSignals(True)
        self.combo_manual_model.clear()
        for m in installed:
            self.combo_manual_model.addItem(m, m)
        self.combo_manual_model.blockSignals(False)

        comp_map = {}
        if self.ai_service and hasattr(self.ai_service, "model_manager"):
            comp_map = self.ai_service.model_manager.get_compatible_models_by_task()
        if not comp_map:
            try:
                from app.ai.model_router import get_model_router
                comp_map = get_model_router().get_compatible_models_by_task()
            except Exception:
                comp_map = {}

        task_combos = {
            "general_conversation": self.combo_pref_general,
            "complex_reasoning": self.combo_pref_reasoning,
            "coding": self.combo_pref_coding,
            "document_summarization": self.combo_pref_summarization,
            "vision": self.combo_pref_vision,
        }

        for task_key, combo in task_combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Auto (Recommended)", "auto")
            models = comp_map.get(task_key, [])
            for m in models:
                combo.addItem(m, m)
            if not models and task_key == "vision":
                combo.addItem("No compatible vision models installed", "")
            combo.blockSignals(False)

    def _update_model_ui_state(self, mode: str) -> None:
        """Toggle UI controls based on automatic vs manual mode (Phase 5)."""
        is_manual = (mode == "manual")
        self.manual_model_container.setVisible(is_manual)
        self.card_priority.setVisible(not is_manual)
        self.card_tasks.setVisible(not is_manual)

    def _check_manual_model_availability(self, model_name: str) -> None:
        """Check if manual model is installed and show alert if unavailable."""
        installed = []
        if self.ai_service and hasattr(self.ai_service, "model_manager"):
            installed = self.ai_service.model_manager.get_installed_models()
        is_available = not installed or (model_name in installed)
        self.lbl_manual_model_warning.setVisible(not is_available)

    @Slot(int)
    def _on_model_mode_changed(self, index: int) -> None:
        mode = str(self.combo_model_mode.currentData()) or "auto"
        self.config_manager.set("ai.model_selection_mode", mode)
        self.config_manager.set("ai.auto_model_routing", mode == "auto")
        self._update_model_ui_state(mode)

    @Slot(int)
    def _on_response_priority_changed(self, index: int) -> None:
        prio = str(self.combo_response_priority.currentData()) or "balanced"
        self.config_manager.set("ai.response_priority", prio)

    @Slot(int)
    def _on_manual_model_changed(self, index: int) -> None:
        model = str(self.combo_manual_model.currentText()).strip()
        if model:
            self._on_model_changed(model)
            self._check_manual_model_availability(model)

    @Slot(str)
    def _on_manual_model_text_changed(self, text: str) -> None:
        model = text.strip()
        if model:
            self._on_model_changed(model)
            self._check_manual_model_availability(model)

    def _on_task_pref_changed(self, task_key: str, combo: QComboBox) -> None:
        val = str(combo.currentData()) or "auto"
        prefs = self.config_manager.get("ai.task_preferred_models", {})
        if not isinstance(prefs, dict):
            prefs = {}
        prefs[task_key] = val
        self.config_manager.set("ai.task_preferred_models", prefs)

    @Slot(bool)
    def _on_autostart_toggled(self, checked: bool) -> None:
        from app.core import startup_manager
        self.config_manager.set("general.start_at_login", checked)
        success = startup_manager.set_startup_enabled(checked)
        logger.info("Startup toggle changed to %s (registry_updated=%s)", checked, success)

    @Slot(int)
    def _on_tts_engine_changed(self, index: int) -> None:
        engine = str(self.tts_engine_combo.currentData())
        self.config_manager.set("voice.engine", engine)
        self.config_manager.set("voice.tts_engine", engine)
        self._update_tts_capability_display()

    # ─── Language & Communication Slots ────────────────────────────────

    @Slot(int)
    def _on_response_lang_changed(self, index: int) -> None:
        code = str(self.combo_response_lang.currentData())
        self.config_manager.set("language.response_language", code)
        self._update_tts_capability_display()
        self._update_script_preview()

    @Slot(int)
    def _on_response_format_changed(self, index: int) -> None:
        fmt = str(self.combo_response_format.currentData())
        self.config_manager.set("language.response_format", fmt)
        self._update_script_preview()

    @Slot(int)
    def _on_voice_lang_changed(self, index: int) -> None:
        mode = str(self.combo_voice_lang.currentData())
        self.config_manager.set("language.voice_output_language", mode)
        if hasattr(self, "combo_specific_voice_lang"):
            self.combo_specific_voice_lang.setEnabled(mode == "specific")
        self._update_tts_capability_display()

    @Slot(int)
    def _on_specific_voice_lang_changed(self, index: int) -> None:
        code = str(self.combo_specific_voice_lang.currentData())
        self.config_manager.set("language.specific_voice_language", code)
        self._update_tts_capability_display()

    @Slot(int)
    def _on_stt_lang_changed(self, index: int) -> None:
        code = str(self.combo_stt_lang.currentData())
        self.config_manager.set("language.stt_language", code)
        self.config_manager.set("voice.language", code)

    @Slot(int)
    def _on_voice_speed_changed(self, val: int) -> None:
        spd = val / 100.0
        self.lbl_voice_speed.setText(f"{spd:.2f}x")
        self.config_manager.set("voice.speed", spd)
        self.config_manager.set("voice.voice_speed", spd)

    @Slot(str)
    def _on_endpoint_changed(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            self.config_manager.set("ai.ollama_host", cleaned)
            if self.ai_service and hasattr(self.ai_service, "client"):
                self.ai_service.client.set_base_url(cleaned)

    # ─── Window Dragging ───────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._is_drag_active = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_drag_active and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._is_drag_active = False
        event.accept()
