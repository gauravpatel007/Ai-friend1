"""Desktop Pet Window — Phase 2 Complete Implementation.

Provides a frameless, transparent, draggable, always-on-top desktop overlay
for the AI companion character with:
- Drag-and-drop movement with threshold detection
- Position persistence with multi-monitor validation
- Character size customization (preset + custom)
- Mouse interactions: single-click, double-click, right-click, hover
- Floating control bar integration
- Always-on-top and click-through mode toggling
- High-DPI rendering support
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional, Union

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QEnterEvent,
    QFont,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from app.character.animation_controller import AnimationController
from app.character.renderer import CharacterRenderer
from app.character.states import CharacterState
from app.core.signals import signals
from app.desktop.control_bar import FloatingControlBar
from app.desktop.speech_bubble import SpeechBubbleWidget
from app.desktop.jarvis_theme import COLORS, qcolor
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

# State speeches matching Showcase Section 3
BUDDY_STATE_SPEECHES = {
    "idle": "Hey! 👋 I'm your AI Friend!",
    "listening": "I'm listening...",
    "thinking": "Hmm...",
    "speaking": "Let me tell you...",
    "happy": "That's awesome!",
    "sleeping": "Z z z ...",
}

# Drag detection threshold in pixels — prevents accidental drags on click
_DRAG_THRESHOLD = 6
# Double-click detection window in milliseconds
_DOUBLE_CLICK_WINDOW_MS = 350
# Hover delay before showing control bar (ms)
_HOVER_SHOW_DELAY_MS = 400
# Hover delay before hiding control bar after mouse leaves (ms)
_HOVER_HIDE_DELAY_MS = 800


class DesktopPetWindow(QWidget):
    """Transparent, draggable desktop overlay window housing the pet character."""

    def __init__(self, config_manager: Optional[ConfigManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config_manager = config_manager or ConfigManager()

        # Drag state
        self._mouse_press_pos: Optional[QPoint] = None
        self._mouse_press_global: Optional[QPoint] = None
        self._is_dragging = False

        # Active status state machine tracking (IDLE, LISTENING, TRANSCRIBING, THINKING, SPEAKING, ERROR, SLEEPING)
        self._active_status_state: str = "IDLE"

        # Click detection state
        self._last_click_time: float = 0.0
        self._pending_single_click = False

        # Click-through mode
        self._click_through_enabled = False

        # Flag to track whether the introductory greeting has been displayed
        self._initial_greeting_shown: bool = False

        # Centralized lifecycle integration on window close
        self._request_shutdown_on_close: bool = True
        self._force_shutdown_in_test: bool = False

        # Single-click timer for distinguishing click vs double-click
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(_DOUBLE_CLICK_WINDOW_MS)
        self._click_timer.timeout.connect(self._on_single_click_confirmed)

        # Hover control bar
        self._hover_show_timer = QTimer(self)
        self._hover_show_timer.setSingleShot(True)
        self._hover_show_timer.setInterval(_HOVER_SHOW_DELAY_MS)
        self._hover_show_timer.timeout.connect(self._show_control_bar)

        self._hover_hide_timer = QTimer(self)
        self._hover_hide_timer.setSingleShot(True)
        self._hover_hide_timer.setInterval(_HOVER_HIDE_DELAY_MS)
        self._hover_hide_timer.timeout.connect(self._hide_control_bar)

        # Character animation loop timer
        self._anim_timer = QTimer(self)
        fps = int(self.config_manager.get("pet.animation_fps", 30))
        self._anim_timer.setInterval(max(10, 1000 // fps))
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

        # Periodic topmost check (5s) to gently maintain z-order without DWM composition flicker
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(5000)
        self._topmost_timer.timeout.connect(self.enforce_topmost)
        self._topmost_timer.start()

        # Initialize components
        self._init_renderer()
        self._init_anim_controller()
        self._init_window()
        self._init_control_bar()
        self._connect_signals()

    # ─── Initialization ───────────────────────────────────────────────

    def _init_renderer(self) -> None:
        """Set up the character rendering engine."""
        char_name = self.config_manager.get("pet.character", "robot")
        size = int(self.config_manager.get("pet.size", 120))
        self.renderer = CharacterRenderer(character_name=char_name, size=size)

    def _init_anim_controller(self) -> None:
        """Set up animation controller wired to character renderer."""
        self.anim_controller = AnimationController(self.renderer, parent=self)
        self.anim_controller.state_changed.connect(self._on_anim_state_changed)
        self.anim_controller.frame_changed.connect(self.update)
        self.anim_controller.start()

    def _init_window(self) -> None:
        """Apply window flags, transparency, size, and position."""
        self._apply_window_flags()
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setStyleSheet("background: transparent; border: none;")

        # Set size from renderer
        render_size = self.renderer.get_render_size()
        self.setFixedSize(render_size)

        # Restore or default position
        self._restore_position()
        self.enforce_topmost()
        companion_name = self.config_manager.get("ai.companion_name") or self.config_manager.get("companion.name") or "Buddy"
        self.setToolTip(f"{companion_name} — AI Desktop Friend")

    def enforce_topmost(self) -> None:
        """Ensure character window remains topmost without stealing focus or triggering DWM screen flicker."""
        if not self.isVisible():
            return
        always_on_top = bool(self.config_manager.get("pet.always_on_top", True))
        if not always_on_top:
            return
        try:
            import ctypes
            from ctypes import wintypes, c_void_p, c_int, c_uint
            user32 = ctypes.windll.user32
            hwnd_val = int(self.winId())
            if not hwnd_val:
                return

            # Check if window is already topmost to avoid redundant DWM layout invalidations
            GWL_EXSTYLE = -20
            WS_EX_TOPMOST = 0x00000008
            ex_style = user32.GetWindowLongW(hwnd_val, GWL_EXSTYLE)
            if ex_style & WS_EX_TOPMOST:
                return  # Already topmost, no-op to prevent screen flicker

            user32.SetWindowPos.argtypes = [
                c_void_p, c_void_p,
                c_int, c_int, c_int, c_int,
                c_uint
            ]
            user32.SetWindowPos.restype = wintypes.BOOL
            HWND_TOPMOST = c_void_p(-1)
            # Never pass SWP_SHOWWINDOW (0x0040) on visible windows to prevent DWM composition flashing
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_NOREDRAW = 0x0008
            SWP_NOSENDCHANGING = 0x0400
            SWP_NOOWNERZORDER = 0x0200
            swp_flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOREDRAW | SWP_NOSENDCHANGING | SWP_NOOWNERZORDER
            user32.SetWindowPos(
                c_void_p(hwnd_val),
                HWND_TOPMOST,
                0, 0, 0, 0,
                swp_flags,
            )
        except Exception:
            pass

    def _apply_window_flags(self) -> None:
        """Build and apply window flags based on configuration.
        
        Uses Qt.Tool, Qt.FramelessWindowHint, and Qt.WindowDoesNotAcceptFocus so the pet character
        floats above desktop applications without stealing keyboard/text focus from chat or active apps.
        """
        flags = (
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )

        always_on_top = bool(self.config_manager.get("pet.always_on_top", True))
        if always_on_top:
            flags |= Qt.WindowStaysOnTopHint

        click_through = self.config_manager.get("pet.click_through", False)
        if click_through:
            flags |= Qt.WindowTransparentForInput
            self._click_through_enabled = True
        else:
            self._click_through_enabled = False

        self.setWindowFlags(flags)

    def get_companion_name(self) -> str:
        """Resolve current companion name from configuration."""
        if hasattr(self, "config_manager") and self.config_manager:
            return (
                self.config_manager.get("ai.companion_name")
                or self.config_manager.get("companion.name")
                or self.config_manager.get("character.name")
                or "Bond"
            )
        return "Bond"

    def _get_conversation_avoid_rect(self) -> Optional[QRect]:
        """Find active visible conversation or chat window geometry to avoid covering message content."""
        priority_classes = (
            "ModernChatWindow",
            "ChatWindow",
            "FloatingChatWindow",
            "VoiceWindow",
            "SettingsDialog",
        )
        for target_cls in priority_classes:
            for widget in QApplication.topLevelWidgets():
                if (
                    widget.isVisible()
                    and widget is not self
                    and widget is not getattr(self, "speech_bubble", None)
                    and widget is not getattr(self, "control_bar", None)
                ):
                    cls_name = widget.__class__.__name__
                    if target_cls in cls_name:
                        return widget.frameGeometry()

        for widget in QApplication.topLevelWidgets():
            if (
                widget.isVisible()
                and widget is not self
                and widget is not getattr(self, "speech_bubble", None)
                and widget is not getattr(self, "control_bar", None)
            ):
                cls_name = widget.__class__.__name__
                if any(kw in cls_name for kw in ("Chat", "Voice", "Conversation")):
                    return widget.frameGeometry()
        return None

    def _get_chat_window_geometry(self) -> Optional[QRect]:
        """Compatibility wrapper: return active conversation window avoid rect."""
        return self._get_conversation_avoid_rect()

    def _update_realtime_tooltip(self) -> None:
        """Set meaningful real-time status tooltip based on current state."""
        state = getattr(self, "_active_status_state", "IDLE").lower()
        name = self.get_companion_name()
        status_map = {
            "idle": f"{name} — Ready to chat",
            "listening": f"{name} — Listening to you...",
            "transcribing": f"{name} — Transcribing speech...",
            "thinking": f"{name} — Thinking...",
            "speaking": f"{name} — Speaking aloud...",
            "error": f"{name} — Attention needed (Error)",
            "sleeping": f"{name} — Sleeping (Say 'Hey {name}' or click to wake)",
            "happy": f"{name} — Pleased to help!",
        }
        self.setToolTip(status_map.get(state, f"{name} — AI Desktop Friend"))

    def _init_control_bar(self) -> None:
        """Create the floating control bar and speech bubble widgets."""
        self.control_bar = FloatingControlBar(pet_window=self)
        self.speech_bubble = SpeechBubbleWidget(parent=None, companion_name=self.get_companion_name())

    def _connect_signals(self) -> None:
        """Connect to central application signal bus."""
        self._signal_connections = [
            signals.show_pet_requested.connect(self.show_pet),
            signals.hide_pet_requested.connect(self.hide_pet),
            signals.toggle_pet_requested.connect(self.toggle_pet),
            signals.reset_pet_position_requested.connect(self.reset_position),
            signals.activate_requested.connect(self.activate_and_highlight),
            signals.character_size_changed.connect(self._on_size_changed),
            signals.character_state_changed.connect(self._on_state_changed),
            signals.always_on_top_changed.connect(self._on_always_on_top_changed),
            signals.click_through_changed.connect(self._on_click_through_changed),
            signals.user_speech_interim.connect(self._on_user_speech_interim),
            signals.user_speech_final.connect(self._on_user_speech_final),
            signals.ai_speech_subtitle.connect(self._on_ai_speech_subtitle),
            signals.ai_speech_finished.connect(self._on_ai_speech_finished),
            signals.ai_cancel_requested.connect(self._on_speech_cancelled),
            signals.emergency_stop_requested.connect(self._on_speech_cancelled),
            signals.sleep_requested.connect(self._on_speech_cancelled),
        ]
        if self.config_manager:
            self.config_manager.setting_changed.connect(self._on_setting_changed)

    @Slot(str, object)
    def _on_setting_changed(self, key: str, val: Any) -> None:
        """Dynamically update pet tooltip and companion references on configuration change."""
        if key in ("ai.companion_name", "companion.name", "character.name"):
            name = str(val).strip() if val else "Bond"
            if hasattr(self, "speech_bubble") and self.speech_bubble:
                self.speech_bubble.set_companion_name(name)
            self._update_realtime_tooltip()

    # ─── Position Management ──────────────────────────────────────────

    def _restore_position(self) -> None:
        """Restore saved position with multi-monitor validation and edge margin safety."""
        pos_x = self.config_manager.get("pet.position_x", None)
        pos_y = self.config_manager.get("pet.position_y", None)

        if pos_x is not None and pos_y is not None:
            target = QPoint(int(pos_x), int(pos_y))
            if self._is_position_on_active_screen(target):
                # Resolve active monitor containing target point (or screen with visible overlap)
                screen = QApplication.screenAt(target)
                if not screen:
                    pet_rect = QRect(target, self.size())
                    for s in QApplication.screens():
                        if s.availableGeometry().intersected(pet_rect).width() >= 30:
                            screen = s
                            break
                if not screen:
                    screen = QApplication.primaryScreen()

                screen_geo = screen.availableGeometry() if screen else None
                if screen_geo:
                    # Clamp within visible screen area of the active monitor with safe margins
                    clamped_x = max(screen_geo.left() + 20, min(int(pos_x), screen_geo.right() - self.width() - 30))
                    clamped_y = max(screen_geo.top() + 20, min(int(pos_y), screen_geo.bottom() - self.height() - 50))
                    self.move(clamped_x, clamped_y)
                    return
            else:
                logger.info(
                    "Saved position (%s, %s) is off-screen. Repositioning to default.",
                    pos_x, pos_y,
                )
        self._place_in_default_position()

    def _is_position_on_active_screen(self, pos: QPoint) -> bool:
        """Check whether the given position falls on any connected monitor."""
        pet_rect = QRect(pos, self.size())
        for screen in QApplication.screens():
            screen_geo = screen.availableGeometry()
            # Character is considered on-screen if at least 30px is visible
            if screen_geo.intersected(pet_rect).width() >= 30:
                return True
        return False

    def _place_in_default_position(self) -> None:
        """Place character near the bottom-right corner of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = screen_geo.right() - self.width() - 40
            y = screen_geo.bottom() - self.height() - 76
            self.move(x, y)

    def _save_position(self) -> None:
        """Persist current position to configuration."""
        self.config_manager.set("pet.position_x", self.x(), auto_save=False)
        self.config_manager.set("pet.position_y", self.y(), auto_save=True)

    # ─── Size Management ──────────────────────────────────────────────

    @Slot(int)
    def _on_size_changed(self, new_size: int) -> None:
        """Handle character size change from settings or context menu."""
        self.renderer.set_size(new_size)
        render_size = self.renderer.get_render_size()
        self.setFixedSize(render_size)
        self.config_manager.set("pet.size", new_size)
        self.update()
        logger.info("Character size changed to %d px", new_size)

    def set_size_preset(self, preset: str) -> None:
        """Apply a named size preset."""
        if preset in CharacterRenderer.SIZE_PRESETS:
            signals.character_size_changed.emit(CharacterRenderer.SIZE_PRESETS[preset])

    # ─── State Management ─────────────────────────────────────────────

    def set_state(self, state: Union[CharacterState, str], *, force: bool = True) -> None:
        """Update character state across anim controller, renderer, speech bubble, and animation timer."""
        if hasattr(state, "name"):
            state_str = state.name.lower()
            target_enum = state
        else:
            state_str = str(state).lower()
            try:
                target_enum = CharacterState[state_str.upper()]
            except (KeyError, ValueError):
                target_enum = None

        # If anim_controller is present, ensure its state is synchronized
        if hasattr(self, "anim_controller") and self.anim_controller:
            if target_enum is not None and self.anim_controller.current_state != target_enum:
                self.anim_controller.request_state(target_enum, force=force)

        self._apply_visual_state(state_str)

    def _on_anim_state_changed(self, state_str: str) -> None:
        """Slot invoked when anim_controller transitions to a new state."""
        self._apply_visual_state(state_str)

    def _apply_visual_state(self, state: Union[CharacterState, str]) -> None:
        """Apply visual changes (renderer, speech bubble, anim_timer) for a given state."""
        if hasattr(state, "name"):
            state_str = state.name.lower().strip()
        else:
            state_str = str(state).lower().strip()

        # Canonicalize state name for animation
        anim_target = "thinking" if state_str == "transcribing" else ("idle" if state_str in ("ready", "active") else state_str)

        self._active_status_state = state_str.upper()
        self.renderer.set_state(anim_target)

        # Throttle animation timer in Sleep Mode (2 FPS) vs Active (Phase 11.5, 11.8)
        if hasattr(self, "_anim_timer"):
            if state_str == "sleeping":
                self._anim_timer.setInterval(500)
            else:
                fps = int(self.config_manager.get("pet.animation_fps", 30))
                self._anim_timer.setInterval(max(10, 1000 // fps))

        self._update_realtime_tooltip()
        self.update()

        companion_name = self.get_companion_name()

        # Handle speech bubble content and dismissals based on state
        if hasattr(self, "speech_bubble") and self.speech_bubble and self.isVisible():
            if state_str == "idle":
                # When conversation finishes, return cleanly to idle and clear subtitles
                self.set_mouth_openness(0.0)
                if not self._initial_greeting_shown:
                    self._initial_greeting_shown = True
                    self.speech_bubble.show_message(
                        f"Hey! 👋 I'm {companion_name}!", self.frameGeometry(), duration_ms=3000,
                        avoid_rect=self._get_conversation_avoid_rect()
                    )
                elif not getattr(self.speech_bubble, "is_holding_for_dismiss", False):
                    # Prevent old captions from remaining visible when conversation ends,
                    # but only if not currently holding for reading
                    self.speech_bubble.clear_subtitles()
            elif state_str == "listening":
                # Clear any lingering AI subtitles from prior turns so old captions don't remain visible
                if (
                    getattr(self.speech_bubble, "is_showing_ai_subtitle", False)
                    or getattr(self.speech_bubble, "is_holding_for_dismiss", False)
                ):
                    self.speech_bubble.clear_subtitles()
            elif state_str in ("thinking", "transcribing"):
                # If speech bubble was showing user speech, fade out so old user words don't linger
                if getattr(self.speech_bubble, "is_showing_user_speech", False):
                    self.speech_bubble.hide_bubble()
            elif state_str == "sleeping":
                self.set_mouth_openness(0.0)
                self.speech_bubble.clear_subtitles()
                self.speech_bubble.hide_bubble()

    @Slot(str)
    def _on_user_speech_interim(self, partial_text: str) -> None:
        """Progressively render live recognized user speech in the speech bubble (Phase 1)."""
        if not hasattr(self, "speech_bubble") or not self.speech_bubble:
            return
        cleaned = partial_text.strip()
        chat_geo = self._get_conversation_avoid_rect()
        self.speech_bubble.show_user_speech(cleaned, self.frameGeometry(), is_interim=True, avoid_rect=chat_geo)
        self._active_status_state = "LISTENING"
        if hasattr(self, "anim_controller") and self.anim_controller:
            self.anim_controller.request_state(CharacterState.LISTENING)
        self._update_realtime_tooltip()
        self.update()

    @Slot(str)
    def _on_user_speech_final(self, final_text: str) -> None:
        """Render finalized verified user speech in the speech bubble (Phase 1)."""
        if not hasattr(self, "speech_bubble") or not self.speech_bubble:
            return
        cleaned = final_text.strip()
        chat_geo = self._get_conversation_avoid_rect()
        if cleaned:
            self.speech_bubble.show_user_speech(cleaned, self.frameGeometry(), is_interim=False, avoid_rect=chat_geo)
        self._active_status_state = "TRANSCRIBING"
        if hasattr(self, "anim_controller") and self.anim_controller:
            self.anim_controller.request_state(CharacterState.THINKING)
        self._update_realtime_tooltip()
        self.update()

    @Slot(str)
    def _on_ai_speech_subtitle(self, sentence: str) -> None:
        """Render synchronized AI spoken sentence subtitle (Phase 2)."""
        if not hasattr(self, "speech_bubble") or not self.speech_bubble:
            return
        cleaned = sentence.strip()
        if cleaned:
            chat_geo = self._get_conversation_avoid_rect()
            self.speech_bubble.show_ai_subtitle(
                cleaned, self.frameGeometry(), avoid_rect=chat_geo, companion_name=self.get_companion_name()
            )
        self._active_status_state = "SPEAKING"
        if hasattr(self, "anim_controller") and self.anim_controller:
            self.anim_controller.request_state(CharacterState.SPEAKING)
        self._update_realtime_tooltip()
        self.update()

    @Slot()
    def _on_ai_speech_finished(self) -> None:
        """Handle completion of all AI speech chunks with clean hold time (Phase 2)."""
        self.set_mouth_openness(0.0)
        if hasattr(self, "speech_bubble") and self.speech_bubble:
            self.speech_bubble.on_ai_speech_finished(hold_ms=1200)
        self._active_status_state = "IDLE"
        if hasattr(self, "anim_controller") and self.anim_controller:
            self.anim_controller.request_state(CharacterState.IDLE, force=True)
        if hasattr(self, "renderer") and self.renderer:
            self.renderer.set_state("idle")
        self._update_realtime_tooltip()
        self.update()

    @Slot()
    def _on_speech_cancelled(self) -> None:
        """Immediately clear subtitles on cancellation or interruption (Phase 2)."""
        self.set_mouth_openness(0.0)
        if hasattr(self, "speech_bubble") and self.speech_bubble:
            self.speech_bubble.clear_subtitles()
        self._active_status_state = "IDLE"
        if hasattr(self, "anim_controller") and self.anim_controller:
            self.anim_controller.request_state(CharacterState.IDLE, force=True)
        if hasattr(self, "renderer") and self.renderer:
            self.renderer.set_state("idle")
        self._update_realtime_tooltip()
        self.update()

    @Slot(object)
    def _on_state_changed(self, state: Any) -> None:
        """Handle character animation state change from central signal bus."""
        st_lower = str(state.value if hasattr(state, "value") else state).lower().strip()
        anim_target = "thinking" if st_lower == "transcribing" else ("idle" if st_lower in ("ready", "active") else st_lower)

        if hasattr(self, "anim_controller") and self.anim_controller:
            self.anim_controller.request_state(anim_target, broadcast_global=False, force=True)
        else:
            self._apply_visual_state(anim_target)

        self._active_status_state = st_lower.upper()
        if st_lower == "idle":
            self.set_mouth_openness(0.0)
        self._update_realtime_tooltip()
        self.update()

    # ─── Always-on-top / Click-through ────────────────────────────────

    @Slot(bool)
    def _on_always_on_top_changed(self, enabled: bool) -> None:
        """Toggle always-on-top at runtime and immediately re-enforce topmost z-order."""
        qapp = QApplication.instance()
        from PySide6.QtCore import QThread
        if qapp and QThread.currentThread() != qapp.thread():
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_on_always_on_top_changed", Qt.ConnectionType.QueuedConnection, enabled)
            return

        self.config_manager.set("pet.always_on_top", enabled)
        was_visible = self.isVisible()

        try:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        except Exception:
            pass

        try:
            import ctypes
            from ctypes import c_void_p
            user32 = ctypes.windll.user32
            hwnd_val = int(self.winId())
            if hwnd_val:
                GWL_EXSTYLE = -20
                WS_EX_TOPMOST = 0x00000008
                ex_style = user32.GetWindowLongW(hwnd_val, GWL_EXSTYLE)

                HWND_TOPMOST = c_void_p(-1)
                HWND_NOTOPMOST = c_void_p(-2)
                HWND_BOTTOM = c_void_p(1)
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                SWP_FRAMECHANGED = 0x0020

                if enabled:
                    user32.SetWindowLongW(hwnd_val, GWL_EXSTYLE, ex_style | WS_EX_TOPMOST)
                    user32.SetWindowPos(
                        c_void_p(hwnd_val),
                        HWND_TOPMOST,
                        0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED
                    )
                else:
                    user32.SetWindowLongW(hwnd_val, GWL_EXSTYLE, ex_style & ~WS_EX_TOPMOST)
                    user32.SetWindowPos(
                        c_void_p(hwnd_val),
                        HWND_NOTOPMOST,
                        0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED
                    )
                    user32.SetWindowPos(
                        c_void_p(hwnd_val),
                        HWND_BOTTOM,
                        0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                    )
        except Exception as e:
            logger.debug("Win32 SetWindowPos topmost note: %s", e)

        if was_visible:
            self.show()
            if enabled:
                self.raise_()
                self.enforce_topmost()

    def set_always_on_top(self, enabled: bool) -> None:
        """Public interface to set always on top with GUI thread dispatching."""
        qapp = QApplication.instance()
        from PySide6.QtCore import QThread
        if qapp and QThread.currentThread() != qapp.thread():
            from PySide6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self, "_on_always_on_top_changed", Qt.ConnectionType.QueuedConnection, Q_ARG(bool, enabled))
            return
        self._on_always_on_top_changed(enabled)

    @Slot()
    def reset_position(self) -> None:
        """Reset pet character back to the default bottom-right on the active monitor."""
        qapp = QApplication.instance()
        from PySide6.QtCore import QThread
        if qapp and QThread.currentThread() != qapp.thread():
            from PySide6.QtCore import QMetaObject
            QMetaObject.invokeMethod(self, "reset_position", Qt.ConnectionType.QueuedConnection)
            return

        self.config_manager.set("pet.visible", True)
        self._place_in_default_position()
        self._save_position()

        # Win32 explicit move for instant hardware-level refresh
        try:
            import ctypes
            from ctypes import c_void_p
            user32 = ctypes.windll.user32
            hwnd_val = int(self.winId())
            if hwnd_val:
                user32.SetWindowPos(
                    c_void_p(hwnd_val),
                    None,
                    int(self.x()),
                    int(self.y()),
                    int(self.width()),
                    int(self.height()),
                    0x0004 | 0x0010  # SWP_NOZORDER | SWP_NOACTIVATE
                )
        except Exception:
            pass

        self.show()
        if bool(self.config_manager.get("pet.always_on_top", True)):
            self.raise_()
            self.enforce_topmost()
        signals.pet_moved.emit(self.x(), self.y())
        signals.pet_visibility_changed.emit(True)
        if hasattr(self, "control_bar") and self.control_bar:
            self.control_bar.update_position(self.frameGeometry())
        if hasattr(self, "speech_bubble") and self.speech_bubble:
            self.speech_bubble.update_position(self.frameGeometry())
        logger.info("Buddy position reset to default bottom-right screen coordinates.")

    @Slot(bool)
    def _on_click_through_changed(self, enabled: bool) -> None:
        """Toggle click-through mode at runtime."""
        self.config_manager.set("pet.click_through", enabled)
        was_visible = self.isVisible()
        self._apply_window_flags()
        if was_visible:
            self.show()
        if enabled:
            logger.info("Click-through mode enabled. Use system tray to regain control.")

    # ─── Visibility ───────────────────────────────────────────────────

    @Slot()
    def show_pet(self) -> None:
        """Display the pet window and greet the user without stealing input focus."""
        qapp = QApplication.instance()
        from PySide6.QtCore import QThread
        if qapp and QThread.currentThread() != qapp.thread():
            from PySide6.QtCore import QMetaObject
            QMetaObject.invokeMethod(self, "show_pet", Qt.ConnectionType.QueuedConnection)
            return

        self.config_manager.set("pet.visible", True)
        self.show()
        always_on_top = bool(self.config_manager.get("pet.always_on_top", True))
        if always_on_top:
            self.raise_()
            self.enforce_topmost()
            try:
                from app.utils.window_elevation import elevate_window_to_front
                elevate_window_to_front(int(self.winId()), keep_topmost=True)
            except Exception:
                pass
        else:
            try:
                import ctypes
                from ctypes import c_void_p
                user32 = ctypes.windll.user32
                hwnd_val = int(self.winId())
                if hwnd_val:
                    user32.SetWindowPos(c_void_p(hwnd_val), c_void_p(-2), 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)
                    user32.SetWindowPos(c_void_p(hwnd_val), c_void_p(1), 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)
            except Exception:
                pass
        signals.pet_visibility_changed.emit(True)
        is_sleeping = False
        try:
            from app.core.buddy_state_manager import get_buddy_state_manager
            is_sleeping = get_buddy_state_manager().is_sleeping
        except Exception:
            pass

        if is_sleeping:
            # Requirement 1: In strict sleep mode on startup, do not show unprompted greetings
            from app.character.states import CharacterState
            self.set_state(CharacterState.SLEEPING, force=True)
            self._initial_greeting_shown = True
            if hasattr(self, "speech_bubble") and self.speech_bubble:
                self.speech_bubble.hide_bubble()
        elif hasattr(self, "speech_bubble") and self.speech_bubble:
            if not self._initial_greeting_shown:
                companion_name = (
                    self.config_manager.get("ai.companion_name")
                    or self.config_manager.get("companion.name")
                    or "Bond"
                )
                self.speech_bubble.show_message(
                    f"Hey! 👋 I'm {companion_name}!", self.frameGeometry(), duration_ms=3200
                )
                self._initial_greeting_shown = True

    @Slot()
    def hide_pet(self) -> None:
        """Hide the pet window, control bar, and speech bubble."""
        qapp = QApplication.instance()
        from PySide6.QtCore import QThread
        if qapp and QThread.currentThread() != qapp.thread():
            from PySide6.QtCore import QMetaObject
            QMetaObject.invokeMethod(self, "hide_pet", Qt.ConnectionType.QueuedConnection)
            return

        self.config_manager.set("pet.visible", False)
        if hasattr(self, "control_bar") and self.control_bar:
            self.control_bar.hide_bar()
        if hasattr(self, "speech_bubble") and self.speech_bubble:
            self.speech_bubble.hide_bubble()
        self.hide()
        signals.pet_visibility_changed.emit(False)

    @Slot()
    def toggle_pet(self) -> None:
        """Toggle visibility of the pet."""
        if self.isVisible():
            self.hide_pet()
        else:
            self.show_pet()

    @Slot()
    def activate_and_highlight(self) -> None:
        """Bring pet to front and alert user without stealing text focus."""
        self.show_pet()
        self.enforce_topmost()

    # ─── Mouse Events — Drag, Click, Double-Click, Right-Click ───────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Track press position for distinguishing click vs drag."""
        if event.button() == Qt.LeftButton:
            self._mouse_press_pos = event.globalPosition().toPoint()
            self._mouse_press_global = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._is_dragging = False
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle drag motion — only initiates after threshold exceeded."""
        if event.buttons() == Qt.LeftButton and self._mouse_press_pos is not None:
            delta = event.globalPosition().toPoint() - self._mouse_press_pos
            distance = (delta.x() ** 2 + delta.y() ** 2) ** 0.5

            if not self._is_dragging and distance > _DRAG_THRESHOLD:
                self._is_dragging = True
                self._click_timer.stop()
                self._pending_single_click = False
                # Change character state to "dragging"
                if hasattr(self, "anim_controller") and self.anim_controller:
                    self.anim_controller.request_state(CharacterState.DRAGGING, force=True)
                else:
                    self.renderer.set_state("dragging")
                self.update()

            if self._is_dragging and self._mouse_press_global is not None:
                new_pos = event.globalPosition().toPoint() - self._mouse_press_global
                self.move(new_pos)
                # Update control bar and speech bubble positions during drag
                self.control_bar.update_position(self.frameGeometry())
                if hasattr(self, "speech_bubble") and self.speech_bubble:
                    self.speech_bubble.update_position(self.frameGeometry())
                signals.pet_moved.emit(self.x(), self.y())
                event.accept()

    def _on_anim_tick(self) -> None:
        """Advance animation frame for gentle breathing and floating motion."""
        if not self.isVisible():
            return
        if hasattr(self, "anim_controller") and self.anim_controller and self.anim_controller.is_running:
            return
        if self.renderer.advance_frame():
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle release — dispatch click or finalize drag."""
        if event.button() == Qt.LeftButton:
            if self._is_dragging:
                # Drag finished — save position, revert state
                self._is_dragging = False
                self._save_position()
                if hasattr(self, "anim_controller") and self.anim_controller:
                    self.anim_controller.restore_previous_state()
                else:
                    self.renderer.set_state("idle")
                self.update()
            else:
                # Not a drag — detect click vs double-click
                now = time.monotonic()
                elapsed = (now - self._last_click_time) * 1000

                if elapsed < _DOUBLE_CLICK_WINDOW_MS:
                    # Double-click detected
                    self._click_timer.stop()
                    self._pending_single_click = False
                    self._on_double_click()
                else:
                    # Potential single click — wait to confirm it's not a double-click
                    self._pending_single_click = True
                    self._click_timer.start()

                self._last_click_time = now

            self._mouse_press_pos = None
            self._mouse_press_global = None
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle native Qt double-click event on Desktop Pet."""
        if event.button() == Qt.LeftButton:
            self._click_timer.stop()
            self._pending_single_click = False
            self._on_double_click()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _on_single_click_confirmed(self) -> None:
        """Handle confirmed single left-click (open chat)."""
        if self._pending_single_click:
            self._pending_single_click = False
            logger.debug("Single click → Open chat")
            signals.open_chat_requested.emit()

    def _on_double_click(self) -> None:
        """Handle double-click (automatically open/elevate main chat window and wake if sleeping)."""
        logger.info("Double-click on Desktop Pet → Automatically opening main chat window.")
        from app.core.buddy_state_manager import get_buddy_state_manager
        buddy_sm = get_buddy_state_manager()
        if buddy_sm.is_sleeping:
            signals.wake_requested.emit()
        signals.open_chat_requested.emit()

    # ─── Context Menu (Right-Click — macOS Styled Floating Menu) ──────

    def _show_context_menu(self, global_pos: QPoint) -> None:
        """Display macOS styled context menu with frosted acrylic background and accent blue hover."""
        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint)
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setStyleSheet(self._context_menu_stylesheet())

        # 1. Open Chat
        chat_action = QAction("Open Chat", menu)
        chat_action.triggered.connect(signals.open_chat_requested.emit)
        menu.addAction(chat_action)

        # 2. Voice Window
        voice_win_action = QAction("Voice Window", menu)
        voice_win_action.triggered.connect(signals.toggle_voice_window_requested.emit)
        menu.addAction(voice_win_action)

        # 3. Enable Voice
        voice_action = QAction("Enable Voice", menu)
        voice_action.triggered.connect(signals.voice_toggle_requested.emit)
        menu.addAction(voice_action)

        # 4. Settings
        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(signals.open_settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        # 5. Always on Top toggle
        aot_action = QAction("Always on Top", menu)
        aot_action.setCheckable(True)
        aot_action.setChecked(self.config_manager.get("pet.always_on_top", True))
        aot_action.triggered.connect(lambda checked: signals.always_on_top_changed.emit(checked))
        menu.addAction(aot_action)

        # 6. Change Character Submenu
        char_menu = menu.addMenu("Change Character")
        char_menu.setStyleSheet(self._context_menu_stylesheet())
        char_menu.setWindowFlags(char_menu.windowFlags() | Qt.FramelessWindowHint)
        char_menu.setAttribute(Qt.WA_TranslucentBackground, True)
        for char_name in self.renderer.available_characters():
            c_action = QAction(char_name.capitalize(), char_menu)
            c_action.triggered.connect(lambda checked=False, c=char_name: self.renderer.switch_character(c))
            char_menu.addAction(c_action)

        # 7. Sleep / Wake Mode
        from app.core.buddy_state_manager import get_buddy_state_manager
        buddy_sm = get_buddy_state_manager()
        if buddy_sm.is_sleeping:
            sleep_action = QAction("Wake Up", menu)
            sleep_action.triggered.connect(lambda: signals.wake_requested.emit())
        else:
            sleep_action = QAction("Sleep Mode", menu)
            sleep_action.triggered.connect(lambda: signals.sleep_requested.emit())
        menu.addAction(sleep_action)

        menu.addSeparator()

        # 8. Hide Character
        hide_action = QAction("Hide Character", menu)
        hide_action.triggered.connect(signals.hide_pet_requested.emit)
        menu.addAction(hide_action)

        # 9. Exit Application
        exit_action = QAction("Exit", menu)
        def _on_pet_exit():
            try:
                signals.shutdown_requested.emit()
            except Exception:
                pass
            from app.core.lifecycle import get_lifecycle_manager
            get_lifecycle_manager().request_shutdown(source="pet_context_menu")
        exit_action.triggered.connect(_on_pet_exit)
        menu.addAction(exit_action)

        menu.exec(global_pos)

    @staticmethod
    def _context_menu_stylesheet() -> str:
        """macOS Sonoma/Ventura styled context menu with dark frosted acrylic look and bright accent blue hover."""
        return """
            QMenu {
                background-color: rgba(30, 31, 35, 0.96);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 10px;
                padding: 5px 4px;
                color: #F5F5F7;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
                font-size: 13px;
                font-weight: 400;
            }
            QMenu::item {
                padding: 5px 22px 5px 12px;
                border-radius: 5px;
                margin: 1px 2px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #007AFF;
                color: #FFFFFF;
                font-weight: 500;
            }
            QMenu::item:disabled {
                color: rgba(255, 255, 255, 0.35);
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 0.12);
                margin: 5px 8px;
            }
            QMenu::indicator {
                width: 14px;
                height: 14px;
                margin-left: 2px;
            }
            QMenu::right-arrow {
                width: 8px;
                height: 8px;
                margin-right: 6px;
            }
        """

    # ─── Hover Events — Show / Hide Control Bar ──────────────────────

    def enterEvent(self, event: QEnterEvent) -> None:
        """Start hover timer to show control bar."""
        self._hover_hide_timer.stop()
        if hasattr(self, "control_bar") and self.control_bar:
            self.control_bar._hide_timer.stop()
        self._hover_show_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Start hover timer to hide control bar."""
        self._hover_show_timer.stop()
        if hasattr(self, "control_bar") and self.control_bar and self.control_bar.isVisible():
            cursor_pos = QCursor.pos()
            bar_rect = self.control_bar.frameGeometry().adjusted(-10, -10, 10, 10)
            if bar_rect.contains(cursor_pos):
                super().leaveEvent(event)
                return
        self._hover_hide_timer.start()
        super().leaveEvent(event)

    def _show_control_bar(self) -> None:
        """Display the control bar and friendly speech bubble."""
        if not self._is_dragging:
            self.control_bar.show_bar(self.frameGeometry())
            if hasattr(self, "speech_bubble") and self.speech_bubble:
                try:
                    from app.core.buddy_state_manager import get_buddy_state_manager
                    if get_buddy_state_manager().is_sleeping:
                        return
                except Exception:
                    pass
                self.speech_bubble.show_message("Need anything?", self.frameGeometry(), duration_ms=2500)

    def _hide_control_bar(self) -> None:
        """Dismiss the control bar and speech bubble."""
        cursor_pos = QCursor.pos()
        pet_rect = self.frameGeometry().adjusted(-10, -10, 10, 10)
        if pet_rect.contains(cursor_pos):
            return
        if hasattr(self, "control_bar") and self.control_bar and self.control_bar.isVisible():
            bar_rect = self.control_bar.frameGeometry().adjusted(-10, -10, 10, 10)
            if bar_rect.contains(cursor_pos):
                return
        self.control_bar.hide_bar()
        if hasattr(self, "speech_bubble") and self.speech_bubble:
            self.speech_bubble.hide_bubble()

    # ─── Paint Event ──────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent) -> None:
        """Render the character sprite with dynamic state aura, speaking ripples, and real-time status."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0

        state = getattr(self, "_active_status_state", "IDLE").upper()

        # 1. State-responsive ambient floor aura
        glow_w = w * 0.48
        glow_h = h * 0.11
        glow_x = (w - glow_w) / 2.0
        glow_y = h - glow_h - 4.0

        aura_colors = {
            "LISTENING": QColor(0, 229, 255, 110),      # Electric Cyan
            "TRANSCRIBING": QColor(191, 90, 242, 110),  # Purple
            "THINKING": QColor(255, 159, 10, 110),      # Amber
            "SPEAKING": QColor(48, 209, 88, 130),       # Green
            "ERROR": QColor(255, 69, 58, 120),          # Red
            "SLEEPING": QColor(160, 140, 255, 50),      # Lavender
            "IDLE": QColor(6, 182, 212, 60),            # Soft Cyan
        }
        floor_color = aura_colors.get(state, aura_colors["IDLE"])
        painter.setPen(Qt.NoPen)
        painter.setBrush(floor_color)
        painter.drawEllipse(QRectF(glow_x, glow_y, glow_w, glow_h))

        # 2. Speaking acoustic ripples while TTS is playing
        if state == "SPEAKING":
            import math
            openness = getattr(self.renderer, "mouth_openness", 0.0)
            if openness <= 0.05:
                # Natural conversational cadence when speech engine does not provide audio packet amplitudes
                openness = 0.28 + 0.35 * abs(math.sin(time.monotonic() * 11.0))
            amp = max(0.25, openness)
            now_t = time.monotonic()
            t1 = (now_t * 2.4) % 1.0
            t2 = ((now_t * 2.4) + 0.5) % 1.0
            for t_val in (t1, t2):
                r_val = (w * 0.32) + (t_val * 24.0) + (amp * 10.0)
                alpha_val = max(0.0, (1.0 - t_val) * 0.55 * amp)
                wave_col = QColor(48, 209, 88)
                wave_col.setAlphaF(alpha_val)
                p_wave = QPen(wave_col)
                p_wave.setWidthF(max(1.2, 2.2 * (1.0 - t_val)))
                painter.setPen(p_wave)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), r_val, r_val)

        # 3. Draw active character sprite
        pixmap = self.renderer.get_current_pixmap()
        x_offset = int((self.width() - pixmap.width()) / 2)
        y_offset = int((self.height() - pixmap.height()) / 2)
        painter.drawPixmap(x_offset, y_offset, pixmap)

        # 4. Floating Real-Time Status Pill (Sleek frosted glass badge)
        if state != "IDLE":
            import math
            pill_h = 18.0
            status_text = {
                "LISTENING": "Listening...",
                "TRANSCRIBING": "Transcribing...",
                "THINKING": "Thinking...",
                "SPEAKING": "Speaking",
                "ERROR": "Attention",
                "SLEEPING": "Sleeping",
            }.get(state, state.capitalize())

            font = QFont("Segoe UI", 8, QFont.DemiBold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(status_text)
            is_speaking = (state == "SPEAKING")
            amp = max(0.25, getattr(self.renderer, "mouth_openness", 0.0))
            pill_w = text_w + (26.0 if is_speaking else 22.0)
            pill_x = cx - (pill_w / 2.0)
            pill_y = h - pill_h - 1.0

            # Frosted glass background
            pill_path = QPainterPath()
            pill_path.addRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 9.0, 9.0)
            painter.fillPath(pill_path, QColor(15, 23, 42, 210))
            painter.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
            painter.drawPath(pill_path)

            if is_speaking:
                # Animated 3-bar soundwave equalizer
                bar_w = 2.0
                bar_sp = 1.5
                t_bars = time.monotonic() * 14.0
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(48, 209, 88, 255))
                for i in range(3):
                    b_phase = i * 1.4
                    b_h = 3.0 + 6.0 * abs(math.sin(t_bars + b_phase)) * max(0.5, amp)
                    bx_bar = pill_x + 6.0 + i * (bar_w + bar_sp)
                    by_bar = pill_y + (pill_h / 2.0) - (b_h / 2.0)
                    painter.drawRoundedRect(QRectF(bx_bar, by_bar, bar_w, b_h), 1.0, 1.0)
                text_x = pill_x + 18.0
            else:
                # Glowing status dot
                dot_color = QColor(floor_color)
                dot_color.setAlpha(255)
                painter.setBrush(dot_color)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(pill_x + 8.0, pill_y + 9.0), 3.0, 3.0)
                text_x = pill_x + 15.0

            # Status label
            painter.setPen(QColor(241, 245, 249))
            painter.drawText(QRectF(text_x, pill_y, text_w + 4, pill_h), Qt.AlignVCenter | Qt.AlignLeft, status_text)

        painter.end()

    def set_mouth_openness(self, openness: float) -> None:
        """Update character mouth openness for lip sync and trigger repaint."""
        self.renderer.set_mouth_openness(openness)
        self.update()

    # ─── Cleanup ──────────────────────────────────────────────────────

    def _disconnect_signals(self) -> None:
        """Disconnect all global signal bus connections."""
        for conn in getattr(self, "_signal_connections", []):
            try:
                QObject.disconnect(conn)
            except Exception:
                pass
        self._signal_connections = []

    def showEvent(self, event) -> None:
        """Resume animation updates when pet becomes visible (Phase 11.5)."""
        super().showEvent(event)
        if hasattr(self, "anim_controller") and self.anim_controller and not self.anim_controller.is_running:
            self.anim_controller.start()
        if hasattr(self, "_anim_timer") and not self._anim_timer.isActive():
            self._anim_timer.start()

    def hideEvent(self, event) -> None:
        """Pause animation loop when pet is hidden to save CPU/GPU cycles (Phase 11.5)."""
        super().hideEvent(event)
        if hasattr(self, "anim_controller") and self.anim_controller and self.anim_controller.is_running:
            self.anim_controller.stop()
        if hasattr(self, "_anim_timer") and self._anim_timer.isActive():
            self._anim_timer.stop()

    def revalidate_screen_position(self) -> None:
        """Ensure pet is not stranded off-screen after multi-monitor rearrangement (Phase 11.7)."""
        current_pos = self.pos()
        if not self._is_position_on_active_screen(current_pos):
            logger.info("Pet window was off-screen after display change. Repositioning to default.")
            self._place_in_default_position()
            self._save_position()

    def closeEvent(self, event) -> None:
        """Disconnect signals and clean up children on close event."""
        if hasattr(self, "anim_controller") and self.anim_controller:
            self.anim_controller.stop()
        if hasattr(self, "_anim_timer"):
            self._anim_timer.stop()
        self._disconnect_signals()
        self._save_position()
        if self.control_bar:
            self.control_bar.close()
        if hasattr(self, "speech_bubble") and self.speech_bubble:
            self.speech_bubble.close()
        super().closeEvent(event)

        try:
            from app.core.lifecycle import get_lifecycle_manager
            lifecycle = get_lifecycle_manager()
            if getattr(self, "_request_shutdown_on_close", True) and not lifecycle.is_shutting_down:
                if not os.environ.get("PYTEST_CURRENT_TEST") or getattr(self, "_force_shutdown_in_test", False):
                    logger.info("[PET_WINDOW] Close event triggered on primary pet window. Requesting central lifecycle shutdown...")
                    lifecycle.request_shutdown(source="pet_window_close")
        except Exception as e:
            logger.debug("[PET_WINDOW] Error requesting lifecycle shutdown on close: %s", e)

    def close(self) -> bool:
        """Clean up control bar and save position before closing."""
        if hasattr(self, "anim_controller") and self.anim_controller:
            self.anim_controller.stop()
        if hasattr(self, "_anim_timer"):
            self._anim_timer.stop()
        self._disconnect_signals()
        self._save_position()
        if self.control_bar:
            self.control_bar.close()
        if hasattr(self, "speech_bubble") and self.speech_bubble:
            self.speech_bubble.close()
        return super().close()
