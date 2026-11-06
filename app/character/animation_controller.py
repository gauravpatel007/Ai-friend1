"""Animation Controller.

Manages loading, caching, frame advancement, and state transitions
for the desktop pet's character animations. Drives repaint at ~30 FPS
via QTimer and emits signals when frames or states change.
"""

from __future__ import annotations

import time
from typing import Optional, Union

from PySide6.QtCore import QObject, QTimer, Signal

from app.character.renderer import CharacterRenderer
from app.character.states import (
    AnimationConfig,
    CharacterState,
    can_transition,
    get_animation_config,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AnimationController(QObject):
    """Controls frame cycling and state transitions for the character."""

    # Emitted every time the visible frame changes (widget should repaint)
    frame_changed = Signal()
    # Emitted when the active animation state changes
    state_changed = Signal(str)  # state name string

    def __init__(
        self,
        renderer: CharacterRenderer,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._renderer = renderer

        # Current logical state
        self._current_state = CharacterState.IDLE
        self._config: AnimationConfig = get_animation_config(CharacterState.IDLE)

        # State to restore after a transient state (e.g. DRAGGING → previous)
        self._previous_state: Optional[CharacterState] = None

        # Reversion timer for transient duration-based states
        self._revert_timer = QTimer(self)
        self._revert_timer.setSingleShot(True)
        self._revert_timer.timeout.connect(self._on_revert_timeout)

        # Frame timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        self._running = False

        # Timestamp when current animation state was entered
        self._state_enter_time: float = time.monotonic()

        # Apply initial state to renderer
        self._apply_state(self._current_state)

    # ─── Public API ───────────────────────────────────────────────────

    @property
    def current_state(self) -> CharacterState:
        return self._current_state

    @property
    def renderer(self) -> CharacterRenderer:
        return self._renderer

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the animation loop."""
        if self._running:
            return
        self._running = True
        self._timer.start(self._config.frame_interval_ms)
        logger.debug(
            "Animation started (state=%s, fps=%.1f)",
            self._current_state.name, self._config.fps
        )

    def stop(self) -> None:
        """Stop the animation loop (freezes on current frame)."""
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        logger.debug("Animation stopped.")

    def pause(self) -> None:
        """Pause animations without clearing state."""
        self._timer.stop()

    def resume(self) -> None:
        """Resume a paused animation."""
        if self._running:
            self._timer.start(self._config.frame_interval_ms)

    def request_state(
        self,
        state: Union[CharacterState, str],
        duration_sec: Optional[float] = None,
        *,
        force: bool = False,
        broadcast_global: bool = True,
    ) -> bool:
        """Request a state transition with priority rules, optional duration, and signal emission.

        Args:
            state: Target CharacterState enum or case-insensitive string name.
            duration_sec: Optional timeout in seconds to automatically revert back to IDLE.
            force: If True, bypass priority and transition validation.
            broadcast_global: If True, broadcast transition over signals.character_state_changed.

        Returns:
            True if state transition was accepted, False if rejected.
        """
        if isinstance(state, str):
            clean_str = state.strip().upper()
            if clean_str == "TRANSCRIBING":
                clean_str = "THINKING"
            elif clean_str in ("TALKING", "SPEAK"):
                clean_str = "SPEAKING"
            elif clean_str in ("LISTEN", "HEARING"):
                clean_str = "LISTENING"
            elif clean_str in ("READY", "ACTIVE", "WAKE", "WAKING"):
                clean_str = "IDLE"
            try:
                target_state = CharacterState[clean_str]
            except KeyError:
                logger.warning("Unknown character state name: '%s'", state)
                return False
        elif isinstance(state, CharacterState):
            target_state = state
        else:
            logger.warning("Invalid state type: %s", type(state))
            return False

        # If already in the target state, just reset revert timer if duration specified
        if target_state == self._current_state:
            if duration_sec is not None and duration_sec > 0:
                self._revert_timer.stop()
                self._revert_timer.setInterval(int(duration_sec * 1000))
                self._revert_timer.start()
            else:
                self._state_enter_time = time.monotonic()
            return True

        if not force:
            # 1. DRAGGING state has highest priority (10); can only be released to IDLE or forced
            if self._current_state == CharacterState.DRAGGING and target_state != CharacterState.IDLE:
                logger.debug("Transition blocked: pet is currently being dragged.")
                return False

            # 2. SLEEPING state blocks all unforced transitions while sleeping (Phase 6)
            if self._current_state == CharacterState.SLEEPING:
                from app.core.buddy_state_manager import get_buddy_state_manager
                sm = get_buddy_state_manager()
                if sm and sm.is_sleeping and target_state != CharacterState.DRAGGING:
                    logger.debug(
                        "Transition %s → %s blocked: character is sleeping and transition is not forced.",
                        self._current_state.name, target_state.name
                    )
                    return False
                elif target_state not in (CharacterState.IDLE, CharacterState.DRAGGING):
                    logger.debug(
                        "Transition %s → %s blocked: character is sleeping.",
                        self._current_state.name, target_state.name
                    )
                    return False

            # 3. Transitions to IDLE or SLEEPING are always allowed from active states
            if target_state not in (CharacterState.IDLE, CharacterState.SLEEPING):
                curr_prio = self._config.priority
                target_cfg = get_animation_config(target_state)
                # Lower priority cannot interrupt higher priority
                if target_cfg.priority < curr_prio:
                    logger.debug(
                        "Transition %s (prio %d) → %s (prio %d) blocked by priority.",
                        self._current_state.name, curr_prio,
                        target_state.name, target_cfg.priority,
                    )
                    return False

            # 4. Check transition matrix
            if not can_transition(self._current_state, target_state):
                logger.debug(
                    "Transition %s → %s blocked by transition rules.",
                    self._current_state.name, target_state.name,
                )
                return False

        # Cancel any active duration timer
        self._revert_timer.stop()

        # Remember previous state for transient states
        if target_state == CharacterState.DRAGGING or (duration_sec is not None and duration_sec > 0):
            self._previous_state = self._current_state

        old_state = self._current_state
        self._apply_state(target_state)
        self._current_state = target_state
        logger.info("State transition: %s → %s", old_state.name, target_state.name)

        # Set up duration revert timer if requested
        if duration_sec is not None and duration_sec > 0:
            self._revert_timer.setInterval(int(duration_sec * 1000))
            self._revert_timer.start()

        # Emit local state changed signal (lowercase string)
        state_name = target_state.name.lower()
        self.state_changed.emit(state_name)

        # Broadcast globally across central signal bus if requested
        if broadcast_global:
            try:
                from app.core.signals import signals
                signals.character_state_changed.emit(state_name)
            except Exception as e:
                logger.debug("Error emitting character_state_changed: %s", e)

        return True

    def set_state(self, state: CharacterState, *, force: bool = False) -> None:
        """Request a state transition (convenience wrapper around request_state)."""
        self.request_state(state, force=force)

    def restore_previous_state(self) -> None:
        """Return to the state before a transient override (e.g. DRAGGING)."""
        target = self._previous_state or CharacterState.IDLE
        self._previous_state = None
        self.request_state(target, force=True)

    def set_state_by_name(self, name: str, *, force: bool = False) -> None:
        """Convenience: transition by string name (e.g. 'idle', 'listening')."""
        self.request_state(name, force=force)

    # ─── Internals ────────────────────────────────────────────────────

    def _on_revert_timeout(self) -> None:
        """Revert transient duration state back to IDLE upon timer expiration."""
        logger.debug("Transient state '%s' duration elapsed; reverting to IDLE.", self._current_state.name)
        self._previous_state = None
        self.request_state(CharacterState.IDLE, force=True)

    def _apply_state(self, state: CharacterState) -> None:
        """Configure renderer and timer for the given state."""
        self._config = get_animation_config(state)
        self._state_enter_time = time.monotonic()
        self._renderer.set_state(state.name.lower())

        # Update timer interval
        if self._running:
            self._timer.setInterval(self._config.frame_interval_ms)

    def _advance_frame(self) -> None:
        """Called by QTimer — advance to the next frame in the animation."""
        frames = self._renderer._frame_cache.get(
            self._current_state.name.lower(), []
        )
        current_idx = self._renderer._current_frame_index

        # For non-looping animations already on their final frame, hold without looping back to frame 0
        if not self._config.looping and frames and current_idx >= len(frames) - 1:
            changed = False
        else:
            changed = self._renderer.advance_frame()

        if changed:
            self.frame_changed.emit()

        # Handle non-looping animations reaching their last frame or minimum hold duration
        current_idx = self._renderer._current_frame_index
        if not self._config.looping and frames:
            # If an explicit duration revert timer is active, let it control reversion
            if self._revert_timer.isActive():
                return

            # Require minimum hold duration before auto-reverting
            min_hold = getattr(self._config, "min_hold_sec", 2.0)
            elapsed = time.monotonic() - getattr(self, "_state_enter_time", 0.0)

            at_end_of_frames = current_idx >= len(frames) - 1
            max_play_time = len(frames) / max(0.1, self._config.fps)
            if (at_end_of_frames and elapsed >= min_hold) or (elapsed >= max(min_hold, max_play_time)):
                next_st = self._config.next_state or CharacterState.IDLE
                logger.debug(
                    "Non-looping animation '%s' finished (held %.2fs >= %.2fs) → %s",
                    self._current_state.name, elapsed, min_hold, next_st.name,
                )
                self.request_state(next_st, force=True)
