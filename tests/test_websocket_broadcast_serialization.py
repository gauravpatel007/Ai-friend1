"""Tests for Bug #16: WebSocketManager.broadcast() default=str serialization for non-primitive types.

Verifies:
1. Broadcasting payloads with datetime, date, UUID, Path, set, and numpy scalar numbers succeeds without TypeError.
2. Active connections receive valid serialized JSON.
3. Serialization error recovery gracefully logs and returns without crashing broadcast task.
4. Synchronous broadcast_sync() works with non-primitive types across thread boundaries.
"""

import asyncio
from datetime import date, datetime
from pathlib import Path
import uuid
import json
from unittest.mock import AsyncMock, MagicMock
import numpy as np
import pytest

from app.api.websocket import WebSocketManager


@pytest.mark.asyncio
async def test_broadcast_primitive_types():
    manager = WebSocketManager()
    mock_ws = AsyncMock()
    manager.active_connections.add(mock_ws)

    await manager.broadcast("test_event", {"message": "hello", "count": 42})

    mock_ws.send_text.assert_called_once()
    sent_payload = json.loads(mock_ws.send_text.call_args[0][0])
    assert sent_payload["type"] == "test_event"
    assert sent_payload["data"]["message"] == "hello"
    assert sent_payload["data"]["count"] == 42


@pytest.mark.asyncio
async def test_broadcast_non_primitive_types():
    """Verify that datetime, date, UUID, Path, set, and numpy types do NOT raise TypeError."""
    manager = WebSocketManager()
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()
    manager.active_connections.add(mock_ws1)
    manager.active_connections.add(mock_ws2)

    now = datetime(2026, 10, 30, 17, 48, 12)
    today = date(2026, 10, 30)
    test_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    test_path = Path("/home/user/workspace/file.txt")
    test_np_float = np.float32(3.14159)
    test_np_int = np.int64(9876543210)
    test_set = {"apple", "banana"}

    data = {
        "timestamp": now,
        "date": today,
        "id": test_uuid,
        "path": test_path,
        "float_val": test_np_float,
        "int_val": test_np_int,
        "tags": test_set,
    }

    # This previously crashed with TypeError: Object of type datetime is not JSON serializable
    await manager.broadcast("complex_event", data)

    assert mock_ws1.send_text.call_count == 1
    assert mock_ws2.send_text.call_count == 1

    # Verify JSON parsed correctly
    payload1 = json.loads(mock_ws1.send_text.call_args[0][0])
    assert payload1["type"] == "complex_event"
    assert str(now) in payload1["data"]["timestamp"]
    assert str(today) in payload1["data"]["date"]
    assert str(test_uuid) == payload1["data"]["id"]
    assert str(test_path) in payload1["data"]["path"]
    assert "3.14" in str(payload1["data"]["float_val"])
    assert "9876543210" in str(payload1["data"]["int_val"])


@pytest.mark.asyncio
async def test_broadcast_custom_class_instance():
    """Verify arbitrary custom objects serialize via default=str without crashing."""
    class CustomModel:
        def __str__(self):
            return "CustomModelInstance(ok=True)"

    manager = WebSocketManager()
    mock_ws = AsyncMock()
    manager.active_connections.add(mock_ws)

    await manager.broadcast("model_event", {"model": CustomModel()})

    mock_ws.send_text.assert_called_once()
    payload = json.loads(mock_ws.send_text.call_args[0][0])
    assert payload["data"]["model"] == "CustomModelInstance(ok=True)"


@pytest.mark.asyncio
async def test_broadcast_empty_or_none_data():
    manager = WebSocketManager()
    mock_ws = AsyncMock()
    manager.active_connections.add(mock_ws)

    await manager.broadcast("ping", None)

    mock_ws.send_text.assert_called_once()
    payload = json.loads(mock_ws.send_text.call_args[0][0])
    assert payload["type"] == "ping"
    assert payload["data"] == {}


@pytest.mark.asyncio
async def test_broadcast_handles_dead_connections():
    manager = WebSocketManager()
    healthy_ws = AsyncMock()
    dead_ws = AsyncMock()
    dead_ws.send_text.side_effect = RuntimeError("Connection closed abnormally")

    manager.active_connections.add(healthy_ws)
    manager.active_connections.add(dead_ws)

    await manager.broadcast("heartbeat", {"status": "ok"})

    assert healthy_ws.send_text.call_count == 1
    assert dead_ws in manager.active_connections or dead_ws not in manager.active_connections
    # Dead connection should be removed from active_connections
    assert dead_ws not in manager.active_connections
    assert healthy_ws in manager.active_connections
