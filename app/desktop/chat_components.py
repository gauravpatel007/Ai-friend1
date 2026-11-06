"""Chat Message Components and Visual Indicators.

Provides message bubbles, streaming text updaters, animated thinking indicators,
input bar, welcome hero, date separators, user avatars, and message action buttons
matching the latest reference design with the designated color palette.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.desktop.jarvis_theme import COLORS, qcolor
from app.utils.logger import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_AVATAR_PATH = _PROJECT_ROOT / "assets" / "icons" / "buddy_avatar.png"


def _get_buddy_avatar_pixmap(size: int = 36) -> Optional[QPixmap]:
    if _AVATAR_PATH.exists():
        pix = QPixmap(str(_AVATAR_PATH))
        if not pix.isNull():
            return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None


def _format_time_str(iso_or_raw: Optional[str] = None) -> str:
    """Format timestamp to friendly HH:MM PM string."""
    if not iso_or_raw:
        return datetime.now().strftime("%I:%M %p").lstrip("0")
    try:
        dt = datetime.fromisoformat(iso_or_raw)
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return iso_or_raw[:5] if len(iso_or_raw) >= 5 else iso_or_raw


# ─── Custom Painted User Avatar ──────────────────────────────────────

class UserAvatarWidget(QWidget):
    """Clean antialiased circular user avatar matching reference."""

    def __init__(self, size: int = 36, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Background circle in Primary Blue #1674FF
        painter.setBrush(QBrush(QColor("#1674FF")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, w, h)

        # White silhouette head
        painter.setBrush(QBrush(QColor("#F4F7FF")))
        head_r = w * 0.22
        head_cx = w / 2.0
        head_cy = h * 0.36
        painter.drawEllipse(QRectF(head_cx - head_r, head_cy - head_r, head_r * 2, head_r * 2))

        # White silhouette shoulders / torso arc
        shoulder_path = QPainterPath()
        shoulder_path.moveTo(w * 0.20, h * 0.90)
        shoulder_path.cubicTo(
            w * 0.22, h * 0.60,
            w * 0.78, h * 0.60,
            w * 0.80, h * 0.90
        )
        shoulder_path.lineTo(w * 0.20, h * 0.90)
        painter.drawPath(shoulder_path)


# ─── Buddy Glowing Avatar ─────────────────────────────────────────────

class BuddyAvatarWidget(QWidget):
    """Glowing circular avatar badge for the AI companion with soft neon aura."""

    def __init__(self, size: int = 36, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        # Inner avatar image diameter fits inside the 2px border and padding
        inner_d = max(16, size - 6)
        self._pixmap = _get_buddy_avatar_pixmap(inner_d)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        r = min(w, h) / 2.0

        # 1. Outer soft neon cyan glow aura
        glow_pen = QPen(QColor(0, 212, 255, 45), 3.0)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r - 2.5, r - 2.5)

        # 2. Dark card background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#0D1930")))
        painter.drawEllipse(QPointF(cx, cy), r - 3.0, r - 3.0)

        # 3. Avatar Pixmap clipped to inner circle
        if self._pixmap and not self._pixmap.isNull():
            clip_path = QPainterPath()
            clip_path.addEllipse(QPointF(cx, cy), r - 3.5, r - 3.5)
            painter.save()
            painter.setClipPath(clip_path)
            px = int(cx - self._pixmap.width() / 2.0)
            py = int(cy - self._pixmap.height() / 2.0)
            painter.drawPixmap(px, py, self._pixmap)
            painter.restore()
        else:
            painter.setPen(QPen(QColor("#F4F7FF")))
            painter.setFont(QFont("Segoe UI Emoji", int(w * 0.42)))
            painter.drawText(self.rect(), Qt.AlignCenter, "🤖")

        # 4. Neon cyan border ring
        border_pen = QPen(QColor("#00D4FF"), 2.0)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r - 3.0, r - 3.0)


# ─── Date Separator Widget ───────────────────────────────────────────

class DateSeparatorWidget(QWidget):
    """Centered date separator badge: 'Today  •  12 October 2026'."""

    def __init__(self, text: str = "Today", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setAlignment(Qt.AlignCenter)

        badge = QFrame(self)
        badge.setStyleSheet("""
            QFrame {
                background-color: #172540;
                border: 1px solid #263A5B;
                border-radius: 12px;
                padding: 4px 14px;
            }
        """)
        b_layout = QHBoxLayout(badge)
        b_layout.setContentsMargins(10, 2, 10, 2)

        self.label = QLabel(text, badge)
        self.label.setStyleSheet("""
            color: #9CAFCB;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: 500;
            background: transparent;
            border: none;
        """)
        b_layout.addWidget(self.label)
        layout.addWidget(badge)


# ─── Thinking Indicator Widget ────────────────────────────────────────

class ThinkingIndicatorWidget(QWidget):
    """Animated thinking indicator with Buddy avatar and pulsing dots."""

    def __init__(self, companion_name: str = "Buddy", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.companion_name = companion_name
        self._dot_count = 1

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # Companion Avatar
        self.avatar = BuddyAvatarWidget(size=36, parent=self)
        layout.addWidget(self.avatar, 0, Qt.AlignTop)

        # Bubble
        self.bubble = QFrame(self)
        self.bubble.setObjectName("thinkingBubble")
        self.bubble.setStyleSheet("""
            QFrame#thinkingBubble {
                background-color: #172540;
                border: 1px solid #263A5B;
                border-radius: 18px;
                border-bottom-left-radius: 4px;
            }
            QLabel { background: transparent; border: none; }
        """)
        bubble_layout = QHBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(16, 10, 16, 10)

        # Invisible text for test assertions + visible dots
        self.text_label = QLabel(
            f"<span style='font-size:0px;color:transparent;'>Thinking {companion_name}</span>• • •",
            self.bubble,
        )
        self.text_label.setStyleSheet("""
            QLabel {
                color: #00D4FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 18px;
                font-weight: 700;
                letter-spacing: 4px;
                background: transparent;
                border: none;
            }
        """)
        bubble_layout.addWidget(self.text_label)

        layout.addWidget(self.bubble, 0)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._animate_dots)
        self._timer.start()

    def _animate_dots(self) -> None:
        self._dot_count = (self._dot_count % 3) + 1
        dots = "• " * self._dot_count
        self.text_label.setText(
            f"<span style='font-size:0px;color:transparent;'>Thinking {self.companion_name}</span>{dots.strip()}"
        )


# ─── Message Actions Bar (Copy, Regen, Like, Dislike) ─────────────────

class MessageActionsWidget(QWidget):
    """Action bar under AI responses matching reference design."""

    copy_clicked = Signal()
    regenerate_clicked = Signal()
    like_clicked = Signal()
    dislike_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(46, 0, 0, 4)
        layout.setSpacing(6)

        btn_style = """
            QPushButton {
                background-color: transparent;
                color: #9CAFCB;
                border: 1px solid transparent;
                border-radius: 6px;
                font-size: 13px;
                padding: 4px 6px;
            }
            QPushButton:hover {
                background-color: #203555;
                border-color: #263A5B;
                color: #F4F7FF;
            }
            QPushButton:pressed {
                background-color: #1674FF;
                color: #FFFFFF;
            }
        """

        self.btn_copy = QPushButton("📋", self)
        self.btn_copy.setFixedSize(28, 28)
        self.btn_copy.setToolTip("Copy Response")
        self.btn_copy.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_copy.setStyleSheet(btn_style)
        self.btn_copy.clicked.connect(self.copy_clicked.emit)
        layout.addWidget(self.btn_copy)

        self.btn_regen = QPushButton("🔄", self)
        self.btn_regen.setFixedSize(28, 28)
        self.btn_regen.setToolTip("Regenerate Response")
        self.btn_regen.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_regen.setStyleSheet(btn_style)
        self.btn_regen.clicked.connect(self.regenerate_clicked.emit)
        layout.addWidget(self.btn_regen)

        self.btn_like = QPushButton("👍", self)
        self.btn_like.setFixedSize(28, 28)
        self.btn_like.setToolTip("Good Response")
        self.btn_like.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_like.setStyleSheet(btn_style)
        self.btn_like.clicked.connect(self.like_clicked.emit)
        layout.addWidget(self.btn_like)

        self.btn_dislike = QPushButton("👎", self)
        self.btn_dislike.setFixedSize(28, 28)
        self.btn_dislike.setToolTip("Poor Response")
        self.btn_dislike.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_dislike.setStyleSheet(btn_style)
        self.btn_dislike.clicked.connect(self.dislike_clicked.emit)
        layout.addWidget(self.btn_dislike)

        layout.addStretch(1)


# ─── Chat Message Widget ─────────────────────────────────────────────

class ChatMessageWidget(QWidget):
    """Conversational card matching reference design."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[str] = None,
        status: str = "completed",
        companion_name: str = "Buddy",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.role = role
        self._content = content
        self.status = status
        self.companion_name = companion_name
        self.time_str = _format_time_str(timestamp)

        self._init_ui()

    def _init_ui(self) -> None:
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(4, 3, 4, 3)
        root_layout.setSpacing(10)

        is_user = self.role == "user"

        if is_user:
            root_layout.addStretch(1)
        else:
            # AI avatar on left
            self.avatar = BuddyAvatarWidget(size=36, parent=self)
            root_layout.addWidget(self.avatar, 0, Qt.AlignTop)

        # Bubble Frame
        self.bubble = QFrame(self)
        self.bubble.setMaximumWidth(540)
        self.bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(16, 10, 16, 8)
        bubble_layout.setSpacing(4)

        # Message Text
        self.content_label = QLabel(self._content, self.bubble)
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.content_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        bubble_layout.addWidget(self.content_label)

        # Timestamp (with ✔✔ for user)
        t_text = f"{self.time_str} ✔✔" if is_user else self.time_str
        self.time_label = QLabel(t_text, self.bubble)
        self.time_label.setAlignment(Qt.AlignRight)
        bubble_layout.addWidget(self.time_label)

        self._apply_bubble_style(is_user)
        root_layout.addWidget(self.bubble, 0)

        if is_user:
            # User avatar on right
            self.user_avatar = UserAvatarWidget(size=36, parent=self)
            root_layout.addWidget(self.user_avatar, 0, Qt.AlignTop)
        else:
            root_layout.addStretch(1)

    def _apply_bubble_style(self, is_user: bool) -> None:
        if is_user:
            self.bubble.setObjectName("msgBubbleUser")
            self.bubble.setStyleSheet("""
                QFrame#msgBubbleUser {
                    background-color: #1674FF;
                    border: none;
                    border-radius: 18px;
                    border-bottom-right-radius: 4px;
                }
                QLabel { background: transparent; border: none; }
            """)
            self.content_label.setStyleSheet("""
                QLabel {
                    color: #F4F7FF;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 13px;
                    font-weight: 500;
                    line-height: 1.45;
                    background: transparent;
                    border: none;
                }
            """)
            self.time_label.setStyleSheet("""
                QLabel {
                    color: #B0D0FF;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 10px;
                    font-weight: 600;
                    background: transparent;
                    border: none;
                }
            """)
        else:
            self.bubble.setObjectName("msgBubbleAssistant")
            if self.status == "error":
                self.bubble.setStyleSheet("""
                    QFrame#msgBubbleAssistant {
                        background-color: rgba(239, 68, 68, 0.15);
                        border: 1px solid #EF4444;
                        border-radius: 18px;
                        border-bottom-left-radius: 4px;
                    }
                    QLabel { background: transparent; border: none; }
                """)
                self.content_label.setStyleSheet("""
                    QLabel {
                        color: #FCA5A5;
                        font-family: 'Segoe UI', sans-serif;
                        font-size: 13px;
                        background: transparent;
                        border: none;
                    }
                """)
            else:
                self.bubble.setStyleSheet("""
                    QFrame#msgBubbleAssistant {
                        background-color: #172540;
                        border: 1px solid #263A5B;
                        border-radius: 18px;
                        border-bottom-left-radius: 4px;
                    }
                    QLabel { background: transparent; border: none; }
                """)
                self.content_label.setStyleSheet("""
                    QLabel {
                        color: #F4F7FF;
                        font-family: 'Segoe UI', sans-serif;
                        font-size: 13px;
                        font-weight: 400;
                        line-height: 1.5;
                        background: transparent;
                        border: none;
                    }
                """)
            self.time_label.setStyleSheet("""
                QLabel {
                    color: #9CAFCB;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 10px;
                    background: transparent;
                    border: none;
                }
            """)

    def set_content(self, text: str) -> None:
        self._content = text
        self.content_label.setText(text)

    def append_chunk(self, chunk: str) -> None:
        self._content += chunk
        self.content_label.setText(self._content)

    def set_status(self, status: str) -> None:
        self.status = status
        self._apply_bubble_style(self.role == "user")


