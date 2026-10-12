"""Tests for SingleInstanceGuard."""

import pytest
from app.core.single_instance import SingleInstanceGuard


def test_single_instance_acquisition_and_conflict(qapp_instance):
    """Test acquiring instance lock and detecting second instance."""
    test_key = "Test_AIDesktopFriend_Lock_Unit"

    guard1 = SingleInstanceGuard(key=test_key)
    guard2 = SingleInstanceGuard(key=test_key)

    try:
        # First instance should successfully acquire
        assert guard1.try_acquire() is True
        assert guard1.is_primary() is True

        # Track activation signal on first instance
        activated_events = []
        guard1.instance_activated.connect(lambda: activated_events.append(True))

        # Second instance should fail and notify first
        assert guard2.try_acquire() is False
        assert guard2.is_primary() is False

        # Process Qt events to handle IPC message
        qapp_instance.processEvents()

        # Release first instance
        guard1.release()
        assert guard1.is_primary() is False

        # Now second instance should be able to acquire
        assert guard2.try_acquire() is True
        assert guard2.is_primary() is True

    finally:
        guard1.release()
        guard2.release()
