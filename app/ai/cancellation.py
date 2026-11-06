"""Thread-safe cancellation token for AI generation operations."""

from __future__ import annotations

import threading
from typing import Callable, List


class CancellationToken:
    """Thread-safe cancellation token to signal and observe abort requests."""

    def __init__(self) -> None:
        self._is_cancelled = False
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[], None]] = []

    @property
    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested."""
        with self._lock:
            return self._is_cancelled

    def cancel(self) -> None:
        """Signal cancellation to all listeners."""
        with self._lock:
            if self._is_cancelled:
                return
            self._is_cancelled = True
            cbs = list(self._callbacks)

        # Invoke callbacks outside lock to avoid deadlocks
        for cb in cbs:
            try:
                cb()
            except Exception:
                pass

    def register(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked immediately if already cancelled, or on cancel."""
        should_invoke = False
        with self._lock:
            if self._is_cancelled:
                should_invoke = True
            else:
                self._callbacks.append(callback)

        if should_invoke:
            try:
                callback()
            except Exception:
                pass

    def reset(self) -> None:
        """Reset the cancellation token for reuse."""
        with self._lock:
            self._is_cancelled = False
            self._callbacks.clear()
