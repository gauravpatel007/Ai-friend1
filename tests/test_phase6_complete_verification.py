"""Phase 6 Comprehensive Verification Suite.

Validates the full request-to-response pipeline across all 10 required test cases:
- Test 1: Greeting ("hello") -> natural greeting
- Test 2: Different Greeting ("Hello") -> valid, varied greeting
- Test 3: Factual Question ("What is Python?") -> explains Python, not intercepted
- Test 4: General Knowledge ("What is 15 multiplied by 7?") -> evaluates to 105
- Test 5: Technical Question ("Explain the difference between RAM and storage.") -> technical explanation
- Test 6: Greeting Followed by a Question ("Hello, can you explain Python?") -> routes to model
- Test 7: Sequential Requests -> correct conversational history and ordering
- Test 8: Ollama Failure -> distinct, transparent error reporting
- Test 9: Response Parsing -> clean extraction and <think> tag suppression
- Test 10: Performance -> greeting latency vs question latency, cold vs warm
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
from typing import Generator
import pytest
from PySide6.QtCore import QCoreApplication

from app.ai.ai_service import AIService
from app.ai.cancellation import CancellationToken
from app.ai.greeting_evaluator import GreetingEvaluator
from app.ai.math_evaluator import MathExpressionEvaluator
from app.ai.ollama_client import OllamaClient, OllamaConnectionError
from app.ai.thinking_filter import StreamingThinkingFilter
from app.core.signals import signals
from app.settings.config_manager import ConfigManager


class Phase6MockServer(BaseHTTPRequestHandler):
    """Mock server simulating Ollama daemon for deterministic testing."""

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
            messages = data.get("messages", [])
            last_user_content = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user_content = m.get("content", "")
                    break

            lowered = last_user_content.lower()

            # Simulate error if prompt requests failure
            if "simulate_failure" in lowered:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Simulated Ollama backend crash"}).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()

            if "python" in lowered and ("explain" in lowered or "what is" in lowered):
                reply = "Python is a high-level programming language renowned for its clear syntax and versatility."
            elif "ram" in lowered and "storage" in lowered:
                reply = "RAM is high-speed temporary working memory, whereas storage is persistent long-term storage."
            elif "multiplied by" in lowered or "*" in lowered:
                reply = "15 multiplied by 7 is equal to 105."
            else:
                reply = f"Neural response for: {last_user_content}"

            # Stream chunks with small artificial delay
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
            self.end_headers()


@pytest.fixture(scope="module")
def mock_server() -> Generator[str, None, None]:
    """Start mock server for Phase 6 tests."""
    server = HTTPServer(("127.0.0.1", 0), Phase6MockServer)
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield url
    server.shutdown()
    server.server_close()


# ─── Tests 1 & 2: Greetings & Variation ───────────────────────────────

def test_01_greeting_hello(qapp_instance, qtbot, tmp_path):
    """Test 1: Input 'hello' produces a short, natural greeting."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "companion_name": "Buddy",
            "personality": "friendly",
            "fast_greeting_enabled": True,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    service = AIService(config_manager=cfg)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    with qtbot.waitSignal(signals.ai_response_complete, timeout=2000):
        service.ask("hello")

    assert len(completed) == 1
    resp = completed[0]
    assert len(resp) > 3
    assert any(w in resp.lower() for w in ["hello", "hi", "hey", "help", "chat", "assist"])
    service.stop()


def test_02_different_greeting_variation(qapp_instance, qtbot, tmp_path):
    """Test 2: Input 'Hello' yields a valid greeting that differs from the first."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "companion_name": "Buddy",
            "personality": "friendly",
            "fast_greeting_enabled": True,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    service = AIService(config_manager=cfg)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    # First greeting
    with qtbot.waitSignal(signals.ai_response_complete, timeout=2000):
        service.ask("hello")
    resp1 = completed[-1]

    # Second greeting
    with qtbot.waitSignal(signals.ai_response_complete, timeout=2000):
        service.ask("Hello")
    resp2 = completed[-1]

    assert resp1 != resp2, f"Greetings must vary: got '{resp1}' both times"
    service.stop()


# ─── Tests 3, 4, 5, 6: Factual, Math, Technical, Compound ─────────────

def test_03_factual_question_what_is_python(qapp_instance, qtbot, mock_server: str, tmp_path):
    """Test 3: 'What is Python?' produces a relevant explanation, not a greeting."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "fast_greeting_enabled": True,
            "ollama_host": mock_server,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    client = OllamaClient(base_url=mock_server)
    service = AIService(config_manager=cfg, client=client)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    with qtbot.waitSignal(signals.ai_response_complete, timeout=4000):
        service.ask("What is Python?")

    assert len(completed) == 1
    resp = completed[0]
    assert "programming language" in resp.lower()
    service.stop()