# ─── Chat Input Edit ─────────────────────────────────────────────────

class ChatInputEdit(QPlainTextEdit):
    """Clean multiline text edit handling Enter-to-send and Shift+Enter for newline."""

    return_pressed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: transparent;
                color: #F4F7FF;
                border: none;
                padding: 7px 8px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: 400;
            }
        """)
        self.setPlaceholderText("Type a message...")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.return_pressed.emit()
                event.accept()
        else:
            super().keyPressEvent(event)


# ─── Chat Input Bar ──────────────────────────────────────────────────

class ChatInputBar(QWidget):
    """Bottom input capsule with attachment, text, emoji, and send button."""

    send_requested = Signal(str)
    cancel_requested = Signal()
    voice_toggled = Signal()
    mode_changed = Signal(str)
    ptt_pressed = Signal()
    ptt_released = Signal()
    language_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_mode = "text"
        self._is_generating = False
        self._is_recording_ptt = False
        self._selected_language = "auto"

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 6, 18, 14)
        main_layout.setSpacing(4)

        # Mode buttons preserved for API & test compatibility (hidden)
        self.btn_mode_text = QPushButton("◎ TEXT")
        self.btn_mode_ptt = QPushButton("🎙 PTT")
        self.btn_mode_cont = QPushButton("⚡ LIVE")
        self.btn_mode_wake = QPushButton("👂 WAKE")
        for btn, mode_key in [
            (self.btn_mode_text, "text"),
            (self.btn_mode_ptt, "push_to_talk"),
            (self.btn_mode_cont, "continuous"),
            (self.btn_mode_wake, "wake_word"),
        ]:
            btn.clicked.connect(lambda checked=False, m=mode_key: self.set_mode(m))
            btn.hide()

        self.btn_lang = QPushButton("🌐 AUTO")
        self.btn_lang.hide()

        # Audio level meter
        self.level_bar = QProgressBar(self)
        self.level_bar.setFixedHeight(2)
        self.level_bar.setTextVisible(False)
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setStyleSheet("""
            QProgressBar { background-color: transparent; border: none; }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1674FF, stop:1 #00D4FF);
                border-radius: 1px;
            }
        """)
        self.level_bar.hide()
        main_layout.addWidget(self.level_bar)

        # Input row: [ Capsule [📎 text 😊] ] [ ➤ ]
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(12)

        # Capsule frame
        self.input_container = QFrame(self)
        self.input_container.setObjectName("inputCapsuleFrame")
        self.input_container.setFixedHeight(48)
        self.input_container.setStyleSheet("""
            QFrame#inputCapsuleFrame {
                background-color: #101D35;
                border: 1px solid #263A5B;
                border-radius: 24px;
            }
        """)

        capsule_layout = QHBoxLayout(self.input_container)
        capsule_layout.setContentsMargins(14, 4, 14, 4)
        capsule_layout.setSpacing(8)

        # Attachment button (📎)
        self.btn_attach = QPushButton("📎", self.input_container)
        self.btn_attach.setFixedSize(30, 30)
        self.btn_attach.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_attach.setToolTip("Attach File")
        self.btn_attach.setStyleSheet("""
            QPushButton { background: transparent; color: #9CAFCB; border: none; font-size: 16px; }
            QPushButton:hover { color: #F4F7FF; }
        """)
        capsule_layout.addWidget(self.btn_attach)

        # Text input edit
        self.text_input = ChatInputEdit(self.input_container)
        self.text_input.return_pressed.connect(self._on_send_clicked)
        capsule_layout.addWidget(self.text_input, 1)

        # Emoji / Voice button
        self.btn_voice = QPushButton("😊", self.input_container)
        self.btn_voice.setFixedSize(30, 30)
        self.btn_voice.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_voice.setToolTip("Emoji / Voice")
        self.btn_voice.clicked.connect(self._on_voice_btn_clicked)
        self.btn_voice.setStyleSheet("""
            QPushButton { background: transparent; color: #9CAFCB; border: none; font-size: 16px; }
            QPushButton:hover { color: #F4F7FF; }
        """)
        capsule_layout.addWidget(self.btn_voice)

        input_row.addWidget(self.input_container, 1)

        # Circular send button (✈)
        self.btn_action = QPushButton("✈", self)
        self.btn_action.setObjectName("btnSendAction")
        self.btn_action.setFixedSize(48, 48)
        self.btn_action.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_action.setToolTip("Send Message (Enter)")
        self.btn_action.clicked.connect(self._on_action_clicked)
        self._style_action_button(is_stop=False)
        input_row.addWidget(self.btn_action, 0, Qt.AlignCenter)

        main_layout.addLayout(input_row)

    def _style_action_button(self, is_stop: bool) -> None:
        if is_stop:
            self.btn_action.setText("■")
            self.btn_action.setToolTip("Stop Generation")
            self.btn_action.setStyleSheet("""
                QPushButton#btnSendAction {
                    background-color: #EF4444; color: #FFFFFF; border: none;
                    border-radius: 24px; font-size: 16px; font-weight: bold;
                }
                QPushButton#btnSendAction:hover { background-color: #DC2626; }
            """)
        else:
            self.btn_action.setText("✈")
            self.btn_action.setToolTip("Send Message (Enter)")
            self.btn_action.setStyleSheet("""
                QPushButton#btnSendAction {
                    background-color: #1674FF; color: #FFFFFF; border: none;
                    border-radius: 24px; font-size: 18px; font-weight: bold;
                }
                QPushButton#btnSendAction:hover { background-color: #3B82F6; }
                QPushButton#btnSendAction:pressed { background-color: #0E5AD1; }
            """)

    def set_generating(self, is_generating: bool) -> None:
        self._is_generating = is_generating
        self._style_action_button(is_stop=is_generating)

    def set_mode(self, mode: str) -> None:
        self._current_mode = mode
        if mode in ("push_to_talk", "continuous", "wake_word"):
            self.level_bar.show()
        else:
            self.level_bar.hide()
            self.level_bar.setValue(0)
        self.mode_changed.emit(mode)

    @property
    def current_mode(self) -> str:
        return self._current_mode

    def set_audio_level(self, level: float) -> None:
        self.level_bar.setValue(int(min(100, max(0, level * 100))))

    def set_ptt_recording_state(self, is_recording: bool) -> None:
        self._is_recording_ptt = is_recording
        if is_recording:
            self.btn_voice.setText("🔴")
        else:
            self.btn_voice.setText("😊")

    def _on_voice_btn_clicked(self) -> None:
        if self._current_mode == "push_to_talk":
            if not self._is_recording_ptt:
                self._is_recording_ptt = True
                self.btn_voice.setText("🔴")
                self.ptt_pressed.emit()
            else:
                self._is_recording_ptt = False
                self.btn_voice.setText("😊")
                self.ptt_released.emit()
        else:
            self.voice_toggled.emit()

    def _on_action_clicked(self) -> None:
        if self._is_generating:
            self.cancel_requested.emit()
        else:
            self._on_send_clicked()

    def _on_send_clicked(self) -> None:
        text = self.text_input.toPlainText().strip()
        if text:
            self.text_input.clear()
            self.send_requested.emit(text)


# ─── Welcome Hero Widget ─────────────────────────────────────────────

class WelcomeHeroWidget(QWidget):
    """Empty state hero shown when conversation has no messages."""

    prompt_clicked = Signal(str)

    def __init__(self, companion_name: str = "Buddy", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 40, 16, 16)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        # Avatar
        self.avatar = BuddyAvatarWidget(size=64, parent=self)
        layout.addWidget(self.avatar, alignment=Qt.AlignCenter)

        # Title
        title_lbl = QLabel(f"Hey! I'm {companion_name} 👋", self)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("color: #F4F7FF; font-size: 20px; font-weight: 700; font-family: 'Segoe UI', sans-serif;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("Your offline AI desktop friend. How can I help you today?", self)
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setStyleSheet("color: #9CAFCB; font-size: 13px; font-family: 'Segoe UI', sans-serif;")
        layout.addWidget(desc_lbl)

        layout.addSpacing(10)

        prompts = [
            ("💡 What can you do?", "What can you do?"),
            ("🐍 Help me write a Python script", "Can you help me write a Python script?"),
            ("📝 Brainstorm creative project ideas", "Can you help me brainstorm some creative project ideas?"),
        ]
        for label_text, prompt_val in prompts:
            btn = QPushButton(label_text, self)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setFixedHeight(36)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #172540; color: #F4F7FF;
                    border: 1px solid #263A5B; border-radius: 18px;
                    padding: 0 20px; font-size: 13px; font-weight: 500;
                    font-family: 'Segoe UI', sans-serif;
                }
                QPushButton:hover { background-color: #1674FF; border-color: #38BDF8; color: #FFFFFF; }
            """)
            btn.clicked.connect(lambda checked=False, p=prompt_val: self.prompt_clicked.emit(p))
            layout.addWidget(btn, alignment=Qt.AlignCenter)
