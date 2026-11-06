"""Unit and integration tests for Model Capability Registry (Phase 2)."""

import pytest
from unittest.mock import MagicMock, patch

from app.ai.model_capability_registry import (
    ModelCapability,
    ModelProfile,
    ModelCapabilityRegistry,
    verify_model_capabilities,
    format_size,
    parse_parameter_size_billions,
    get_model_capability_registry,
)
from app.ai.model_manager import ModelManager


class TestModelCapabilityEnum:
    """Verify all required capability categories exist."""

    def test_all_nine_capabilities_defined(self):
        expected_caps = {
            "fast_response",
            "general_conversation",
            "reasoning",
            "coding",
            "long_context",
            "summarization",
            "structured_output",
            "vision",
            "multilingual",
        }
        actual_caps = {c.value for c in ModelCapability}
        assert expected_caps.issubset(actual_caps)
        assert len(actual_caps) == 9


class TestModelProfile:
    """Verify ModelProfile serialization and helper methods."""

    def test_model_profile_serialization_roundtrip(self):
        prof = ModelProfile(
            model_id="llama3.2:3b",
            display_name="Llama 3.2 (3.2B)",
            installed=True,
            size_bytes=2019393536,
            size_formatted="1.88 GB",
            quantization="Q4_K_M",
            family="llama",
            families=["llama"],
            parameter_size="3.2B",
            context_capacity=131072,
            estimated_vram_mb=2726,
            capabilities=[
                ModelCapability.FAST_RESPONSE,
                ModelCapability.GENERAL_CONVERSATION,
                ModelCapability.LONG_CONTEXT,
                ModelCapability.SUMMARIZATION,
                ModelCapability.STRUCTURED_OUTPUT,
            ],
            is_online=True,
            is_local=True,
            benchmark_scores={"first_token_ms": 420},
            verification_details={"verified_via": "metadata"},
        )

        d = prof.to_dict()
        assert d["model_id"] == "llama3.2:3b"
        assert d["capabilities"] == [
            "fast_response",
            "general_conversation",
            "long_context",
            "summarization",
            "structured_output",
        ]
        assert d["estimated_vram_mb"] == 2726
        assert d["benchmark_scores"]["first_token_ms"] == 420

        restored = ModelProfile.from_dict(d)
        assert restored.model_id == prof.model_id
        assert restored.display_name == prof.display_name
        assert restored.capabilities == prof.capabilities
        assert restored.has_capability(ModelCapability.FAST_RESPONSE)
        assert not restored.has_capability(ModelCapability.VISION)


