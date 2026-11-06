"""Tests for Bug #12: Companion Repeatedly Flashes Introductory Greeting on Every Conversation Turn.

Validates:
1. DesktopPetWindow._initial_greeting_shown defaults to False.
2. Initial greeting is displayed only once upon initial pet display or initial IDLE visual state.
3. Subsequent transitions to CharacterState.IDLE (after conversation turn, drag, wake, cancel) do NOT re-trigger the greeting.
4. show_pet() respects _initial_greeting_shown and does not re-introduce the companion on repeated calls.
5. Other visual states (listening, thinking, speaking, happy, sleeping) continue to update correctly without re-triggering idle speech.
6. Custom companion names are dynamically reflected in the initial greeting.
"""

from pathlib import Path
from unittest.mock import MagicMock
import uuid

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent

from app.character.states import CharacterState
from app.desktop.pet_window import DesktopPetWindow
from app.settings.config_manager import ConfigManager

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


def test_initial_greeting_shown_flag_default(qapp_instance) -> None:
    """Verify DesktopPetWindow._initial_greeting_shown defaults to False upon instantiation."""
    config_file = SCRATCH_DIR / f"test_pet_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)

    assert hasattr(pet, "_initial_greeting_shown")
    assert pet._initial_greeting_shown is False

    pet.close()
    if config_file.exists():
        config_file.unlink()


def test_initial_idle_state_shows_greeting_and_sets_flag(qapp_instance) -> None:
    """Verify initial IDLE visual state shows greeting bubble once and sets _initial_greeting_shown = True."""
    config_file = SCRATCH_DIR / f"test_pet_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    cfg.set("ai.companion_name", "Buddy")
    pet = DesktopPetWindow(config_manager=cfg)
    pet.resize(120, 120)
    pet.show()

    assert pet._initial_greeting_shown is False

    # Apply visual state idle initially
    pet._apply_visual_state("idle")

    assert pet._initial_greeting_shown is True
    assert pet.speech_bubble.isVisible() is True
    assert "Hey! 👋 I'm Buddy!" in pet.speech_bubble.label.text()

    pet.close()
    if config_file.exists():
        config_file.unlink()


def test_subsequent_idle_state_does_not_show_greeting(qapp_instance) -> None:
    """Verify subsequent transitions to IDLE do NOT display the introductory greeting."""
    config_file = SCRATCH_DIR / f"test_pet_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)
    pet.resize(120, 120)
    pet.show()

    # Trigger initial greeting
    pet._apply_visual_state("idle")
    assert pet._initial_greeting_shown is True

    # Dismiss / hide speech bubble
    pet.speech_bubble.hide_bubble()
    pet.speech_bubble.label.setText("")

    # Spy on show_message
    spy = MagicMock(wraps=pet.speech_bubble.show_message)
    pet.speech_bubble.show_message = spy

    # Re-apply visual state idle (simulating return to idle after TTS / speech)
    pet._apply_visual_state("idle")

    # show_message should NOT have been called with the introductory greeting
    spy.assert_not_called()
    assert pet.speech_bubble.label.text() == ""

    pet.close()
    if config_file.exists():
        config_file.unlink()


def test_show_pet_shows_greeting_only_once(qapp_instance) -> None:
    """Verify show_pet() only shows greeting on initial display and not on subsequent calls."""
    config_file = SCRATCH_DIR / f"test_pet_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    cfg.set("ai.companion_name", "Buddy")
    pet = DesktopPetWindow(config_manager=cfg)

    # First show_pet call
    pet.show_pet()
    assert pet._initial_greeting_shown is True
    assert pet.speech_bubble.isVisible() is True
    assert "Hey! 👋 I'm Buddy!" in pet.speech_bubble.label.text()

    # Clear bubble and spy
    pet.speech_bubble.hide_bubble()
    spy = MagicMock(wraps=pet.speech_bubble.show_message)
    pet.speech_bubble.show_message = spy

    # Second show_pet call (e.g. unhiding from system tray)
    pet.show_pet()
    spy.assert_not_called()

    # Subsequent idle transition
    pet.set_state(CharacterState.IDLE)
    spy.assert_not_called()

    pet.close()
    if config_file.exists():
        config_file.unlink()


