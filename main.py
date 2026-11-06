"""AI Desktop Friend - Application Entry Point.

Initializes logging, verifies single-instance protection,
sets up the Qt application environment, and starts the ApplicationController.
"""

import argparse
import os
from pathlib import Path
import signal
import sys

# Resolve project root regardless of launch origin (e.g. Windows Startup HKCU\Run executing in System32)
if getattr(sys, "frozen", False):
    project_root = Path(sys.executable).resolve().parent
else:
    project_root = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except Exception:
    pass

try:
    os.chdir(project_root)
except Exception:
    pass

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure Chromium WebEngine initializes cleanly across Windows environments
# Maintained with multi-process isolation and sandbox protections intact.
# Flags eliminate DirectX/DComposition swapchain conflicts with transparent overlay windows
# to prevent screen flickering during video playback and desktop pet rendering.
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--enable-gpu-rasterization "
    "--ignore-gpu-blocklist "
    "--enable-zero-copy "
    "--disable-direct-composition-video-overlays"
)

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import QApplication

from app.core.controller import ApplicationController
from app.core.lifecycle import get_lifecycle_manager
from app.core.single_instance import SingleInstanceGuard
from app.settings.config_manager import ConfigManager
from app.utils.icon_utils import get_application_icon, set_windows_app_user_model_id
from app.utils.logger import get_logger, setup_logging


def main() -> int:
    """Main application lifecycle entry point."""
    lifecycle = get_lifecycle_manager()
    lifecycle.setup_console_ctrl_handler()
    parser = argparse.ArgumentParser(description="AI Desktop Friend")
    parser.add_argument(
        "--test-run",
        action="store_true",
        help="Initialize application and exit after 1 second for smoke validation",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Launch the first-run Setup Wizard to reconfigure companion settings",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force launch without waiting for single instance lock",
    )
    args, unknown = parser.parse_known_args()
    # 1. Setup rotating logging
    log_path = setup_logging()
    logger = get_logger("main")
    logger.info("Starting AI Desktop Friend...")

    # 2. Configure Windows AppUserModelID & Qt application
    set_windows_app_user_model_id()
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    QApplication.setApplicationName("AI Desktop Friend")
    QApplication.setOrganizationName("AIDesktopFriend")
    QApplication.setApplicationVersion("0.1.0")

    app = QApplication(sys.argv)
    app.setWindowIcon(get_application_icon())
    # Prevent application from automatically terminating when the last window closes,
    # as the pet window may be toggled or minimized to tray.
    app.setQuitOnLastWindowClosed(False)

    # Apply central JARVIS sci-fi HUD theme and Google fonts
    from app.desktop.jarvis_theme import get_global_stylesheet, load_jarvis_fonts
    load_jarvis_fonts()
    app.setStyleSheet(get_global_stylesheet())

    # 3. Enforce single-instance protection
    guard = SingleInstanceGuard()
    if not args.force and not guard.try_acquire():
        print("\n" + "=" * 60)
        print("  [AI Desktop Friend] Application is already running!")
        print("  Brought the existing Desktop Pet and Chat window to front.")
        print("  If you want to start a fresh instance, use: python main.py --force")
        print("=" * 60 + "\n")
        logger.info("Application is already running. Existing instance was notified. Exiting secondary launch.")
        return 0

    # 4. Allow Python interpreter to process POSIX/Windows SIGINT (Ctrl+C)
    timer = QTimer()
    timer.timeout.connect(lambda: None)  # Wakes Python event loop periodically
    timer.start(50)

    # 5. Initialize configuration manager
    config_manager = ConfigManager()

    # 5.1. First-Run Setup Wizard check
    if not args.test_run and (args.setup or not config_manager.get("general.setup_completed", False)):
        logger.info("First run detected or --setup requested: opening Setup Wizard...")
        from app.desktop.setup_wizard import SetupWizard
        wizard = SetupWizard(config_manager=config_manager)
        if wizard.exec() != SetupWizard.Accepted:
            logger.info("Setup wizard cancelled by user. Exiting.")
            guard.release()
            return 0
        config_manager.load()

    # 6. Initialize central application controller
    controller = ApplicationController(
        app=app,
        config_manager=config_manager,
        single_instance_guard=guard,
    )
    lifecycle.register_emergency_exit_handler(controller.emergency_fast_exit)
    lifecycle.register_shutdown_hook(controller.shutdown, priority=200, name="ApplicationController")
    lifecycle.register_shutdown_hook(guard.release, priority=10, name="SingleInstanceGuard")

    def handle_sigint(signum, frame):
        """Request clean shutdown on SIGINT / Ctrl+C."""
        logger.info("[SHUTDOWN] Terminal SIGINT (Ctrl+C) detected.")
        lifecycle.request_shutdown(source="terminal_sigint")

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    # Register native Windows console control handler
    if sys.platform == "win32":
        try:
            import ctypes

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)
            def main_ctrl_handler(ctrl_type: int) -> bool:
                """Handle all console close events (Ctrl+C, window close, logoff, shutdown)."""
                logger.info("[SHUTDOWN] Native Windows console control event %d received.", ctrl_type)
                lifecycle.request_shutdown(source=f"console_ctrl_{ctrl_type}")
                return True

            global _main_ctrl_handler_ref
            _main_ctrl_handler_ref = main_ctrl_handler
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_main_ctrl_handler_ref, True)
        except Exception as e:
            logger.debug("Failed to set console ctrl handler: %s", e)

    if not controller.initialize():
        logger.critical("Failed to initialize ApplicationController. Aborting launch.")
        lifecycle.request_shutdown(source="initialization_failure")
        return 1

    if args.test_run:
        logger.info("--test-run flag detected: scheduling automatic shutdown in 1000ms.")
        QTimer.singleShot(1000, lambda: lifecycle.request_shutdown(source="test_run"))

    if lifecycle.is_shutting_down:
        logger.info("Shutdown already requested before event loop start. Exiting.")
        return 0

    logger.info("Entering Qt main event loop.")
    exit_code = app.exec()
    logger.info("Qt event loop exited with code %d.", exit_code)

    logger.info("AI Desktop Friend terminated cleanly.")

    # Never invoke app.processEvents() after app.exec() has returned to avoid
    # QDxgiVSyncService / DirectX thread deadlocks on the terminating event loop.
    # Arm a 1.5-second bounded grace watchdog to allow clean process exit while
    # guaranteeing that unmanaged native C-threads (WASAPI/DirectX) will not hang the process.
    try:
        from app.core.lifecycle import LifecycleManager
        LifecycleManager.arm_exit_watchdog(exit_code=exit_code, timeout_sec=1.5)
    except Exception:
        def _fallback_watchdog():
            import time
            time.sleep(1.5)
            try:
                os._exit(exit_code)
            except Exception:
                pass
        threading.Thread(target=_fallback_watchdog, daemon=True, name="FallbackGraceWatchdog").start()

    # Flush all output buffers before exit
    sys.stdout.flush()
    sys.stderr.flush()

    if "PYTEST_CURRENT_TEST" in os.environ:
        return exit_code

    # Terminate the Windows process deterministically to eliminate QDxgiVSyncService /
    # DirectX thread deadlocks during C++ CRT dynamic library unload.
    os._exit(exit_code)


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    if "PYTEST_CURRENT_TEST" in os.environ:
        sys.exit(exit_code)
    os._exit(exit_code)
