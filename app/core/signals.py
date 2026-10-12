"""Central Application Signal Bus.

Provides decoupled Qt signals for inter-module event coordination.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    """Central singleton-like signal bus for the application."""

    # UI / Window Actions
    show_pet_requested = Signal()
    hide_pet_requested = Signal()
    toggle_pet_requested = Signal()
    pet_visibility_changed = Signal(bool)
    pet_moved = Signal(int, int)  # x, y

    # System & Lifecycle
    activate_requested = Signal()
    shutdown_requested = Signal()

    # Character State
    character_state_changed = Signal(str)  # idle, listening, thinking, speaking, etc.

    # Voice & Audio
    voice_state_changed = Signal(str)      # muted, listening, processing, speaking
    voice_transcription_ready = Signal(str) # transcription text

    # AI & Memory
    ai_response_chunk = Signal(str)        # streaming chunk
    ai_response_complete = Signal(str)     # full response

    # Settings
    setting_updated = Signal(str, object)  # key_path, new_value

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)


# Shared global bus instance
signals = AppSignals()
