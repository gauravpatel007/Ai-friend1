"""Tests for CancellationToken."""

import threading
from app.ai.cancellation import CancellationToken


def test_cancellation_token_initial_state():
    """Verify newly created token is not cancelled."""
    token = CancellationToken()
    assert token.is_cancelled is False


def test_cancellation_token_cancel():
    """Verify calling cancel marks token as cancelled."""
    token = CancellationToken()
    token.cancel()
    assert token.is_cancelled is True


def test_cancellation_token_callbacks():
    """Verify registered callbacks fire when cancelled."""
    token = CancellationToken()
    called = []
    token.register(lambda: called.append(1))
    token.register(lambda: called.append(2))

    assert called == []
    token.cancel()
    assert called == [1, 2]


def test_cancellation_token_register_after_cancel():
    """Verify callback registered on already cancelled token executes immediately."""
    token = CancellationToken()
    token.cancel()

    called = []
    token.register(lambda: called.append("late"))
    assert called == ["late"]


def test_cancellation_token_reset():
    """Verify reset restores token to uncancelled state."""
    token = CancellationToken()
    token.cancel()
    assert token.is_cancelled is True

    token.reset()
    assert token.is_cancelled is False