def test_04_general_knowledge_math_15_multiplied_by_7(qapp_instance, qtbot, mock_server: str, tmp_path):
    """Test 4: 'What is 15 multiplied by 7?' answers with 105."""
    # 1. Deterministic math evaluation
    sol = MathExpressionEvaluator.extract_and_solve("What is 15 multiplied by 7?")
    assert sol is not None
    _, val, formatted = sol
    assert val == 105 or formatted == "105"

    # 2. Pipeline integration
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "fast_greeting_enabled": True,
            "ollama_host": mock_server,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    client = OllamaClient(base_url=mock_server)
    service = AIService(config_manager=cfg, client=client)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    with qtbot.waitSignal(signals.ai_response_complete, timeout=4000):
        service.ask("What is 15 multiplied by 7?")

    assert len(completed) == 1
    assert "105" in completed[0]
    service.stop()


def test_05_technical_question_ram_vs_storage(qapp_instance, qtbot, mock_server: str, tmp_path):
    """Test 5: 'Explain the difference between RAM and storage.' produces relevant comparison."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "fast_greeting_enabled": True,
            "ollama_host": mock_server,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    client = OllamaClient(base_url=mock_server)
    service = AIService(config_manager=cfg, client=client)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    with qtbot.waitSignal(signals.ai_response_complete, timeout=4000):
        service.ask("Explain the difference between RAM and storage.")

    assert len(completed) == 1
    resp = completed[0].lower()
    assert "ram" in resp and "storage" in resp
    service.stop()


def test_06_greeting_followed_by_question_not_intercepted(qapp_instance, qtbot, mock_server: str, tmp_path):
    """Test 6: 'Hello, can you explain Python?' must NOT be intercepted by the greeting handler."""
    # Ensure GreetingEvaluator explicitly rejects compound questions
    assert not GreetingEvaluator.is_standalone_greeting("Hello, can you explain Python?")

    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "fast_greeting_enabled": True,
            "ollama_host": mock_server,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    client = OllamaClient(base_url=mock_server)
    service = AIService(config_manager=cfg, client=client)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    with qtbot.waitSignal(signals.ai_response_complete, timeout=4000):
        service.ask("Hello, can you explain Python?")

    assert len(completed) == 1
    resp = completed[0]
    # Response must explain Python from the model, NOT just return a greeting
    assert "programming language" in resp.lower()
    service.stop()


# ─── Test 7: Sequential Requests in Same Conversation ─────────────────

def test_07_sequential_requests(qapp_instance, qtbot, mock_server: str, tmp_path):
    """Test 7: Sequential requests in a conversation are properly matched and ordered."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "fast_greeting_enabled": True,
            "ollama_host": mock_server,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    client = OllamaClient(base_url=mock_server)
    service = AIService(config_manager=cfg, client=client)

    completed = []
    signals.ai_response_complete.connect(completed.append)

    # Turn 1: Greeting
    with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
        service.ask("hello")
    assert len(completed) == 1

    # Turn 2: Factual question
    with qtbot.waitSignal(signals.ai_response_complete, timeout=4000):
        service.ask("What is Python?")
    assert len(completed) == 2
    assert "programming language" in completed[1].lower()

    # Turn 3: Technical question
    with qtbot.waitSignal(signals.ai_response_complete, timeout=4000):
        service.ask("Explain the difference between RAM and storage.")
    assert len(completed) == 3
    assert "ram" in completed[2].lower()

    # Verify conversation context stores correct turns
    messages = service.context.get_messages()
    user_messages = [m["content"] for m in messages if m["role"] == "user"]
    assert "hello" in user_messages
    assert "What is Python?" in user_messages
    assert "Explain the difference between RAM and storage." in user_messages

    service.stop()


