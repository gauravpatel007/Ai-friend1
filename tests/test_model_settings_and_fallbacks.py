"""Comprehensive unit and integration tests for Phase 5:
Model Settings, User Preferences, Compatible Model Filtering, and Automatic Fallbacks.
"""

import time
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
)
from app.ai.model_manager import ModelManager


@pytest.fixture
def mock_registry():
    """Create a mock capability registry with installed local test models."""
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


class TestModelSelectionModes:
    """Test Manual vs. Automatic selection modes (Phase 5 requirement B)."""

    def test_manual_mode_strictly_respects_selected_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        # Even though prompt is complex coding (normally routes to deepseek or qwen),
        # manual mode must NOT switch from llama3.2:3b
        decision = router.route_request(
            prompt="Write a complete binary search tree in Rust with lifetimes and deletion.",
            current_active_model="llama3.2:3b",
            model_selection_mode="manual",
        )
        assert decision.selected_model == "llama3.2:3b"
        assert decision.switched is False
        assert "Manual mode" in decision.reason
        assert decision.model_unavailable is False

    def test_manual_mode_detects_unavailable_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="Hello there",
            current_active_model="nonexistent-model:99b",
            model_selection_mode="manual",
        )
        assert decision.selected_model == "nonexistent-model:99b"
        assert decision.switched is False
        assert decision.model_unavailable is True
        assert "unavailable" in decision.reason.lower() or "not installed" in decision.reason.lower()

    def test_auto_routing_enabled_false_acts_as_manual(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="Debug this Python traceback",
            current_active_model="gemma3:4b",
            auto_routing_enabled=False,
        )
        assert decision.selected_model == "gemma3:4b"
        assert decision.switched is False
        assert ("Manual mode" in decision.reason) or ("Auto-routing disabled" in decision.reason)