def test_state_transitions_to_idle_do_not_flash_greeting(qapp_instance) -> None:
    """Verify full conversation cycle (listening -> thinking -> speaking -> idle) does not flash greeting."""
    config_file = SCRATCH_DIR / f"test_pet_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    cfg.set("ai.companion_name", "Buddy")
    pet = DesktopPetWindow(config_manager=cfg)
    pet.show_pet()

    greeting_text = "Hey! 👋 I'm Buddy!"
    assert greeting_text in pet.speech_bubble.label.text()

    # Now spy on show_message to track all calls
    spy = MagicMock(wraps=pet.speech_bubble.show_message)
    pet.speech_bubble.show_message = spy

    # Transition to LISTENING
    pet.set_state(CharacterState.LISTENING)
    spy.assert_called_with("I'm listening...", pet.frameGeometry(), duration_ms=3200)

    # Transition to THINKING
    pet.set_state(CharacterState.THINKING)
    spy.assert_called_with("Thinking...", pet.frameGeometry(), duration_ms=3200)

    # Transition to SPEAKING
    pet.set_state(CharacterState.SPEAKING)
    spy.assert_called_with("Let me tell you...", pet.frameGeometry(), duration_ms=3200)

    # Transition back to IDLE (after TTS completes)
    spy.reset_mock()
    pet.set_state(CharacterState.IDLE)

    # Must NOT call show_message with the greeting!
    for call in spy.call_args_list:
        assert greeting_text not in call[0][0]
    assert spy.call_count == 0

    pet.close()
    if config_file.exists():
        config_file.unlink()


def test_sleep_wake_cycle_does_not_reflash_greeting(qapp_instance) -> None:
    """Verify transitioning to SLEEPING and back to IDLE does not flash introductory greeting."""
    config_file = SCRATCH_DIR / f"test_pet_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)
    pet.show_pet()

    greeting_text = f"Hey! 👋 I'm {pet.config_manager.get('ai.companion_name', 'Buddy')}!"

    spy = MagicMock(wraps=pet.speech_bubble.show_message)
    pet.speech_bubble.show_message = spy

    # Go to sleeping
    pet.set_state(CharacterState.SLEEPING)
    spy.assert_called_with("Z z z ...", pet.frameGeometry(), duration_ms=2500)

    # Wake up back to idle
    spy.reset_mock()
    pet.set_state(CharacterState.IDLE)

    # Greeting should not re-flash
    assert spy.call_count == 0

    pet.close()
    if config_file.exists():
        config_file.unlink()


def test_drag_release_does_not_reflash_greeting(qapp_instance) -> None:
    """Verify releasing pet after drag restores previous state without re-flashing greeting."""
    config_file = SCRATCH_DIR / f"test_pet_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)
    pet.show_pet()

    # Simulate drag state
    pet._is_dragging = True
    pet._mouse_press_pos = QPoint(100, 100)
    pet._mouse_press_global = QPoint(10, 10)

    spy = MagicMock(wraps=pet.speech_bubble.show_message)
    pet.speech_bubble.show_message = spy

    # Simulate mouse release
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(150, 150),
        QPoint(150, 150),
        Qt.LeftButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    pet.mouseReleaseEvent(event)

    # Verify drag ended and idle did not flash greeting
    assert pet._is_dragging is False
    assert spy.call_count == 0

    pet.close()
    if config_file.exists():
        config_file.unlink()


def test_custom_companion_name_used_in_greeting(qapp_instance) -> None:
    """Verify configured companion name (e.g. 'Jarvis') is reflected in initial greeting."""
    config_file = SCRATCH_DIR / f"test_pet_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    cfg.set("ai.companion_name", "Jarvis")
    pet = DesktopPetWindow(config_manager=cfg)

    pet.show_pet()
    assert pet._initial_greeting_shown is True
    assert "Hey! 👋 I'm Jarvis!" in pet.speech_bubble.label.text()

    pet.close()
    if config_file.exists():
        config_file.unlink()
