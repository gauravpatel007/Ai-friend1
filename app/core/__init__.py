"""Core application management, lifecycle, and IPC."""

from app.core.lifecycle import LifecycleManager, get_lifecycle_manager
from app.core.signals import AppSignals, signals
from app.core.single_instance import SingleInstanceGuard


def __getattr__(name: str):
    if name == "ApplicationController":
        from app.core.controller import ApplicationController
        return ApplicationController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ApplicationController",
    "SingleInstanceGuard",
    "AppSignals",
    "signals",
    "LifecycleManager",
    "get_lifecycle_manager",
]