class TestResponsePriorities:
    """Test Fastest, Balanced, and Quality response priorities (Phase 5 requirement A)."""

    def test_fastest_priority_favors_compact_fast_models(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        # For general conversation, fastest should strongly favor lightweight fast models
        decision = router.route_request(
            prompt="Can you give me a few book recommendations for science fiction?",
            current_active_model="deepseek-r1:7b",
            response_priority="fastest",
        )
        # llama3.2:3b is fast and lightweight (2.0 GB)
        assert decision.selected_model in ["llama3.2:3b", "gemma3:4b"]
        assert decision.selected_model != "deepseek-r1:7b"

    def test_quality_priority_favors_reasoning_and_larger_models(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        decision = router.route_request(
            prompt="Think step by step and prove that the square root of 2 is irrational.",
            current_active_model="llama3.2:3b",
            response_priority="quality",
        )
        # deepseek-r1:7b has REASONING capability and 7B parameter capacity
        assert decision.selected_model == "deepseek-r1:7b"


class TestTaskSpecificPreferences:
    """Test user-defined task model preferences (Phase 5 requirement A)."""

    def test_task_preference_routes_to_preferred_model(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        task_prefs = {
            "coding": "qwen3.5:4b",
            "complex_reasoning": "deepseek-r1:7b",
        }

        # Coding prompt routed with user preference
        decision = router.route_request(
            prompt="def quicksort(arr):",
            current_active_model="llama3.2:3b",
            task_preferences=task_prefs,
        )
        assert decision.selected_model == "qwen3.5:4b"
        assert "preferred model" in decision.reason

    def test_auto_task_preference_uses_routing_algorithm(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        task_prefs = {
            "coding": "auto",
        }
        decision = router.route_request(
            prompt="Implement an LRU cache in Python",
            current_active_model="llama3.2:3b",
            task_preferences=task_prefs,
        )
        assert decision.selected_model in ["qwen3.5:4b", "deepseek-r1:7b"]


class TestCompatibleModelFiltering:
    """Test get_compatible_models_by_task only returns verified compatible models (Phase 5)."""

    def test_get_compatible_models_by_task(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        comp = router.get_compatible_models_by_task()

        assert "general_conversation" in comp
        assert "complex_reasoning" in comp
        assert "coding" in comp
        assert "document_summarization" in comp
        assert "vision" in comp

        # Vision should ONLY include gemma3:4b (the only model with VISION capability)
        assert comp["vision"] == ["gemma3:4b"]
        assert "llama3.2:3b" not in comp["vision"]
        assert "deepseek-r1:7b" not in comp["vision"]

        # Complex reasoning should include deepseek-r1:7b
        assert "deepseek-r1:7b" in comp["complex_reasoning"]
        assert "gemma3:4b" not in comp["complex_reasoning"]

        # Coding should include qwen3.5:4b and deepseek-r1:7b
        assert "qwen3.5:4b" in comp["coding"]
        assert "deepseek-r1:7b" in comp["coding"]
        assert "gemma3:4b" not in comp["coding"]


class TestModelFailureAndFallback:
    """Test Automatic Fallback Engine and Failure Tracking (Phase 5 requirement C & D)."""

    def test_model_manager_failure_tracking(self):
        mm = ModelManager(default_model="llama3.2:3b")
        assert mm.get_failed_models() == []

        mm.record_model_failure("deepseek-r1:7b", "CUDA out of memory")
        assert "deepseek-r1:7b" in mm.get_failed_models()

        # Clearing failure
        mm.clear_model_failure("deepseek-r1:7b")
        assert "deepseek-r1:7b" not in mm.get_failed_models()

    def test_router_excludes_failed_models_and_falls_back(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        # Prompt would normally select deepseek-r1:7b for complex reasoning
        # But deepseek-r1:7b has failed
        decision = router.route_request(
            prompt="Analyze this complex logical paradox and step through each contradiction",
            current_active_model="deepseek-r1:7b",
            failed_models=["deepseek-r1:7b"],
        )
        assert decision.selected_model != "deepseek-r1:7b"
        assert decision.selected_model in ["qwen3.5:4b", "llama3.2:3b", "gemma3:4b"]
        assert decision.fallback_used is True

    def test_material_capability_change_warning_on_fallback(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        # Deepseek (reasoning) failed -> fallback to llama3.2 (no reasoning)
        decision = router.route_request(
            prompt="Analyze this formal mathematical proof",
            current_active_model="deepseek-r1:7b",
            failed_models=["deepseek-r1:7b", "qwen3.5:4b"],
        )
        assert decision.fallback_used is True
        assert decision.material_change_note is not None
        assert "reasoning" in decision.material_change_note.lower()

    def test_memory_aware_fallback_avoids_heavyweight_models(self, mock_registry):
        router = ModelRouter(registry=mock_registry)
        # DeepSeek requires ~5200MB, but available memory is 3500MB
        decision = router.route_request(
            prompt="Solve this algorithm problem",
            current_active_model="llama3.2:3b",
            max_allowed_ram_mb=3500,
        )
        # Must not pick deepseek-r1:7b (exceeds 3500MB)
        assert decision.selected_model != "deepseek-r1:7b"
        assert decision.selected_model in ["qwen3.5:4b", "llama3.2:3b"]


class TestModelPreferencesAPI:
    """Test REST endpoints GET/POST /api/models/preferences."""

    def test_preferences_api_endpoints(self):
        from fastapi.testclient import TestClient
        from app.api.server import app

        client = TestClient(app)

        # 1. GET preferences
        resp = client.get("/api/models/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert "model_selection_mode" in data
        assert "response_priority" in data
        assert "task_preferred_models" in data
        assert "compatible_models_by_task" in data

        # 2. POST preferences update
        payload = {
            "model_selection_mode": "manual",
            "response_priority": "fastest",
            "active_model": "llama3.2:3b",
            "task_preferred_models": {
                "general_conversation": "auto",
                "complex_reasoning": "deepseek-r1:7b",
                "coding": "qwen3.5:4b",
                "document_summarization": "auto",
                "vision": "gemma3:4b",
            },
        }
        post_resp = client.post("/api/models/preferences", json=payload)
        assert post_resp.status_code == 200
        post_data = post_resp.json()
        assert post_data["model_selection_mode"] == "manual"
        assert post_data["response_priority"] == "fastest"
        assert post_data["task_preferred_models"]["coding"] == "qwen3.5:4b"

        # 3. Verify GET reflects persisted values
        verify_resp = client.get("/api/models/preferences")
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()
        assert verify_data["model_selection_mode"] == "manual"
        assert verify_data["response_priority"] == "fastest"
