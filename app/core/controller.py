"""Main Application Controller.

Central coordinator of desktop windows, system tray, background services,
and application lifecycle.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication

from app.core.signals import signals
from app.core.single_instance import SingleInstanceGuard
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.tray_icon import SystemTrayManager
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ApplicationController(QObject):
    """Central controller coordinating the AI Desktop Friend application."""

    # Controller lifecycle signals
    initialized = Signal()
    shutting_down = Signal()

    def __init__(
        self,
        app: QApplication,
        config_manager: Optional[ConfigManager] = None,
        single_instance_guard: Optional[SingleInstanceGuard] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.config_manager = config_manager or ConfigManager(parent=self)
        self.guard = single_instance_guard

        self.tray_manager: Optional[SystemTrayManager] = None
        self.pet_window: Optional[DesktopPetWindow] = None
        self._background_services: List[QObject] = []
        self._is_shutting_down = False

    def initialize(self) -> bool:
        """Initialize all components, desktop character, and system tray."""
        logger.info("Initializing ApplicationController...")

        try:
            # 1. Connect core lifecycle signals
            signals.shutdown_requested.connect(self.shutdown)
            if self.guard:
                self.guard.instance_activated.connect(signals.activate_requested.emit)

            # 2. Initialize Desktop Pet Window
            logger.info("Initializing Desktop Pet...")
            self.pet_window = DesktopPetWindow(self.config_manager)
            self.pet_window.show_pet()

            # 3. Initialize System Tray
            logger.info("Initializing System Tray...")
            self.tray_manager = SystemTrayManager(self)
            tray_success = self.tray_manager.initialize()
            if not tray_success:
                logger.warning("System tray initialization was not supported or failed.")

            # 4. Hook app aboutToQuit
            self.app.aboutToQuit.connect(self._on_app_about_to_quit)

            logger.info("ApplicationController successfully initialized.")
            self.initialized.emit()
            return True

        except Exception as e:
            logger.critical("Fatal error during ApplicationController initialization: %s", e, exc_info=True)
            return False

    def register_background_service(self, service: QObject) -> None:
        """Register a background service/worker for clean shutdown coordination."""
        self._background_services.append(service)

    @Slot()
    def shutdown(self) -> None:
        """Execute coordinated, graceful shutdown of the application."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger.info("Application shutdown requested. Starting clean teardown...")

        self.shutting_down.emit()

        # 1. Stop background workers
        for service in self._background_services:
            try:
                if hasattr(service, "stop"):
                    service.stop()
            except Exception as e:
                logger.error("Error stopping background service %s: %s", service, e)

        # 2. Hide and close pet window
        if self.pet_window:
            try:
                self.pet_window.close()
                self.pet_window = None
            except Exception as e:
                logger.error("Error closing pet window: %s", e)

        # 3. Clean up system tray
        if self.tray_manager:
            try:
                self.tray_manager.cleanup()
                self.tray_manager = None
            except Exception as e:
                logger.error("Error cleaning up tray manager: %s", e)

        # 4. Save final settings
        try:
            self.config_manager.save()
        except Exception as e:
            logger.error("Error saving final configuration: %s", e)

        # 5. Release single-instance lock
        if self.guard:
            try:
                self.guard.release()
            except Exception as e:
                logger.error("Error releasing single instance guard: %s", e)

        logger.info("Clean shutdown completed. Quitting application event loop.")
        self.app.quit()

    def _on_app_about_to_quit(self) -> None:
        """Final safety hook when Qt event loop begins quitting."""
        if not self._is_shutting_down:
            self.shutdown()
