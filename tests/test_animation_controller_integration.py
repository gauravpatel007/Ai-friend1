"""Integration tests for Bug 14: AnimationController & DesktopPetWindow Integration.

Validates:
1. DesktopPetWindow instantiates and exposes AnimationController as self.anim_controller.
2. request_state() parses CharacterState enums and strings.
3. State priority rules, transitions, and blocking behaviors.
4. Transient states with duration_sec automatic timeout reversion to IDLE.
5. DesktopPetWindow reactivity: renderer frames, speech bubble, and animation timer intervals.
6. ApplicationController lifecycle hooks (speech, transcription, speaking, finished, emotion,
   wake word, sleep mode, wake up) driving character animation states.
7. Central signal bus broadcasting and loop prevention.
"""

from pathlib import Path
import time
from unittest.mock import MagicMock, patch
import uuid

import pytest
from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication

from app.character.animation_controller import AnimationController
from app.character.states import CharacterState
from app.core.controller import ApplicationController
from app.core.signals import signals
from app.desktop.pet_window import DesktopPetWindow
from app.settings.config_manager import ConfigManager

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


# ─── 1. Instantiation & Connection Tests ────────────────────────────────────────

def test_anim_controller_instantiation_in_pet_window(qapp_instance):
    """Verify DesktopPetWindow instantiates anim_controller wired to CharacterRenderer."""
    config_file = SCRATCH_DIR / f"test_anim_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)

    # 1. anim_controller is present and is an AnimationController instance
    assert hasattr(pet, "anim_controller")
    assert isinstance(pet.anim_controller, AnimationController)

    # 2. anim_controller shares pet renderer
    assert pet.anim_controller.renderer is pet.renderer

    # 3. Default state is IDLE and animation loop is running
    assert pet.anim_controller.current_state == CharacterState.IDLE
    assert pet.anim_controller.is_running is True

    pet.close()
    if config_file.exists():
        config_file.unlink()


# ─── 2. State Request Parsing & Basic Transitions ─────────────────────────────

def test_request_state_enums_and_strings(qapp_instance):
    """Verify request_state accepts CharacterState enums and case-insensitive strings."""
    config_file = SCRATCH_DIR / f"test_anim_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)
    ctrl = pet.anim_controller

    # Enum member
    assert ctrl.request_state(CharacterState.LISTENING) is True
    assert ctrl.current_state == CharacterState.LISTENING

    # Lowercase string
    assert ctrl.request_state("thinking") is True
    assert ctrl.current_state == CharacterState.THINKING

    # Uppercase string
    assert ctrl.request_state("SPEAKING") is True
    assert ctrl.current_state == CharacterState.SPEAKING

    # Back to IDLE
    assert ctrl.request_state("idle") is True
    assert ctrl.current_state == CharacterState.IDLE

    # Invalid string rejected
    assert ctrl.request_state("non_existent_state") is False
    assert ctrl.current_state == CharacterState.IDLE

    # Invalid type rejected
    assert ctrl.request_state(12345) is False  # type: ignore[arg-type]
    assert ctrl.current_state == CharacterState.IDLE

    pet.close()
    if config_file.exists():
        config_file.unlink()


# ─── 3. Priority Evaluation & Blocking Rules ──────────────────────────────────

def test_state_priority_evaluation(qapp_instance):
    """Verify state priorities: lower priority cannot interrupt higher priority without force."""
    config_file = SCRATCH_DIR / f"test_anim_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)
    ctrl = pet.anim_controller

    # 1. HAPPY (priority 3) interrupts SPEAKING (priority 2)
    ctrl.request_state(CharacterState.SPEAKING)
    assert ctrl.current_state == CharacterState.SPEAKING
    assert ctrl.request_state(CharacterState.HAPPY) is True
    assert ctrl.current_state == CharacterState.HAPPY

    # 2. LISTENING (priority 2) cannot interrupt HAPPY (priority 3)
    assert ctrl.request_state(CharacterState.LISTENING) is False
    assert ctrl.current_state == CharacterState.HAPPY

    # 3. IDLE (priority 0) can always be restored (resting state)
    assert ctrl.request_state(CharacterState.IDLE) is True
    assert ctrl.current_state == CharacterState.IDLE

    # 4. SLEEPING state blocks non-wake events (e.g. background speech)
    assert ctrl.request_state(CharacterState.SLEEPING) is True
    assert ctrl.current_state == CharacterState.SLEEPING

    assert ctrl.request_state(CharacterState.LISTENING) is False
    assert ctrl.request_state(CharacterState.SPEAKING) is False
    assert ctrl.request_state(CharacterState.HAPPY) is False
    assert ctrl.current_state == CharacterState.SLEEPING

    # Wake up back to IDLE succeeds
    assert ctrl.request_state(CharacterState.IDLE) is True
    assert ctrl.current_state == CharacterState.IDLE

    # 5. DRAGGING (priority 10) blocks lower priority events until released
    assert ctrl.request_state(CharacterState.DRAGGING, force=True) is True
    assert ctrl.current_state == CharacterState.DRAGGING

    assert ctrl.request_state(CharacterState.SPEAKING) is False
    assert ctrl.current_state == CharacterState.DRAGGING

    ctrl.restore_previous_state()
    assert ctrl.current_state == CharacterState.IDLE

    pet.close()
    if config_file.exists():
        config_file.unlink()


# ─── 4. Duration Timeout & Reversion ──────────────────────────────────────────

