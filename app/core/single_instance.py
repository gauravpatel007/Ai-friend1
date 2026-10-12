"""Single-Instance Application Protection.

Prevents multiple copies of the application from running simultaneously.
Uses QLocalServer and QLocalSocket on Windows to activate the existing instance.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_SERVER_KEY = "AIDesktopFriend_SingleInstance_IPC"


class SingleInstanceGuard(QObject):
    """Guarantees a single running application instance using QLocalServer."""

    # Emitted when another instance launches and requests activation
    instance_activated = Signal()

    def __init__(self, key: str = DEFAULT_SERVER_KEY, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.key = key
        self._server: Optional[QLocalServer] = None
        self._is_primary = False

    def is_primary(self) -> bool:
        """Check if this instance owns the lock."""
        return self._is_primary

    def try_acquire(self, timeout_ms: int = 600) -> bool:
        """Attempt to acquire primary instance ownership.

        If another instance is already running, sends 'ACTIVATE' to it and returns False.
        If no instance is running, starts the local server and returns True.
        """
        # Step 1: Attempt connecting to existing server
        test_socket = QLocalSocket()
        test_socket.connectToServer(self.key)
        connected = test_socket.waitForConnected(timeout_ms)

        if connected:
            # Another instance is actively running
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

        # Step 2: Clean up any stale sockets from prior crashes
        QLocalServer.removeServer(self.key)

        # Step 3: Start local server
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._handle_incoming_connection)

        if not self._server.listen(self.key):
            logger.error("Failed to start single instance local server: %s", self._server.errorString())
            # Try once more with clean removal
            QLocalServer.removeServer(self.key)
            if not self._server.listen(self.key):
                logger.critical("Fatal: Unable to listen on single instance server: %s", self._server.errorString())
                return False

        self._is_primary = True
        logger.info("Single instance lock acquired successfully (key: %s)", self.key)
        return True

    def _handle_incoming_connection(self) -> None:
        """Handle incoming connection from a secondary instance launch."""
        if not self._server:
            return

        client_socket = self._server.nextPendingConnection()
        if not client_socket:
            return

        def on_ready_read():
            data = bytes(client_socket.readAll()).decode("utf-8", errors="ignore").strip()
            logger.info("Received message from secondary instance launch: '%s'", data)
            if "ACTIVATE" in data:
                self.instance_activated.emit()
            client_socket.disconnectFromServer()

        client_socket.readyRead.connect(on_ready_read)

    def release(self) -> None:
        """Release the server lock upon clean shutdown."""
        if self._server:
            logger.info("Releasing single instance lock...")
            self._server.close()
            QLocalServer.removeServer(self.key)
            self._server = None
        self._is_primary = False
