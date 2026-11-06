"""Automated tests for DateTimeProvider, DateTimeEvaluator, Prompt Context, and AIService Routing."""

from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
from typing import Generator
import pytest
from unittest.mock import patch

from app.ai.ai_service import AIService
from app.ai.datetime_evaluator import DateTimeEvaluator, DateTimeIntent
from app.ai.ollama_client import OllamaClient
from app.ai.personality_manager import PersonalityManager
from app.core.signals import signals
from app.utils.datetime_utils import (
    format_date_in_format,
    get_current_datetime,
    get_timezone,
)

FROZEN_TIME_INDIA = datetime(2026, 10, 28, 14, 30, 0, tzinfo=timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata"))
# Same instant in UTC: 2026-10-28 09:00:00 UTC
FROZEN_TIME_UTC = datetime(2026, 10, 28, 9, 0, 0, tzinfo=timezone.utc)
# Midnight boundary test: 2026-10-27 23:30:00 UTC -> 2026-10-28 05:00:00 in India
FROZEN_MIDNIGHT_UTC = datetime(2026, 10, 27, 23, 30, 0, tzinfo=timezone.utc)


class TestDateTimeUtils:
    """Tests for centralized datetime utilities."""

    def test_returns_valid_date_and_weekday(self):
        info = get_current_datetime(reference_time=FROZEN_TIME_INDIA)
        assert info["date"] == "October 28, 2026"
        assert info["weekday"] == "Wednesday"
        assert info["year"] == 2026
        assert info["month"] == "October"
        assert info["day"] == 28
        assert "Wednesday, October 28, 2026" in info["full_date"]

    def test_timezone_resolution_and_conversion(self):
        info = get_current_datetime(timezone_name="Asia/Kolkata", reference_time=FROZEN_TIME_UTC)
        assert info["date"] == "October 28, 2026"
        assert info["weekday"] == "Wednesday"
        assert info["time"] == "02:30 PM"
        assert info["timezone"] == "Asia/Kolkata"

    def test_midnight_boundary_timezone_shift(self):
        # 11:30 PM Oct 27 in UTC is 5:00 AM Oct 28 in India (new day!)
        info_utc = get_current_datetime(timezone_name="UTC", reference_time=FROZEN_MIDNIGHT_UTC)
        assert info_utc["date"] == "October 27, 2026"
        assert info_utc["weekday"] == "Tuesday"

        info_india = get_current_datetime(timezone_name="Asia/Kolkata", reference_time=FROZEN_MIDNIGHT_UTC)
        assert info_india["date"] == "October 28, 2026"
        assert info_india["weekday"] == "Wednesday"
        assert info_india["time"] == "05:00 AM"

    def test_invalid_timezone_fallback(self):
        info = get_current_datetime(timezone_name="Invalid/Fantasy_Land", reference_time=FROZEN_TIME_INDIA)
        assert info["date"] == "October 28, 2026"
        assert info["weekday"] == "Wednesday"

    def test_format_date_in_format(self):
        assert format_date_in_format(FROZEN_TIME_INDIA, "DD/MM/YYYY") == "28/10/2026"
        assert format_date_in_format(FROZEN_TIME_INDIA, "DD-MM-YYYY") == "28-10-2026"
        assert format_date_in_format(FROZEN_TIME_INDIA, "MM/DD/YYYY") == "10/28/2026"
        assert format_date_in_format(FROZEN_TIME_INDIA, "YYYY-MM-DD") == "2026-10-28"
        assert format_date_in_format(FROZEN_TIME_INDIA, "WEEKDAY") == "Wednesday"


class TestDateTimeIntentEvaluator:
    """Tests for deterministic date intent detection and answering."""

    @pytest.mark.parametrize(
        "query,expected_intent,expected_tz",
        [
            ("today's date ?", DateTimeIntent.DATE, None),
            ("give today's date", DateTimeIntent.DATE, None),
            ("what is the date", DateTimeIntent.DATE, None),
            ("What day is it today?", DateTimeIntent.DAY, None),
            ("What's today's date in India?", DateTimeIntent.DATE, "Asia/Kolkata"),
            ("what is date i am in india", DateTimeIntent.DATE, "Asia/Kolkata"),
            ("shut up and give today's date", DateTimeIntent.DATE, None),
            ("What day is today?", DateTimeIntent.DAY, None),
            ("What is the current date and time?", DateTimeIntent.DATETIME, None),
            ("Tell me today's date in DD/MM/YYYY format.", DateTimeIntent.DATE, None),
            ("What date is it right now?", DateTimeIntent.DATE, None),
            ("what time is it", DateTimeIntent.TIME, None),
            ("what is the current time", DateTimeIntent.TIME, None),
            # Hindi
            ("aaj ki date kya hai", DateTimeIntent.DATE, None),
            ("aaj kaun sa din hai", DateTimeIntent.DAY, None),
            ("kitne baje hai", DateTimeIntent.TIME, None),
        ],
    )
    def test_intent_detection_positive(self, query, expected_intent, expected_tz):
        detected = DateTimeEvaluator.detect_intent(query)
        assert detected is not None, f"Failed to detect intent for query: '{query}'"
        intent, tz, location, fmt = detected
        assert intent == expected_intent
        if expected_tz is not None:
            assert tz == expected_tz

    @pytest.mark.parametrize(
        "query",
        [
            "How's your day going so far?",
            "I went on a date yesterday.",
            "Can we set a date for lunch?",
            "What is your expiration date?",
            "Save the date for the wedding.",
            "Have a nice day!",
            "I have an appointment next week.",
            "What happened on this day in 1945?",
        ],
    )
    def test_intent_detection_negative_cases(self, query):
        """Conversational or non-current date usages must NEVER trigger date intent."""
        detected = DateTimeEvaluator.detect_intent(query)
        assert detected is None, f"Incorrectly matched non-date query: '{query}' -> {detected}"

    def test_extract_and_answer_reported_failures(self):
        """Verify the exact user failure cases produce accurate answers."""
        # 1. User: "Today's Date?"
        ans1, _ = DateTimeEvaluator.extract_and_answer("Today's Date?", reference_time=FROZEN_TIME_INDIA)
        assert "Wednesday, October 28, 2026" in ans1
        assert "[insert current date]" not in ans1
        assert "classified" not in ans1.lower()

        # 2. User: "Give today's date."
        ans2, _ = DateTimeEvaluator.extract_and_answer("Give today's date.", reference_time=FROZEN_TIME_INDIA)
        assert "Wednesday, October 28, 2026" in ans2
        assert "March 12, 2023" not in ans2

        # 3. User: "What's the date? I am in India."
        ans3, d3 = DateTimeEvaluator.extract_and_answer("What's the date? I am in India.", reference_time=FROZEN_TIME_INDIA)
        assert "Wednesday, October 28, 2026" in ans3
        assert d3["timezone"] == "Asia/Kolkata"

        # 4. User: "Shut up and give today's date."
        ans4, _ = DateTimeEvaluator.extract_and_answer("Shut up and give today's date.", reference_time=FROZEN_TIME_INDIA)
        assert "Wednesday, October 28, 2026" in ans4
        assert "March 12, 2023" not in ans4

        # 5. User: "Tell me today's date in DD/MM/YYYY format."
        ans5, _ = DateTimeEvaluator.extract_and_answer("Tell me today's date in DD/MM/YYYY format.", reference_time=FROZEN_TIME_INDIA)
        assert "28/10/2026" in ans5

        # 6. User: "What day is today?"
        ans6, _ = DateTimeEvaluator.extract_and_answer("What day is today?", reference_time=FROZEN_TIME_INDIA)
        assert "Wednesday" in ans6


class TestPromptDynamicVariables:
    """Tests ensuring prompt templates populate dynamic temporal variables and suppress placeholders."""

    def test_system_prompt_temporal_ground_truth(self):
        pm = PersonalityManager(companion_name="Buddy")
        prompt = pm.build_system_prompt(reference_time=FROZEN_TIME_INDIA)

        assert "Wednesday, October 28, 2026" in prompt
        assert "Current Environment & Temporal Ground Truth" in prompt
        assert "Factual Accuracy & Reliability Guidelines" in prompt
        assert "[insert current date]" not in prompt
        assert "[current date]" not in prompt

    def test_custom_prompt_interpolation(self):
        pm = PersonalityManager(companion_name="Buddy", user_name="Alex")
        pm.set_custom_prompt(
            "Hello {user_name}, I am {name}. Today is {current_date} ({weekday}) at {current_time}."
        )
        prompt = pm.build_system_prompt(reference_time=FROZEN_TIME_INDIA)

        assert "Hello Alex, I am Buddy." in prompt
        assert "October 28, 2026 (Wednesday)" in prompt
        assert "{current_date}" not in prompt
        assert "{user_name}" not in prompt

    def test_placeholder_suppression_and_missing_variable_safety(self):
        pm = PersonalityManager(companion_name="Buddy")
        # Template containing inadvertent literal placeholders and an unknown variable
        pm.set_custom_prompt(
            "System initialized on [insert current date]. State: {unknown_variable}."
        )
        prompt = pm.build_system_prompt(reference_time=FROZEN_TIME_INDIA)

        assert "[insert current date]" not in prompt
        assert "October 28, 2026" in prompt
        # Unknown variable should not cause a crash
        assert "{unknown_variable}" in prompt


class MockAIServerHandler(BaseHTTPRequestHandler):
    """Mock Ollama server for testing non-date fallback requests."""

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
            c1 = {"message": {"role": "assistant", "content": "I am having a wonderful day, thanks!"}, "done": True}
            self.wfile.write((json.dumps(c1) + "\n").encode("utf-8"))
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
def mock_server_endpoint() -> Generator[str, None, None]:
    server = HTTPServer(("127.0.0.1", 0), MockAIServerHandler)
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield url
    server.shutdown()
    server.server_close()


class TestAIServiceRouting:
    """Tests for AIService routing: deterministic date handling vs LLM conversations."""

    def test_deterministic_date_routing_and_signals(self, qapp_instance, qtbot):
        """A date request must receive a deterministic answer via signal bus without Ollama."""
        # Using an offline/dummy client to prove no Ollama call is required
        dummy_client = OllamaClient(base_url="http://127.0.0.1:59998", timeout=0.1)
        service = AIService(client=dummy_client)

        completed_answers = []
        chunks_emitted = []
        states = []

        signals.ai_response_complete.connect(completed_answers.append)
        signals.ai_response_chunk.connect(chunks_emitted.append)
        signals.character_state_changed.connect(states.append)

        with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
            service.ask("today's date ?")

        assert len(completed_answers) == 1
        answer = completed_answers[0]
        # Must contain valid full date
        assert "Today is" in answer
        assert len(chunks_emitted) > 0
        assert "".join(chunks_emitted).strip() == answer
        assert "[insert current date]" not in answer
        assert "March 12, 2023" not in answer
        assert "classified" not in answer.lower()

        # Personality check: playful preset must not override deterministic truth
        service.set_personality("playful")
        completed_playful = []
        signals.ai_response_complete.connect(completed_playful.append)
        with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
            service.ask("Give today's date.")
        assert "Today is" in completed_playful[-1]
        assert "007" not in completed_playful[-1]

        service.stop()

    def test_date_request_for_india_timezone(self, qapp_instance, qtbot):
        """A date request explicitly specifying India must use Asia/Kolkata."""
        dummy_client = OllamaClient(base_url="http://127.0.0.1:59998", timeout=0.1)
        service = AIService(client=dummy_client)

        responses = []
        signals.ai_response_complete.connect(responses.append)

        with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
            service.ask("what is date i am in india")

        assert len(responses) == 1
        ans = responses[0]
        assert "India" in ans
        assert "Today is" in ans

        service.stop()

    def test_normal_conversation_routes_to_llm(self, qapp_instance, qtbot, mock_server_endpoint: str):
        """Normal conversational queries continue through the standard AI model pipeline."""
        client = OllamaClient(base_url=mock_server_endpoint)
        service = AIService(client=client)

        completed = []
        signals.ai_response_complete.connect(completed.append)

        # 5. User: "How's your day going so far?"
        with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
            service.ask("How's your day going so far?")

        assert len(completed) == 1
        assert "wonderful day" in completed[0]

        service.stop()

    def test_negative_phrase_with_date_does_not_trigger_date_handler(self, qapp_instance, qtbot, mock_server_endpoint: str):
        """The phrase 'I went on a date yesterday' must NOT trigger the date handler."""
        client = OllamaClient(base_url=mock_server_endpoint)
        service = AIService(client=client)

        completed = []
        signals.ai_response_complete.connect(completed.append)

        with qtbot.waitSignal(signals.ai_response_complete, timeout=3000):
            service.ask("I went on a date yesterday.")

        assert len(completed) == 1
        # It routed to the model, not the deterministic date handler
        assert "Today is" not in completed[0]

        service.stop()