def test_request_state_duration_timeout(qapp_instance, qtbot):
    """Verify transient state with duration_sec automatically reverts back to IDLE."""
    config_file = SCRATCH_DIR / f"test_anim_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)
    ctrl = pet.anim_controller

    # Request HAPPY for 0.08 seconds (80 ms)
    assert ctrl.request_state(CharacterState.HAPPY, duration_sec=0.08) is True
    assert ctrl.current_state == CharacterState.HAPPY

    # Wait for timeout to fire (120ms)
    qtbot.wait(120)

    # Reverted to IDLE automatically
    assert ctrl.current_state == CharacterState.IDLE

    # Test interrupting a duration state before timer fires cancels the revert
    assert ctrl.request_state(CharacterState.HAPPY, duration_sec=0.20) is True
    assert ctrl.current_state == CharacterState.HAPPY

    qtbot.wait(40)
    # Transition to SLEEPING
    assert ctrl.request_state(CharacterState.SLEEPING) is True
    assert ctrl.current_state == CharacterState.SLEEPING

    # Wait out the original timer duration
    qtbot.wait(200)
    # Should NOT have reverted to IDLE because the HAPPY duration timer was cancelled!
    assert ctrl.current_state == CharacterState.SLEEPING

    pet.close()
    if config_file.exists():
        config_file.unlink()


# ─── 5. DesktopPetWindow Reactivity ───────────────────────────────────────────

def test_pet_window_reactivity_to_anim_controller(qapp_instance):
    """Verify DesktopPetWindow synchronizes renderer, speech bubble, and anim timers on state change."""
    config_file = SCRATCH_DIR / f"test_anim_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    cfg.set("pet.animation_fps", 30)
    pet = DesktopPetWindow(config_manager=cfg)

    # 1. State change to LISTENING
    pet.anim_controller.request_state(CharacterState.LISTENING)
    assert pet.renderer._current_state == "listening"
    assert pet._anim_timer.interval() == pytest.approx(33, abs=2)

    # 2. State change to SLEEPING throttles timer to 500ms (2 FPS)
    pet.anim_controller.request_state(CharacterState.SLEEPING)
    assert pet.renderer._current_state == "sleeping"
    assert pet._anim_timer.interval() == 500

    # 3. Direct pet.set_state updates both anim_controller and renderer
    pet.set_state("thinking")
    assert pet.anim_controller.current_state == CharacterState.THINKING
    assert pet.renderer._current_state == "thinking"
    assert pet._anim_timer.interval() == pytest.approx(33, abs=2)

    pet.close()
    if config_file.exists():
        config_file.unlink()


# ─── 6. ApplicationController Lifecycle Integration ───────────────────────────

def test_application_controller_lifecycle_hooks(qapp_instance):
    """Verify all 8 ApplicationController lifecycle hooks smoothly update pet.anim_controller."""
    config_file = SCRATCH_DIR / f"test_anim_ctrl_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    cfg.set("pet.animation_fps", 30)

    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)

    with patch("app.ai.ai_service.AIService"), \
         patch("app.voice.voice_service.VoiceService") as mock_voice_cls, \
         patch("app.desktop.modern_chat_window.ModernChatWindow"), \
         patch.object(ctrl, "_start_api_server"):
        init_ok = ctrl.initialize()
        assert init_ok is True

    pet = ctrl.pet_window
    assert pet is not None
    assert hasattr(pet, "anim_controller")
    anim = pet.anim_controller

    # 1. Speech detected -> LISTENING
    ctrl._on_speech_detected()
    assert anim.current_state == CharacterState.LISTENING
    assert pet.renderer._current_state == "listening"

    # 2. Transcription started -> THINKING
    ctrl._on_transcription_started()
    assert anim.current_state == CharacterState.THINKING
    assert pet.renderer._current_state == "thinking"

    # 3. Speaking started -> SPEAKING
    ctrl._on_speaking_started()
    assert anim.current_state == CharacterState.SPEAKING
    assert pet.renderer._current_state == "speaking"

    # 4. Speaking finished -> IDLE
    ctrl._on_speaking_finished()
    assert anim.current_state == CharacterState.IDLE
    assert pet.renderer._current_state == "idle"

    # 5. User emotion detected (happy with high confidence) -> HAPPY
    ctrl._on_user_emotion_detected("happy", 0.85)
    assert anim.current_state == CharacterState.HAPPY
    assert pet.renderer._current_state == "happy"

    # Revert to IDLE for next test
    anim.request_state(CharacterState.IDLE, force=True)

    # 6. Wake word detected -> LISTENING
    ctrl._on_wake_word_detected("buddy", 0.92)
    assert anim.current_state == CharacterState.LISTENING
    assert pet.renderer._current_state == "listening"

    # 7. Enter sleep mode -> SLEEPING (throttled)
    ctrl.enter_sleep_mode()
    assert anim.current_state == CharacterState.SLEEPING
    assert pet.renderer._current_state == "sleeping"
    assert pet._anim_timer.interval() == 500

    # 8. Wake up -> IDLE (normal interval restored)
    ctrl.wake_up()
    assert anim.current_state == CharacterState.IDLE
    assert pet.renderer._current_state == "idle"
    assert pet._anim_timer.interval() == pytest.approx(33, abs=2)

    ctrl.shutdown()
    if config_file.exists():
        config_file.unlink()


# ─── 7. Global Signal Bus Synchronization ─────────────────────────────────────

def test_global_signal_broadcasting(qapp_instance):
    """Verify request_state broadcasts state across central signal bus."""
    config_file = SCRATCH_DIR / f"test_anim_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    pet = DesktopPetWindow(config_manager=cfg)

    received_states = []
    signals.character_state_changed.connect(lambda s: received_states.append(s))

    pet.anim_controller.request_state(CharacterState.LISTENING)
    assert "listening" in received_states

    pet.anim_controller.request_state(CharacterState.SPEAKING)
    assert "speaking" in received_states

    pet.close()
    if config_file.exists():
        config_file.unlink()
