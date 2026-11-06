"""Centralized Application Lifecycle, Process, and Audio Shutdown Manager.

Provides a unified, thread-safe, idempotent shutdown mechanism that handles:
- Terminal SIGINT / SIGTERM (Ctrl+C in CMD and PowerShell)
- Native Windows Console Control events (CTRL_C_EVENT, CTRL_CLOSE_EVENT, CTRL_BREAK_EVENT)
- Qt application quit and window close events
- Child process tree tracking and guaranteed termination via Windows Job Objects
- Immediate termination of microphone capture, TTS playback, and background threads
"""

from __future__ import annotations

import atexit
import ctypes
import os
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger("app.core.lifecycle")


class LifecycleState:
    UNINITIALIZED = "uninitialized"
    STARTING = "starting"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN_COMPLETED = "shutdown_completed"


class LifecycleManager:
    """Centralized lifecycle coordinator for AI Friend."""

    _instance: Optional[LifecycleManager] = None
    _singleton_lock = threading.Lock()

    def __new__(cls) -> LifecycleManager:
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._state = LifecycleState.STARTING
        self._lock = threading.RLock()
        self._shutdown_hooks: List[Tuple[int, str, Callable[[], Any]]] = []
        self._emergency_handlers: List[Callable[[], Any]] = []
        self._child_pids: set[int] = set()
        self._job_object_handle: Optional[int] = None
        self._shutdown_initiated = False
        self._shutdown_completed = False
        self._watchdog_timer: Optional[threading.Timer] = None

        # Setup OS signal handlers and Windows Job Object
        self._setup_job_object()
        self._setup_signal_handlers()
        atexit.register(self._on_atexit)
        logger.info("[LIFECYCLE] Centralized LifecycleManager initialized (PID=%d)", os.getpid())

    # -------------------------------------------------------------------------
    # Lifecycle State Queries
    # -------------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown_initiated or self._state in (
            LifecycleState.SHUTTING_DOWN,
            LifecycleState.SHUTDOWN_COMPLETED,
        )

    def mark_running(self) -> None:
        with self._lock:
            if self._state == LifecycleState.STARTING:
                self._state = LifecycleState.RUNNING
                logger.info("[LIFECYCLE] Application lifecycle state transitioned to RUNNING.")

    # -------------------------------------------------------------------------
    # Windows Job Object & Subprocess Management
    # -------------------------------------------------------------------------

    def _setup_job_object(self) -> None:
        """Create a Windows Job Object with KILL_ON_JOB_CLOSE to guarantee no orphaned child processes."""
        if sys.platform != "win32":
            return

        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateJobObjectW.restype = ctypes.c_void_p
            kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.GetCurrentProcess.argtypes = []
            kernel32.AssignProcessToJobObject.restype = ctypes.c_int
            kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            kernel32.SetInformationJobObject.restype = ctypes.c_int
            kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]

            # Create job object with NULL security attributes and unique name
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                logger.debug("[LIFECYCLE] CreateJobObjectW returned NULL (error %d)", kernel32.GetLastError())
                return

            # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
            # LimitFlags = 0x2000 (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", ctypes.c_uint32),
                    ("SchedulingClass", ctypes.c_uint32),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryLimit", ctypes.c_size_t),
                    ("PeakJobMemoryLimit", ctypes.c_size_t),
                ]

            JobObjectExtendedLimitInformation = 9
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            success = kernel32.SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )

            if success:
                # Assign current process to this job object
                try:
                    current_process = kernel32.GetCurrentProcess()
                    assign_ok = kernel32.AssignProcessToJobObject(job, current_process)
                    if assign_ok:
                        self._job_object_handle = job
                        logger.info("[LIFECYCLE] Bound PID %d to Windows Job Object (KILL_ON_JOB_CLOSE enabled).", os.getpid())
                    else:
                        logger.debug("[LIFECYCLE] AssignProcessToJobObject returned 0 (error %d)", kernel32.GetLastError())
                except Exception as ex:
                    logger.debug("[LIFECYCLE] AssignProcessToJobObject notice: %s", ex)
            else:
                logger.debug("[LIFECYCLE] SetInformationJobObject returned 0 (error %d)", kernel32.GetLastError())
        except Exception as e:
            logger.debug("[LIFECYCLE] Job object initialization notice: %s", e)

    def register_child_process(self, pid_or_proc: Any) -> None:
        """Track child process PID for guaranteed cleanup on shutdown."""
        pid = None
        if isinstance(pid_or_proc, int):
            pid = pid_or_proc
        elif hasattr(pid_or_proc, "pid"):
            pid = pid_or_proc.pid

        if pid and pid > 0:
            with self._lock:
                self._child_pids.add(pid)
                logger.info("[LIFECYCLE] Registered child process PID %d for lifecycle tracking.", pid)

    def _terminate_child_processes(self) -> None:
        """Terminate all registered child processes and descendants."""
        with self._lock:
            pids = list(self._child_pids)
            self._child_pids.clear()

        if not pids:
            return

        import psutil

        current_pid = os.getpid()
        for pid in pids:
            if pid == current_pid:
                continue
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    logger.info("[LIFECYCLE] Terminating owned child process PID %d (%s)...", pid, proc.name())
                    # Terminate children first
                    for child in proc.children(recursive=True):
                        try:
                            child.terminate()
                        except Exception:
                            pass
                    proc.terminate()
                    try:
                        proc.wait(timeout=1.0)
                    except psutil.TimeoutExpired:
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception as e:
                logger.debug("[LIFECYCLE] Error terminating child PID %d: %s", pid, e)

    def fast_kill_children(self) -> None:
        """Instantly kill all child processes (including Chromium QtWebEngineProcess) without blocking."""
        with self._lock:
            pids = list(self._child_pids)
            self._child_pids.clear()

        # 1. Kill all direct OS child processes and descendants of current process (e.g. QtWebEngineProcess)
        try:
            import psutil
            parent = psutil.Process(os.getpid())
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
        except Exception:
            pass

        # 2. Kill any explicitly registered child PIDs
        if pids:
            try:
                import psutil
                current_pid = os.getpid()
                for pid in pids:
                    if pid == current_pid:
                        continue
                    try:
                        proc = psutil.Process(pid)
                        if proc.is_running():
                            for child in proc.children(recursive=True):
                                try:
                                    child.kill()
                                except Exception:
                                    pass
                            proc.kill()
                    except Exception:
                        pass
            except Exception:
                pass

    def register_emergency_exit_handler(self, fn: Callable[[], Any]) -> None:
        """Register a callback for immediate emergency exit (Ctrl+C / console close)."""
        with self._lock:
            if fn not in self._emergency_handlers:
                self._emergency_handlers.append(fn)
                logger.debug("[LIFECYCLE] Registered emergency exit handler: %s", getattr(fn, "__name__", str(fn)))

    @staticmethod
    def _hard_kill_process() -> None:
        """Unconditionally terminate current process without waiting for DLL detach or thread joins."""
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.GetCurrentProcess.restype = ctypes.c_void_p
                kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                kernel32.TerminateProcess.restype = ctypes.c_bool
                kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 0)
            except Exception:
                pass
        try:
            os._exit(0)
        except Exception:
            pass

    @classmethod
    def arm_exit_watchdog(cls, exit_code: int = 0, timeout_sec: float = 1.5) -> threading.Thread:
        """Start a background watchdog thread to enforce process termination if unmanaged native C-threads hang.

        Allows the main process to exit cleanly and invoke os._exit(exit_code)
        if native threads (WASAPI, DirectX/QDxgiVSyncService) fail to join within timeout_sec.
        """
        def _watchdog_target():
            time.sleep(timeout_sec)
            logger.warning(
                "[SHUTDOWN] Native threads failed to join within %.1fs grace period. Forcing os._exit(%d)...",
                timeout_sec,
                exit_code,
            )
            try:
                from app.core.single_instance import SingleInstanceGuard
                SingleInstanceGuard.clean_lock_file()
            except Exception:
                pass
            cls._hard_kill_process()
            try:
                os._exit(exit_code)
            except Exception:
                pass

        watchdog = threading.Thread(
            target=_watchdog_target,
            daemon=True,
            name="ExitGraceWatchdog",
        )
        watchdog.start()
        return watchdog

    def trigger_emergency_exit(self) -> None:
        """Execute all emergency exit handlers and terminate immediately via TerminateProcess / os._exit."""
        with self._lock:
            handlers = list(self._emergency_handlers)
        for handler in handlers:
            try:
                handler()
            except Exception as ex:
                logger.debug("[LIFECYCLE] Emergency exit handler exception: %s", ex)
        self.fast_kill_children()
        self._hard_kill_process()

    # -------------------------------------------------------------------------
    # Signal and Console Handlers
    # -------------------------------------------------------------------------

    def setup_console_ctrl_handler(self) -> None:
        """Public entry point to ensure Windows Console Control Handler and signal handlers are installed."""
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Configure POSIX and Windows console control handlers."""
        if getattr(self, "_signal_handlers_installed", False):
            return
        self._signal_handlers_installed = True

        def handle_signal(signum: int, frame: Any) -> None:
            sig_name = "SIGINT" if signum == signal.SIGINT else ("SIGTERM" if signum == signal.SIGTERM else str(signum))
            logger.info("[SHUTDOWN] Termination signal %s received. Requesting centralized shutdown...", sig_name)
            self.request_shutdown(source=f"signal_{sig_name}")

        try:
            signal.signal(signal.SIGINT, handle_signal)
        except Exception:
            pass

        try:
            signal.signal(signal.SIGTERM, handle_signal)
        except Exception:
            pass

        # Windows-specific console control handler for CMD and PowerShell
        if sys.platform == "win32":
            try:
                @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)
                def console_ctrl_handler(ctrl_type: int) -> bool:
                    CTRL_C_EVENT = 0
                    CTRL_BREAK_EVENT = 1
                    CTRL_CLOSE_EVENT = 2
                    CTRL_LOGOFF_EVENT = 5
                    CTRL_SHUTDOWN_EVENT = 6

                    names = {
                        CTRL_C_EVENT: "CTRL_C_EVENT",
                        CTRL_BREAK_EVENT: "CTRL_BREAK_EVENT",
                        CTRL_CLOSE_EVENT: "CTRL_CLOSE_EVENT",
                        CTRL_LOGOFF_EVENT: "CTRL_LOGOFF_EVENT",
                        CTRL_SHUTDOWN_EVENT: "CTRL_SHUTDOWN_EVENT",
                    }
                    name = names.get(ctrl_type, f"CTRL_UNKNOWN({ctrl_type})")
                    print(f"\n[!] Console {name} (Ctrl+C) received. Closing AI Desktop Friend...", flush=True)
                    self.request_shutdown(source=f"console_{name}")
                    return True

                self._console_ctrl_handler_ref = console_ctrl_handler
                ctypes.windll.kernel32.SetConsoleCtrlHandler(self._console_ctrl_handler_ref, True)
                logger.info("[LIFECYCLE] Registered Windows SetConsoleCtrlHandler successfully.")
            except Exception as e:
                logger.debug("[LIFECYCLE] SetConsoleCtrlHandler registration notice: %s", e)

    # -------------------------------------------------------------------------
    # Shutdown Hooks & Execution
    # -------------------------------------------------------------------------

    def register_shutdown_hook(self, fn: Callable[[], Any], name: str = "", priority: int = 100) -> None:
        """Register a callback to be executed during shutdown.
        
        Args:
            fn: Callable taking no arguments.
            name: Diagnostic description for logging.
            priority: Higher priority runs earlier (e.g., 200 runs before 100).
        """
        hook_name = name or getattr(fn, "__name__", str(fn))
        with self._lock:
            # Prevent duplicate registration
            for _, existing_name, existing_fn in self._shutdown_hooks:
                if existing_fn == fn or (hook_name and existing_name == hook_name):
                    return
            self._shutdown_hooks.append((priority, hook_name, fn))
            # Sort descending by priority
            self._shutdown_hooks.sort(key=lambda item: item[0], reverse=True)
            logger.debug("[LIFECYCLE] Registered shutdown hook '%s' (priority=%d)", hook_name, priority)

    def request_shutdown(
        self,
        source: str = "explicit",
        exit_code: int = 0,
        exit_process: bool = True,
    ) -> None:
        """Centralized, thread-safe entry point to request application shutdown.
        
        - First call: Initiates graceful 9-step shutdown sequence.
        - Subsequent call (emergency double-trigger): Immediately forces exit without hanging.
        - Guaranteed watchdog: Automatically forces exit after 2.0s if anything deadlocks.
        """
        with self._lock:
            if self._shutdown_initiated:
                # If shutdown was already requested and user triggers again, treat as emergency forced exit
                logger.warning("[SHUTDOWN] Second shutdown request from '%s'. Forcing immediate termination...", source)
                try:
                    from app.core.single_instance import SingleInstanceGuard
                    SingleInstanceGuard.clean_lock_file()
                except Exception:
                    pass
                self.fast_kill_children()
                try:
                    import sounddevice as sd
                    sd.stop()
                except Exception:
                    pass
                if exit_process and "PYTEST_CURRENT_TEST" not in os.environ:
                    self._hard_kill_process()
                return

            self._shutdown_initiated = True
            self._state = LifecycleState.SHUTTING_DOWN

        logger.info("[SHUTDOWN] Request received: source=%s (PID=%d)", source, os.getpid())

        # Start 2.5s watchdog to GUARANTEE process death even if any C thread hangs
        if exit_process and "PYTEST_CURRENT_TEST" not in os.environ:
            def _enforce_exit_watchdog():
                time.sleep(2.5)
                logger.warning("[SHUTDOWN] Graceful shutdown deadline (2.5s) reached. Forcing clean process termination...")
                try:
                    from app.core.single_instance import SingleInstanceGuard
                    SingleInstanceGuard.clean_lock_file()
                except Exception:
                    pass
                self.fast_kill_children()
                try:
                    import sounddevice as sd
                    sd.stop()
                except Exception:
                    pass
                self._hard_kill_process()

            self._watchdog_timer = threading.Thread(target=_enforce_exit_watchdog, daemon=True, name="ShutdownWatchdog")
            self._watchdog_timer.start()

        # If called from a secondary thread, marshal execution onto the Qt GUI main thread
        try:
            from PySide6.QtCore import QCoreApplication, QTimer
            qapp = QCoreApplication.instance()
            if qapp and threading.current_thread() != threading.main_thread():
                logger.info("[SHUTDOWN] Dispatching shutdown to Qt main thread from thread '%s'...", threading.current_thread().name)
                # MUST pass qapp as context object so timer executes on the Qt main GUI thread!
                QTimer.singleShot(0, qapp, lambda: self._execute_shutdown(source=source, exit_code=exit_code, exit_process=exit_process))
                try:
                    qapp.wakeUpGuiThread()
                except Exception:
                    pass
                return
        except Exception as e:
            logger.debug("[SHUTDOWN] Main thread dispatch note: %s", e)

        self._execute_shutdown(source=source, exit_code=exit_code, exit_process=exit_process)

    def shutdown(
        self,
        reason: str = "Explicit Request",
        force_exit_delay_sec: float = 8.0,
        exit_process: bool = False,
    ) -> None:
        """Execute centralized, idempotent, clean shutdown across all subsystems."""
        self.request_shutdown(source=reason, exit_process=exit_process)

    def _execute_shutdown(self, source: str, exit_code: int = 0, exit_process: bool = True) -> None:
        """Execute the coordinated 9-step shutdown sequence."""
        logger.info("=" * 60)
        logger.info("[SHUTDOWN] >>> SHUTDOWN SEQUENCE STARTED (Source: %s, PID: %d) <<<", source, os.getpid())
        logger.info("=" * 60)

        # Execute registered hooks in descending priority order
        with self._lock:
            hooks_to_run = list(self._shutdown_hooks)

        for priority, hook_name, hook_fn in hooks_to_run:
            try:
                if hook_name == "SingleInstanceGuard":
                    logger.info("[SHUTDOWN] Step 8/9: Releasing single instance guard...")
                logger.info("[SHUTDOWN] Executing hook: '%s' (priority=%d)...", hook_name, priority)
                hook_fn()
            except Exception as e:
                logger.error("[SHUTDOWN] Error executing hook '%s': %s", hook_name, e)

        # Terminate any remaining child processes
        self._terminate_child_processes()

        # Stop PortAudio output/input globally
        try:
            import sounddevice as sd
            sd.stop()
            logger.info("[SHUTDOWN] PortAudio sounddevice.stop() executed.")
        except Exception:
            pass

        # Flush Qt deferred delete events safely without spinning terminating loop
        try:
            from PySide6.QtCore import QCoreApplication, QEvent
            qapp = QCoreApplication.instance()
            if qapp:
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        except Exception:
            pass

        with self._lock:
            self._shutdown_completed = True
            self._state = LifecycleState.SHUTDOWN_COMPLETED

        logger.info("[SHUTDOWN] Step 9/9: Exiting Qt event loop...")
        logger.info("[SHUTDOWN] All subsystems shutdown cleanly. Qt event loop quitting.")

        # Quit Qt application event loop so app.exec() exits naturally
        try:
            from PySide6.QtCore import QCoreApplication
            qapp = QCoreApplication.instance()
            if qapp:
                qapp.quit()
        except Exception:
            pass

        # Post-quit fallback: if Qt event loop or DLL detach blocks, terminate process after 1.5s
        if exit_process and "PYTEST_CURRENT_TEST" not in os.environ:
            def _post_quit_force():
                time.sleep(1.5)
                self._hard_kill_process()

            post_quit_thread = threading.Thread(target=_post_quit_force, daemon=True, name="PostQuitForce")
            post_quit_thread.start()

    def _on_atexit(self) -> None:
        """Safety hook executed by Python runtime on process exit."""
        self._in_atexit = True
        if not self._shutdown_initiated:
            logger.info("[SHUTDOWN] atexit triggered: running graceful shutdown...")
            self.request_shutdown(source="atexit")


def get_lifecycle_manager() -> LifecycleManager:
    """Return the global LifecycleManager singleton."""
    return LifecycleManager()
