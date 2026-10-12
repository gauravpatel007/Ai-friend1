"""AI Desktop Friend - Application Entry Point.

Initializes logging, verifies single-instance protection,
sets up the Qt application environment, and starts the ApplicationController.
"""

import argparse
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.controller import ApplicationController
from app.core.single_instance import SingleInstanceGuard
from app.settings.config_manager import ConfigManager
from app.utils.icon_utils import get_application_icon
from app.utils.logger import get_logger, setup_logging


def main() -> int:
    """Main application lifecycle entry point."""
    parser = argparse.ArgumentParser(description="AI Desktop Friend")
    parser.add_argument(
        "--test-run",
        action="store_true",
        help="Initialize application and exit after 1 second for smoke validation",
    )
    args, unknown = parser.parse_known_args()
    # 1. Setup rotating logging
    log_path = setup_logging()
    logger = get_logger("main")
    logger.info("Starting AI Desktop Friend...")

    # 2. Configure Qt application
    QApplication.setApplicationName("AI Desktop Friend")
    QApplication.setOrganizationName("AIDesktopFriend")
    QApplication.setApplicationVersion("0.1.0")

    app = QApplication(sys.argv)
    app.setWindowIcon(get_application_icon())
    # Prevent application from automatically terminating when the last window closes,
    # as the pet window may be toggled or minimized to tray.
    app.setQuitOnLastWindowClosed(False)

    # 3. Enforce single-instance protection
    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        logger.info("Application is already running. Existing instance was notified. Exiting secondary launch.")
        return 0

    # 4. Allow Python interpreter to process POSIX/Windows SIGINT (Ctrl+C)
    timer = QTimer()
    timer.timeout.connect(lambda: None)  # Wakes Python event loop periodically
    timer.start(500)

    # 5. Initialize configuration manager
    config_manager = ConfigManager()

    # 6. Initialize central application controller
    controller = ApplicationController(
        app=app,
        config_manager=config_manager,
        single_instance_guard=guard,
    )

    def handle_sigint(signum, frame):
        logger.info("Received termination signal (%s). Initiating clean shutdown...", signum)
        controller.shutdown()

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    if not controller.initialize():
        logger.critical("Failed to initialize ApplicationController. Aborting launch.")
        guard.release()
        return 1

    if args.test_run:
        logger.info("--test-run flag detected: scheduling automatic shutdown in 1000ms.")
        QTimer.singleShot(1000, controller.shutdown)

    logger.info("Entering Qt main event loop.")
    exit_code = app.exec()
    logger.info("Qt event loop exited with code %d.", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
