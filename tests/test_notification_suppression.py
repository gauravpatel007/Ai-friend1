"""Unit tests verifying notification suppression for empty speech and tray settings."""

from unittest.mock import MagicMock, patch
import pytest

from app.core.controller import ApplicationController
from app.core.error_recovery import ErrorRecoveryCoordinator
from app.settings.config_manager import ConfigManager


def test_empty_transcription_does_not_emit_user_alert(qapp_instance):
    """Ensure handle_empty_transcription suppresses intrusive user alert toasts."""
    coordinator = ErrorRecoveryCoordinator()
    alerts = []
    coordinator.user_alert_requested.connect(lambda t, m, u: alerts.append((t, m, u)))

    mock_ctrl = MagicMock()
    desc = coordinator.handle_empty_transcription(voice_controller=mock_ctrl, notify_user=False)

    assert desc.error_type == "empty_transcription"
    assert len(alerts) == 0, "Empty transcription should not trigger user alert toasts by default"
    mock_ctrl.vad_engine.reset_states.assert_called_once()


def test_controller_suppresses_empty_speech_notification_by_default(qapp_instance):
    """Ensure ApplicationController._on_user_alert suppresses 'No Speech Heard' when notify_on_empty_speech is False."""
    cfg = ConfigManager()
    cfg.set("voice.notify_on_empty_speech", False)
    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)
    ctrl.tray_manager = MagicMock()

    with patch("app.desktop.notification_toast.show_buddy_toast") as mock_toast:
        ctrl._on_user_alert("No Speech Heard", "I couldn't hear any speech.", "info")
        mock_toast.assert_not_called()
        ctrl.tray_manager.show_message.assert_not_called()


def test_controller_suppresses_all_tray_notifications_when_disabled(qapp_instance):
    """Ensure ApplicationController._on_user_alert suppresses all alerts when show_tray_notifications is False."""
    cfg = ConfigManager()
    cfg.set("general.show_tray_notifications", False)
    ctrl = ApplicationController(app=qapp_instance, config_manager=cfg)
    ctrl.tray_manager = MagicMock()

    with patch("app.desktop.notification_toast.show_buddy_toast") as mock_toast:
        ctrl._on_user_alert("Important Warning", "Device disconnected.", "warning")
        mock_toast.assert_not_called()
        ctrl.tray_manager.show_message.assert_not_called()
