"""Tests for ModelManager."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
from typing import Generator
import pytest

from app.ai.model_manager import ModelManager
from app.ai.ollama_client import OllamaClient


class MockModelServerHandler(BaseHTTPRequestHandler):
    """Mock handler for model manager testing."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "models": [
                    {
                        "name": "nomic-embed-text:latest",
                        "model": "nomic-embed-text:latest",
                        "capabilities": "embedding",
                    },
                    {
                        "name": "llama3.2:latest",
                        "model": "llama3.2:latest",
                        "capabilities": "completion tools",
                    },
                    {
                        "name": "qwen3:4b",
                        "model": "qwen3:4b",
                        "capabilities": "completion thinking",
                    },
                ]
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 0:
            self.rfile.read(content_len)

        if self.path in ("/api/generate", "/api/chat"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def mock_model_server() -> Generator[str, None, None]:
    """Start mock model server."""
    server = HTTPServer(("127.0.0.1", 0), MockModelServerHandler)
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield url
    server.shutdown()
    server.server_close()


def test_model_manager_discovery_filters_embeddings(mock_model_server: str):
    """Verify that pure embedding models are filtered out from companion models."""
    client = OllamaClient(base_url=mock_model_server)
    mgr = ModelManager(client=client)

    installed = mgr.refresh_installed_models()
    assert "nomic-embed-text:latest" not in installed
    assert "llama3.2:latest" in installed
    assert "qwen3:4b" in installed


def test_model_manager_auto_selection(mock_model_server: str):
    """Verify selecting active model matches preferred models."""
    client = OllamaClient(base_url=mock_model_server)
    mgr = ModelManager(client=client, default_model="llama3.2:latest")

    selected = mgr.select_active_model()
    assert selected == "llama3.2:latest"

    mgr.set_model("qwen3:4b")
    assert mgr.active_model == "qwen3:4b"


def test_model_manager_fallback_when_configured_missing(mock_model_server: str):
    """Verify fallback to another installed model if requested model is missing."""
    client = OllamaClient(base_url=mock_model_server)
    mgr = ModelManager(client=client, default_model="nonexistent-model")

    selected = mgr.select_active_model()
    # Should fallback to one of the installed preferred models (e.g. qwen3:4b or llama3.2)
    assert selected in ("qwen3:4b", "llama3.2:latest")


def test_model_manager_inactivity_unloading(mock_model_server: str):
    """Verify inactivity timer unloads model when threshold exceeded."""
    client = OllamaClient(base_url=mock_model_server)
    # Set small inactivity timeout (0.1s)
    mgr = ModelManager(client=client, inactivity_timeout_seconds=0.1)
    mgr.touch_activity()
    assert mgr._is_model_loaded is True

    time.sleep(0.15)
    unloaded = mgr.check_inactivity_and_unload()
    assert unloaded is True
    assert mgr._is_model_loaded is False


def test_model_manager_diagnostics_online(mock_model_server: str):
    """Verify status diagnostics when server is online."""
    client = OllamaClient(base_url=mock_model_server)
    mgr = ModelManager(client=client, default_model="qwen3:4b")
    status = mgr.get_status()

    assert status["online"] is True
    assert status["status"] == "Ready"
    assert status["error"] is None
    assert "qwen3:4b" in status["installed_models"]


def test_model_manager_diagnostics_offline():
    """Verify status diagnostics when server is offline."""
    client = OllamaClient(base_url="http://127.0.0.1:59998", timeout=0.2)
    mgr = ModelManager(client=client)
    status = mgr.get_status()

    assert status["online"] is False
    assert status["status"] == "Ollama Offline"
    assert "Ollama is not running" in status["error"]
