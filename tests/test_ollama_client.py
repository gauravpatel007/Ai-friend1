"""Tests for OllamaClient with mocked HTTP server."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
from typing import Generator
import pytest

from app.ai.cancellation import CancellationToken
from app.ai.ollama_client import (
    OllamaCancelledError,
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)


class MockOllamaHandler(BaseHTTPRequestHandler):
    """Mock handler simulating Ollama REST API endpoints."""

    def log_message(self, format, *args):
        pass  # Suppress console logging during tests

    def do_GET(self):
        if self.path == "/api/tags":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "models": [
                    {"name": "qwen3:4b", "model": "qwen3:4b", "size": 2500000000},
                    {"name": "llama3.2:latest", "model": "llama3.2:latest", "size": 2000000000},
                ]
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        payload = json.loads(body)

        if self.path == "/api/chat":
            model = payload.get("model", "")
            if model == "non-existent-model":
                self.send_response(404)
                self.end_headers()
                return

            if model == "timeout-model":
                time.sleep(1.5)  # Will trigger short timeout
                self.send_response(200)
                self.end_headers()
                return

            # Normal streaming chat response
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()

            # Line 1: with internal thinking tag to test filtering
            chunk1 = {
                "message": {"role": "assistant", "content": "<think>internal reasoning</think>Hello "},
                "done": False,
            }
            self.wfile.write((json.dumps(chunk1) + "\n").encode("utf-8"))
            self.wfile.flush()

            # Line 2: normal content
            chunk2 = {
                "message": {"role": "assistant", "content": "there, friend!"},
                "done": True,
            }
            self.wfile.write((json.dumps(chunk2) + "\n").encode("utf-8"))
            self.wfile.flush()

        elif self.path == "/api/generate":
            # Model unload test
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def mock_ollama_server() -> Generator[str, None, None]:
    """Start mock Ollama server on ephemeral port."""
    server = HTTPServer(("127.0.0.1", 0), MockOllamaHandler)
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}"
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    yield url
    server.shutdown()
    server.server_close()


def test_ollama_client_health_and_list_models(mock_ollama_server: str):
    """Verify health check and model discovery against mock server."""
    client = OllamaClient(base_url=mock_ollama_server)
    assert client.is_server_reachable() is True

    models = client.list_models()
    assert len(models) == 2
    names = client.get_model_names()
    assert "qwen3:4b" in names
    assert "llama3.2:latest" in names


def test_ollama_client_chat_stream_and_filtering(mock_ollama_server: str):
    """Verify streaming chat and automatic thinking tag removal."""
    client = OllamaClient(base_url=mock_ollama_server)
    messages = [{"role": "user", "content": "Hello"}]
    chunks = list(client.chat_stream(messages=messages, model="qwen3:4b"))

    full_text = "".join(chunks)
    assert full_text == "Hello there, friend!"
    assert "<think>" not in full_text
    assert "internal reasoning" not in full_text


def test_ollama_client_chat_synchronous(mock_ollama_server: str):
    """Verify synchronous chat wrapper."""
    client = OllamaClient(base_url=mock_ollama_server)
    messages = [{"role": "user", "content": "Hi"}]
    response = client.chat(messages=messages, model="qwen3:4b")
    assert response == "Hello there, friend!"


def test_ollama_client_unload_model(mock_ollama_server: str):
    """Verify model unloading endpoint."""
    client = OllamaClient(base_url=mock_ollama_server)
    assert client.unload_model("qwen3:4b") is True


def test_ollama_client_model_not_found(mock_ollama_server: str):
    """Verify error raised when requested model is not found."""
    client = OllamaClient(base_url=mock_ollama_server)
    with pytest.raises(OllamaModelNotFoundError):
        list(client.chat_stream(messages=[{"role": "user", "content": "Hi"}], model="non-existent-model"))


def test_ollama_client_server_offline():
    """Verify error raised when Ollama host is unreachable."""
    # Point to an unallocated port
    offline_client = OllamaClient(base_url="http://127.0.0.1:59999", timeout=1.0)
    assert offline_client.is_server_reachable(timeout=0.5) is False
    with pytest.raises(OllamaConnectionError):
        offline_client.list_models(timeout=0.5)


def test_ollama_client_timeout(mock_ollama_server: str):
    """Verify timeout error handling."""
    fast_client = OllamaClient(base_url=mock_ollama_server, timeout=0.3)
    with pytest.raises(OllamaTimeoutError):
        list(fast_client.chat_stream(messages=[{"role": "user", "content": "Hi"}], model="timeout-model"))


def test_ollama_client_cancellation(mock_ollama_server: str):
    """Verify cancelling token raises OllamaCancelledError."""
    client = OllamaClient(base_url=mock_ollama_server)
    token = CancellationToken()
    token.cancel()  # Cancel prior to starting
    with pytest.raises(OllamaCancelledError):
        list(
            client.chat_stream(
                messages=[{"role": "user", "content": "Hi"}],
                model="qwen3:4b",
                cancellation_token=token,
            )
        )


def test_ollama_client_cancellation_handles_closed_stream_value_error(monkeypatch):
    """Bug #5: Verify ValueError from closed file stream maps to OllamaCancelledError."""
    client = OllamaClient()
    token = CancellationToken()

    class MockClosedResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def close(self):
            pass
        def __iter__(self):
            # Simulate background thread closing the stream during iteration
            token.cancel()
            raise ValueError("I/O operation on closed file")

    monkeypatch.setattr(client, "_open", lambda *args, **kwargs: MockClosedResponse())

    with pytest.raises(OllamaCancelledError, match="Stream aborted per cancellation request."):
        list(client.chat_stream(messages=[{"role": "user", "content": "Hi"}], model="test", cancellation_token=token))


def test_ollama_client_cancellation_handles_closed_stream_attribute_error(monkeypatch):
    """Bug #5: Verify AttributeError from closed response fp maps to OllamaCancelledError."""
    client = OllamaClient()
    token = CancellationToken()

    class MockNoneFpResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def close(self):
            pass
        def __iter__(self):
            token.cancel()
            raise AttributeError("'NoneType' object has no attribute 'readline'")

    monkeypatch.setattr(client, "_open", lambda *args, **kwargs: MockNoneFpResponse())

    with pytest.raises(OllamaCancelledError, match="Stream aborted per cancellation request."):
        list(client.chat_stream(messages=[{"role": "user", "content": "Hi"}], model="test", cancellation_token=token))


def test_ollama_client_uncancelled_value_error_re_raised(monkeypatch):
    """Verify ValueError without cancellation is re-raised and not swallowed."""
    client = OllamaClient()
    token = CancellationToken()

    class MockFailingResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def close(self):
            pass
        def __iter__(self):
            raise ValueError("Unexpected data format")

    monkeypatch.setattr(client, "_open", lambda *args, **kwargs: MockFailingResponse())

    with pytest.raises(ValueError, match="Unexpected data format"):
        list(client.chat_stream(messages=[{"role": "user", "content": "Hi"}], model="test", cancellation_token=token))