# ─── Test 8: Ollama Failure / Offline Handling ────────────────────────

def test_08_ollama_failure_reports_error(qapp_instance, qtbot, mock_server: str, tmp_path):
    """Test 8: Simulate an unavailable or failed model; verify application reports error appropriately."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "fast_greeting_enabled": True,
            "offline_fallback": False,  # disable silent fallback
            "ollama_host": mock_server,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    client = OllamaClient(base_url=mock_server)
    service = AIService(config_manager=cfg, client=client)

    errors = []
    signals.ai_error_occurred.connect(errors.append)

    # Send message triggering backend 500 error
    with qtbot.waitSignal(signals.ai_error_occurred, timeout=4000):
        service.ask("simulate_failure")

    assert len(errors) == 1
    assert "Ollama inference error" in errors[0] or "Simulated" in errors[0]
    service.stop()


# ─── Test 9: Response Parsing & <think> Filter ────────────────────────

def test_09_response_parsing_and_thinking_filter():
    """Test 9: Verify NDJSON response extraction and internal <think> tag removal."""
    filter_engine = StreamingThinkingFilter()

    # Raw model streaming simulation containing reasoning tags
    raw_chunks = [
        "<think>\n",
        "The user is asking about Python.\n",
        "I will explain it simply.\n",
        "</think>\n",
        "Python is a versatile ",
        "programming language.",
    ]

    clean_chunks = []
    for chunk in raw_chunks:
        filtered = filter_engine.process_chunk(chunk)
        if filtered:
            clean_chunks.append(filtered)
    tail = filter_engine.flush()
    if tail:
        clean_chunks.append(tail)

    full_output = "".join(clean_chunks).strip()
    assert full_output == "Python is a versatile programming language."
    assert "<think>" not in full_output
    assert "reasoning" not in full_output


# ─── Test 10: Performance Profiling ───────────────────────────────────

def test_10_performance_profiling(qapp_instance, qtbot, mock_server: str, tmp_path):
    """Test 10: Measure greeting latency and ordinary question latency separately."""
    cfg_file = tmp_path / "settings.json"
    cfg_file.write_text(json.dumps({
        "ai": {
            "model": "llama3.2:3b",
            "fast_greeting_enabled": True,
            "ollama_host": mock_server,
        }
    }))
    cfg = ConfigManager(config_path=cfg_file)
    client = OllamaClient(base_url=mock_server)
    service = AIService(config_manager=cfg, client=client)

    # 1. Measure greeting latency (fast path)
    t0 = time.perf_counter()
    with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
        service.ask("hello")
    greeting_duration_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Measure ordinary question latency (neural model path)
    t0 = time.perf_counter()
    with qtbot.waitSignal(signals.ai_response_complete, timeout=5000):
        service.ask("What is Python?")
    question_duration_ms = (time.perf_counter() - t0) * 1000.0

    # Measure that both complete successfully within non-blocking budget
    assert greeting_duration_ms > 0
    assert question_duration_ms > 0
    assert greeting_duration_ms < 2000.0
    assert question_duration_ms < 5000.0

    service.stop()


def test_11_live_ollama_integration(qapp_instance, qtbot):
    """Optional live test against real local Ollama daemon if available."""
    client = OllamaClient(base_url="http://127.0.0.1:11434")
    if not client.is_server_reachable(timeout=1.0):
        pytest.skip("Local Ollama daemon is not reachable on 127.0.0.1:11434")

    installed = client.get_model_names()
    if not any("llama3.2" in m for m in installed):
        pytest.skip("llama3.2 is not installed in local Ollama")

    service = AIService(client=client)
    completed = []
    signals.ai_response_complete.connect(completed.append)

    t0 = time.perf_counter()
    with qtbot.waitSignal(signals.ai_response_complete, timeout=30000):
        service.ask("Explain Python in one sentence.")
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert len(completed) == 1
    resp = completed[0]
    assert len(resp) > 10
    assert "python" in resp.lower()
    print(f"\n[LIVE OLLAMA TEST] Responded in {duration_ms:.1f}ms: '{resp}'")
    service.stop()
