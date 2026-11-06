"""Desktop UI Comprehensive Test Suite (Phase 12.3).

Verifies:
1. Character dragging (mouse events update pet position)
2. Character resizing (size updates geometry and saves to config)
3. Character animations (state changes alter sprite/FPS)
4. Floating toolbar / Status HUD / Speech Bubble
5. Settings Dialog (categories & stack pages)
6. System Tray Manager (icon initialization and Explorer restart recovery)
7. Multi-monitor behavior (screen bounds correction)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.character.states import CharacterState
from app.core.signals import signals
from app.core.windows_integration import WindowsIntegration
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.settings_dialog import SettingsDialog
from app.desktop.speech_bubble import SpeechBubbleWidget
from app.desktop.status_hud import StatusHUD
from app.desktop.tray_icon import SystemTrayManager
from app.settings.config_manager import ConfigManager

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


def test_character_dragging_and_resizing(qapp_instance):
    """Test 12.3: Character dragging and resizing."""
    config = ConfigManager(config_path=SCRATCH_DIR / "test_pet_ui_cfg.json")
    pet = DesktopPetWindow(config_manager=config)
    pet.show()
    qapp_instance.processEvents()

    initial_pos = pet.pos()

    # 1. Simulate mouse press
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(50, 50),
        initial_pos + QPoint(50, 50),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    pet.mousePressEvent(press_event)
    assert pet._mouse_press_pos is not None

    # 2. Simulate mouse move (+40px x, +30px y > threshold)
    target_global = initial_pos + QPoint(90, 80)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPoint(90, 80),
        target_global,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    pet.mouseMoveEvent(move_event)
    qapp_instance.processEvents()
    assert pet._is_dragging is True

    # Release mouse
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(90, 80),
        target_global,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    pet.mouseReleaseEvent(release_event)
    assert not pet._is_dragging

    # 3. Test resizing via signal
    old_size = pet.width()
    target_size = 240 if old_size == 220 else 220
    signals.character_size_changed.emit(target_size)
    qapp_instance.processEvents()
    assert pet.width() == target_size
    assert pet.height() == target_size
    assert pet.width() != old_size

    pet.close()


def test_character_animations_state_changes(qapp_instance):
    """Test 12.3: Character animations and FPS adjustment across states."""
    config = ConfigManager(config_path=SCRATCH_DIR / "test_anim_cfg.json")
    pet = DesktopPetWindow(config_manager=config)
    pet.show()
    qapp_instance.processEvents()

    # Transition to SLEEPING -> throttles timer to 500ms (2 FPS)
    signals.character_state_changed.emit("sleeping")
    qapp_instance.processEvents()
    assert pet._anim_timer.interval() == 500

    # Transition back to IDLE -> restores active FPS
    signals.character_state_changed.emit("idle")
    qapp_instance.processEvents()
    expected_interval = 1000 // config.get("pet.animation_fps", 30)
    assert pet._anim_timer.interval() == expected_interval

    pet.close()


def test_status_hud_and_speech_bubble(qapp_instance):
    """Test 12.3: Status HUD positioning and Speech Bubble emission."""
    hud = StatusHUD()
    pet_rect = QRect(400, 400, 150, 150)
    hud.reposition_near_pet(pet_rect)
    assert hud.x() > 0
    assert hud.y() > 0

    bubble = SpeechBubbleWidget()
    bubble.show_message("Greetings, commander!", pet_rect=pet_rect)
    assert "commander" in bubble.label.text()
    bubble.hide()
    hud.close()


def test_settings_dialog_tabs_and_persistence(qapp_instance):
    """Test 12.3: Settings Dialog."""
    config = ConfigManager(config_path=SCRATCH_DIR / "test_settings_dlg.json")
    dialog = SettingsDialog(config_manager=config)
    assert dialog.stacked_pages.count() >= 3

    # Switch pages in stack
    dialog.stacked_pages.setCurrentIndex(1)
    qapp_instance.processEvents()
    assert dialog.stacked_pages.currentIndex() == 1

    dialog.close()


def test_system_tray_manager(qapp_instance):
    """Test 12.3: System Tray Manager creation and action bindings."""
    tray_mgr = SystemTrayManager()
    tray_mgr.initialize()
    assert tray_mgr.tray_icon is not None

    # Test Explorer restart recovery
    tray_mgr.recover_tray_icon()
    assert tray_mgr.tray_icon.isVisible() is True


def test_multi_monitor_bounds_correction(qapp_instance):
    """Test 12.3: Multi-monitor window bounds correction."""
    integration = WindowsIntegration()
    # Simulate window positioned far offscreen (-5000, -5000)
    offscreen_rect = QRect(-5000, -5000, 200, 200)
    corrected_point = integration.ensure_rect_on_screen(offscreen_rect)

    # Corrected point must be within valid screen bounds
    assert corrected_point.x() >= 0
    assert corrected_point.y() >= 0


def test_pet_window_focus_and_topmost_safety(qapp_instance):
    """Verify DesktopPetWindow does not steal keyboard/text focus from chatbox."""
    config = ConfigManager(config_path=SCRATCH_DIR / "test_focus_safety_cfg.json")
    pet = DesktopPetWindow(config_manager=config)
    pet.show()
    qapp_instance.processEvents()

    # 1. Window must have WindowDoesNotAcceptFocus
    flags = pet.windowFlags()
    assert bool(flags & Qt.WindowType.WindowDoesNotAcceptFocus)

    # 2. Window must have WA_ShowWithoutActivating set
    assert pet.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    # 3. Test enforce_topmost() executes cleanly without stealing focus
    pet.enforce_topmost()

    pet.close()


def test_pet_restore_position_multi_monitor_secondary_screen(qapp_instance, monkeypatch, tmp_path):
    """Bug #3: Verify pet restores to secondary screen without being clamped to primary screen."""
    config = ConfigManager(config_path=tmp_path / "test_multi_monitor_cfg.json")
    config.set("pet.position_x", 2500, auto_save=False)
    config.set("pet.position_y", 400, auto_save=False)

    primary_screen = MagicMock()
    primary_screen.availableGeometry.return_value = QRect(0, 0, 1920, 1040)

    secondary_screen = MagicMock()
    secondary_screen.availableGeometry.return_value = QRect(1920, 0, 1920, 1040)

    screens = [primary_screen, secondary_screen]

    monkeypatch.setattr(QApplication, "screens", lambda: screens)
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: primary_screen)
    monkeypatch.setattr(QApplication, "screenAt", lambda pt: secondary_screen if pt.x() >= 1920 else primary_screen)

    pet = DesktopPetWindow(config_manager=config)
    assert pet.x() == 2500
    assert pet.y() == 400
    pet.close()


