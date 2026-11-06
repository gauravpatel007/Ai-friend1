"""Floating Speech Bubble Overlay anchored near the desktop pet.

Matches the cartoon speech bubbles in the Showcase UI:
- "Hey! 👋 I'm your AI Friend!"
- "Need anything?"
- "I'm listening..."
- "Hmm..."
- "Let me tell you..."
- "That's awesome!"
- "Z z z ..."
"""

from __future__ import annotations

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
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.desktop.jarvis_theme import COLORS


class SpeechBubbleWidget(QWidget):
    """Floating cartoon speech bubble positioned above Buddy with real-time speech display."""

    MAX_BUBBLE_WIDTH = 340
    MIN_BUBBLE_WIDTH = 140

    def __init__(self, parent: Optional[QWidget] = None, companion_name: str = "Bond") -> None:
        super().__init__(parent)
        self._opacity = 0.0
        self._text = ""
        self._target_visible = False
        self._pet_rect: Optional[QRect] = None
        self._is_showing_user_speech = False
        self._is_showing_ai_subtitle = False
        self._companion_name = companion_name
        self._pointer_direction = "bottom"
        self._pointer_x = 70.0

        self._init_ui()
        self._init_animation()

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide_bubble)

    def set_companion_name(self, name: str) -> None:
        """Update companion name reference for subtitle badges."""
        if name and name.strip():
            self._companion_name = name.strip()

    @property
    def is_showing_user_speech(self) -> bool:
        return self._is_showing_user_speech and self.isVisible()

    @property
    def is_showing_ai_subtitle(self) -> bool:
        return self._is_showing_ai_subtitle and self.isVisible()

    @property
    def is_holding_for_dismiss(self) -> bool:
        """Return True if bubble is visible and currently counting down to dismiss."""
        return self.isVisible() and self._target_visible and self._dismiss_timer.isActive()

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

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 8, 14, 16)  # extra bottom margin for triangle pointer

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', 'Rajdhani', sans-serif;
                font-size: 13px;
                font-weight: 600;
                line-height: 1.35;
                background: transparent;
            }
        """)
        self.layout.addWidget(self.label)

    def _init_animation(self) -> None:
        self._anim = QPropertyAnimation(self, b"bubble_opacity", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, val: float) -> None:
        self._opacity = val
        self.setWindowOpacity(val)
        if val <= 0.01 and not self._target_visible:
            self.hide()

    bubble_opacity = Property(float, _get_opacity, _set_opacity)

    def _compute_bubble_size(self, text: str, is_interim: bool = False) -> tuple[int, int]:
        """Compute ideal width and height for text content with bounded wrapping."""
        import re
        fm = self.label.fontMetrics()
        avail_w = self.MAX_BUBBLE_WIDTH - 28
        plain = re.sub(r'<[^>]+>', '', text).strip()
        if not plain:
            plain = "..."
        bounding = fm.boundingRect(QRect(0, 0, avail_w, 2000), Qt.TextWordWrap | Qt.AlignCenter, plain)
        ideal_w = max(self.MIN_BUBBLE_WIDTH, min(self.MAX_BUBBLE_WIDTH, bounding.width() + 32))
        ideal_h = max(56, bounding.height() + 28)
        if is_interim and self.isVisible() and getattr(self, "_is_showing_user_speech", False):
            ideal_w = max(self.width(), ideal_w)
        return ideal_w, ideal_h

    def show_message(self, text: str, pet_rect: QRect, duration_ms: int = 4000, avoid_rect: Optional[QRect] = None) -> None:
        """Display bubble with text positioned directly above/below pet."""
        self._is_showing_user_speech = False
        self._is_showing_ai_subtitle = False
        self._text = text
        self._pet_rect = pet_rect
        self.label.setText(text)

        w, h = self._compute_bubble_size(text)
        self.setFixedSize(w, h)
        self._reposition(pet_rect, avoid_rect=avoid_rect)
        self._target_visible = True
        self.show()

        self._anim.stop()
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(1.0)
        self._anim.start()

        if duration_ms > 0:
            self._dismiss_timer.start(duration_ms)
        else:
            self._dismiss_timer.stop()

    def show_user_speech(
        self, text: str, pet_rect: QRect, is_interim: bool = True, avoid_rect: Optional[QRect] = None
    ) -> None:
        """Display progressive real-time recognized user speech word-by-word with live interim feedback."""
        import html
        self._is_showing_user_speech = True
        self._is_showing_ai_subtitle = False
        self._text = text
        self._pet_rect = pet_rect

        clean_text = text.strip()
        badge = "<span style='color: #00E5FF; font-weight: 700;'>🎙️ You: </span>"
        if is_interim:
            if clean_text:
                escaped = html.escape(clean_text)
                content_html = f"<span style='color: #F1F5F9; font-weight: 600;'>{escaped}</span><span style='color: #00E5FF; font-weight: 700;'>...</span>"
            else:
                content_html = "<span style='color: #94A3B8; font-style: italic;'>Listening...</span>"
            display_html = f"{badge}{content_html}"
            self.label.setText(display_html)
            self._dismiss_timer.stop()  # Do not dismiss while user is actively speaking
        else:
            escaped = html.escape(clean_text)
            display_html = f"{badge}<span style='color: #FFFFFF; font-weight: 600;'>{escaped}</span>"
            self.label.setText(display_html)
            self._dismiss_timer.start(1400)  # Hold briefly before fading or being replaced by answer

        w, h = self._compute_bubble_size(clean_text, is_interim=is_interim)
        self.setFixedSize(w, h)
        self._reposition(pet_rect, avoid_rect=avoid_rect)

        if not self._target_visible or self._opacity < 0.95:
            self._target_visible = True
            self.show()
            self._anim.stop()
            self._anim.setStartValue(self._opacity)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self.update()

    def show_ai_subtitle(
        self, text: str, pet_rect: QRect, avoid_rect: Optional[QRect] = None, companion_name: Optional[str] = None
    ) -> None:
        """Display synchronized sentence subtitle while AI companion is actively speaking aloud."""
        import html
        self._is_showing_user_speech = False
        self._is_showing_ai_subtitle = True
        self._text = text
        self._pet_rect = pet_rect

        clean_text = text.strip()
        if not clean_text:
            return

        name = companion_name or self._companion_name or "Bond"
        escaped = html.escape(clean_text)
        badge = f"<span style='color: #30D158; font-weight: 700;'>🔊 {name}: </span>"
        display_html = f"{badge}<span style='color: #F8FAFC; font-weight: 600;'>{escaped}</span>"
        self.label.setText(display_html)

        # Do NOT auto-dismiss while audio playback is actively ongoing
        self._dismiss_timer.stop()

        w, h = self._compute_bubble_size(clean_text)
        self.setFixedSize(w, h)
        self._reposition(pet_rect, avoid_rect=avoid_rect)

        if not self._target_visible or self._opacity < 0.95:
            self._target_visible = True
            self.show()
            self._anim.stop()
            self._anim.setStartValue(self._opacity)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self.update()

    def on_ai_speech_finished(self, hold_ms: int = 1200) -> None:
        """Handle completion of all AI speech chunks with clean reading hold timer."""
        self._is_showing_ai_subtitle = False
        if hold_ms > 0 and self.isVisible() and self._target_visible:
            self._dismiss_timer.start(hold_ms)
        else:
            self.hide_bubble()

    def clear_subtitles(self) -> None:
        """Immediately abort, hide, and clear subtitles without delay on completion or interruption."""
        self._is_showing_ai_subtitle = False
        self._is_showing_user_speech = False
        self._target_visible = False
        self._dismiss_timer.stop()
        self._anim.stop()
        self._opacity = 0.0
        self.setWindowOpacity(0.0)
        self.hide()

    def hide_bubble(self) -> None:
        """Fade out speech bubble."""
        self._is_showing_user_speech = False
        self._is_showing_ai_subtitle = False
        self._target_visible = False
        self._dismiss_timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _reposition(self, pet_rect: QRect, avoid_rect: Optional[QRect] = None) -> None:
        """Smart positioning that avoids screen edges and active conversation windows."""
        w = self.width()
        h = self.height()

        screen = (
            QApplication.screenAt(pet_rect.center())
            or QApplication.screenAt(pet_rect.topLeft())
            or self.screen()
            or QApplication.primaryScreen()
        )
        if not screen:
            return

        s_geo = screen.availableGeometry()

        # Candidates: (candidate_x, candidate_y, pointer_direction, preference_rank)
        # preference_rank: lower is better (0=above center, 1=above shifted, 2=below center, 3=below shifted, 4=right, 5=left)
        candidates = []

        above_y = pet_rect.top() - h - 8
        above_cx = pet_rect.center().x() - (w // 2)
        candidates.append((above_cx, above_y, "bottom", 0))

        if avoid_rect and avoid_rect.isValid():
            if avoid_rect.center().x() < pet_rect.center().x():
                # Avoid rect on left: shift bubble right
                cand_x = max(avoid_rect.right() + 8, pet_rect.right() - w + 10)
                candidates.append((cand_x, above_y, "bottom", 1))
            else:
                # Avoid rect on right: shift bubble left
                cand_x = min(avoid_rect.left() - w - 8, pet_rect.left() - 10)
                candidates.append((cand_x, above_y, "bottom", 1))

        below_y = pet_rect.bottom() + 8
        below_cx = pet_rect.center().x() - (w // 2)
        candidates.append((below_cx, below_y, "top", 2))

        if avoid_rect and avoid_rect.isValid():
            if avoid_rect.center().x() < pet_rect.center().x():
                cand_x = max(avoid_rect.right() + 8, pet_rect.right() - w + 10)
                candidates.append((cand_x, below_y, "top", 3))
            else:
                cand_x = min(avoid_rect.left() - w - 8, pet_rect.left() - 10)
                candidates.append((cand_x, below_y, "top", 3))

        right_x = pet_rect.right() + 10
        right_y = pet_rect.center().y() - (h // 2)
        candidates.append((right_x, right_y, "bottom", 4))

        left_x = pet_rect.left() - w - 10
        left_y = pet_rect.center().y() - (h // 2)
        candidates.append((left_x, left_y, "bottom", 5))

        best_cand = None
        best_score = float("inf")

        for bx, by, direction, pref_rank in candidates:
            clamped_x = max(s_geo.left() + 8, min(bx, s_geo.right() - w - 8))
            clamped_y = max(s_geo.top() + 8, min(by, s_geo.bottom() - h - 8))

            cand_rect = QRect(clamped_x, clamped_y, w, h)

            avoid_overlap = 0
            if avoid_rect and avoid_rect.isValid() and avoid_rect.intersects(cand_rect):
                inter = cand_rect.intersected(avoid_rect)
                avoid_overlap = inter.width() * inter.height()

            pet_overlap = 0
            if cand_rect.intersects(pet_rect):
                p_inter = cand_rect.intersected(pet_rect)
                pet_overlap = p_inter.width() * p_inter.height()

            offscreen_penalty = (abs(clamped_x - bx) + abs(clamped_y - by)) * 10
            score = (avoid_overlap * 1000) + (pet_overlap * 500) + offscreen_penalty + (pref_rank * 50)

            if score < best_score:
                best_score = score
                best_cand = (clamped_x, clamped_y, direction)

        if not best_cand:
            best_cand = (max(s_geo.left() + 8, min(above_cx, s_geo.right() - w - 8)),
                         max(s_geo.top() + 8, min(above_y, s_geo.bottom() - h - 8)),
                         "bottom")

        chosen_x, chosen_y, chosen_dir = best_cand

        rel_pet_center_x = pet_rect.center().x() - chosen_x
        self._pointer_x = max(18.0, min(float(w - 18.0), float(rel_pet_center_x)))
        self._pointer_direction = chosen_dir

        if chosen_dir == "top":
            self.layout.setContentsMargins(14, 16, 14, 8)
        else:
            self.layout.setContentsMargins(14, 8, 14, 16)

        self.move(chosen_x, chosen_y)

    def update_position(self, pet_rect: QRect, avoid_rect: Optional[QRect] = None) -> None:
        self._pet_rect = pet_rect
        if self.isVisible():
            self._reposition(pet_rect, avoid_rect=avoid_rect)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        pointer_h = 8.0

        path = QPainterPath()
        tip_x = max(18.0, min(w - 18.0, getattr(self, "_pointer_x", w * 0.5)))

        if getattr(self, "_pointer_direction", "bottom") == "top":
            # Pointer at top pointing up to pet
            bubble_top = pointer_h
            path.addRoundedRect(QRectF(1, bubble_top, w - 2, h - pointer_h - 2), 12.0, 12.0)
            path.moveTo(tip_x - 7, bubble_top + 0.5)
            path.lineTo(tip_x, 1)
            path.lineTo(tip_x + 7, bubble_top + 0.5)
            path.closeSubpath()
        else:
            # Pointer at bottom pointing down to pet
            bubble_h = h - pointer_h
            path.addRoundedRect(QRectF(1, 1, w - 2, bubble_h - 2), 12.0, 12.0)
            path.moveTo(tip_x - 7, bubble_h - 0.5)
            path.lineTo(tip_x, h - 1)
            path.lineTo(tip_x + 7, bubble_h - 0.5)
            path.closeSubpath()

        # Fill with sleek dark card color
        painter.fillPath(path, QColor(COLORS.get("bg_card", "#0F172A")))

        # Subtle high-tech border
        pen = QPen(QColor(COLORS.get("hud_border", "#334155")))
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()
