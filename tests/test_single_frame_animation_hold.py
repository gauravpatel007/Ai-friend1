"""Tests for Single-Frame Animation Minimum Hold Duration (Bug #24).

Verifies that non-looping animations like HAPPY and ERROR do not vanish after 100ms
when sprite assets have only a single frame, and are held for min_hold_sec.
"""

from pathlib import Path
import time
from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.character.animation_controller import AnimationController
from app.character.renderer import CharacterRenderer
from app.character.states import AnimationConfig, CharacterState, get_animation_config


@pytest.fixture
def anim_controller(qapp_instance):
    renderer = CharacterRenderer(character_name="robot", size=120)
    controller = AnimationController(renderer=renderer)
    controller.start()
    yield controller
    controller.stop()


def test_happy_does_not_revert_after_100ms(anim_controller: AnimationController, qtbot):
    """Bug #24: HAPPY must not vanish after 100ms when robot asset is single-frame."""
    # Ensure robot has 1 frame for happy
    frames = anim_controller.renderer._frame_cache.get("happy", [])
    assert len(frames) >= 1

    assert anim_controller.request_state(CharacterState.HAPPY) is True
    assert anim_controller.current_state == CharacterState.HAPPY

    # Wait 250ms (well past the old 100ms bug window where it used to revert)
    qtbot.wait(250)

    # Must still be HAPPY
    assert anim_controller.current_state == CharacterState.HAPPY


def test_happy_holds_for_min_hold_duration_then_reverts(anim_controller: AnimationController):
    """Bug #24: Verify HAPPY holds until min_hold_sec has elapsed, then reverts to IDLE."""
    anim_controller.request_state(CharacterState.HAPPY)
    assert anim_controller.current_state == CharacterState.HAPPY

    config = get_animation_config(CharacterState.HAPPY)
    assert config.min_hold_sec >= 2.0

    # Advance frame multiple times while elapsed < min_hold_sec
    anim_controller._state_enter_time = time.monotonic() - 0.5  # 0.5s elapsed
    anim_controller._advance_frame()
    assert anim_controller.current_state == CharacterState.HAPPY

    anim_controller._state_enter_time = time.monotonic() - 1.5  # 1.5s elapsed
    anim_controller._advance_frame()
    assert anim_controller.current_state == CharacterState.HAPPY

    # Now simulate elapsed >= min_hold_sec (e.g. 2.3s)
    anim_controller._state_enter_time = time.monotonic() - 2.5
    anim_controller._advance_frame()

    # Reverted to IDLE
    assert anim_controller.current_state == CharacterState.IDLE


def test_non_looping_multi_frame_holds_on_final_frame(anim_controller: AnimationController):
    """Verify multi-frame non-looping animation stays on last frame instead of looping back to 0."""
    # Mock a 3-frame cache for 'happy'
    mock_frames = [MagicMock(), MagicMock(), MagicMock()]
    anim_controller.renderer._frame_cache["happy"] = mock_frames

    anim_controller.request_state(CharacterState.HAPPY)
    anim_controller._state_enter_time = time.monotonic()

    # Step to frame 1
    anim_controller._advance_frame()
    assert anim_controller.renderer._current_frame_index == 1

    # Step to frame 2 (last frame)
    anim_controller._advance_frame()
    assert anim_controller.renderer._current_frame_index == 2

    # Step again while elapsed < min_hold: must freeze on frame 2 without looping to 0
    anim_controller._advance_frame()
    assert anim_controller.renderer._current_frame_index == 2
    assert anim_controller.current_state == CharacterState.HAPPY


def test_caller_duration_sec_overrides_min_hold(anim_controller: AnimationController, qtbot):
    """Verify explicit duration_sec (e.g. 100ms) overrides min_hold via _revert_timer."""
    assert anim_controller.request_state(CharacterState.HAPPY, duration_sec=0.1) is True
    assert anim_controller.current_state == CharacterState.HAPPY

    # Wait for explicit duration timeout (150ms)
    qtbot.wait(150)

    # Reverted to IDLE automatically via revert timer
    assert anim_controller.current_state == CharacterState.IDLE


def test_repeated_happy_request_extends_hold_time(anim_controller: AnimationController):
    """Requesting HAPPY again while already in HAPPY refreshes _state_enter_time."""
    anim_controller.request_state(CharacterState.HAPPY)
    old_time = time.monotonic() - 1.5
    anim_controller._state_enter_time = old_time

    # Call again without duration
    anim_controller.request_state(CharacterState.HAPPY)
    assert anim_controller._state_enter_time > old_time
