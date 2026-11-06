from pathlib import Path
from unittest.mock import MagicMock
import uuid

import pytest
from app.character.states import CharacterState
from app.core.controller import ApplicationController
from app.core.signals import signals
from app.settings.config_manager import ConfigManager

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def temp_controller(qapp_instance):
    config_file = SCRATCH_DIR / f"test_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    cfg.set("voice.mode", "push_to_talk")
    cfg.set("pet.animation_fps", 30)

    controller = ApplicationController(app=qapp_instance, config_manager=cfg)

    # Mock subsystems
    controller.pet_window = MagicMock()
    controller.pet_window.anim_controller = MagicMock()

    controller.ai_service = MagicMock()
    controller.ai_service.model_manager = MagicMock()

    controller.voice_service = MagicMock()

    yield controller
    try:
        if config_file.exists():
            config_file.unlink()
    except Exception:
        pass


def test_enter_sleep_mode(temp_controller):
    app_modes = []
    signals.app_mode_changed.connect(lambda mode: app_modes.append(mode))

    assert not temp_controller._is_sleeping

    # Enter sleep mode
    temp_controller.enter_sleep_mode()

    assert temp_controller._is_sleeping is True

    # 1. Voice service transitioned to wake-word standby mode (Phase 4: wake detection remains active)
    from app.voice.voice_service import VoiceMode
    temp_controller.voice_service.set_mode.assert_called_with(VoiceMode.WAKE_WORD)
    temp_controller.voice_service.stop_speaking.assert_called()

    # 2. AI generation cancelled
    temp_controller.ai_service.cancel_generation.assert_called()

    # 3. Models unloaded to free RAM
    temp_controller.ai_service.model_manager.unload_immediately.assert_called()
    temp_controller.voice_service.unload_models.assert_called()

    # 4. Pet requested state is SLEEPING
    temp_controller.pet_window.anim_controller.request_state.assert_called_with(CharacterState.SLEEPING, force=True)

    # 5. Signal emitted
    assert "sleeping" in app_modes


def test_wake_up_mode(temp_controller):
    temp_controller._is_sleeping = True

    app_modes = []
    signals.app_mode_changed.connect(lambda mode: app_modes.append(mode))

    temp_controller.wake_up()

    assert temp_controller._is_sleeping is False

    # Pet requested state is IDLE
    temp_controller.pet_window.anim_controller.request_state.assert_called_with(CharacterState.IDLE, force=True)

    # Voice service restored to configured mode
    temp_controller.voice_service.set_mode.assert_called_with("push_to_talk")

    # Signal emitted
    assert "active" in app_modes


def test_pet_window_throttles_fps_in_sleep(qapp_instance):
    """Verify DesktopPetWindow slows down animation timer to 500ms (2 FPS) when sleeping."""
    from app.desktop.pet_window import DesktopPetWindow

    config_file = SCRATCH_DIR / f"pet_test_cfg_{uuid.uuid4().hex}.json"
    cfg = ConfigManager(config_path=str(config_file))
    cfg.set("pet.animation_fps", 30)

    pet = DesktopPetWindow(config_manager=cfg)

    # Default interval: 1000 // 30 = 33ms
    assert pet._anim_timer.interval() == pytest.approx(33, abs=2)

    # Simulate transition to sleeping state
    pet._on_state_changed(CharacterState.SLEEPING)
    # Sleeping interval throttled to 500ms (2 FPS)
    assert pet._anim_timer.interval() == 500

    # Simulate transition back to idle state
    pet._on_state_changed(CharacterState.IDLE)
    # Restored to ~33ms
    assert pet._anim_timer.interval() == pytest.approx(33, abs=2)

    pet.close()
    try:
        if config_file.exists():
            config_file.unlink()
    except Exception:
        pass


def test_wake_up_from_background_thread_marshals_via_signal(temp_controller, qapp_instance):
    """Verify wake_up called from a secondary thread marshals safely via signals.wake_requested."""
    import threading
    from PySide6.QtCore import QCoreApplication

    wake_signals = []
    signals.wake_requested.connect(lambda: wake_signals.append(True))

    def run_in_thread():
        temp_controller.wake_up()

    t = threading.Thread(target=run_in_thread)
    t.start()
    t.join(timeout=2.0)

    # Process pending events posted across thread boundaries to main Qt thread
    QCoreApplication.processEvents()

    assert len(wake_signals) > 0


def test_enter_sleep_mode_from_background_thread_marshals_via_signal(temp_controller, qapp_instance):
    """Verify enter_sleep_mode called from a secondary thread marshals safely via signals.sleep_requested."""
    import threading
    from PySide6.QtCore import QCoreApplication

    sleep_signals = []
    signals.sleep_requested.connect(lambda: sleep_signals.append(True))

    def run_in_thread():
        temp_controller.enter_sleep_mode()

    t = threading.Thread(target=run_in_thread)
    t.start()
    t.join(timeout=2.0)

    # Process pending events posted across thread boundaries to main Qt thread
    QCoreApplication.processEvents()

    assert len(sleep_signals) > 0


def test_companion_wake_and_sleep_api_endpoints(qapp_instance):
    """Verify FastAPI POST /api/companion/wake and /api/companion/sleep operate cleanly without hangs."""
    from fastapi.testclient import TestClient
    from PySide6.QtCore import QCoreApplication
    from app.api.server import create_app

    app = create_app()
    client = TestClient(app)

    wake_signals = []
    sleep_signals = []
    signals.wake_requested.connect(lambda: wake_signals.append(True))
    signals.sleep_requested.connect(lambda: sleep_signals.append(True))

    # Test wake endpoint
    res_wake = client.post("/api/companion/wake")
    assert res_wake.status_code == 200
    assert res_wake.json()["status"] == "ok"
    assert res_wake.json()["state"] == "active"

    QCoreApplication.processEvents()
    assert len(wake_signals) > 0

    # Test sleep endpoint
    res_sleep = client.post("/api/companion/sleep")
    assert res_sleep.status_code == 200
    assert res_sleep.json()["status"] == "ok"
    assert res_sleep.json()["state"] == "sleeping"

    QCoreApplication.processEvents()
    assert len(sleep_signals) > 0

    # Teardown: Restore singleton buddy_state_manager to active state for subsequent test modules
    from app.core.buddy_state_manager import get_buddy_state_manager
    get_buddy_state_manager().wake_up(reason="test_teardown")

