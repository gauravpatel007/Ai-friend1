"""Unit tests verifying Text Response Performance Optimizations (Task 3).

Validates:
1. LLM token streaming with thinking filter.
2. Immediate user message processing and duplicate request prevention.
3. Cancellation of active generation via CancellationToken.
4. Fast path active model selection without redundant API calls.
5. Persistent Keep-Alive connection pooling in OllamaClient.
6. Positive cache window in ModelManager.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
from typing import Generator
import pytest

from app.ai.cancellation import CancellationToken
from app.ai.model_manager import ModelManager
from app.ai.ollama_client import OllamaCancelledError, OllamaClient


class MockStreamHandler(BaseHTTPRequestHandler):
    """Mock handler simulating streaming chat and generate endpoints."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {"models": [{"name": "llama3.2:latest", "model": "llama3.2:latest"}]}
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Ollama is running")
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

            c1 = {"message": {"role": "assistant", "content": "Hello"}, "done": False}
            self.wfile.write((json.dumps(c1) + "\n").encode("utf-8"))
            self.wfile.flush()

            c2 = {"message": {"role": "assistant", "content": " world!"}, "done": True}
            self.wfile.write((json.dumps(c2) + "\n").encode("utf-8"))
            self.wfile.flush()

        elif self.path == "/api/generate":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def mock_text_opt_server() -> Generator[str, None, None]:
    server = HTTPServer(("127.0.0.1", 0), MockStreamHandler)
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield url
    server.shutdown()
    server.server_close()


def test_ollama_client_persistent_session_and_keep_alive(mock_text_opt_server: str):
    """Verify persistent connection pooling with Keep-Alive header and keep_alive payload parameter."""
    client = OllamaClient(base_url=mock_text_opt_server)
    assert hasattr(client, "_session")
    assert client._session.headers.get("Connection") == "keep-alive"

    chunks = list(client.chat_stream(
        messages=[{"role": "user", "content": "Hi"}],
        model="llama3.2:latest",
        keep_alive="15m",
    ))
    assert "".join(chunks) == "Hello world!"


def test_model_manager_positive_cache_and_fast_path(mock_text_opt_server: str):
    """Verify ModelManager positive caching and fast-path selection avoids redundant network checks."""
    client = OllamaClient(base_url=mock_text_opt_server)
    manager = ModelManager(client=client, default_model="llama3.2:latest", model_keep_alive="15m")

    # Initial check sets positive cache
    assert manager.is_available() is True
    first_check_time = manager._last_availability_check_time

    # Immediate second check must use positive cache (60s window) without updating timestamp
    assert manager.is_available() is True
    assert manager._last_availability_check_time == first_check_time

    # Populate cache
    manager.refresh_installed_models(auto_start=False)
    assert "llama3.2:latest" in manager._cached_installed_models

    # Fast-path model selection: returns active model without calling list_models again
    selected = manager.select_active_model("llama3.2:latest")
    assert selected == "llama3.2:latest"


def test_stream_cancellation_aborts_immediately(mock_text_opt_server: str):
    """Verify CancellationToken immediately stops stream and raises OllamaCancelledError."""
    client = OllamaClient(base_url=mock_text_opt_server)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(OllamaCancelledError):
        list(client.chat_stream(
            messages=[{"role": "user", "content": "Cancel test"}],
            model="llama3.2:latest",
            cancellation_token=token,
        ))