class TestCapabilityVerification:
    """Verify capability classification based on metadata, architecture, and constraints."""

    def test_vision_not_granted_by_model_name_alone(self):
        """A model named 'vision-master:latest' without vision architecture MUST NOT have VISION capability."""
        caps, ctx, vram, details = verify_model_capabilities(
            model_id="vision-master:latest",
            tag_details={"family": "llama", "parameter_size": "7B"},
            show_data={"model_info": {"general.architecture": "llama"}},
            size_bytes=4 * (1024 ** 3),
        )
        assert ModelCapability.VISION not in caps
        assert details["vision_verified"] is False

    def test_vision_verified_by_clip_family(self):
        """Gemma 3 with 'clip' in families is verified as VISION capable."""
        caps, ctx, vram, details = verify_model_capabilities(
            model_id="gemma3:4b",
            tag_details={"family": "gemma3", "families": ["gemma3", "clip"], "parameter_size": "3.9B"},
            show_data={
                "model_info": {
                    "general.architecture": "gemma3",
                    "gemma3.context_length": 131072,
                }
            },
            size_bytes=int(3.12 * (1024 ** 3)),
        )
        assert ModelCapability.VISION in caps
        assert details["vision_verified"] is True
        assert any("CLIP" in ev for ev in details["vision_evidence"])

    def test_vision_verified_by_mllama(self):
        """Llama 3.2-Vision with 'mllama' family is verified as VISION capable."""
        caps, ctx, vram, details = verify_model_capabilities(
            model_id="llama3.2-vision:11b",
            tag_details={"family": "mllama", "families": ["mllama"], "parameter_size": "11B"},
            show_data={"model_info": {"general.architecture": "mllama", "mllama.context_length": 131072}},
            size_bytes=int(7.9 * (1024 ** 3)),
        )
        assert ModelCapability.VISION in caps
        assert details["vision_verified"] is True

    def test_reasoning_verified_by_thinking_template(self):
        """Model with <think> in template (DeepSeek-R1) is verified as REASONING capable."""
        caps, ctx, vram, details = verify_model_capabilities(
            model_id="deepseek-r1:7b",
            tag_details={"family": "qwen2", "families": ["qwen2"], "parameter_size": "7.6B"},
            show_data={
                "template": "{{ if .System }}{{ .System }}{{ end }}<think>\n{{ .Prompt }}</think>",
                "model_info": {"general.architecture": "qwen2", "qwen2.context_length": 131072},
            },
            size_bytes=int(4.36 * (1024 ** 3)),
        )
        assert ModelCapability.REASONING in caps
        assert ModelCapability.CODING in caps
        assert details["reasoning_verified"] is True

    def test_fast_response_for_small_model_only(self):
        """Small models (<= 4.5B) are marked FAST_RESPONSE; large models (70B) are not."""
        small_caps, _, _, _ = verify_model_capabilities(
            model_id="llama3.2:3b",
            tag_details={"family": "llama", "parameter_size": "3.2B"},
            show_data={"model_info": {"llama.context_length": 131072}},
            size_bytes=int(1.88 * (1024 ** 3)),
        )
        assert ModelCapability.FAST_RESPONSE in small_caps

        large_caps, _, _, _ = verify_model_capabilities(
            model_id="llama3.3:70b",
            tag_details={"family": "llama", "parameter_size": "70B"},
            show_data={"model_info": {"llama.context_length": 131072}},
            size_bytes=int(42 * (1024 ** 3)),
        )
        assert ModelCapability.FAST_RESPONSE not in large_caps

    def test_cloud_models_not_marked_fast_response(self):
        """Cloud models (e.g. 1.65T) are not marked as small local FAST_RESPONSE."""
        cloud_caps, _, _, _ = verify_model_capabilities(
            model_id="deepseek-v4-pro:cloud",
            tag_details={"family": "deepseek", "parameter_size": "1.65T"},
            show_data={"model_info": {"deepseek.context_length": 1048576}},
            size_bytes=0,
        )
        assert ModelCapability.FAST_RESPONSE not in cloud_caps

    def test_context_capacity_and_long_context(self):
        """Context >= 16384 enables LONG_CONTEXT; < 16384 does not."""
        long_caps, ctx_long, _, _ = verify_model_capabilities(
            model_id="qwen3.5:4b",
            tag_details={"family": "qwen35", "parameter_size": "4.2B"},
            show_data={"model_info": {"qwen35.context_length": 262144}},
            size_bytes=int(3.1 * (1024 ** 3)),
        )
        assert ctx_long == 262144
        assert ModelCapability.LONG_CONTEXT in long_caps
        assert ModelCapability.SUMMARIZATION in long_caps

        short_caps, ctx_short, _, _ = verify_model_capabilities(
            model_id="legacy-model:latest",
            tag_details={"family": "legacy", "parameter_size": "3B"},
            show_data={"model_info": {"legacy.context_length": 2048}},
            size_bytes=int(2.0 * (1024 ** 3)),
        )
        assert ctx_short == 2048
        assert ModelCapability.LONG_CONTEXT not in short_caps
        assert ModelCapability.SUMMARIZATION not in short_caps


