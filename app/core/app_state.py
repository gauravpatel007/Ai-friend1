"""Application State Manager.

Manages the three primary operating states of the application:
- Active: Character visible, AI available, animations running.
- Sleeping: Character visible, mic disabled, heavy models unloaded.
- Hidden: Character invisible, app lives in system tray only.

Coordinates resource optimization across modules when states change.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QObject, Signal

from app.utils.logger import get_logger

logger = get_logger(__name__)


class AppMode(Enum):
    """Primary operating modes of the application."""

    ACTIVE = auto()
    SLEEPING = auto()
    HIDDEN = auto()


class AppStateManager(QObject):
    """Manages transitions between application operating modes."""

    # Emitted when the app mode changes, carries the new AppMode name
    mode_changed = Signal(str)
    # Granular resource signals for subscribers
    animations_enabled_changed = Signal(bool)
    voice_capture_enabled_changed = Signal(bool)
    ai_services_enabled_changed = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._mode = AppMode.ACTIVE

    @property
    def mode(self) -> AppMode:
        return self._mode

    @property
    def is_active(self) -> bool:
        return self._mode == AppMode.ACTIVE

    @property
    def is_sleeping(self) -> bool:
        return self._mode == AppMode.SLEEPING

    @property
    def is_hidden(self) -> bool:
        return self._mode == AppMode.HIDDEN

    def set_mode(self, mode: AppMode) -> None:
        """Transition to a new application mode."""
        if mode == self._mode:
            return

        old_mode = self._mode
        self._mode = mode

        logger.info("Application mode: %s → %s", old_mode.name, mode.name)
        self.mode_changed.emit(mode.name.lower())

        # Emit resource-level signals based on the new mode
        if mode == AppMode.ACTIVE:
            self.animations_enabled_changed.emit(True)
            self.voice_capture_enabled_changed.emit(True)
            self.ai_services_enabled_changed.emit(True)

        elif mode == AppMode.SLEEPING:
            self.animations_enabled_changed.emit(True)   # Still show sleep anim
            self.voice_capture_enabled_changed.emit(False)
            self.ai_services_enabled_changed.emit(False)

        elif mode == AppMode.HIDDEN:
            self.animations_enabled_changed.emit(False)
            self.voice_capture_enabled_changed.emit(False)
            self.ai_services_enabled_changed.emit(False)

    def set_mode_by_name(self, name: str) -> None:
        """Set mode from a string (e.g. 'active', 'sleeping', 'hidden')."""
        try:
            mode = AppMode[name.upper()]
        except KeyError:
            logger.warning("Unknown app mode name: '%s'", name)
            return
        self.set_mode(mode)

    def wake_up(self) -> None:
        """Convenience: transition from any mode back to ACTIVE."""
        self.set_mode(AppMode.ACTIVE)

    def sleep(self) -> None:
        """Convenience: transition to SLEEPING."""
        self.set_mode(AppMode.SLEEPING)

    def go_hidden(self) -> None:
        """Convenience: transition to HIDDEN."""
        self.set_mode(AppMode.HIDDEN)
