"""Unit and integration tests for Desktop Notification Toasts (BUG 20).

Validates garbage collection retention, active toasts registry,
dismissal/cleanup, hover pause, click interaction, and tray integration.
"""

import gc
import weakref
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from app.core.signals import signals
from app.desktop.notification_toast import (
    NotificationToast,
    show_buddy_toast,
    get_active_toasts,
    clear_all_toasts,
)
from app.desktop.tray_icon import SystemTrayManager


@pytest.fixture(autouse=True)
def cleanup_toasts():
    """Ensure all toasts are cleared before and after each test."""
    clear_all_toasts()
    yield
    clear_all_toasts()


def test_show_buddy_toast_retains_reference_without_garbage_collection(qapp_instance):
    """Bug 20: Calling show_buddy_toast must NOT be garbage-collected when caller drops reference."""
    def spawn_toast():
        toast = show_buddy_toast(title="Meeting Alert", message="Sprint review at 3pm")
        return weakref.ref(toast)

    toast_ref = spawn_toast()
    # Force full garbage collection cycles
    gc.collect()
    gc.collect()

    toast = toast_ref()
    assert toast is not None, "NotificationToast was prematurely destroyed by garbage collection!"
    assert toast in get_active_toasts()
    assert toast.title_lbl.text() == "Meeting Alert"
    assert "Sprint review" in toast.msg_lbl.text()


def test_toast_dismiss_removes_from_active_toasts(qapp_instance):
    """Verify dismiss/close removes the toast from the active registry."""
    toast = show_buddy_toast(title="Dismiss Test", message="Testing dismissal")
    assert toast in get_active_toasts()

    # Direct close
    toast.close()
    qapp_instance.processEvents()
    assert toast not in get_active_toasts()


def test_clear_all_toasts_clears_active_set(qapp_instance):
    """Verify clear_all_toasts closes and empties all active toasts."""
    t1 = show_buddy_toast("Notice 1", "Body 1")
    t2 = show_buddy_toast("Notice 2", "Body 2")
    assert len(get_active_toasts()) == 2

    clear_all_toasts()
    qapp_instance.processEvents()
    assert len(get_active_toasts()) == 0


def test_toast_hover_pauses_and_resumes_timer(qapp_instance):
    """Verify mouse hover pauses the auto-dismiss timer and mouse leave resumes it."""
    toast = show_buddy_toast("Hover Test", "Body", duration_ms=5000)
    assert toast._dismiss_timer.isActive() is True

    # Simulate hover enter
    toast.enterEvent(None)
    assert toast._dismiss_timer.isActive() is False

    # Simulate hover leave
    toast.leaveEvent(None)
    assert toast._dismiss_timer.isActive() is True


def test_toast_click_emits_open_chat_signal(qapp_instance):
    """Verify clicking the toast emits signals.open_chat_requested and dismisses."""
    toast = show_buddy_toast("Click Test", "Click to open chat")
    opened_chat = []
    signals.open_chat_requested.connect(lambda: opened_chat.append(True))

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(50, 50),
        QPoint(50, 50),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    toast.mousePressEvent(event)
    qapp_instance.processEvents()

    assert len(opened_chat) == 1, "open_chat_requested was not emitted on toast click"
    assert toast._is_closing is True


def test_tray_icon_manager_show_message_integration(qapp_instance):
    """Verify TrayIconManager.show_message spawns toast and retains reference without crash."""
    tray_mgr = SystemTrayManager()
    tray_mgr.show_message("Buddy Alert", "Scheduled reminder")
    qapp_instance.processEvents()

    # Force GC to ensure tray-spawned toast is protected
    gc.collect()

    active = get_active_toasts()
    assert len(active) == 1
    toast = next(iter(active))
    assert toast.title_lbl.text() == "Buddy Alert"
    assert "Scheduled reminder" in toast.msg_lbl.text()
    assert len(tray_mgr._active_toasts) == 1
