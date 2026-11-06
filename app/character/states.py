"""Character Animation State Machine.

Defines all character states, their animation properties,
valid transitions, and metadata for the animation controller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, FrozenSet, Optional


class CharacterState(Enum):
    """All possible visual/behavioral states of the desktop character."""

    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    HAPPY = auto()
    SLEEPING = auto()
    ERROR = auto()
    DRAGGING = auto()


@dataclass(frozen=True)
class AnimationConfig:
    """Configuration for a single animation state."""

    # Frames per second for this animation
    fps: float = 8.0
    # Whether the animation loops continuously
    looping: bool = True
    # Total frame count expected (used for programmatic generation)
    frame_count: int = 4
    # State to transition to after a non-looping animation completes
    next_state: Optional[CharacterState] = None
    # Priority — higher values interrupt lower ones
    priority: int = 0
    # Minimum duration (seconds) to hold non-looping animations before auto-reverting
    min_hold_sec: float = 2.0

    @property
    def frame_interval_ms(self) -> int:
        """Milliseconds between frames for QTimer."""
        return max(16, int(1000.0 / self.fps))


# Animation configuration registry — one entry per CharacterState
ANIMATION_CONFIGS: Dict[CharacterState, AnimationConfig] = {
    CharacterState.IDLE: AnimationConfig(
        fps=4.0, looping=True, frame_count=8, priority=0,
    ),
    CharacterState.LISTENING: AnimationConfig(
        fps=6.0, looping=True, frame_count=6, priority=2,
    ),
    CharacterState.THINKING: AnimationConfig(
        fps=5.0, looping=True, frame_count=6, priority=2,
    ),
    CharacterState.SPEAKING: AnimationConfig(
        fps=8.0, looping=True, frame_count=6, priority=2,
    ),
    CharacterState.HAPPY: AnimationConfig(
        fps=10.0, looping=False, frame_count=8,
        next_state=CharacterState.IDLE, priority=3,
        min_hold_sec=2.2,
    ),
    CharacterState.SLEEPING: AnimationConfig(
        fps=2.0, looping=True, frame_count=4, priority=1,
    ),
    CharacterState.ERROR: AnimationConfig(
        fps=4.0, looping=False, frame_count=4,
        next_state=CharacterState.IDLE, priority=3,
        min_hold_sec=2.0,
    ),
    CharacterState.DRAGGING: AnimationConfig(
        fps=6.0, looping=True, frame_count=4, priority=10,
    ),
}


# Valid state transitions (from → set of allowed target states)
_TRANSITIONS: Dict[CharacterState, FrozenSet[CharacterState]] = {
    CharacterState.IDLE: frozenset({
        CharacterState.LISTENING,
        CharacterState.THINKING,
        CharacterState.SPEAKING,
        CharacterState.HAPPY,
        CharacterState.SLEEPING,
        CharacterState.ERROR,
        CharacterState.DRAGGING,
    }),
    CharacterState.LISTENING: frozenset({
        CharacterState.IDLE,
        CharacterState.THINKING,
        CharacterState.SPEAKING,
        CharacterState.HAPPY,
        CharacterState.SLEEPING,
        CharacterState.ERROR,
        CharacterState.DRAGGING,
    }),
    CharacterState.THINKING: frozenset({
        CharacterState.IDLE,
        CharacterState.SPEAKING,
        CharacterState.LISTENING,
        CharacterState.HAPPY,
        CharacterState.SLEEPING,
        CharacterState.ERROR,
        CharacterState.DRAGGING,
    }),
    CharacterState.SPEAKING: frozenset({
        CharacterState.IDLE,
        CharacterState.LISTENING,
        CharacterState.THINKING,
        CharacterState.HAPPY,
        CharacterState.SLEEPING,
        CharacterState.ERROR,
        CharacterState.DRAGGING,
    }),
    CharacterState.HAPPY: frozenset({
        CharacterState.IDLE,
        CharacterState.LISTENING,
        CharacterState.SPEAKING,
        CharacterState.SLEEPING,
        CharacterState.DRAGGING,
    }),
    CharacterState.SLEEPING: frozenset({
        CharacterState.IDLE,
        CharacterState.DRAGGING,
    }),
    CharacterState.ERROR: frozenset({
        CharacterState.IDLE,
        CharacterState.SLEEPING,
        CharacterState.DRAGGING,
    }),
    CharacterState.DRAGGING: frozenset({
        CharacterState.IDLE,
        CharacterState.LISTENING,
        CharacterState.THINKING,
        CharacterState.SPEAKING,
        CharacterState.SLEEPING,
        CharacterState.HAPPY,
    }),
}


def can_transition(from_state: CharacterState, to_state: CharacterState) -> bool:
    """Check whether a given state transition is valid."""
    if from_state == to_state:
        return False
    allowed = _TRANSITIONS.get(from_state, frozenset())
    return to_state in allowed


def get_animation_config(state: CharacterState) -> AnimationConfig:
    """Return the animation config for a state, with a sensible default."""
    return ANIMATION_CONFIGS.get(
        state,
        AnimationConfig(fps=4.0, looping=True, frame_count=4, priority=0),
    )
