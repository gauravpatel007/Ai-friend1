"""Integration tests for AIService and Qt Signal Bus."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
from typing import Generator
import pytest
from PySide6.QtCore import QCoreApplication

from app.ai.ai_service import AIService
from app.ai.ollama_client import OllamaClient
from app.core.signals import signals


class MockAIServiceServerHandler(BaseHTTPRequestHandler):
    """Mock Ollama server for AIService testing."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {"models": [{"name": "qwen3:4b", "model": "qwen3:4b"}]}
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 0:
            self.rfile.read(content_len)

        if self.path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()

            # Emit chunk 1
            time.sleep(0.05)
            c1 = {"message": {"role": "assistant", "content": "I am "}, "done": False}
            self.wfile.write((json.dumps(c1) + "\n").encode("utf-8"))
            self.wfile.flush()

            # Emit chunk 2
            time.sleep(0.05)
            c2 = {"message": {"role": "assistant", "content": "Buddy!"}, "done": True}
            self.wfile.write((json.dumps(c2) + "\n").encode("utf-8"))
            self.wfile.flush()
        elif self.path in ("/api/generate", "/api/chat"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def mock_ai_server() -> Generator[str, None, None]:
    """Start mock server for AIService."""
    server = HTTPServer(("127.0.0.1", 0), MockAIServiceServerHandler)
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield url
    server.shutdown()
    server.server_close()


def test_ai_service_streaming_response_and_state_transitions(qapp_instance, qtbot, mock_ai_server: str):
    """Verify streaming generation and character state transitions (thinking -> speaking -> idle)."""
    client = OllamaClient(base_url=mock_ai_server)
    service = AIService(client=client)

    states_recorded = []
    chunks_received = []
    completed_responses = []

    signals.character_state_changed.connect(states_recorded.append)
    signals.ai_response_chunk.connect(chunks_received.append)
    signals.ai_response_complete.connect(completed_responses.append)

    with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
        service.ask("Hello!")

    assert len(completed_responses) == 1
    assert completed_responses[0] == "I am Buddy!"
    assert "".join(chunks_received) == "I am Buddy!"

    # Verify state transitions occurred
    assert "thinking" in states_recorded
    assert "speaking" in states_recorded
    assert states_recorded[-1] == "idle"

    service.stop()


def test_ai_service_multi_turn_dialogue(qapp_instance, qtbot, mock_ai_server: str):
    """Verify multi-turn conversations persist in context."""
    client = OllamaClient(base_url=mock_ai_server)
    service = AIService(client=client)

    with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
        service.ask("Turn 1 prompt")

    with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
        service.ask("Turn 2 prompt")

    messages = service.context.get_messages()
    # 1 system + 2 turns (4 messages) = 5 messages
    assert len(messages) == 5
    assert messages[1]["content"] == "Turn 1 prompt"
    assert messages[2]["content"] == "I am Buddy!"
    assert messages[3]["content"] == "Turn 2 prompt"
    assert messages[4]["content"] == "I am Buddy!"

    service.stop()


def test_ai_service_cancellation(qapp_instance, qtbot, mock_ai_server: str):
    """Verify generation cancellation stops generation and resets character state."""
    client = OllamaClient(base_url=mock_ai_server)
    service = AIService(client=client)

    cancelled_fired = []
    service.generation_cancelled.connect(cancelled_fired.append)

    # Trigger generation
    service.ask("Test cancel")
    assert service._is_generating is True

    # Immediate cancellation
    service.cancel_generation()
    assert service._is_generating is False
    assert len(cancelled_fired) == 1

    service.stop()


def test_ai_service_offline_error_handling(qapp_instance, qtbot):
    """Verify graceful error reporting when Ollama server is offline."""
    offline_client = OllamaClient(base_url="http://127.0.0.1:59997", timeout=0.2)
    service = AIService(client=offline_client)

    errors = []
    service.error_occurred.connect(errors.append)

    service.ask("Will fail")
    qapp_instance.processEvents()

    assert len(errors) == 1
    assert "offline" in errors[0].lower()

    service.stop()
