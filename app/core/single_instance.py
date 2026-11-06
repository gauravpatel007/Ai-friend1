"""Single-Instance Application Protection.

Prevents multiple copies of the application from running simultaneously.
Uses QLocalServer on Windows with automatic loopback TCP fallback if named pipes are restricted.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QHostAddress, QLocalServer, QLocalSocket, QTcpServer, QTcpSocket

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_SERVER_KEY = "AIDesktopFriend_SingleInstance_IPC"


class SingleInstanceGuard(QObject):
    """Guarantees a single running application instance using QLocalServer / QTcpServer."""

    # Emitted when another instance launches and requests activation
    instance_activated = Signal()

    def __init__(self, key: str = DEFAULT_SERVER_KEY, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.key = key
        self._local_server: Optional[QLocalServer] = None
        self._tcp_server: Optional[QTcpServer] = None
        self._is_primary = False
        self._use_tcp_fallback = False

    def is_primary(self) -> bool:
        """Check if this instance owns the lock."""
        return self._is_primary

    def _get_lock_file(self) -> Path:
        """Get path to the fallback port lockfile."""
        # Prefer workspace scratch if it exists (for sandbox tests)
        scratch_dir = Path("tests/_test_scratch")
        if scratch_dir.exists():
            return scratch_dir / f"{self.key}.port"

        try:
            from platformdirs import user_data_dir
            base_dir = Path(user_data_dir("AI Desktop Friend", "Gaurav Patel"))
            base_dir.mkdir(parents=True, exist_ok=True)
            return base_dir / f"{self.key}.port"
        except Exception:
            return Path(tempfile.gettempdir()) / f"{self.key}.port"

    def try_acquire(self, timeout_ms: int = 600) -> bool:
        """Attempt to acquire primary instance ownership.

        If another instance is already running, sends 'ACTIVATE' to it and returns False.
        If no instance is running, starts the local server and returns True.
        """
        # --- Attempt 1: Native QLocalServer / Named Pipe ---
        test_socket = QLocalSocket()
        test_socket.connectToServer(self.key)
        connected = test_socket.waitForConnected(timeout_ms)

        if connected:
            logger.info("Another instance of AI Desktop Friend is already running. Sending activate signal.")
            try:
                test_socket.write(b"ACTIVATE\n")
                test_socket.waitForBytesWritten(timeout_ms)
                test_socket.disconnectFromServer()
            except Exception as e:
                logger.warning("Error notifying existing instance: %s", e)
            finally:
                test_socket.close()
            self._is_primary = False
            return False

        test_socket.close()
        QLocalServer.removeServer(self.key)

        local_server = QLocalServer(self)
        local_server.newConnection.connect(self._handle_incoming_local_connection)

        if local_server.listen(self.key):
            self._local_server = local_server
            self._is_primary = True
            logger.info("Single instance lock acquired successfully via QLocalServer (key: %s)", self.key)
            return True

        logger.warning(
            "QLocalServer listen failed (%s). Falling back to loopback TCP lock.",
            local_server.errorString(),
        )
        local_server.close()

        # --- Attempt 2: Fallback Loopback TCP Lock ---
        return self._try_acquire_tcp(timeout_ms)

    def _try_acquire_tcp(self, timeout_ms: int = 600) -> bool:
        """Fallback mechanism using local loopback TCP port file."""
        self._use_tcp_fallback = True
        lock_file = self._get_lock_file()

        # Check if an existing port is recorded
        if lock_file.exists():
            try:
                port_str = lock_file.read_text(encoding="utf-8").strip()
                if port_str.isdigit():
                    port = int(port_str)
                    tcp_socket = QTcpSocket()
                    tcp_socket.connectToHost(QHostAddress.SpecialAddress.LocalHost, port)
                    if tcp_socket.waitForConnected(timeout_ms):
                        logger.info("Active instance found on fallback TCP port %d. Sending activate.", port)
                        try:
                            tcp_socket.write(b"ACTIVATE\n")
                            tcp_socket.waitForBytesWritten(timeout_ms)
                            tcp_socket.disconnectFromHost()
                        except Exception as e:
                            logger.warning("Error notifying existing TCP instance: %s", e)
                        finally:
                            tcp_socket.close()
                        self._is_primary = False
                        return False
                    tcp_socket.close()
            except Exception as e:
                logger.debug("Error checking existing TCP lock: %s", e)

        # Start new TCP server on ephemeral port
        tcp_server = QTcpServer(self)
        tcp_server.newConnection.connect(self._handle_incoming_tcp_connection)

        if not tcp_server.listen(QHostAddress.SpecialAddress.LocalHost, 0):
            logger.critical("Fatal: Unable to listen on TCP fallback server: %s", tcp_server.errorString())
            self._is_primary = False
            return False

        port = tcp_server.serverPort()
        try:
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            lock_file.write_text(str(port), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to write single instance port lockfile: %s", e)
            tcp_server.close()
            self._is_primary = False
            return False

        self._tcp_server = tcp_server
        self._is_primary = True
        logger.info("Single instance lock acquired successfully via TCP port %d (key: %s)", port, self.key)
        return True

    def _handle_incoming_local_connection(self) -> None:
        """Handle incoming connection on QLocalServer."""
        if not self._local_server:
            return
        client_socket = self._local_server.nextPendingConnection()
        if not client_socket:
            return

        def on_ready_read():
            data = bytes(client_socket.readAll().data()).decode("utf-8", errors="ignore").strip()
            if "ACTIVATE" in data:
                self.instance_activated.emit()
            client_socket.disconnectFromServer()

        client_socket.readyRead.connect(on_ready_read)

    def _handle_incoming_tcp_connection(self) -> None:
        """Handle incoming connection on QTcpServer."""
        if not self._tcp_server:
            return
        client_socket = self._tcp_server.nextPendingConnection()
        if not client_socket:
            return

        def on_ready_read():
            data = bytes(client_socket.readAll().data()).decode("utf-8", errors="ignore").strip()
            if "ACTIVATE" in data:
                self.instance_activated.emit()
            client_socket.disconnectFromHost()

        client_socket.readyRead.connect(on_ready_read)

    @classmethod
    def clean_lock_file(cls, key: str = "AIDesktopFriend_SingleInstance_Mutex") -> None:
        """Safely unlink single-instance lock file without touching any Qt objects."""
        try:
            from platformdirs import user_data_dir
            base_dir = Path(user_data_dir("AI Desktop Friend", "Gaurav Patel"))
            lock_file = base_dir / f"{key}.port"
            if lock_file.exists():
                lock_file.unlink()
        except Exception:
            pass
        try:
            temp_lock = Path(tempfile.gettempdir()) / f"{key}.port"
            if temp_lock.exists():
                temp_lock.unlink()
        except Exception:
            pass

    def fast_release(self) -> None:
        """Instant lock release safe to call from any thread without touching QObject event loops."""
        self.clean_lock_file(self.key)
        self._is_primary = False

        # Only invoke Qt server methods if running safely on the Qt GUI main thread
        try:
            from PySide6.QtCore import QThread
            from PySide6.QtWidgets import QApplication
            app_inst = QApplication.instance()
            if app_inst and QThread.currentThread() == app_inst.thread():
                if self._local_server:
                    try:
                        self._local_server.close()
                    except Exception:
                        pass
                    self._local_server = None
                if self._tcp_server:
                    try:
                        self._tcp_server.close()
                    except Exception:
                        pass
                    self._tcp_server = None
                try:
                    QLocalServer.removeServer(self.key)
                except Exception:
                    pass
            else:
                self._local_server = None
                self._tcp_server = None
        except Exception:
            self._local_server = None
            self._tcp_server = None

    def release(self) -> None:
        """Release the server lock upon clean shutdown."""
        self.fast_release()
        if self._local_server:
            logger.info("Releasing QLocalServer single instance lock...")
            try:
                self._local_server.close()
            except Exception:
                pass
            self._local_server = None

        if self._tcp_server:
            logger.info("Releasing QTcpServer single instance lock...")
            try:
                self._tcp_server.close()
            except Exception:
                pass
            self._tcp_server = None
