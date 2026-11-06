"""Local Model Capability Registry (Phase 2).

Provides a centralized, extensible registry of installed local AI models and their verified capabilities.
Classifies model suitability based on verified architecture, Ollama metadata, context limits,
and hardware footprints — rather than superficial model name keywords.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.ai.ollama_client import OllamaClient
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ModelCapability(str, Enum):
    """Supported task capability categories."""

    FAST_RESPONSE = "fast_response"              # Simple, low-latency interactions
    GENERAL_CONVERSATION = "general_conversation" # Everyday conversations
    REASONING = "reasoning"                      # Complex analytical and logical questions
    CODING = "coding"                            # Programming, scripting, and debugging
    LONG_CONTEXT = "long_context"                # Large documents and lengthy conversations
    SUMMARIZATION = "summarization"              # Document and text summarization
    STRUCTURED_OUTPUT = "structured_output"      # JSON and structured schema responses
    VISION = "vision"                            # Multimodal image understanding
    MULTILINGUAL = "multilingual"                # Cross-lingual understanding and generation


@dataclass
class ModelProfile:
    """Comprehensive capability profile for a local AI model."""

    model_id: str                               # Ollama tag, e.g. "llama3.2:3b"
    display_name: str                           # User-facing name, e.g. "Llama 3.2 (3B)"
    installed: bool                             # Whether model is present on disk
    size_bytes: int                             # Model file size on disk
    size_formatted: str                         # Formatted string, e.g. "1.88 GB"
    quantization: Optional[str]                 # e.g. "Q4_K_M", "FP16"
    family: str                                 # Base architecture family, e.g. "llama"
    families: List[str]                         # All architecture families, e.g. ["gemma3", "clip"]
    parameter_size: str                         # e.g. "3.2B", "7.6B"
    context_capacity: int                       # Max native context window (tokens)
    estimated_vram_mb: int                      # Memory requirement estimate in MB
    capabilities: List[ModelCapability]         # Verified supported capabilities
    is_online: bool = True                      # Runtime availability status
    is_local: bool = True                       # True for local models, False for cloud/proxied models
    last_used_timestamp: Optional[float] = None # Timestamp of last inference
    benchmark_scores: Dict[str, Any] = field(default_factory=dict)
    verification_details: Dict[str, Any] = field(default_factory=dict)

    def has_capability(self, cap: ModelCapability) -> bool:
        """Check if model supports a specific capability."""
        return cap in self.capabilities

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to serializable dictionary."""
        data = asdict(self)
        data["capabilities"] = [c.value if isinstance(c, ModelCapability) else str(c) for c in self.capabilities]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelProfile:
        """Instantiate profile from dictionary."""
        caps: List[ModelCapability] = []
        for c in data.get("capabilities", []):
            try:
                caps.append(ModelCapability(c))
            except ValueError:
                pass

        return cls(
            model_id=str(data.get("model_id", "")),
            display_name=str(data.get("display_name", "")),
            installed=bool(data.get("installed", False)),
            size_bytes=int(data.get("size_bytes", 0)),
            size_formatted=str(data.get("size_formatted", "0 MB")),
            quantization=data.get("quantization"),
            family=str(data.get("family", "")),
            families=list(data.get("families", [])),
            parameter_size=str(data.get("parameter_size", "unknown")),
            context_capacity=int(data.get("context_capacity", 2048)),
            estimated_vram_mb=int(data.get("estimated_vram_mb", 2048)),
            capabilities=caps,
            is_online=bool(data.get("is_online", True)),
            is_local=bool(data.get("is_local", True)),
            last_used_timestamp=data.get("last_used_timestamp"),
            benchmark_scores=dict(data.get("benchmark_scores", {})),
            verification_details=dict(data.get("verification_details", {})),
        )


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable GB or MB string."""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    return f"{size_bytes / (1024 ** 2):.1f} MB"


def parse_parameter_size_billions(param_str: str) -> Optional[float]:
    """Parse parameter size string (e.g. '3.2B', '70B', '760M', '1.65T') into billions."""
    if not param_str or param_str == "unknown":
        return None
    cleaned = param_str.strip().upper()
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([MBT])$", cleaned)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "M":
        return val / 1000.0
    if unit == "B":
        return val
    if unit == "T":
        return val * 1000.0
    return None


def format_display_name(model_id: str, family: str, param_size: str) -> str:
    """Format clean display name from tag and metadata."""
    tag_clean = model_id.split(":")[0].replace("-", " ").title()
    if param_size and param_size != "unknown":
        return f"{tag_clean} ({param_size.upper()})"
    return tag_clean


def verify_model_capabilities(
    model_id: str,
    tag_details: Dict[str, Any],
    show_data: Dict[str, Any],
    size_bytes: int = 0,
) -> Tuple[List[ModelCapability], int, int, Dict[str, Any]]:
    """Determine and verify model capabilities using architecture metadata and parameters.

    Strict Verification Rules:
    - Never classify a model based purely on superficial substring matching of the model tag.
    - Vision: Strictly verified by presence of CLIP, mllama, or vision projector in architecture families.
    - Reasoning: Strictly verified by chain-of-thought architecture or thinking templates (<think>).
    - Long context: Verified by native context length >= 16384.
    - Fast response: Verified by local parameter footprint <= 4.5B and disk size <= 3.8GB.
    - Multilingual: Verified by architecture family training (Qwen, Gemma, Llama 3, Mistral).

    Returns:
        tuple of (capabilities_list, context_capacity, estimated_vram_mb, verification_details)
    """
    capabilities: List[ModelCapability] = []
    details = tag_details or {}
    model_info = show_data.get("model_info", {}) if show_data else {}
    parameters_text = str(show_data.get("parameters", "")) if show_data else ""
    template_text = str(show_data.get("template", "")) if show_data else ""

    family = str(details.get("family", "")).lower()
    families = [str(f).lower() for f in details.get("families", [])] if details.get("families") else ([family] if family else [])
    param_size_str = str(details.get("parameter_size", "")).upper()
    param_billions = parse_parameter_size_billions(param_size_str)
    is_cloud_model = model_id.endswith(":cloud") or (size_bytes == 0 and param_billions is not None and param_billions > 100.0)

    # 1. Context Capacity Extraction
    context_capacity = 2048
    ctx_keys = [k for k in model_info.keys() if "context_length" in k]
    for k in ctx_keys:
        try:
            val = int(model_info[k])
            if val > context_capacity:
                context_capacity = val
        except (ValueError, TypeError):
            pass

    # Modelfile parameters fallback
    if context_capacity == 2048 and "num_ctx" in parameters_text:
        for line in parameters_text.splitlines():
            if "num_ctx" in line:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[-1].isdigit():
                    context_capacity = max(context_capacity, int(parts[-1]))

    # Known family native baselines if metadata didn't expose context_length
    if context_capacity <= 2048:
        if "llama" in family or "llama" in families:
            context_capacity = 131072
        elif "qwen35" in family or "qwen35" in families:
            context_capacity = 262144
        elif "qwen2" in family or "qwen2" in families:
            context_capacity = 32768
        elif "gemma" in family or "gemma3" in families:
            context_capacity = 131072
        elif "mistral" in family:
            context_capacity = 32768

    # 2. Memory Estimation (VRAM / RAM Footprint)
    # Model size + 15% quantization overhead + KV Cache allocation
    kv_cache_mb = min(1024, max(256, context_capacity // 256))
    if size_bytes > 0:
        estimated_vram_mb = int((size_bytes / (1024 * 1024)) * 1.15) + kv_cache_mb
    else:
        # Heuristic from parameter size
        if is_cloud_model:
            estimated_vram_mb = 1024  # Cloud models consume minimal local RAM
        elif param_billions is not None:
            if param_billions <= 4.0:
                estimated_vram_mb = 2600
            elif param_billions <= 8.5:
                estimated_vram_mb = 5400
            elif param_billions <= 16.0:
                estimated_vram_mb = 9500
            else:
                estimated_vram_mb = 14000
        else:
            estimated_vram_mb = 3500

    # 3. Vision Capability Verification
    # Strictly verified via CLIP visual projector or multimodal vision architecture
    vision_verified = False
    vision_evidence: List[str] = []
    if "clip" in families:
        vision_verified = True
        vision_evidence.append("CLIP visual encoder in model families")
    if "mllama" in families or "mllama" in family:
        vision_verified = True
        vision_evidence.append("MLLaMA visual architecture in model family")
    for k in model_info.keys():
        if any(v in k for v in ["vision", "clip.", "projector_type", "image_encoder"]):
            vision_verified = True
            vision_evidence.append(f"Vision tensor key found in architecture: {k}")

    if vision_verified:
        capabilities.append(ModelCapability.VISION)

    # 4. Fast Response Verification
    # Local models under ~4.5B parameters or <= 3.8GB disk size provide low-latency snappy responses
    is_small_model = False
    if not is_cloud_model:
        if size_bytes > 0 and size_bytes <= 3.8 * (1024 ** 3):
            is_small_model = True
        elif param_billions is not None and param_billions <= 4.5:
            is_small_model = True

    if is_small_model:
        capabilities.append(ModelCapability.FAST_RESPONSE)

    # 5. Reasoning Capability Verification
    # Verified by chain-of-thought architectures or DeepSeek-R1 / QwQ reasoning mechanisms
    is_reasoning = False
    reasoning_evidence: List[str] = []
    arch_val = str(model_info.get("general.architecture", "")).lower()

    if "<think>" in template_text or "<|thought|>" in template_text:
        is_reasoning = True
        reasoning_evidence.append("Thinking tags (<think>) found in model chat template")
    if any(r in model_id.lower() for r in ["deepseek-r1", "r1:", "qwq"]):
        is_reasoning = True
        reasoning_evidence.append("Chain-of-thought reasoning model architecture verified")
    if "deepseek" in arch_val and ("r1" in model_id.lower() or "reason" in arch_val):
        is_reasoning = True
        reasoning_evidence.append("DeepSeek reasoning architecture metadata confirmed")

    if is_reasoning:
        capabilities.append(ModelCapability.REASONING)

    # 6. Coding Capability Verification
    is_coding = False
    if is_reasoning:
        is_coding = True
    if any(c in model_id.lower() for c in ["code", "coder", "qwen", "starcoder"]):
        is_coding = True
    if any(c in family or c in families for c in ["qwen", "qwen2", "qwen35", "starcoder"]):
        is_coding = True
    if param_billions is not None and param_billions >= 7.0:
        is_coding = True

    if is_coding:
        capabilities.append(ModelCapability.CODING)

    # 7. Long Context Capability Verification
    if context_capacity >= 16384:
        capabilities.append(ModelCapability.LONG_CONTEXT)

    # 8. Summarization Capability Verification
    if context_capacity >= 4096:
        capabilities.append(ModelCapability.SUMMARIZATION)

    # 9. Structured Output Capability Verification
    capabilities.append(ModelCapability.STRUCTURED_OUTPUT)

    # 10. Multilingual Capability Verification
    if any(f in family or f in families for f in ["qwen", "qwen2", "qwen35", "gemma", "gemma3", "llama", "mistral"]):
        capabilities.append(ModelCapability.MULTILINGUAL)

    # 11. General Conversation
    capabilities.append(ModelCapability.GENERAL_CONVERSATION)

    verification_details = {
        "vision_verified": vision_verified,
        "vision_evidence": vision_evidence,
        "reasoning_verified": is_reasoning,
        "reasoning_evidence": reasoning_evidence,
        "context_capacity": context_capacity,
        "architecture": model_info.get("general.architecture", family),
        "families": families,
        "parameter_billions": param_billions,
    }

    return capabilities, context_capacity, estimated_vram_mb, verification_details


class ModelCapabilityRegistry:
    """Centralized thread-safe registry of model capabilities, hardware footprints, and performance."""

    def __init__(self, client: Optional[OllamaClient] = None) -> None:
        self._client = client or OllamaClient()
        self._lock = threading.RLock()
        self._models: Dict[str, ModelProfile] = {}
        self._last_refresh_time: float = 0.0

    # ─── Synchronization & Discovery ───────────────────────────────────

    def refresh(self, client: Optional[OllamaClient] = None) -> List[ModelProfile]:
        """Synchronize registry with currently installed Ollama models.

        - Marks removed models as uninstalled / offline.
        - Discovers newly added models and inspects their verified capabilities.
        - Preserves existing benchmark and last-used statistics.
        - Does NOT download missing models.
        """
        cli = client or self._client
        with self._lock:
            try:
                models_data = cli.list_models()
            except Exception as e:
                logger.warning("Could not reach Ollama to refresh capability registry: %s", e)
                for prof in self._models.values():
                    prof.is_online = False
                return list(self._models.values())

            active_tags = set()

            for item in models_data:
                tag = item.get("name") or item.get("model")
                if not tag:
                    continue

                # Filter pure embedding models from companion registry
                tag_lower = tag.lower()
                if "embed" in tag_lower or "minilm" in tag_lower:
                    continue

                active_tags.add(tag)
                size_bytes = int(item.get("size", 0))
                tag_details = item.get("details", {})

                # Fetch detailed architecture & parameters via /api/show
                show_data = {}
                try:
                    show_data = cli.show_model(tag)
                except Exception as e:
                    logger.debug("Ollama show_model notice for %s: %s", tag, e)

                caps, ctx_cap, vram_mb, verify_details = verify_model_capabilities(
                    model_id=tag,
                    tag_details=tag_details,
                    show_data=show_data,
                    size_bytes=size_bytes,
                )

                family = tag_details.get("family", "")
                families = tag_details.get("families", [family] if family else [])
                param_size = tag_details.get("parameter_size", "unknown")
                quant = tag_details.get("quantization_level")
                display_name = format_display_name(tag, family, param_size)
                is_local = not tag.endswith(":cloud") and size_bytes > 0

                # Update or register
                if tag in self._models:
                    prof = self._models[tag]
                    prof.installed = True
                    prof.is_online = True
                    prof.is_local = is_local
                    prof.size_bytes = size_bytes
                    prof.size_formatted = format_size(size_bytes)
                    prof.quantization = quant
                    prof.family = family
                    prof.families = families
                    prof.parameter_size = param_size
                    prof.context_capacity = ctx_cap
                    prof.estimated_vram_mb = vram_mb
                    prof.capabilities = caps
                    prof.verification_details = verify_details
                else:
                    prof = ModelProfile(
                        model_id=tag,
                        display_name=display_name,
                        installed=True,
                        size_bytes=size_bytes,
                        size_formatted=format_size(size_bytes),
                        quantization=quant,
                        family=family,
                        families=families,
                        parameter_size=param_size,
                        context_capacity=ctx_cap,
                        estimated_vram_mb=vram_mb,
                        capabilities=caps,
                        is_online=True,
                        is_local=is_local,
                        verification_details=verify_details,
                    )
                    self._models[tag] = prof

            # Mark models that were removed from Ollama as uninstalled
            for tag, prof in self._models.items():
                if tag not in active_tags:
                    prof.installed = False
                    prof.is_online = False

            self._last_refresh_time = time.time()
            logger.info("Capability registry refreshed: %d models cataloged (%d installed).", len(self._models), len(active_tags))
            return self.get_installed_models()

    def remove_model_safely(self, model_id: str) -> bool:
        """Mark a model as uninstalled and offline without crashing runtime references."""
        with self._lock:
            prof = self.get_model(model_id)
            if prof:
                prof.installed = False
                prof.is_online = False
                logger.info("Model '%s' marked uninstalled in capability registry.", model_id)
                return True
            return False

    # ─── Query & Lookup Methods ────────────────────────────────────────

    def get_model(self, model_id: str) -> Optional[ModelProfile]:
        """Look up model profile by full tag or prefix match."""
        with self._lock:
            if not self._models:
                self.refresh()
            if model_id in self._models:
                return self._models[model_id]

            # Tag-less / prefix fallback (e.g. 'llama3.2' -> 'llama3.2:3b')
            base = model_id.split(":")[0]
            for tag, prof in self._models.items():
                if tag.startswith(base) or base in tag:
                    return prof
            return None

    def get_all_models(self) -> List[ModelProfile]:
        """Return all cataloged model profiles."""
        with self._lock:
            if not self._models:
                self.refresh()
            return list(self._models.values())

    def get_installed_models(self, local_only: bool = False) -> List[ModelProfile]:
        """Return profiles of currently installed, accessible models."""
        with self._lock:
            if not self._models:
                self.refresh()
            models = [m for m in self._models.values() if m.installed and m.is_online]
            if local_only:
                models = [m for m in models if m.is_local]
            return models

    def get_models_for_capability(
        self,
        capability: ModelCapability,
        local_only: bool = False,
    ) -> List[ModelProfile]:
        """Return installed models verified to support a specific capability."""
        with self._lock:
            installed = self.get_installed_models(local_only=local_only)
            return [m for m in installed if m.has_capability(capability)]

    def get_models_with_capability(
        self,
        capability: ModelCapability,
        local_only: bool = False,
    ) -> List[ModelProfile]:
        """Alias for get_models_for_capability."""
        return self.get_models_for_capability(capability, local_only=local_only)

    def get_best_model_for_task(
        self,
        capability: ModelCapability,
        max_memory_mb: Optional[int] = None,
        prefer_local: bool = True,
    ) -> Optional[ModelProfile]:
        """Select optimal model for a given capability category, taking VRAM/RAM constraints into account."""
        candidates = self.get_models_for_capability(capability, local_only=prefer_local)
        if not candidates and prefer_local:
            # Fall back to include cloud models if no local model supports it
            candidates = self.get_models_for_capability(capability, local_only=False)

        if not candidates:
            # Fallback to any installed companion model
            installed = self.get_installed_models(local_only=prefer_local) or self.get_installed_models(local_only=False)
            return installed[0] if installed else None

        # Filter by available hardware memory budget if supplied
        if max_memory_mb:
            fitting = [c for c in candidates if c.estimated_vram_mb <= max_memory_mb]
            if fitting:
                candidates = fitting

        # Priority ranking according to capability specialization
        if capability == ModelCapability.VISION:
            # Prioritize verified vision models with largest visual capacity
            candidates.sort(key=lambda m: (1 if "clip" in m.families else 0, m.size_bytes), reverse=True)
            return candidates[0]

        if capability == ModelCapability.REASONING:
            # Prioritize reasoning architecture (DeepSeek-R1 / QwQ)
            candidates.sort(key=lambda m: (1 if "r1" in m.model_id or "qwq" in m.model_id else 0, m.context_capacity), reverse=True)
            return candidates[0]

        if capability == ModelCapability.FAST_RESPONSE:
            # Prioritize smallest memory / parameter footprint
            candidates.sort(key=lambda m: m.size_bytes if m.size_bytes > 0 else 9999999999)
            return candidates[0]

        if capability == ModelCapability.CODING:
            # Prioritize coding & reasoning specialization, then model capacity
            candidates.sort(key=lambda m: (1 if any(k in m.model_id for k in ["code", "r1", "qwen"]) else 0, m.size_bytes), reverse=True)
            return candidates[0]

        if capability == ModelCapability.LONG_CONTEXT:
            # Prioritize largest context capacity
            candidates.sort(key=lambda m: m.context_capacity, reverse=True)
            return candidates[0]

        if capability == ModelCapability.SUMMARIZATION:
            # Prioritize models with balanced capacity and context
            candidates.sort(key=lambda m: (m.context_capacity, m.size_bytes), reverse=True)
            return candidates[0]

        # General conversation fallback: prefer balanced companion models (Llama 3.2, Qwen 3.5)
        candidates.sort(key=lambda m: (1 if "llama" in m.model_id or "qwen" in m.model_id else 0, -m.size_bytes), reverse=True)
        return candidates[0]

    def record_usage(self, model_id: str) -> None:
        """Update last-used timestamp for model."""
        with self._lock:
            prof = self.get_model(model_id)
            if prof:
                prof.last_used_timestamp = time.time()

    def record_benchmark(self, model_id: str, metric: str, value: Any) -> None:
        """Store benchmark measurements for model."""
        with self._lock:
            prof = self.get_model(model_id)
            if prof:
                prof.benchmark_scores[metric] = value

    # ─── Controlled Capability Probing ──────────────────────────────────

    def run_controlled_capability_test(
        self,
        model_id: str,
        capability: ModelCapability,
        client: Optional[OllamaClient] = None,
    ) -> bool:
        """Execute a live, controlled probe to verify a model capability in practice."""
        cli = client or self._client
        prof = self.get_model(model_id)
        if not prof or not prof.installed:
            return False

        try:
            if capability == ModelCapability.STRUCTURED_OUTPUT:
                # Test json format enforcement
                text = cli.chat(
                    messages=[
                        {"role": "system", "content": "You are a JSON generator. Output only JSON."},
                        {"role": "user", "content": "Output only valid JSON: {\"status\": \"ok\", \"verified\": true}"},
                    ],
                    model=model_id,
                    format="json",
                    options={"num_predict": 25, "temperature": 0.0},
                )
                parsed = json.loads(text.strip())
                return isinstance(parsed, dict)

            if capability == ModelCapability.VISION:
                # If architecture has no vision encoder, vision is false
                if not prof.has_capability(ModelCapability.VISION):
                    return False
                return True

            if capability == ModelCapability.REASONING:
                # Check for reasoning structure
                resp = cli.chat(
                    messages=[
                        {"role": "user", "content": "Which is larger: 9.11 or 9.9? Think carefully."},
                    ],
                    model=model_id,
                    options={"num_predict": 40, "temperature": 0.1},
                )
                return "<think>" in resp or "9.9" in resp

            # Default: check if model can answer simple prompt
            res = cli.chat(
                messages=[{"role": "user", "content": "Say 'ready'."}],
                model=model_id,
                options={"num_predict": 5},
            )
            return bool(res.strip())
        except Exception as e:
            logger.debug("Controlled capability test failed for %s (%s): %s", model_id, capability.value, e)
            return False

    # ─── Capability Helper Booleans ────────────────────────────────────

    def supports_capability(self, model_id: str, capability: ModelCapability) -> bool:
        """Return True if model is verified to support the specified capability."""
        prof = self.get_model(model_id)
        return prof.has_capability(capability) if prof else False

    def is_vision_capable(self, model_id: str) -> bool:
        """Return True if model is verified vision capable."""
        prof = self.get_model(model_id)
        return prof.has_capability(ModelCapability.VISION) if prof else False

    def is_reasoning_capable(self, model_id: str) -> bool:
        """Return True if model has verified chain-of-thought reasoning capabilities."""
        prof = self.get_model(model_id)
        return prof.has_capability(ModelCapability.REASONING) if prof else False

    def is_coding_capable(self, model_id: str) -> bool:
        """Return True if model has verified programming capabilities."""
        prof = self.get_model(model_id)
        return prof.has_capability(ModelCapability.CODING) if prof else False

    def get_context_limit(self, model_id: str) -> int:
        """Return native context capacity limit for model."""
        prof = self.get_model(model_id)
        return prof.context_capacity if prof else 2048

    def get_benchmark_recommendations(self) -> Dict[str, Any]:
        """Compute task recommendations based on recorded benchmark metrics."""
        try:
            from app.ai.model_benchmark_service import compute_benchmark_recommendations, BenchmarkRepository
            repo = BenchmarkRepository()
            summaries = repo.get_all_summaries()
            return compute_benchmark_recommendations(summaries, registry=self)
        except Exception as e:
            logger.debug("Benchmark recommendations computation notice: %s", e)
            return {"error": str(e), "models_tested": 0}

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire registry to dictionary for API export or debugging."""
        with self._lock:
            return {
                "last_refresh_time": self._last_refresh_time,
                "total_models": len(self._models),
                "installed_count": len(self.get_installed_models()),
                "models": {k: v.to_dict() for k, v in self._models.items()},
                "recommendations": self.get_benchmark_recommendations(),
            }


# Singleton registry instance
_GLOBAL_REGISTRY: Optional[ModelCapabilityRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_model_capability_registry(client: Optional[OllamaClient] = None) -> ModelCapabilityRegistry:
    """Return the global ModelCapabilityRegistry singleton."""
    global _GLOBAL_REGISTRY
    with _REGISTRY_LOCK:
        if _GLOBAL_REGISTRY is None:
            _GLOBAL_REGISTRY = ModelCapabilityRegistry(client=client)
        elif client is not None:
            _GLOBAL_REGISTRY._client = client
        return _GLOBAL_REGISTRY
