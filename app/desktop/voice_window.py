"""Voice Conversation Window — Apple Design Human Interface Aesthetic.

Provides a dedicated full voice conversation UI matching Apple HIG & Siri aesthetics:
- Frosted glass window with subtle hairline borders and deep ambient shadow.
- Clean header without clunky window controls, featuring a centered Apple Dynamic Island pill.
- Vector status indicator dot with soft glowing aura (NO emojis).
- Top-right minimal frosted close button.
- Siri-inspired iridescent aura portal with concentric acoustic rings and character sprite.
- Apple San Francisco typography and sleek real-time status display.
- Voice Memos / Siri-style organic multi-color rounded equalizer waveform.
- Frosted glass action dock with Apple SF vector icons (Mic, Stop, Settings) — zero text emojis.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.voice.voice_service import VoiceService

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from app.core.signals import signals
from app.desktop.apple_icons import create_button_icon
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_WIDTH = 420
DEFAULT_HEIGHT = 550

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ASSETS_DIR = _PROJECT_ROOT / "assets"
_AVATAR_PATH = _ASSETS_DIR / "icons" / "buddy_avatar.png"
_SPRITES_DIR = _ASSETS_DIR / "characters" / "robot"


class StatusIndicatorDot(QWidget):
    """Clean vector status indicator dot with soft glowing aura (no emojis)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._color = QColor(52, 199, 89)  # Apple System Green

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx = self.width() / 2.0
        cy = self.height() / 2.0

        # Outer soft glow aura
        glow = QColor(self._color)
        glow.setAlpha(60)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), 6.0, 6.0)

        # Center core dot
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(QPointF(cx, cy), 3.5, 3.5)