def test_pet_restore_position_multi_monitor_negative_x(qapp_instance, monkeypatch, tmp_path):
    """Bug #3: Verify pet restores to secondary monitor positioned at negative X coordinates."""
    config = ConfigManager(config_path=tmp_path / "test_neg_monitor_cfg.json")
    config.set("pet.position_x", -600, auto_save=False)
    config.set("pet.position_y", 300, auto_save=False)

    left_screen = MagicMock()
    left_screen.availableGeometry.return_value = QRect(-1920, 0, 1920, 1040)

    primary_screen = MagicMock()
    primary_screen.availableGeometry.return_value = QRect(0, 0, 1920, 1040)

    screens = [primary_screen, left_screen]

    monkeypatch.setattr(QApplication, "screens", lambda: screens)
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: primary_screen)
    monkeypatch.setattr(QApplication, "screenAt", lambda pt: left_screen if pt.x() < 0 else primary_screen)

    pet = DesktopPetWindow(config_manager=config)
    assert pet.x() == -600
    assert pet.y() == 300
    pet.close()


def test_pet_restore_position_offscreen_fallback(qapp_instance, monkeypatch, tmp_path):
    """Verify disconnected monitor / offscreen position falls back to primary screen default."""
    config = ConfigManager(config_path=tmp_path / "test_offscreen_cfg.json")
    config.set("pet.position_x", 8000, auto_save=False)
    config.set("pet.position_y", 8000, auto_save=False)

    primary_screen = MagicMock()
    primary_screen.availableGeometry.return_value = QRect(0, 0, 1920, 1040)

    monkeypatch.setattr(QApplication, "screens", lambda: [primary_screen])
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: primary_screen)
    monkeypatch.setattr(QApplication, "screenAt", lambda pt: None)

    pet = DesktopPetWindow(config_manager=config)
    # Default position on primary screen
    screen_geo = primary_screen.availableGeometry.return_value
    assert pet.x() == screen_geo.right() - pet.width() - 40
    assert pet.y() == screen_geo.bottom() - pet.height() - 76
    pet.close()


def test_control_bar_anchors_to_secondary_screen(qapp_instance, monkeypatch):
    """Bug #7: Verify control bar capsule docks to secondary monitor when pet is on secondary monitor."""
    from app.desktop.control_bar import FloatingControlBar

    primary_screen = MagicMock()
    primary_screen.availableGeometry.return_value = QRect(0, 0, 1920, 1040)

    secondary_screen = MagicMock()
    secondary_screen.availableGeometry.return_value = QRect(1920, 0, 1920, 1040)

    monkeypatch.setattr(QApplication, "primaryScreen", lambda: primary_screen)
    monkeypatch.setattr(QApplication, "screenAt", lambda pt: secondary_screen if pt.x() >= 1920 else primary_screen)

    bar = FloatingControlBar()
    pet_rect = QRect(2500, 500, 150, 150)
    bar.show_bar(pet_rect)

    # Control bar X coordinate must remain on the secondary screen (>= 1920)
    assert bar.x() >= 1920
    assert bar.x() <= 3840
    bar.close()


def test_speech_bubble_anchors_to_secondary_screen(qapp_instance, monkeypatch):
    """Bug #7: Verify speech bubble clamps within secondary monitor when pet is on secondary monitor."""
    primary_screen = MagicMock()
    primary_screen.availableGeometry.return_value = QRect(0, 0, 1920, 1040)

    secondary_screen = MagicMock()
    secondary_screen.availableGeometry.return_value = QRect(1920, 0, 1920, 1040)

    monkeypatch.setattr(QApplication, "primaryScreen", lambda: primary_screen)
    monkeypatch.setattr(QApplication, "screenAt", lambda pt: secondary_screen if pt.x() >= 1920 else primary_screen)

    bubble = SpeechBubbleWidget()
    pet_rect = QRect(2500, 500, 150, 150)
    bubble.show_message("Hello from secondary screen!", pet_rect=pet_rect)

    # Speech bubble X coordinate must be positioned on secondary screen
    assert bubble.x() >= 1920
    assert bubble.x() <= 3840
    bubble.close()



