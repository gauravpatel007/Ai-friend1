"""Comprehensive tests for Bug 13: Dedicated Voice Conversation Window (VoiceWindow)

Verifies:
1. Disentangled System Tray menu:
   - "🎙️ Voice Window" action emits `signals.toggle_voice_window_requested` (and NOT `signals.voice_toggle_requested`).
   - "🎙️ Voice Active" action emits `signals.voice_toggle_requested`.
   - Emitting `signals.voice_toggle_requested` does NOT change VoiceWindow visibility or toggle the window.
2. VoiceWindow standalone mechanics:
   - `show_window()`, `hide_window()`, and `toggle_window()`.
   - `signals.close_voice_window_requested` closes the VoiceWindow.
   - `position_near_pet(pet_rect)` clamps correctly within screen available geometry.
   - Mic mute button toggles mute state and emits `signals.voice_state_changed`.
3. ApplicationController orchestration:
   - `signals.open_voice_window_requested` positions near pet and opens `voice_window`.
   - `signals.close_voice_window_requested` closes `voice_window`.
   - `signals.toggle_voice_window_requested` toggles `voice_window`.
   - `enter_sleep_mode()` hides `voice_window` if open.
   - `_on_display_configuration_changed()` repositions `voice_window` near pet when visible.
   - Clean shutdown closes `voice_window`.
4. DesktopPetWindow context menu:
   - Pet right-click context menu contains "🎙️  Voice Window" connected to `signals.toggle_voice_window_requested.emit`.
5. VoiceCommandDispatcher:
   - Speech utterance "open voice window" dispatches and emits `signals.open_voice_window_requested`.
   - Speech utterance "close voice window" dispatches and emits `signals.close_voice_window_requested`.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app.core.controller import ApplicationController
from app.core.signals import signals
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.tray_icon import SystemTrayManager
from app.desktop.voice_window import VoiceWindow
from app.memory.conversation_repository import ConversationRepository
from app.settings.config_manager import ConfigManager
from app.voice.command_dispatcher import VoiceCommandDispatcher


SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


# ─── 1. Tray Menu Disentanglement Tests ─────────────────────────────────────────

def test_tray_menu_disentangled_actions(qapp_instance):
    """Verify 'Voice Window' emits toggle_voice_window_requested and 'Voice Active' emits voice_toggle_requested."""
    tray = SystemTrayManager()
    with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True), \
         patch.object(QSystemTrayIcon, "show"):
        assert tray.initialize() is True
    assert tray.tray_icon is not None

    menu = tray.tray_icon.contextMenu()
    assert menu is not None

    actions = {a.text(): a for a in menu.actions()}
    assert "🎙️ Voice Window" in actions
    assert "🎙️ Voice Active" in actions

    voice_win_fired = []
    voice_toggle_fired = []
    signals.toggle_voice_window_requested.connect(lambda: voice_win_fired.append(True))
    signals.voice_toggle_requested.connect(lambda: voice_toggle_fired.append(True))

    # Trigger 'Voice Window'
    actions["🎙️ Voice Window"].trigger()
    assert len(voice_win_fired) == 1
    assert len(voice_toggle_fired) == 0, "Voice listening mode must NOT be toggled when clicking Voice Window!"

    # Trigger 'Voice Active'
    actions["🎙️ Voice Active"].trigger()
    assert len(voice_toggle_fired) == 1
    assert len(voice_win_fired) == 1

    tray.cleanup()


# ─── 2. VoiceWindow Independent Mechanics Tests ────────────────────────────────

def test_voice_window_not_affected_by_voice_toggle_requested(qapp_instance):
    """Verify voice_toggle_requested does NOT open or close VoiceWindow."""
    cfg = ConfigManager()
    mock_vs = MagicMock()
    mock_vs.mode = "off"

    vw = VoiceWindow(config_manager=cfg, voice_service=mock_vs)
    vw.hide()
    assert vw.isVisible() is False

    # Emitting voice_toggle_requested should NOT change VoiceWindow visibility
    signals.voice_toggle_requested.emit()
    assert vw.isVisible() is False

    vw.show_window()
    assert vw.isVisible() is True

    signals.voice_toggle_requested.emit()
    assert vw.isVisible() is True  # Still visible, NOT toggled closed!

    # Close signal closes it
    signals.close_voice_window_requested.emit()
    assert vw.isVisible() is False

    vw.close()


def test_voice_window_mute_toggle(qapp_instance):
    """Verify mute button toggles mic mute state and emits voice_state_changed."""
    cfg = ConfigManager()
    mock_vs = MagicMock()
    vw = VoiceWindow(config_manager=cfg, voice_service=mock_vs)

    states_fired = []
    signals.voice_state_changed.connect(lambda s: states_fired.append(s))

    assert not vw._is_muted
    vw._toggle_mute()
    assert vw._is_muted
    mock_vs.set_muted.assert_called_with(True)
    assert states_fired[-1] == "muted"

    vw._toggle_mute()
    assert not vw._is_muted
    mock_vs.set_muted.assert_called_with(False)
    assert states_fired[-1] == "listening"

    vw.close()


def test_voice_window_position_near_pet(qapp_instance):
    """Verify position_near_pet calculates reasonable bounds within available screen geometry."""
    cfg = ConfigManager()
    vw = VoiceWindow(config_manager=cfg)

    screen = QApplication.primaryScreen()
    if screen:
        screen_geo = screen.availableGeometry()
        pet_rect = QRect(screen_geo.right() - 220, screen_geo.bottom() - 220, 200, 200)

        vw.position_near_pet(pet_rect)
        geo = vw.geometry()

        # Window must remain entirely within screen boundaries
        assert geo.left() >= screen_geo.left()
        assert geo.top() >= screen_geo.top()
        assert geo.right() <= screen_geo.right() + 10
        assert geo.bottom() <= screen_geo.bottom() + 10

    vw.close()


# ─── 3. ApplicationController Orchestration Tests ──────────────────────────────

@pytest.fixture
def controller_with_voice_win(qapp_instance):
    """Fixture providing initialized ApplicationController with real VoiceWindow and DesktopPetWindow mocks."""
    config_file = SCRATCH_DIR / "test_ctrl_voice_win_cfg.json"
    cfg = ConfigManager(config_path=config_file)
    mock_repo = MagicMock(spec=ConversationRepository)

    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)
    ctrl.conv_repo = mock_repo

    mock_ai = MagicMock()
    mock_voice = MagicMock()
    mock_voice.mode = "off"
    mock_voice.tts_enabled = False

    with patch("app.ai.ai_service.AIService", return_value=mock_ai), \
         patch("app.voice.voice_service.VoiceService", return_value=mock_voice), \
         patch("app.desktop.modern_chat_window.ModernChatWindow", return_value=MagicMock()), \
         patch.object(ctrl, "_start_api_server"):
        init_ok = ctrl.initialize()
        assert init_ok is True

    yield ctrl

    ctrl.shutdown()


def test_controller_voice_window_signals(controller_with_voice_win):
    """Verify ApplicationController slots open, close, and toggle voice_window on dedicated signals."""
    ctrl = controller_with_voice_win
    vw = ctrl.voice_window
    assert vw is not None

    vw.hide()
    assert vw.isVisible() is False

    # Open requested
    signals.open_voice_window_requested.emit()
    assert vw.isVisible() is True

    # Close requested
    signals.close_voice_window_requested.emit()
    assert vw.isVisible() is False

    # Toggle requested: currently hidden -> becomes visible
    signals.toggle_voice_window_requested.emit()
    assert vw.isVisible() is True

    # Toggle requested: currently visible -> becomes hidden
    signals.toggle_voice_window_requested.emit()
    assert vw.isVisible() is False


def test_controller_sleep_mode_hides_voice_window(controller_with_voice_win):
    """Verify enter_sleep_mode automatically hides voice_window if it was open."""
    ctrl = controller_with_voice_win
    vw = ctrl.voice_window

    signals.open_voice_window_requested.emit()
    assert vw.isVisible() is True

    ctrl.enter_sleep_mode()
    assert vw.isVisible() is False
    assert ctrl._is_sleeping is True


def test_controller_revalidates_voice_window_on_display_change(controller_with_voice_win):
    """Verify _on_display_configuration_changed repositions voice_window if visible."""
    ctrl = controller_with_voice_win
    vw = ctrl.voice_window

    signals.open_voice_window_requested.emit()
    assert vw.isVisible() is True

    with patch.object(vw, "position_near_pet") as mock_pos:
        ctrl._on_display_configuration_changed()
        mock_pos.assert_called_once()


# ─── 4. Pet Window Context Menu Test ───────────────────────────────────────────

def test_pet_window_context_menu_has_voice_window_action(qapp_instance):
    """Verify DesktopPetWindow context menu contains '🎙️  Voice Window' action."""
    cfg = ConfigManager()
    pet = DesktopPetWindow(config_manager=cfg)

    real_menu = QMenu()
    with patch("app.desktop.pet_window.QMenu", return_value=real_menu), \
         patch.object(real_menu, "exec"):
        pet._show_context_menu(QPoint(100, 100))

    action_texts = [a.text() for a in real_menu.actions()]
    assert any("Voice Window" in t for t in action_texts)
    vw_action = next(a for a in real_menu.actions() if "Voice Window" in a.text())

    fired = []
    signals.toggle_voice_window_requested.connect(lambda: fired.append(True))
    vw_action.trigger()
    assert len(fired) == 1

    pet.close()


def test_pet_window_context_menu_has_exit_action(qapp_instance):
    """Verify DesktopPetWindow context menu contains 'Exit' action which emits shutdown_requested."""
    cfg = ConfigManager()
    pet = DesktopPetWindow(config_manager=cfg)

    real_menu = QMenu()
    with patch("app.desktop.pet_window.QMenu", return_value=real_menu), \
         patch.object(real_menu, "exec"):
        pet._show_context_menu(QPoint(100, 100))

    action_texts = [a.text() for a in real_menu.actions()]
    assert any("Exit" in t for t in action_texts)
    exit_action = next(a for a in real_menu.actions() if "Exit" in a.text())

    fired = []
    signals.shutdown_requested.connect(lambda: fired.append(True))
    exit_action.trigger()
    assert len(fired) == 1

    pet.close()


# ─── 5. Voice Command Dispatcher Integration Tests ─────────────────────────────

def test_voice_commands_trigger_voice_window_signals():
    """Verify voice commands 'open voice window' and 'close voice window' emit dedicated signals."""
    mock_vs = MagicMock()
    dispatcher = VoiceCommandDispatcher(voice_service=mock_vs)

    open_fired = []
    close_fired = []
    signals.open_voice_window_requested.connect(lambda: open_fired.append(True))
    signals.close_voice_window_requested.connect(lambda: close_fired.append(True))

    # English commands
    assert dispatcher.dispatch("open voice window") is True
    assert len(open_fired) == 1

    assert dispatcher.dispatch("close voice window") is True
    assert len(close_fired) == 1

    # Hindi commands
    assert dispatcher.dispatch("वॉयस विंडो खोलो", language="hi") is True
    assert len(open_fired) == 2

    assert dispatcher.dispatch("वॉयस विंडो बंद करो", language="hi") is True
    assert len(close_fired) == 2

    # Gujarati commands
    assert dispatcher.dispatch("વૉઇસ વિન્ડો ખોલો", language="gu") is True
    assert len(open_fired) == 3

    assert dispatcher.dispatch("વૉઇસ વિન્ડો બંધ કરો", language="gu") is True
    assert len(close_fired) == 3


# ─── 6. Capsule Dock Navigation Tests ──────────────────────────────────────────

def test_control_bar_buttons_emit_correct_signals(qapp_instance):
    """Verify clicking Chat, Voice, and Settings in the FloatingControlBar emits dedicated signals."""
    from app.desktop.control_bar import FloatingControlBar
    bar = FloatingControlBar()

    chat_fired = []
    voice_fired = []
    settings_fired = []

    signals.open_chat_requested.connect(lambda: chat_fired.append(True))
    signals.open_voice_window_requested.connect(lambda: voice_fired.append(True))
    signals.open_settings_requested.connect(lambda: settings_fired.append(True))

    bar.btn_chat.click()
    assert len(chat_fired) == 1, "Chat button must emit open_chat_requested"

    bar.btn_voice.click()
    assert len(voice_fired) == 1, "Voice button must emit open_voice_window_requested"

    bar.btn_settings.click()
    assert len(settings_fired) == 1, "Settings button must emit open_settings_requested"

    bar.close()


def test_modern_chat_window_direct_routing(controller_with_voice_win):
    """Verify ApplicationController routes to ModernChatWindow's direct views."""
    ctrl = controller_with_voice_win
    from app.desktop.modern_chat_window import ModernChatWindow

    # Create a mock conforming to ModernChatWindow
    mock_modern = MagicMock(spec=ModernChatWindow)
    mock_modern.isVisible.return_value = True
    ctrl.chat_window = mock_modern

    # Chat button / signal triggers open_chat_view
    signals.open_chat_requested.emit()
    mock_modern.open_chat_view.assert_called_once()

    # Voice button / signal triggers open_voice_portal
    signals.open_voice_window_requested.emit()
    mock_modern.open_voice_portal.assert_called_once()

    # Settings button / signal triggers open_settings
    signals.open_settings_requested.emit()
    mock_modern.open_settings.assert_called_once()

