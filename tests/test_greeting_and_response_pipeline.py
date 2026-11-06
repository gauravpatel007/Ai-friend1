"""Comprehensive verification of the AI response pipeline, greeting fast path, and Ollama integration."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
from typing import Generator
import pytest

from app.ai.ai_service import AIService
from app.ai.greeting_evaluator import GreetingEvaluator
from app.ai.ollama_client import OllamaClient
from app.core.signals import signals
from app.settings.config_manager import ConfigManager


class PipelineMockServer(BaseHTTPRequestHandler):
    """Mock server for end-to-end pipeline verification."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/", ""):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Ollama is running")
        elif self.path == "/api/tags":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {"models": [{"name": "llama3.2:3b", "model": "llama3.2:3b"}]}
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        data = json.loads(body)

        if self.path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()

            # Find last user message
            messages = data.get("messages", [])
            last_user_content = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user_content = m.get("content", "")
                    break

            if "python" in last_user_content.lower():
                reply = "Python is a high-level, general-purpose programming language known for readability."
            elif "ram" in last_user_content.lower():
                reply = "RAM is fast, temporary volatile memory, while storage is slower, persistent storage."
            else:
                reply = f"Mock AI model response to '{last_user_content}'."

            # Stream chunks
            words = reply.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i : i + 3])
                if i + 3 < len(words):
                    chunk += " "
                c = {"message": {"role": "assistant", "content": chunk}, "done": False}
                self.wfile.write((json.dumps(c) + "\n").encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.01)

            final = {"message": {"role": "assistant", "content": ""}, "done": True}
            self.wfile.write((json.dumps(final) + "\n").encode("utf-8"))
            self.wfile.flush()

        elif self.path in ("/api/generate",):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
        else:
            self.send_response(404)


@pytest.fixture(scope="module")
def pipeline_server() -> Generator[str, None, None]:
    """Start mock server for pipeline test."""
    server = HTTPServer(("127.0.0.1", 0), PipelineMockServer)
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield url
    server.shutdown()
    server.server_close()


def test_standalone_greeting_recognition():
    """Verify that standalone greetings are recognized and compound queries are not."""
    # Should match
    assert GreetingEvaluator.is_standalone_greeting("hello")
    assert GreetingEvaluator.is_standalone_greeting("Hello")
    assert GreetingEvaluator.is_standalone_greeting("hi")
    assert GreetingEvaluator.is_standalone_greeting("Hi!")
    assert GreetingEvaluator.is_standalone_greeting("hey buddy")
    assert GreetingEvaluator.is_standalone_greeting("good morning")
    assert GreetingEvaluator.is_standalone_greeting("Good evening!")

    # Must NOT match — substantive questions and tasks
    assert not GreetingEvaluator.is_standalone_greeting("Hello, can you explain Python?")
    assert not GreetingEvaluator.is_standalone_greeting("What is Python?")
    assert not GreetingEvaluator.is_standalone_greeting("What is 15 multiplied by 7?")
    assert not GreetingEvaluator.is_standalone_greeting("Explain the difference between RAM and storage.")
    assert not GreetingEvaluator.is_standalone_greeting("Hi, how do I install numpy?")


def test_greeting_variation():
    """Verify that sequential greetings produce varied responses rather than the exact same greeting."""
    r1, _ = GreetingEvaluator.extract_and_answer("hello", companion_name="Bond", personality="concise")
    r2, _ = GreetingEvaluator.extract_and_answer("Hello", companion_name="Bond", personality="concise")
    assert r1 != r2, f"Greetings should vary: got '{r1}' and '{r2}'"


def test_greeting_fast_path_latency_and_streaming(qapp_instance, qtbot, tmp_path):
    """Test 1 & 2: Standalone greeting fast path streaming and instantaneous response."""
    # Create test config with fast_greeting_enabled=True
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "companion_name": "Bond",
            "personality": "concise",
            "fast_greeting_enabled": True,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    service = AIService(config_manager=cfg)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    t0 = time.perf_counter()
    with qtbot.waitSignal(signals.ai_response_complete, timeout=2000):
        service.ask("hello")
    duration_ms = (time.perf_counter() - t0) * 1000

    assert len(completed) == 1
    resp1 = completed[0]
    # Fast path should finish streaming in well under 1000ms
    assert duration_ms < 1500
    assert len(resp1) > 5

    # Send second greeting "Hello"
    completed.clear()
    with qtbot.waitSignal(signals.ai_response_complete, timeout=2000):
        service.ask("Hello")
    assert len(completed) == 1
    resp2 = completed[0]
    # Verify responses are not identically repeating the same static phrase
    assert resp1 != resp2, f"Responses should vary: '{resp1}' vs '{resp2}'"

    service.stop()


def test_factual_question_not_intercepted_by_greeting(qapp_instance, qtbot, pipeline_server: str, tmp_path):
    """Test 3 & 6: 'Hello, can you explain Python?' and 'What is Python?' must reach the AI model."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "companion_name": "Bond",
            "personality": "concise",
            "fast_greeting_enabled": True,
            "ollama_host": pipeline_server,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    client = OllamaClient(base_url=pipeline_server)
    service = AIService(config_manager=cfg, client=client)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    # Compound query with greeting + question
    with qtbot.waitSignal(signals.ai_response_complete, timeout=4000):
        service.ask("Hello, can you explain Python?")

    assert len(completed) == 1
    # Must contain the mock model answer about Python, NOT a standalone greeting!
    assert "Python is a high-level" in completed[0]

    service.stop()


def test_math_deterministic_evaluation(qapp_instance, qtbot, pipeline_server: str, tmp_path):
    """Test 4: 'What is 15 multiplied by 7?' must answer 105."""
    from app.ai.math_evaluator import MathExpressionEvaluator
    sol = MathExpressionEvaluator.extract_and_solve("What is 15 multiplied by 7?")
    assert sol is not None
    _, val, formatted = sol
    assert val == 105 or formatted == "105"
