"""WebSocket Connection Manager and Event Dispatcher.

Enables real-time duplex communication between the Python backend
and the Tauri / React frontend interface.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket
from app.utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketManager:
    """Manages active WebSocket connections and threadsafe broadcasts."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the running asyncio event loop for thread-safe dispatches."""
        self.loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new client connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("WebSocket client connected. Total clients: %d", len(self.active_connections))
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_backend_connection("connected")
        except Exception:
            pass

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a client connection."""
        self.active_connections.discard(websocket)
        logger.info("WebSocket client disconnected. Total clients: %d", len(self.active_connections))
        if not self.active_connections:
            try:
                from app.core.diagnostic_mode import diagnostic_tracker
                diagnostic_tracker.update_backend_connection("disconnected")
            except Exception:
                pass

    async def broadcast(self, event_type: str, data: Any = None) -> None:
        """Broadcast an event to all connected clients asynchronously."""
        if not self.active_connections:
            return

        try:
            payload = json.dumps(
                {"type": event_type, "data": data if data is not None else {}},
                default=str,
            )
        except Exception as e:
            logger.error("Failed to serialize WebSocket broadcast payload for event '%s': %s", event_type, e)
            return

        dead_connections: List[WebSocket] = []

        for conn in list(self.active_connections):
            try:
                await conn.send_text(payload)
            except Exception as e:
                logger.warning("Failed to send message to client: %s", e)
                dead_connections.append(conn)

        for dead in dead_connections:
            self.disconnect(dead)

    def broadcast_sync(self, event_type: str, data: Any = None) -> None:
        """Thread-safe synchronous broadcast callable from Qt signal handlers/threads."""
        if not self.loop or self.loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), self.loop)
        except RuntimeError:
            pass


ws_manager = WebSocketManager()