class TestModelCapabilityRegistry:
    """Test registry refresh, lookup, filtering, hardware awareness, and dynamic model updates."""

    @pytest.fixture
    def mock_ollama_client(self):
        cli = MagicMock()
        cli.list_models.return_value = [
            {
                "name": "llama3.2:3b",
                "size": int(1.88 * (1024 ** 3)),
                "details": {"family": "llama", "parameter_size": "3.2B", "quantization_level": "Q4_K_M"},
            },
            {
                "name": "gemma3:4b",
                "size": int(3.12 * (1024 ** 3)),
                "details": {"family": "gemma3", "families": ["gemma3", "clip"], "parameter_size": "3.9B"},
            },
            {
                "name": "deepseek-r1:7b",
                "size": int(4.36 * (1024 ** 3)),
                "details": {"family": "qwen2", "families": ["qwen2"], "parameter_size": "7.6B"},
            },
            {
                "name": "all-minilm:latest",
                "size": int(0.12 * (1024 ** 3)),
                "details": {"family": "bert"},
            },
        ]
        cli.show_model.side_effect = lambda tag: {
            "llama3.2:3b": {"model_info": {"llama.context_length": 131072}},
            "gemma3:4b": {"model_info": {"gemma3.context_length": 131072}},
            "deepseek-r1:7b": {
                "template": "<think>{{ .Prompt }}</think>",
                "model_info": {"qwen2.context_length": 131072},
            },
        }.get(tag, {})
        return cli

    def test_registry_refresh_and_model_filtering(self, mock_ollama_client):
        reg = ModelCapabilityRegistry(client=mock_ollama_client)
        models = reg.refresh()

        # Pure embedding models (all-minilm) must be filtered out
        ids = [m.model_id for m in models]
        assert "llama3.2:3b" in ids
        assert "gemma3:4b" in ids
        assert "deepseek-r1:7b" in ids
        assert "all-minilm:latest" not in ids

    def test_capability_queries(self, mock_ollama_client):
        reg = ModelCapabilityRegistry(client=mock_ollama_client)
        reg.refresh()

        # Vision query
        vision_models = reg.get_models_for_capability(ModelCapability.VISION)
        assert len(vision_models) == 1
        assert vision_models[0].model_id == "gemma3:4b"
        assert reg.is_vision_capable("gemma3:4b") is True
        assert reg.is_vision_capable("llama3.2:3b") is False

        # Reasoning query
        reasoning_models = reg.get_models_for_capability(ModelCapability.REASONING)
        assert len(reasoning_models) == 1
        assert reasoning_models[0].model_id == "deepseek-r1:7b"
        assert reg.is_reasoning_capable("deepseek-r1:7b") is True
        assert reg.is_reasoning_capable("llama3.2:3b") is False

    def test_get_best_model_for_task(self, mock_ollama_client):
        reg = ModelCapabilityRegistry(client=mock_ollama_client)
        reg.refresh()

        # Best vision model
        best_vision = reg.get_best_model_for_task(ModelCapability.VISION)
        assert best_vision is not None
        assert best_vision.model_id == "gemma3:4b"

        # Best reasoning model
        best_reasoning = reg.get_best_model_for_task(ModelCapability.REASONING)
        assert best_reasoning is not None
        assert best_reasoning.model_id == "deepseek-r1:7b"

        # Best fast response model
        best_fast = reg.get_best_model_for_task(ModelCapability.FAST_RESPONSE)
        assert best_fast is not None
        assert best_fast.model_id == "llama3.2:3b"

    def test_hardware_aware_filtering(self, mock_ollama_client):
        reg = ModelCapabilityRegistry(client=mock_ollama_client)
        reg.refresh()

        # Restrict to low VRAM budget (3000 MB)
        # DeepSeek-R1 (needs ~5600 MB) should be excluded
        best_model = reg.get_best_model_for_task(ModelCapability.GENERAL_CONVERSATION, max_memory_mb=3000)
        assert best_model is not None
        assert best_model.estimated_vram_mb <= 3000

    def test_dynamic_model_removal(self, mock_ollama_client):
        reg = ModelCapabilityRegistry(client=mock_ollama_client)
        reg.refresh()
        assert reg.get_model("gemma3:4b").installed is True

        # Simulate user uninstalling gemma3
        mock_ollama_client.list_models.return_value = [
            {
                "name": "llama3.2:3b",
                "size": int(1.88 * (1024 ** 3)),
                "details": {"family": "llama", "parameter_size": "3.2B"},
            }
        ]
        reg.refresh()

        # Gemma3 profile should remain known but marked uninstalled & offline
        gemma = reg.get_model("gemma3:4b")
        assert gemma is not None
        assert gemma.installed is False
        assert gemma.is_online is False

        # Only llama3.2 is installed
        installed = reg.get_installed_models()
        assert len(installed) == 1
        assert installed[0].model_id == "llama3.2:3b"

    def test_record_usage_and_benchmarks(self, mock_ollama_client):
        reg = ModelCapabilityRegistry(client=mock_ollama_client)
        reg.refresh()

        reg.record_usage("llama3.2:3b")
        prof = reg.get_model("llama3.2:3b")
        assert prof.last_used_timestamp is not None

        reg.record_benchmark("llama3.2:3b", "p95_ms", 1250)
        assert prof.benchmark_scores["p95_ms"] == 1250


class TestModelManagerIntegration:
    """Test ModelManager integration with ModelCapabilityRegistry."""

    def test_model_manager_has_capability_helpers(self):
        mock_cli = MagicMock()
        mock_cli.list_models.return_value = [
            {
                "name": "llama3.2:3b",
                "size": int(1.88 * (1024 ** 3)),
                "details": {"family": "llama", "parameter_size": "3.2B"},
            },
            {
                "name": "gemma3:4b",
                "size": int(3.12 * (1024 ** 3)),
                "details": {"family": "gemma3", "families": ["gemma3", "clip"], "parameter_size": "3.9B"},
            },
        ]
        mock_cli.show_model.return_value = {"model_info": {"llama.context_length": 131072}}

        mgr = ModelManager(client=mock_cli, default_model="llama3.2:3b")
        mgr.refresh_installed_models(auto_start=False)

        assert mgr.capability_registry is not None
        assert mgr.is_vision_capable("gemma3:4b") is True
        assert mgr.is_vision_capable("llama3.2:3b") is False

        # Check get_status includes capabilities list
        status = mgr.get_status()
        assert "capabilities" in status
        assert len(status["capabilities"]) >= 1

        # Check best model for task
        best_vision = mgr.get_best_model_for_task(ModelCapability.VISION)
        assert best_vision == "gemma3:4b"
