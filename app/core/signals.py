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
    reset_pet_position_requested = Signal()
    pet_visibility_changed = Signal(bool)
    pet_moved = Signal(int, int)  # x, y

    # System & Lifecycle
    activate_requested = Signal()
    shutdown_requested = Signal()

    # Character State
    character_state_changed = Signal(str)  # idle, listening, thinking, speaking, etc.
    character_size_changed = Signal(int)   # new pixel size

    # Voice & Audio
    voice_state_changed = Signal(str)      # muted, listening, processing, speaking
    voice_transcription_ready = Signal(str) # transcription text
    user_speech_interim = Signal(str)      # progressive interim user speech transcription
    user_speech_final = Signal(str)        # finalized verified user speech transcription
    ai_speech_subtitle = Signal(str)       # synchronized AI spoken sentence subtitle (Phase 2)
    ai_speech_finished = Signal()          # AI speech playback completed or stopped (Phase 2)
    voice_toggle_requested = Signal()      # toggle voice on/off
    emergency_stop_requested = Signal()    # emergency stop listening immediately (Phase 9.9)
    wake_word_detected = Signal(str, float) # wake phrase, score (Phase 9.5)
    activation_mode_changed = Signal(str)  # "push_to_talk", "wake_word", "continuous", "off" (Phase 9.8)
    voice_profile_changed = Signal(str)    # new voice profile_id e.g. "arjun", "mira" (Phase 1)

    # AI & Memory
    ai_response_chunk = Signal(str)        # streaming chunk
    ai_response_complete = Signal(str)     # full response
    ai_generation_started = Signal(str)    # prompt text
    ai_generation_cancelled = Signal()     # generation was cancelled
    ai_cancel_requested = Signal()         # request to cancel generation
    ai_error_occurred = Signal(str)        # error message
    model_routed = Signal(dict)            # routing decision dict (Phase 4): task, model, ui_badge
    user_emotion_detected = Signal(str, float) # emotion ("happy", "excited", etc.), confidence (Phase 10.8)
    adaptive_style_changed = Signal(str)       # style name ("quick_answer", "detailed_explanation", etc.) (Phase 5)
    memory_stored = Signal(object)         # Memory instance added (Phase 10.3)
    memory_updated = Signal(object)        # Memory instance updated (Phase 10.5)
    memory_deleted = Signal(str)           # memory_id (Phase 10.6)

    # Chat Window Controls
    open_chat_requested = Signal()
    close_chat_requested = Signal()
    minimize_chat_requested = Signal()
    maximize_chat_requested = Signal()
    drag_chat_requested = Signal()
    move_chat_delta = Signal(int, int)

    # Voice Window Controls
    open_voice_window_requested = Signal()
    close_voice_window_requested = Signal()
    toggle_voice_window_requested = Signal()

    # Settings
    open_settings_requested = Signal()
    setting_updated = Signal(str, object)  # key_path, new_value

    # Always-on-top / Click-through
    always_on_top_changed = Signal(bool)
    click_through_changed = Signal(bool)

    # ─── Phase 3 — Application Mode & Background ─────────────────────

    # Application mode transitions (active / sleeping / hidden)
    app_mode_changed = Signal(str)       # mode name string
    sleep_requested = Signal()           # request transition to sleeping
    wake_requested = Signal()            # request transition to active

    # Animation control
    animation_pause_requested = Signal()
    animation_resume_requested = Signal()

    # Windows startup
    startup_enabled_changed = Signal(bool)  # whether auto-start is on/off

    # Movie Hub Controls (Phase 11 Voice-Powered Discovery)
    open_movie_hub_requested = Signal()
    movie_voice_search_requested = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)


# Shared global bus instance
signals = AppSignals()
