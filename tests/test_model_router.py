"""Unit and integration tests for Intelligent Automatic Model Router (Phase 4)."""

import pytest
from unittest.mock import MagicMock, patch

from app.ai.model_capability_registry import (
    ModelCapability,
    ModelCapabilityRegistry,
    ModelProfile,
)
from app.ai.model_router import (
    ModelRouter,
    RoutingDecision,
    TaskCategory,
    TaskDetector,
    TASK_UI_BADGES,
    get_model_router,
)


@pytest.fixture
def mock_registry():
    """Create a mock capability registry with standard local test models."""
    registry = MagicMock(spec=ModelCapabilityRegistry)

    llama = ModelProfile(
        model_id="llama3.2:3b",
        display_name="Llama 3.2 (3.2B)",
        installed=True,
        size_bytes=2000000000,
        size_formatted="2.0 GB",
        quantization="Q4_K_M",
        family="llama",
        families=["llama"],
        parameter_size="3.2B",
        context_capacity=131072,
        estimated_vram_mb=2400,
        capabilities=[
            ModelCapability.FAST_RESPONSE,
            ModelCapability.GENERAL_CONVERSATION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.SUMMARIZATION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.MULTILINGUAL,
        ],
        is_online=True,
        is_local=True,
    )

    gemma = ModelProfile(
        model_id="gemma3:4b",
        display_name="Gemma 3 (4B Vision)",
        installed=True,
        size_bytes=3000000000,
        size_formatted="3.0 GB",
        quantization="Q4_K_M",
        family="gemma3",
        families=["gemma3"],
        parameter_size="4B",
        context_capacity=131072,
        estimated_vram_mb=3200,
        capabilities=[
            ModelCapability.FAST_RESPONSE,
            ModelCapability.GENERAL_CONVERSATION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.VISION,
        ],
        is_online=True,
        is_local=True,
    )

    deepseek = ModelProfile(
        model_id="deepseek-r1:7b",
        display_name="DeepSeek R1 (7B Reasoning)",
        installed=True,
        size_bytes=4700000000,
        size_formatted="4.7 GB",
        quantization="Q4_K_M",
        family="deepseek",
        families=["deepseek", "qwen2"],
        parameter_size="7B",
        context_capacity=131072,
        estimated_vram_mb=5200,
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.SUMMARIZATION,
        ],
        is_online=True,
        is_local=True,
    )

    qwen = ModelProfile(
        model_id="qwen3.5:4b",
        display_name="Qwen 3.5 (4B Coding)",
        installed=True,
        size_bytes=2800000000,
        size_formatted="2.8 GB",
        quantization="Q4_K_M",
        family="qwen",
        families=["qwen"],
        parameter_size="4B",
        context_capacity=262144,
        estimated_vram_mb=3000,
        capabilities=[
            ModelCapability.FAST_RESPONSE,
            ModelCapability.CODING,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.MULTILINGUAL,
        ],
        is_online=True,
        is_local=True,
    )

    registry.get_installed_models.return_value = [llama, gemma, deepseek, qwen]
    registry.get_model.side_effect = lambda m_id: {
        "llama3.2:3b": llama,
        "gemma3:4b": gemma,
        "deepseek-r1:7b": deepseek,
        "qwen3.5:4b": qwen,
    }.get(m_id)

    return registry


