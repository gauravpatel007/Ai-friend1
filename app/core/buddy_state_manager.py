"""Centralized Buddy Companion State Manager (Phase 1 & Phase 2).

Provides a single source of truth for Buddy's operating states:
- ACTIVE: Buddy listens to the user, processes voice commands, normal AI conversations work,
  text chat works, and voice responses speak aloud.
- SLEEPING: Buddy does not process ordinary voice commands or generate AI responses to ordinary speech,
  Buddy does not speak. The desktop application remains open, and the wake-word detection
  mechanism remains operational to listen for explicit wake commands.
- MUTED: Buddy does not speak (audio output suppressed), but voice input and text chat remain
  available. A separate unmute command restores speech output.
"""

from __future__ import annotations

from enum import Enum
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from app.core.signals import signals
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BuddyState(str, Enum):
    """Primary companion operational states."""

    ACTIVE = "active"
    SLEEPING = "sleeping"
    MUTED = "muted"


class BuddyStateManager(QObject):
    """Centralized state machine and coordinator for Buddy companion states."""

    # State transition signals
    state_changed = Signal(str, str)     # (old_state, new_state)
    entered_sleep = Signal(str)          # (reason)
    woken_up = Signal(str)               # (reason)
    muted = Signal(str)                  # (reason)
    unmuted = Signal(str)                # (reason)

    def __init__(self, parent: Optional[QObject] = None, audio_player: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        # Requirement 1: Bond must ALWAYS start in SLEEP MODE when the application launches
        self._state: BuddyState = BuddyState.SLEEPING
        self._previous_state: BuddyState = BuddyState.SLEEPING
        self.audio_player = audio_player
        logger.info("[BUDDY_STATE] Initialized in strict SLEEP MODE (resting default state).")

    def set_audio_player(self, player: Any) -> None:
        """Register audio player to halt playback upon sleep."""
        self.audio_player = player

    # ─── State Inspection Properties ───────────────────────────────────

    @property
    def state(self) -> BuddyState:
        """Current companion state."""
        with self._lock:
            return self._state

    def get_state(self) -> BuddyState:
        """Return the current companion state."""
        with self._lock:
            return self._state

    def set_state(self, new_state: BuddyState) -> None:
        """Set companion state directly."""
        with self._lock:
            old_state = self._state
            self._state = new_state
            if old_state != new_state:
                self.state_changed.emit(old_state.value, new_state.value)

    @property
    def state_name(self) -> str:
        """String representation of current state ('active', 'sleeping', 'muted')."""
        with self._lock:
            return self._state.value

    @property
    def is_active(self) -> bool:
        """Return True if Buddy is awake and unmuted."""
        with self._lock:
            return self._state == BuddyState.ACTIVE

    @property
    def is_sleeping(self) -> bool:
        """Return True if Buddy is currently in sleep mode."""
        with self._lock:
            return self._state == BuddyState.SLEEPING

    @property
    def is_muted(self) -> bool:
        """Return True if Buddy's spoken audio output is muted."""
        with self._lock:
            return self._state == BuddyState.MUTED

    @property
    def can_process_speech(self) -> bool:
        """Return True if user speech can be routed to AI conversation (ACTIVE or MUTED)."""
        with self._lock:
            return self._state != BuddyState.SLEEPING

    @property
    def can_speak(self) -> bool:
        """Return True if Buddy is permitted to speak aloud via TTS (only when ACTIVE)."""
        with self._lock:
            return self._state == BuddyState.ACTIVE

    @property
    def is_wake_word_only(self) -> bool:
        """Return True if voice system should operate in wake-word detection standby."""
        with self._lock:
            return self._state == BuddyState.SLEEPING

    # ─── State Transitions ─────────────────────────────────────────────

    @Slot(str)
    def enter_sleep(self, reason: str = "user_command") -> bool:
        """Transition Buddy to SLEEPING state.

        Immediately halts speech synthesis, stops audio playback, cancels pending
        AI generation, blocks ordinary voice routing, transitions character animation
        to sleeping, and leaves the wake-word detector active.
        """
        with self._lock:
            if self._state == BuddyState.SLEEPING:
                logger.debug("BuddyStateManager.enter_sleep ignored: already sleeping.")
                return False

            old_state = self._state
            self._previous_state = old_state
            self._state = BuddyState.SLEEPING

        logger.info(
            "Buddy State Transition: %s → SLEEPING (reason: '%s')",
            old_state.value, reason,
        )

        # 1. Immediately cancel ongoing AI generation and stop audio playback
        try:
            signals.ai_cancel_requested.emit()
            if hasattr(self, "audio_player") and self.audio_player and hasattr(self.audio_player, "stop"):
                self.audio_player.stop()
            signals.ai_speech_finished.emit()
        except Exception as e:
            logger.debug("Error emitting stop signals during sleep: %s", e)

        # 2. Emit companion state transitions
        self.entered_sleep.emit(reason)
        self.state_changed.emit(old_state.value, BuddyState.SLEEPING.value)

        # 3. Synchronize with global application signals
        try:
            signals.app_mode_changed.emit("sleeping")
            signals.character_state_changed.emit("sleeping")
        except Exception as e:
            logger.debug("Error notifying UI signals of sleep: %s", e)

        return True

    @Slot(str)
    def wake_up(self, reason: str = "wake_command") -> bool:
        """Transition Buddy from SLEEPING to ACTIVE state.

        Restores character to idle/awake state, restores configured voice mode,
        and re-enables ordinary voice conversations.
        """
        with self._lock:
            if self._state != BuddyState.SLEEPING:
                logger.debug("BuddyStateManager.wake_up ignored: not sleeping (current=%s).", self._state.value)
                return False

            old_state = self._state
            # Return to ACTIVE (or previous unmuted state)
            new_state = BuddyState.ACTIVE
            self._previous_state = old_state
            self._state = new_state

        logger.info(
            "Buddy State Transition: SLEEPING → %s (reason: '%s')",
            new_state.value, reason,
        )

        # 1. Emit transition signals
        self.woken_up.emit(reason)
        self.state_changed.emit(old_state.value, new_state.value)

        # 2. Synchronize character animation & app mode
        try:
            signals.app_mode_changed.emit("active")
            signals.character_state_changed.emit("idle")
            signals.voice_state_changed.emit("listening")
        except Exception as e:
            logger.debug("Error notifying UI signals of wake: %s", e)

        return True

    @Slot(bool, str)
    def set_muted(self, muted: bool, reason: str = "user_command") -> bool:
        """Mute or unmute Buddy's spoken voice output."""
        with self._lock:
            old_state = self._state
            if muted:
                if self._state == BuddyState.MUTED:
                    return False
                if self._state == BuddyState.SLEEPING:
                    # In sleep mode, recording that unmuted is False
                    return False
                new_state = BuddyState.MUTED
            else:
                if self._state != BuddyState.MUTED:
                    return False
                new_state = BuddyState.ACTIVE

            self._previous_state = old_state
            self._state = new_state

        logger.info(
            "Buddy State Transition: %s → %s (reason: '%s')",
            old_state.value, new_state.value, reason,
        )

        if muted:
            self.muted.emit(reason)
        else:
            self.unmuted.emit(reason)

        self.state_changed.emit(old_state.value, new_state.value)
        return True

    @property
    def autonomous_messages_allowed(self) -> bool:
        """Return True if autonomous unsolicited messages are permitted. Strictly False while sleeping."""
        with self._lock:
            if self._state == BuddyState.SLEEPING:
                return False
            return False

    def reset(self, initial_state: BuddyState = BuddyState.SLEEPING) -> None:
        """Reset state manager to default SLEEPING state."""
        with self._lock:
            self._state = initial_state
            self._previous_state = initial_state


# ─── Singleton Accessor ────────────────────────────────────────────────────────

_buddy_state_manager_instance: Optional[BuddyStateManager] = None
_instance_lock = threading.Lock()


def get_buddy_state_manager() -> BuddyStateManager:
    """Return the centralized singleton BuddyStateManager instance."""
    global _buddy_state_manager_instance
    if _buddy_state_manager_instance is None:
        with _instance_lock:
            if _buddy_state_manager_instance is None:
                _buddy_state_manager_instance = BuddyStateManager()
    return _buddy_state_manager_instance

