"""Core application management, lifecycle, and IPC."""

from app.core.controller import ApplicationController
from app.core.signals import AppSignals, signals
from app.core.single_instance import SingleInstanceGuard

__all__ = ["ApplicationController", "SingleInstanceGuard", "AppSignals", "signals"]
