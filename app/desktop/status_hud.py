"""JARVIS Live Status HUD Widget.

Displays real-time system telemetry (CPU, RAM) and AI subsystem states
(Voice, Core) in a futuristic holographic HUD data strip:
    CPU: [▓▓░░] 24%  •  RAM: [▓▓▓░] 58%  •  CORE: ONLINE  •  VOICE: READY
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from app.core.signals import signals
from app.desktop.holographic_effects import draw_corner_brackets, draw_scan_lines
from app.desktop.jarvis_theme import COLORS, qcolor
from app.utils.logger import get_logger

logger = get_logger(__name__)

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class StatusHUD(QWidget):
    """Futuristic holographic telemetry readout widget anchored near JARVIS orb."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._cpu_percent = 0.0
        self._ram_percent = 0.0
        self._core_status = "ONLINE"
        self._voice_status = "STANDBY"
        self._opacity_val = 0.0

        self._init_ui()
        self._init_timer()
        self._connect_signals()

    def _init_ui(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        # Telemetry Text Readout
        self.label_readout = QLabel(self)
        self.label_readout.setStyleSheet("""
            QLabel {
                color: #C8E8FF;
                font-family: 'Share Tech Mono', 'Rajdhani', monospace;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.8px;
            }
        """)
        layout.addWidget(self.label_readout)

        self.setLayout(layout)
        self.setFixedHeight(28)

        self._update_readout_text()

    def _init_timer(self) -> None:
        """Poll telemetry every 2.5 seconds."""
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2500)
        self._poll_timer.timeout.connect(self.update_telemetry)
        self._poll_timer.start()

        # Initial sample
        self.update_telemetry()

    def _connect_signals(self) -> None:
        """Listen to bus events to update subsystem statuses."""
        signals.character_state_changed.connect(self._on_character_state_changed)
        signals.voice_state_changed.connect(self._on_voice_state_changed)

    def _on_character_state_changed(self, state: str) -> None:
        state_map = {
            "idle": "ONLINE",
            "listening": "EARS ACTIVE",
            "thinking": "NEURAL SYNC",
            "speaking": "TRANSMITTING",
            "error": "OVERLOAD",
            "sleeping": "STANDBY",
            "dragging": "KINETIC WARP",
        }
        self._core_status = state_map.get(state.lower(), state.upper())
        self._update_readout_text()

    def _on_voice_state_changed(self, state: str) -> None:
        """Update live voice subsystem telemetry when voice state changes (Phase 8)."""
        state_map = {
            "sleeping": "STANDBY",
            "wake_word_detected": "WAKE ARMED",
            "listening": "LISTENING",
            "user_speaking": "RECEIVING",
            "processing": "PROCESSING",
            "generating_response": "GENERATING",
            "speaking": "TRANSMITTING",
            "interrupted": "INTERRUPTED",
            "muted": "MUTED",
            "microphone_unavailable": "NO MIC",
            "error": "ERROR",
            "idle": "READY",
        }
        self._voice_status = state_map.get(state.lower(), state.upper())
        self._update_readout_text()

    def set_voice_mode(self, mode: str) -> None:
        """Update displayed voice subsystem mode."""
        mode_map = {
            "text": "STANDBY",
            "push_to_talk": "PTT READY",
            "continuous": "LIVE COMMS",
            "wake_word": "WAKE ARMED",
        }
        self._voice_status = mode_map.get(mode, mode.upper())
        self._update_readout_text()

    def update_telemetry(self) -> None:
        """Sample system CPU and RAM usage."""
        if _HAS_PSUTIL:
            try:
                self._cpu_percent = psutil.cpu_percent(interval=None)
                self._ram_percent = psutil.virtual_memory().percent
            except Exception:
                pass
        self._update_readout_text()

    def _render_bar(self, percent: float, width_chars: int = 4) -> str:
        """Render a mini ASCII progress meter like [■■□□]."""
        filled = int(round((percent / 100.0) * width_chars))
        filled = max(0, min(width_chars, filled))
        return "■" * filled + "□" * (width_chars - filled)

    def _update_readout_text(self) -> None:
        cpu_bar = self._render_bar(self._cpu_percent, 4)
        ram_bar = self._render_bar(self._ram_percent, 4)

        text = (
            f"CPU: {cpu_bar} {int(self._cpu_percent)}%  │  "
            f"RAM: {ram_bar} {int(self._ram_percent)}%  │  "
            f"CORE: <font color='#00E5FF'>{self._core_status}</font>  │  "
            f"VOX: <font color='#00BFFF'>{self._voice_status}</font>"
        )
        self.label_readout.setText(text)
        self.adjustSize()

    # ─── Repositioning ─────────────────────────────────────────────────

    def reposition_near_pet(self, pet_rect: QRect) -> None:
        """Position HUD directly above the character orb."""
        hud_w = self.width()
        hud_h = self.height()

        target_x = pet_rect.center().x() - hud_w // 2
        target_y = pet_rect.top() - hud_h - 6

        # Multi-monitor bounds check
        screen = self.screen()
        if screen is None:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()

        if screen:
            screen_geo = screen.availableGeometry()
            if target_y < screen_geo.top():
                target_y = pet_rect.bottom() + 40
            if target_x < screen_geo.left():
                target_x = screen_geo.left() + 4
            elif target_x + hud_w > screen_geo.right():
                target_x = screen_geo.right() - hud_w - 4

        self.move(target_x, target_y)

    # ─── Paint Event (JARVIS HUD Backplate) ────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(1, 1, -1, -1)
        r_float = QRectF(rect)

        # 1. Dark tech background
        path = QPainterPath()
        path.addRoundedRect(r_float, 4.0, 4.0)
        painter.fillPath(path, QColor("#050A0F"))

        # 2. Scanlines
        draw_scan_lines(painter, r_float, spacing=3, opacity=0.04)

        # 3. Outer HUD border
        pen = QPen(qcolor("hud_border"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)

        # 4. Corner brackets
        draw_corner_brackets(
            painter, r_float, size=6, color=qcolor("arc_bright"), width=1, offset=1
        )

        painter.end()
        super().paintEvent(event)