class TestTaskDetector:
    """Test deterministic multi-factor task classification across all 12 categories."""

    def test_greeting_detection(self):
        cat, _ = TaskDetector.detect_task("Hello Bond!")
        assert cat == TaskCategory.GREETING

        cat, _ = TaskDetector.detect_task("Good morning, how are you?")
        assert cat == TaskCategory.GREETING

    def test_simple_voice_command_detection(self):
        cat, _ = TaskDetector.detect_task("stop speaking", is_voice=True)
        assert cat == TaskCategory.SIMPLE_VOICE_COMMAND

        cat, _ = TaskDetector.detect_task("pause volume", is_voice=True)
        assert cat == TaskCategory.SIMPLE_VOICE_COMMAND

    def test_quick_factual_question_detection(self):
        cat, _ = TaskDetector.detect_task("What is the capital of France?")
        assert cat == TaskCategory.QUICK_FACTUAL_QUESTION

        cat, _ = TaskDetector.detect_task("Who wrote Romeo and Juliet?")
        assert cat == TaskCategory.QUICK_FACTUAL_QUESTION

    def test_general_conversation_detection(self):
        cat, _ = TaskDetector.detect_task("Tell me an interesting story about a dog and a cat.")
        assert cat == TaskCategory.GENERAL_CONVERSATION

        cat, _ = TaskDetector.detect_task("I had a really busy day today at work.")
        assert cat == TaskCategory.GENERAL_CONVERSATION

    def test_coding_detection_with_code_blocks(self):
        prompt = "Here is my function:\n```python\ndef add(a, b):\n    return a + b\n```\nHow can I improve it?"
        cat, meta = TaskDetector.detect_task(prompt)
        assert cat == TaskCategory.CODING

    def test_coding_detection_with_multiword_intent_no_code_block(self):
        # Mandatory requirement: "Can you explain this Python code?" must classify as CODING, not general conversation
        prompt = "Can you explain this Python code?"
        cat, meta = TaskDetector.detect_task(prompt)
        assert cat == TaskCategory.CODING

        prompt = "Write a Python script to download images from a list of URLs"
        cat, meta = TaskDetector.detect_task(prompt)
        assert cat == TaskCategory.CODING

    def test_coding_followup_context_detection(self):
        # Multi-turn context test: assistant provided code in last turn, user asks follow-up
        context = [
            {"role": "user", "content": "How do I make a web request in python?"},
            {"role": "assistant", "content": "```python\nimport httpx\nr = httpx.get('url')\n```"},
        ]
        cat, meta = TaskDetector.detect_task("now add error handling and retry logic", context_history=context)
        assert cat == TaskCategory.CODING

    def test_debugging_detection(self):
        prompt = "I keep getting this error:\nTraceback (most recent call last):\n  File 'app.py', line 12, in <module>\nIndexError: list index out of range"
        cat, meta = TaskDetector.detect_task(prompt)
        assert cat == TaskCategory.DEBUGGING

        prompt = "Why does my code throw NullPointerException on line 45?"
        cat, meta = TaskDetector.detect_task(prompt)
        assert cat == TaskCategory.DEBUGGING

    def test_complex_reasoning_detection(self):
        cat, meta = TaskDetector.detect_task("Which is larger, 9.11 or 9.9?")
        assert cat == TaskCategory.COMPLEX_REASONING

        cat, meta = TaskDetector.detect_task("Think step by step and prove that square root of 2 is irrational.")
        assert cat == TaskCategory.COMPLEX_REASONING

    def test_document_summarization_detection(self):
        long_text = (
            "Summarize the following document: The Industrial Revolution was a period of global transition "
            "of the human economy towards more widespread, efficient and stable manufacturing processes that "
            "succeeded the Agricultural Revolution. It began in Great Britain and spread to continental Europe "
            "and the United States during the period from around 1760 to about 1840. This transition included "
            "going from hand production methods to machines, new chemical manufacturing and iron production "
            "processes, the increasing use of steam power and water power, the development of machine tools "
            "and the rise of the mechanized factory system. The Industrial Revolution also led to an unprecedented "
            "rise in the rate of population growth. Textiles were the dominant industry of the Industrial "
            "Revolution in terms of employment, value of output and capital invested. The textile industry was "
            "also the first to use modern production methods. What are the key takeaways?"
        )
        cat, meta = TaskDetector.detect_task(long_text)
        assert cat == TaskCategory.DOCUMENT_SUMMARIZATION

    def test_long_form_generation_detection(self):
        cat, meta = TaskDetector.detect_task("Write a detailed essay about the future of artificial intelligence in healthcare.")
        assert cat == TaskCategory.LONG_FORM_GENERATION

        cat, meta = TaskDetector.detect_task("Generate a comprehensive guide on modern distributed systems.")
        assert cat == TaskCategory.LONG_FORM_GENERATION

    def test_image_understanding_detection(self):
        # 1. Image in images list
        cat, meta = TaskDetector.detect_task("What is shown here?", images=["base64_image_data"])
        assert cat == TaskCategory.IMAGE_UNDERSTANDING

        # 2. Image attachment
        attachments = [{"file_name": "chart.png", "mime_type": "image/png", "path": "C:/tmp/chart.png"}]
        cat, meta = TaskDetector.detect_task("Explain the trends in this file", attachments=attachments)
        assert cat == TaskCategory.IMAGE_UNDERSTANDING

    def test_structured_data_extraction_detection(self):
        # 1. Explicit format_json flag
        cat, meta = TaskDetector.detect_task("Extract the users from this list", format_json=True)
        assert cat == TaskCategory.STRUCTURED_DATA_EXTRACTION

        # 2. Text asking for JSON output
        cat, meta = TaskDetector.detect_task("Return the output strictly in valid JSON format with keys name and age")
        assert cat == TaskCategory.STRUCTURED_DATA_EXTRACTION

    def test_research_oriented_analysis_detection(self):
        cat, meta = TaskDetector.detect_task("Provide an in-depth comparative analysis of React vs Vue architecture based on published benchmarks.")
        assert cat == TaskCategory.RESEARCH_ORIENTED_ANALYSIS