class VoicePortalWidget(QWidget):
    """Siri-inspired iridescent luminous portal with concentric acoustic rings and character."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(250, 250)
        self._pulse_phase = 0.0
        self._audio_level = 0.0
        self._current_state = "listening"
        self._sprite_pixmaps: dict[str, QPixmap] = {}
        self._load_sprites()

        # Smooth animation timer (~30 FPS)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_pulse_tick)
        self._timer.start()

    def _load_sprites(self) -> None:
        for state in ("idle", "listening", "thinking", "speaking", "happy", "sleeping"):
            p = _SPRITES_DIR / f"{state}.png"
            if p.exists():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    self._sprite_pixmaps[state] = pix

    def set_character_state(self, state: str) -> None:
        raw_state = state.lower()
        state_map = {
            "sleeping": "sleeping",
            "wake_word_detected": "listening",
            "listening": "listening",
            "user_speaking": "listening",
            "processing": "thinking",
            "transcribing": "thinking",
            "submitting_user_message": "thinking",
            "generating_response": "thinking",
            "thinking": "thinking",
            "speaking": "speaking",
            "interrupted": "listening",
            "muted": "idle",
            "microphone_unavailable": "idle",
            "mic_unavailable": "idle",
            "error": "idle",
            "idle": "idle",
            "ready": "idle",
        }
        self._current_state = state_map.get(raw_state, raw_state)
        self.update()

    def set_audio_level(self, level: float) -> None:
        self._audio_level = max(0.0, min(1.0, level))
        self.update()

    def _on_pulse_tick(self) -> None:
        self._pulse_phase += 0.05
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase -= 2 * math.pi
        self.update()

    def closeEvent(self, event) -> None:
        if hasattr(self, "_timer") and self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        base_r = min(cx, cy) - 22.0

        breathe = math.sin(self._pulse_phase) * 5.0
        reactive = self._audio_level * 18.0

        # 1. Siri-inspired Multi-layer Ambient Aura Glow
        glow_r = base_r + 25.0 + reactive * 0.5
        glow_grad = QRadialGradient(cx, cy, glow_r)
        glow_grad.setColorAt(0.0, QColor(30, 41, 59, 130))
        glow_grad.setColorAt(0.35, QColor(10, 132, 255, int(45 + self._audio_level * 40)))
        glow_grad.setColorAt(0.65, QColor(191, 90, 242, int(30 + self._audio_level * 35)))
        glow_grad.setColorAt(0.85, QColor(0, 229, 255, 15))
        glow_grad.setColorAt(1.0, QColor(20, 22, 27, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(glow_r), int(glow_r))

        # 2. Concentric Acoustic Waves (Apple sound wave resonance)
        ring_radii = [
            base_r + breathe + reactive,
            base_r * 0.84 + breathe * 0.65 + reactive * 0.65,
            base_r * 0.66 + breathe * 0.35 + reactive * 0.35,
        ]

        pens = [
            QPen(QColor(10, 132, 255, 80), 1.0, Qt.SolidLine),
            QPen(QColor(191, 90, 242, 110), 1.5, Qt.SolidLine),
            QPen(QColor(0, 229, 255, 140), 1.5, Qt.SolidLine),
        ]

        painter.setBrush(Qt.NoBrush)
        for r, pen in zip(ring_radii, pens):
            if r > 10:
                painter.setPen(pen)
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r))

        # 3. Soft Pedestal Floor Shadow under character
        shadow_w = int(base_r * 0.75)
        shadow_h = 12
        shadow_y = int(cy + base_r * 0.52)
        shadow_grad = QRadialGradient(cx, shadow_y + shadow_h / 2, shadow_w / 2)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 120))
        shadow_grad.setColorAt(0.6, QColor(0, 0, 0, 40))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(cx - shadow_w / 2), shadow_y, shadow_w, shadow_h)

        # 4. Buddy Character Sprite in Center
        pix = self._sprite_pixmaps.get(self._current_state) or self._sprite_pixmaps.get("idle")
        if pix and not pix.isNull():
            target_size = int(base_r * 1.12)
            scaled = pix.scaled(
                target_size,
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            float_y = int(math.sin(self._pulse_phase) * 4.0)
            x = int(cx - scaled.width() / 2.0)
            y = int(cy - scaled.height() / 2.0 + float_y - 4)
            painter.drawPixmap(x, y, scaled)


class AudioWaveformWidget(QWidget):
    """Apple Voice Memos / Siri style organic multi-color rounded equalizer waveform."""

    SILENCE_THRESHOLD = 0.02
    RESTING_BAR_HEIGHT = 5.0

    def __init__(self, bar_count: int = 28, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.bar_count = bar_count
        self.setFixedHeight(38)
        self._level = 0.0
        self._anim_phase = 0.0
        self._mode = "listening"  # "listening" | "speaking"

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # 30 FPS
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def set_level(self, level: float) -> None:
        """Set current audio level normalized to [0.0, 1.0]."""
        lvl = max(0.0, min(1.0, float(level)))
        if lvl <= self.SILENCE_THRESHOLD:
            self._level = 0.0
        else:
            self._level = lvl
        self.update()

    def set_mode(self, mode: str) -> None:
        """Set waveform visual mode: 'listening' (cyan/blue) or 'speaking' (purple/violet)."""
        if mode in ("speaking", "listening"):
            self._mode = mode
            self.update()

    @property
    def mode(self) -> str:
        return self._mode

    def _on_tick(self) -> None:
        if self._level > self.SILENCE_THRESHOLD:
            self._anim_phase += 0.12
            if self._anim_phase > 2 * math.pi:
                self._anim_phase -= 2 * math.pi
            self.update()
        elif self._anim_phase != 0.0:
            self._anim_phase = 0.0
            self.update()

    def closeEvent(self, event) -> None:
        if hasattr(self, "_timer") and self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        gap = 4.0
        total_gaps = (self.bar_count - 1) * gap
        bar_w = max(3.0, (w - 40 - total_gaps) / self.bar_count)
        start_x = (w - (self.bar_count * bar_w + total_gaps)) / 2.0
        cy = h / 2.0

        is_silent = self._level <= self.SILENCE_THRESHOLD

        for i in range(self.bar_count):
            x = start_x + i * (bar_w + gap)

            if is_silent:
                # Stable flat baseline pills during silence (Requirement 8.2)
                bar_h = self.RESTING_BAR_HEIGHT
            else:
                # Gaussian bell curve envelope
                dist_from_center = abs(i - self.bar_count / 2.0) / (self.bar_count / 2.0)
                envelope = math.cos(dist_from_center * math.pi / 2.0) ** 1.3

                # Harmonic sinusoidal oscillation scaled strictly by actual audio intensity
                norm_level = (self._level - self.SILENCE_THRESHOLD) / (1.0 - self.SILENCE_THRESHOLD)
                osc1 = math.sin(self._anim_phase + i * 0.32) * 0.5 + 0.5
                osc2 = math.cos(self._anim_phase * 1.5 - i * 0.22) * 0.3 + 0.3
                osc = (osc1 + osc2) * 0.5 * 0.16 * norm_level

                height_ratio = 0.14 + (norm_level * 0.76 + osc) * envelope
                bar_h = max(self.RESTING_BAR_HEIGHT, min(h - 4.0, height_ratio * (h - 4.0)))

            y = cy - bar_h / 2.0
            r = bar_w / 2.0

            if self._mode == "speaking":
                # Apple Purple / Violet Siri gradient during assistant speaking (Requirement 8.3)
                grad = QLinearGradient(x, y, x, y + bar_h)
                grad.setColorAt(0.0, QColor(191, 90, 242, 230))  # Apple System Purple
                grad.setColorAt(0.5, QColor(94, 92, 230, 220))   # Apple Indigo
                grad.setColorAt(1.0, QColor(255, 55, 95, 210))   # Apple System Pink
            else:
                # Apple Luminous Cyan / System Blue gradient during listening & user speech (Requirement 8.2)
                grad = QLinearGradient(x, y, x, y + bar_h)
                grad.setColorAt(0.0, QColor(0, 229, 255, 230))   # Luminous Cyan
                grad.setColorAt(0.5, QColor(10, 132, 255, 220))  # Apple System Blue
                grad.setColorAt(1.0, QColor(52, 199, 89, 210))   # Apple System Green

            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), r, r)


class VoiceWindow(QWidget):
    """Dedicated Apple-designed voice interface matching Apple HIG & macOS Sonoma."""

    def __init__(
        self,
        config_manager: ConfigManager,
        voice_service: Optional[VoiceService] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.voice_service = voice_service

        self._is_drag_active = False
        self._drag_pos = QPoint()
        self._is_muted = False
        self._current_state = "idle"

        self._init_window()
        self._init_ui()
        self._connect_signals()

    def _init_window(self) -> None:
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self.setMinimumSize(360, 480)

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(14, 14, 14, 14)

        # Apple Frosted Glass Container
        self.bg_frame = QFrame(self)
        self.bg_frame.setObjectName("voiceBgFrame")
        self.bg_frame.setStyleSheet("""
            QFrame#voiceBgFrame {
                background-color: #14161B;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 24px;
            }
        """)

        # Apple Soft Deep Diffused Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.bg_frame.setGraphicsEffect(shadow)

        frame_layout = QVBoxLayout(self.bg_frame)
        frame_layout.setContentsMargins(0, 0, 0, 22)
        frame_layout.setSpacing(10)

        # 1. Clean Apple Window Header (No left traffic lights, centered Dynamic Island, right close)
        self._init_header(frame_layout)

        # 2. Glowing Portal with Character
        self.portal = VoicePortalWidget(self.bg_frame)
        frame_layout.addWidget(self.portal, 1, alignment=Qt.AlignCenter)

        # 3. Status text ("Ready to talk", "I'm listening...")
        self.status_label = QLabel("Ready to talk", self.bg_frame)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 18px;
                font-weight: 600;
                letter-spacing: -0.3px;
                background: transparent;
            }
        """)
        frame_layout.addWidget(self.status_label)

        # Subtitle hint
        self.hint_label = QLabel("Tap microphone or speak naturally", self.bg_frame)
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet("""
            QLabel {
                color: #8E8E93;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 400;
                background: transparent;
                margin-top: -4px;
                margin-bottom: 4px;
            }
        """)
        frame_layout.addWidget(self.hint_label)

        # 4. Animated Audio Waveform
        self.waveform = AudioWaveformWidget(bar_count=28, parent=self.bg_frame)
        frame_layout.addWidget(self.waveform)

        # 5. Bottom Controls (Mute, Stop, Settings) using Apple Vector Icons (NO EMOJIS)
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(20, 12, 20, 0)
        controls_layout.setSpacing(24)
        controls_layout.setAlignment(Qt.AlignCenter)

        # Mute button (48x48 circular frosted glass with vector mic icon)
        self.btn_mute = QPushButton(self.bg_frame)
        self.btn_mute.setFixedSize(48, 48)
        self.btn_mute.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_mute.setToolTip("Mute Microphone")
        self.btn_mute.setIcon(create_button_icon("mic", size=22, color=QColor(245, 245, 247)))
        self.btn_mute.setIconSize(QSize(22, 22))
        self.btn_mute.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 24px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
                border-color: rgba(255, 255, 255, 0.25);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.22);
            }
        """)
        self.btn_mute.clicked.connect(self._toggle_mute)
        controls_layout.addWidget(self.btn_mute)

        # Stop button (56x56 circular Apple Red with vector rounded stop square)
        self.btn_stop = QPushButton(self.bg_frame)
        self.btn_stop.setFixedSize(56, 56)
        self.btn_stop.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_stop.setToolTip("Stop Voice Interaction")
        self.btn_stop.setIcon(create_button_icon("stop", size=20, color=QColor(255, 255, 255)))
        self.btn_stop.setIconSize(QSize(20, 20))
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF453A, stop:1 #D70015);
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 28px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF5F56, stop:1 #E0443E);
            }
            QPushButton:pressed {
                background: #B91C1C;
            }
        """)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        controls_layout.addWidget(self.btn_stop)

        # Settings button (48x48 circular frosted glass with vector gear icon)
        self.btn_settings = QPushButton(self.bg_frame)
        self.btn_settings.setFixedSize(48, 48)
        self.btn_settings.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_settings.setToolTip("Open Settings")
        self.btn_settings.setIcon(create_button_icon("gear", size=22, color=QColor(200, 200, 205)))
        self.btn_settings.setIconSize(QSize(22, 22))
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 24px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
                border-color: rgba(255, 255, 255, 0.25);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.22);
            }
        """)
        self.btn_settings.clicked.connect(signals.open_settings_requested.emit)
        controls_layout.addWidget(self.btn_settings)

        frame_layout.addLayout(controls_layout)
        outer_layout.addWidget(self.bg_frame)

    def _init_header(self, parent_layout: QVBoxLayout) -> None:
        """Header with NO left 3 options, centered Apple Dynamic Island, and right subtle close button."""
        self.header_frame = QFrame(self.bg_frame)
        self.header_frame.setFixedHeight(48)
        self.header_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.02);
                border-top-left-radius: 24px;
                border-top-right-radius: 24px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)

        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(16, 0, 14, 0)
        header_layout.setSpacing(0)

        # Left spacer to keep center pill perfectly centered (balancing right close button)
        left_balance_spacer = QWidget(self.header_frame)
        left_balance_spacer.setFixedSize(32, 32)
        left_balance_spacer.setStyleSheet("background: transparent; border: none;")
        header_layout.addWidget(left_balance_spacer)

        header_layout.addStretch(1)

        # Dynamic Island Center Capsule
        island_pill = QFrame(self.header_frame)
        island_pill.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 14px;
            }
        """)
        pill_layout = QHBoxLayout(island_pill)
        pill_layout.setContentsMargins(10, 4, 12, 4)
        pill_layout.setSpacing(8)

        # Avatar Thumbnail
        avatar_lbl = QLabel(island_pill)
        avatar_lbl.setFixedSize(18, 18)
        avatar_lbl.setStyleSheet("background: transparent; border: none;")
        if _AVATAR_PATH.exists():
            pix = QPixmap(str(_AVATAR_PATH)).scaled(
                18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            avatar_lbl.setPixmap(pix)
        else:
            # Vector fallback icon
            avatar_lbl.setPixmap(create_button_icon("character", size=18, color=QColor(0, 229, 255)).pixmap(18, 18))
        pill_layout.addWidget(avatar_lbl)

        # Vector Glowing Status Dot (NO EMOJIS)
        self.status_dot = StatusIndicatorDot(island_pill)
        pill_layout.addWidget(self.status_dot)

        # Dynamic Title text (Pure text, NO EMOJIS)
        companion_name = self.config_manager.get("ai.companion_name", "Buddy")
        self.title_label = QLabel(f"{companion_name}  •  Voice Mode", island_pill)
        self.title_label.setStyleSheet("""
            QLabel {
                color: #F5F5F7;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: -0.1px;
                background: transparent;
                border: none;
            }
        """)
        pill_layout.addWidget(self.title_label)
        header_layout.addWidget(island_pill)

        header_layout.addStretch(1)

        # Right subtle Apple circular close button (No left 3 dots)
        self.btn_close = QPushButton(self.header_frame)
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.setToolTip("Close")
        self.btn_close.setIcon(create_button_icon("close", size=14, color=QColor(161, 161, 166)))
        self.btn_close.setIconSize(QSize(14, 14))
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
                border-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.btn_close.clicked.connect(self.hide)
        header_layout.addWidget(self.btn_close)

        parent_layout.addWidget(self.header_frame)

    def _connect_signals(self) -> None:
        signals.close_voice_window_requested.connect(self.hide_window)
        signals.voice_state_changed.connect(self.set_state)
        signals.character_state_changed.connect(self._on_character_state_changed)
        signals.ai_speech_finished.connect(self._on_speaking_finished)
        if self.config_manager:
            self.config_manager.setting_changed.connect(self._on_setting_changed)

        if self.voice_service:
            self.voice_service.speech_detected.connect(lambda: self.set_state("listening"))
            self.voice_service.transcription_started.connect(lambda: self.set_state("processing"))
            self.voice_service.speaking_started.connect(lambda: self.set_state("speaking"))
            self.voice_service.speaking_finished.connect(self._on_speaking_finished)
            self.voice_service.audio_level.connect(self._on_mic_audio_level)
            if hasattr(self.voice_service, "audio_player") and self.voice_service.audio_player:
                self.voice_service.audio_player.amplitude_updated.connect(self._on_playback_amplitude)
                self.voice_service.audio_player.playback_stopped.connect(self._on_speaking_finished)
            if hasattr(self.voice_service, "conversation_controller") and self.voice_service.conversation_controller:
                try:
                    self.voice_service.conversation_controller.state_changed.connect(
                        lambda st: self.set_state(st.value if hasattr(st, "value") else str(st))
                    )
                except Exception:
                    pass

    @Slot(str)
    def _on_character_state_changed(self, char_state: str) -> None:
        """Synchronize portal character state if currently in idle/ready mode."""
        if self._current_state in ("idle", "ready"):
            self.portal.set_character_state(char_state)

    @Slot(str, object)
    def _on_setting_changed(self, key: str, val: Any) -> None:
        if key in ("ai.companion_name", "companion.name"):
            name = str(val).strip() if val else "Buddy"
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.set_state(self._current_state))

    @Slot(str)
    def set_state(self, state: str) -> None:
        """Display visual status for all 11 required voice states (Phase 8.1 - 8.5)."""
        self._current_state = state.lower()
        self.portal.set_character_state(self._current_state)

        companion_name = self.config_manager.get("ai.companion_name", "Buddy") if self.config_manager else "Buddy"

        # Update waveform mode (listening vs assistant speaking)
        if self._current_state in ("speaking", "ai_speaking"):
            self.waveform.set_mode("speaking")
        else:
            self.waveform.set_mode("listening")

        # 1. Sleeping State
        if self._current_state in ("sleeping", "wake_word_standby", "sleep"):
            self.status_label.setText("Asleep")
            self.hint_label.setText("Say wake word or tap to wake")
            self.title_label.setText(f"{companion_name}  •  Asleep")
            self.status_dot.set_color(QColor(142, 142, 147))  # Apple System Gray
            self.waveform.set_level(0.0)

        # 2. Wake-word detected
        elif self._current_state in ("wake_word_detected", "wake_detected"):
            self.status_label.setText("Wake Word Detected")
            self.hint_label.setText("Listening for your command...")
            self.title_label.setText(f"{companion_name}  •  Wake Word")
            self.status_dot.set_color(QColor(164, 198, 57))  # Apple Lime/Yellow-Green

        # 3. Listening State
        elif self._current_state == "listening":
            self.status_label.setText("I'm Listening...")
            self.hint_label.setText("Speak clearly into your microphone")
            self.title_label.setText(f"{companion_name}  •  Listening")
            self.status_dot.set_color(QColor(52, 199, 89))  # Apple System Green

        # 4. User Speaking State
        elif self._current_state == "user_speaking":
            self.status_label.setText("User Speaking")
            self.hint_label.setText("Capturing voice input...")
            self.title_label.setText(f"{companion_name}  •  User Speaking")
            self.status_dot.set_color(QColor(0, 229, 255))  # Apple Luminous Cyan

        # 5. Processing State (STT decoding / transcription)
        elif self._current_state in ("processing", "transcribing", "submitting_user_message"):
            self.status_label.setText("Processing...")
            self.hint_label.setText("Analyzing your speech...")
            self.title_label.setText(f"{companion_name}  •  Processing")
            self.status_dot.set_color(QColor(10, 132, 255))  # Apple System Blue
            self.waveform.set_level(0.0)

        # 6. Generating Response State (LLM generation)
        elif self._current_state in ("generating_response", "thinking", "ai_thinking"):
            self.status_label.setText("Generating Response...")
            self.hint_label.setText("Formulating answer...")
            self.title_label.setText(f"{companion_name}  •  Generating")
            self.status_dot.set_color(QColor(255, 159, 10))  # Apple System Orange
            self.waveform.set_level(0.0)

        # 7. Speaking State (Assistant TTS Audio Playback)
        elif self._current_state in ("speaking", "ai_speaking"):
            self.status_label.setText("Speaking...")
            self.hint_label.setText(f"{companion_name} is responding")
            self.title_label.setText(f"{companion_name}  •  Speaking")
            self.status_dot.set_color(QColor(191, 90, 242))  # Apple System Purple

        # 8. Interrupted State (User Barge-in Detected)
        elif self._current_state in ("interrupted", "barge_in"):
            self.status_label.setText("Interrupted")
            self.hint_label.setText("Stopping playback...")
            self.title_label.setText(f"{companion_name}  •  Interrupted")
            self.status_dot.set_color(QColor(255, 149, 0))  # Apple System Amber
            self.waveform.set_level(0.0)

        # 9. Muted State
        elif self._current_state in ("muted", "mute"):
            self.status_label.setText("Microphone Muted")
            self.hint_label.setText("Tap microphone to unmute")
            self.title_label.setText(f"{companion_name}  •  Muted")
            self.status_dot.set_color(QColor(255, 69, 58))  # Apple System Red
            self.waveform.set_level(0.0)

        # 10. Microphone Unavailable State
        elif self._current_state in ("microphone_unavailable", "mic_unavailable", "no_mic"):
            self.status_label.setText("Microphone Unavailable")
            self.hint_label.setText("Check audio input hardware")
            self.title_label.setText(f"{companion_name}  •  Mic Unavailable")
            self.status_dot.set_color(QColor(255, 59, 48))  # Apple Warning Red
            self.waveform.set_level(0.0)

        # 11. Error State
        elif self._current_state in ("error",):
            self.status_label.setText("Voice Error")
            self.hint_label.setText("An issue occurred during voice processing")
            self.title_label.setText(f"{companion_name}  •  Error")
            self.status_dot.set_color(QColor(215, 0, 21))  # Apple Deep Red
            self.waveform.set_level(0.0)

        # Fallback / Ready State
        else:
            self.status_label.setText("Ready to talk")
            self.hint_label.setText("Tap microphone or speak naturally")
            self.title_label.setText(f"{companion_name}  •  Ready")
            self.status_dot.set_color(QColor(52, 199, 89))  # Apple System Green

    @Slot(float)
    def _on_mic_audio_level(self, level: float) -> None:
        """Handle incoming microphone audio RMS level (Phase 8.2)."""
        if self._current_state in ("listening", "user_speaking", "ready", "idle"):
            self.portal.set_audio_level(level)
            self.waveform.set_level(level)

    @Slot(float)
    def _on_playback_amplitude(self, amplitude: float) -> None:
        """Handle real-time speech playback amplitude from AudioPlayer (Phase 8.3)."""
        if self._current_state in ("speaking", "ai_speaking"):
            self.portal.set_audio_level(amplitude)
            self.waveform.set_level(amplitude)

    @Slot()
    def _on_speaking_finished(self) -> None:
        """Immediately stop speaking animation when playback finishes or stops (Phase 8.3)."""
        self.waveform.set_level(0.0)
        self.portal.set_audio_level(0.0)
        if self._current_state in ("speaking", "ai_speaking"):
            self.set_state("listening")

    def _toggle_mute(self) -> None:
        """Toggle microphone mute with dedicated visual indicators and input suppression (Phase 8.4)."""
        self._is_muted = not self._is_muted
        if self.voice_service and hasattr(self.voice_service, "set_muted"):
            self.voice_service.set_muted(self._is_muted)
        if self._is_muted:
            self.btn_mute.setIcon(create_button_icon("mic_muted", size=22, color=QColor(255, 69, 58)))
            self.btn_mute.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 69, 58, 0.22);
                    border: 1px solid #FF453A;
                    border-radius: 24px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 69, 58, 0.32);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 69, 58, 0.42);
                }
            """)
            self.set_state("muted")
            signals.voice_state_changed.emit("muted")
        else:
            self.btn_mute.setIcon(create_button_icon("mic", size=22, color=QColor(245, 245, 247)))
            self.btn_mute.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    border-radius: 24px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.16);
                    border-color: rgba(255, 255, 255, 0.25);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.22);
                }
            """)
            self.set_state("listening")
            signals.voice_state_changed.emit("listening")

    def _on_stop_clicked(self) -> None:
        """Halt active playback and cancel current inference turn without disabling voice mode."""
        if self.voice_service and hasattr(self.voice_service, "audio_player"):
            try:
                self.voice_service.audio_player.stop()
            except Exception:
                pass
        if self.voice_service and hasattr(self.voice_service, "stop_speaking"):
            try:
                self.voice_service.stop_speaking()
            except Exception:
                pass
        signals.ai_cancel_requested.emit()
        self.waveform.set_level(0.0)
        self.portal.set_audio_level(0.0)
        self.set_state("listening")

    def show_window(self) -> None:
        """Show and bring the voice window to front."""
        if self.isMinimized():
            self.showNormal()

        # Bounds safety check before presenting: ensure window is within screen boundaries
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            curr_x = self.x()
            curr_y = self.y()
            min_x = geo.left() + 10
            max_x = max(min_x, geo.right() - self.width() - 10)
            min_y = geo.top() + 10
            max_y = max(min_y, geo.bottom() - self.height() - 10)
            if curr_x < min_x or curr_x > max_x or curr_y < min_y or curr_y > max_y:
                self.move(
                    max(min_x, min(curr_x, max_x)),
                    max(min_y, min(curr_y, max_y))
                )

        self.show()
        self.raise_()
        self.activateWindow()

    def hide_window(self) -> None:
        """Hide the voice window."""
        self.hide()

    def toggle_window(self) -> None:
        """Toggle voice window visibility."""
        if self.isVisible():
            self.hide_window()
        else:
            self.show_window()

    def position_near_pet(self, pet_rect: QRect) -> None:
        """Position the voice window intelligently relative to the floating pet, ensuring 100% on-screen visibility."""
        screen = QApplication.screenAt(pet_rect.center())
        if not screen:
            screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        win_w = self.width()
        win_h = self.height()

        # Available clearance on both horizontal sides of pet
        space_left = pet_rect.left() - geo.left()
        space_right = geo.right() - pet_rect.right()
        margin = 16

        # Prefer side with adequate clearance; fall back to side with larger space
        if space_left >= win_w + margin:
            target_x = pet_rect.left() - win_w - margin
        elif space_right >= win_w + margin:
            target_x = pet_rect.right() + margin
        else:
            if space_left >= space_right:
                target_x = pet_rect.left() - win_w - margin
            else:
                target_x = pet_rect.right() + margin

        # Align vertically with pet, keeping within vertical bounds
        target_y = pet_rect.top()
        if target_y + win_h > geo.bottom() - 10:
            target_y = pet_rect.bottom() - win_h
            if target_y < geo.top() + 10:
                target_y = geo.bottom() - win_h - 10

        # Absolute screen bounds clamping (guarantees the window is NEVER pushed off-screen)
        min_x = geo.left() + 10
        max_x = max(min_x, geo.right() - win_w - 10)
        clamped_x = max(min_x, min(target_x, max_x))

        min_y = geo.top() + 10
        max_y = max(min_y, geo.bottom() - win_h - 10)
        clamped_y = max(min_y, min(target_y, max_y))

        self.move(clamped_x, clamped_y)

    # Draggable Header
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            if self.header_frame.geometry().contains(event.position().toPoint()):
                self._is_drag_active = True
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_drag_active and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._is_drag_active = False
        super().mouseReleaseEvent(event)

    def closeEvent(self, event) -> None:
        if hasattr(self, "waveform") and hasattr(self.waveform, "close"):
            self.waveform.close()
        if hasattr(self, "portal") and hasattr(self.portal, "close"):
            self.portal.close()
        super().closeEvent(event)
