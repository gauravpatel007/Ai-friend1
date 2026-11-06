"""Unit tests for WindowsIntegration (Phase 11.7)."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint, QRect
from app.core.windows_integration import (
    PBT_APMRESUMEAUTOMATIC,
    PBT_APMSUSPEND,
    WM_POWERBROADCAST,
    WindowsIntegration,
    _WindowsNativeEventFilter,
)


def test_windows_integration_initialization(qapp_instance):
    integration = WindowsIntegration()
    assert integration is not None
    integration.cleanup()


def test_power_broadcast_signals(qapp_instance):
    integration = WindowsIntegration()

    sleep_signals_received = []
    resume_signals_received = []

    integration.system_sleep_requested.connect(lambda: sleep_signals_received.append(True))
    integration.system_resumed.connect(lambda: resume_signals_received.append(True))

    # Simulate suspend event
    integration.simulate_power_event("suspend")
    assert len(sleep_signals_received) == 1
    assert len(resume_signals_received) == 0

    # Simulate resume event
    integration.simulate_power_event("resume")
    assert len(sleep_signals_received) == 1
    assert len(resume_signals_received) == 1

    integration.cleanup()


def test_native_event_filter_dispatch(qapp_instance):
    integration = WindowsIntegration()

    sleep_count = 0
    resume_count = 0

    def on_sleep():
        nonlocal sleep_count
        sleep_count += 1

    def on_resume():
        nonlocal resume_count
        resume_count += 1

    integration.system_sleep_requested.connect(on_sleep)
    integration.system_resumed.connect(on_resume)

    # Directly dispatch WM_POWERBROADCAST to integration's message handler
    integration._on_native_windows_message(WM_POWERBROADCAST, PBT_APMSUSPEND, 0)
    assert sleep_count == 1
    assert resume_count == 0

    integration._on_native_windows_message(WM_POWERBROADCAST, PBT_APMRESUMEAUTOMATIC, 0)
    assert sleep_count == 1
    assert resume_count == 1

    integration.cleanup()


def test_taskbar_created_dispatch(qapp_instance):
    integration = WindowsIntegration()
    integration._taskbar_created_msg_id = 0xC123  # Mock registered message ID

    taskbar_events = []
    integration.taskbar_created.connect(lambda: taskbar_events.append(True))

    # Send the taskbar created message
    integration._on_native_windows_message(0xC123, 0, 0)
    assert len(taskbar_events) == 1

    integration.cleanup()


def test_ensure_rect_on_screen(qapp_instance):
    integration = WindowsIntegration()

    # Create a rect that is wildly off-screen (-5000, -5000)
    offscreen_rect = QRect(-5000, -5000, 200, 200)
    adjusted_point = integration.ensure_rect_on_screen(offscreen_rect)

    # Adjusted point must be within reasonable desktop coordinates (non-negative or primary screen bounds)
    assert adjusted_point.x() >= 0
    assert adjusted_point.y() >= 0

    integration.cleanup()