class TestModelRouter:
    """Test deterministic model scoring, capability matching, and anti-thrashing affinity."""

    def test_vision_task_routes_to_vision_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="What is inside this picture?",
            current_active_model="llama3.2:3b",
            images=["data:image/png;base64,abc1234"],
        )
        assert decision.selected_model == "gemma3:4b"
        assert decision.detected_task == TaskCategory.IMAGE_UNDERSTANDING
        assert decision.switched is True
        assert "Vision Model" in decision.ui_badge

    def test_complex_reasoning_routes_to_reasoning_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="Which number is bigger: 9.11 or 9.9? Think step by step.",
            current_active_model="llama3.2:3b",
        )
        assert decision.selected_model == "deepseek-r1:7b"
        assert decision.detected_task == TaskCategory.COMPLEX_REASONING
        assert decision.switched is True
        assert "Reasoning Model" in decision.ui_badge

    def test_coding_routes_to_strong_coding_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="Can you explain this Python code and refactor it into an async generator?",
            current_active_model="llama3.2:3b",
        )
        # deepseek-r1:7b and qwen3.5:4b are both coding models
        assert decision.selected_model in ["deepseek-r1:7b", "qwen3.5:4b"]
        assert decision.detected_task == TaskCategory.CODING
        assert "Coding Model" in decision.ui_badge

    def test_greeting_routes_to_fast_lightweight_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="Hello Bond! Good morning!",
            current_active_model="deepseek-r1:7b",
        )
        assert decision.selected_model == "llama3.2:3b"
        assert decision.detected_task == TaskCategory.GREETING
        assert decision.switched is True
        assert "Fast Model" in decision.ui_badge

    def test_anti_thrashing_affinity_retains_active_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        # When llama3.2:3b is already active and receives a general conversation request,
        # it should retain llama3.2:3b rather than switching back and forth
        decision = router.route_request(
            prompt="Tell me an interesting fun fact about dolphins.",
            current_active_model="llama3.2:3b",
        )
        assert decision.selected_model == "llama3.2:3b"
        assert decision.switched is False
        assert "+15 active model affinity" in decision.reason

    def test_auto_routing_disabled_respects_pinned_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="Write a Python script for web scraping",
            current_active_model="llama3.2:3b",
            auto_routing_enabled=False,
        )
        # Even though task is coding, user disabled auto-routing
        assert decision.selected_model == "llama3.2:3b"
        assert decision.switched is False
        assert "Auto-routing disabled" in decision.reason

    def test_resource_aware_safe_fallback(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        # Restrict max allowed RAM to 2600 MB (deepseek requires 5200 MB, gemma 3200 MB, qwen 3000 MB)
        decision = router.route_request(
            prompt="Think step by step and prove this logic theorem",
            current_active_model="deepseek-r1:7b",
            max_allowed_ram_mb=2500,
        )
        # DeepSeek is heavily penalized for exceeding RAM budget; lightweight model is selected
        assert decision.selected_model == "llama3.2:3b"
        assert decision.fallback_used is True

    def test_research_limitation_flag(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="What is the latest Apple stock price today?",
            current_active_model="llama3.2:3b",
        )
        # When real-time query terms are detected
        assert decision.research_limitation_noted is True

    def test_get_router_status(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        status = router.get_router_status()
        assert status["registered_models_count"] == 4
        assert "llama3.2:3b" in status["installed_models"]
        assert status["has_vision_model"] is True
        assert status["has_reasoning_model"] is True
        assert status["has_coding_model"] is True
        assert len(status["supported_categories"]) == 12


class TestModelManagerRoutingIntegration:
    """Verify ModelManager integration with ModelRouter."""

    def test_route_and_select_model_triggers_switch(self, mock_registry):
        from app.ai.model_manager import ModelManager

        mock_client = MagicMock()
        mock_client.list_models.return_value = [
            {"name": "llama3.2:3b", "model": "llama3.2:3b"},
            {"name": "gemma3:4b", "model": "gemma3:4b"},
            {"name": "deepseek-r1:7b", "model": "deepseek-r1:7b"},
        ]

        manager = ModelManager(client=mock_client)
        manager.capability_registry = mock_registry
        manager.router = ModelRouter(registry=mock_registry)
        manager.set_model("llama3.2:3b")

        # Vision request should trigger automatic switch to gemma3:4b
        decision = manager.route_and_select_model(
            prompt="Analyze this diagram",
            images=["image_data_here"],
        )

        assert decision.selected_model == "gemma3:4b"
        assert decision.switched is True
        assert manager.active_model == "gemma3:4b"
        assert manager.get_last_routing_decision()["selected_model"] == "gemma3:4b"


class TestRouterApiEndpoints:
    """Verify REST API endpoints for model router status and toggling."""

    def test_router_status_and_toggle_endpoints(self):
        from fastapi.testclient import TestClient
        from app.api.server import create_app

        app = create_app()
        client = TestClient(app, base_url="http://127.0.0.1:8000")

        # Test status endpoint
        resp = client.get("/api/models/router/status", headers={"Origin": "http://127.0.0.1:8000"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "auto_routing_enabled" in data
        assert "router" in data
        assert len(data["router"]["supported_categories"]) == 12

        # Test toggle endpoint: turn off auto routing
        resp_toggle = client.post(
            "/api/models/router/toggle",
            json={"enabled": False},
            headers={"Origin": "http://127.0.0.1:8000"},
        )
        assert resp_toggle.status_code == 200
        assert resp_toggle.json()["auto_routing_enabled"] is False

        # Re-enable auto routing
        resp_toggle_back = client.post(
            "/api/models/router/toggle",
            json={"enabled": True},
            headers={"Origin": "http://127.0.0.1:8000"},
        )
        assert resp_toggle_back.status_code == 200
        assert resp_toggle_back.json()["auto_routing_enabled"] is True
