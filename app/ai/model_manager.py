"""AI Model Manager.

Coordinates local LLM lifecycle, model discovery, active model selection,
on-demand model loading, and inactivity-based VRAM/RAM reclamation.
Ensures application resilience with descriptive diagnostics if Ollama is offline.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.ai.ollama_client import (
    OllamaClient,
    OllamaClientError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)
from app.ai.ollama_supervisor import OllamaSupervisor
from app.ai.model_capability_registry import (
    ModelCapability,
    ModelCapabilityRegistry,
    ModelProfile,
    get_model_capability_registry,
)
from app.ai.model_benchmark_service import (
    BenchmarkRepository,
    ModelBenchmarkRunner,
    get_model_benchmark_runner,
)
from app.ai.model_router import (
    ModelRouter,
    RoutingDecision,
    TaskCategory,
    get_model_router,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Priority order for auto-selecting small/efficient companion models
PREFERRED_MODELS = [
    "llama3.2:latest",
    "llama3.2:3b",
    "llama3.2",
    "qwen3.5:4b",
    "gemma3:4b",
    "qwen3:4b",
    "qwen3:1.7b",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "llama3.1:8b",
    "deepseek-r1:7b",
    "mistral:7b",
    "phi3:mini",
]

DEFAULT_INACTIVITY_TIMEOUT = 300.0  # 5 minutes


class ModelManager:
    """Manages Ollama model selection, memory unloading, and lifecycle diagnostics."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        default_model: str = "llama3.2:latest",
        inactivity_timeout_seconds: float = DEFAULT_INACTIVITY_TIMEOUT,
        model_keep_alive: str = "15m",
        supervisor: Optional[OllamaSupervisor] = None,
        config_manager: Optional[Any] = None,
    ) -> None:
        self.client = client or OllamaClient()
        self._configured_model = default_model
        self.active_model = default_model
        self.inactivity_timeout = inactivity_timeout_seconds
        self.model_keep_alive = model_keep_alive
        self.config_manager = config_manager
        self.supervisor = supervisor or OllamaSupervisor(config_manager=config_manager)
        self.capability_registry = get_model_capability_registry(client=self.client)
        self.benchmark_runner = get_model_benchmark_runner(client=self.client)
        self.router = get_model_router()
        self._last_activity_time = time.time()
        self._is_model_loaded = False
        self._cached_installed_models: List[str] = []
        self._last_availability_check_time: float = 0.0
        self._cached_availability: bool = False
        self._recent_failures: Dict[str, float] = {}

    def set_keep_alive(self, keep_alive: str) -> None:
        """Set Ollama keep_alive parameter (e.g. '2m', '5m', '15m')."""
        self.model_keep_alive = keep_alive.strip()

    def set_inactivity_timeout(self, timeout_seconds: float) -> None:
        """Set inactivity timeout in seconds before auto-unloading from RAM/VRAM."""
        self.inactivity_timeout = max(30.0, float(timeout_seconds))

    # ─── Availability & Discovery ──────────────────────────────────────

    def is_available(self, auto_start: bool = False) -> bool:
        """Check if local Ollama engine is reachable, optionally auto-launching it.

        Uses a tiered cache strategy:
        - If confirmed available within the last 10 seconds, skip the network check.
        - If confirmed unavailable within the last 2 seconds, skip to avoid repeated timeouts.
        """
        now = time.time()
        elapsed = now - self._last_availability_check_time

        # Positive cache: if recently confirmed available, trust it longer (60 seconds)
        if self._cached_availability and elapsed < 60.0:
            return True
        # Negative cache: avoid hammering if recently confirmed offline
        if not self._cached_availability and elapsed < 2.0:
            if auto_start:
                started = self.supervisor.ensure_server_running(self.client.base_url)
                self._cached_availability = started
                self._last_availability_check_time = now
                return started
            return False

        reachable = self.client.is_server_reachable(timeout=2.0)
        self._last_availability_check_time = now
        self._cached_availability = reachable
        if reachable:
            return True
        if auto_start:
            started = self.supervisor.ensure_server_running(self.client.base_url)
            self._cached_availability = started
            return started
        return False

    def refresh_installed_models(self, auto_start: bool = True) -> List[str]:
        """Fetch and cache list of installed models from Ollama."""
        if auto_start and not self.client.is_server_reachable():
            self.supervisor.ensure_server_running(self.client.base_url, timeout=4.0)

        try:
            models_data = self.client.list_models()
            names: List[str] = []
            for m in models_data:
                name = m.get("name") or m.get("model")
                if not name:
                    continue

                # Filter out pure embedding models from companion selection
                caps = m.get("capabilities") or []
                if isinstance(caps, str):
                    caps_str = caps.lower()
                    is_pure_embed = "embedding" in caps_str and "completion" not in caps_str
                elif isinstance(caps, (list, tuple, set)):
                    caps_lower = [str(c).lower() for c in caps]
                    is_pure_embed = "embedding" in caps_lower and "completion" not in caps_lower
                else:
                    is_pure_embed = False

                name_lower = name.lower()
                if "embed" in name_lower or "minilm" in name_lower or is_pure_embed:
                    continue

                names.append(name)

            self._cached_installed_models = names
            # Synchronize model capability registry
            try:
                self.capability_registry.refresh(self.client)
            except Exception as reg_err:
                logger.debug("Capability registry refresh notice: %s", reg_err)
            return names
        except OllamaClientError as e:
            logger.warning("Ollama server unavailable or timed out: %s. Using configured model.", e)
            self._cached_installed_models = []
            return []
        except Exception as e:
            logger.warning("Error discovering Ollama models: %s. Using configured model.", e)
            self._cached_installed_models = []
            return []

    def get_installed_models(self) -> List[str]:
        """Return list of installed models, refreshing if cache is empty."""
        if not self._cached_installed_models:
            return self.refresh_installed_models()
        return list(self._cached_installed_models)

    # ─── Model Selection ───────────────────────────────────────────────

    def select_active_model(self, model_name: Optional[str] = None) -> str:
        """Select active model with smart fallback to installed models.
        
        Args:
            model_name: Desired model name, or None to use configured/auto.
            
        Returns:
            The selected model name.
        """
        target = (model_name or self._configured_model).strip()
        if not target:
            return self.active_model

        # Fast path 1: active model already matches target and models are known
        if self.active_model and self.active_model == target and self._cached_installed_models:
            return self.active_model

        # Fast path 2: check cached installed models first to avoid blocking network calls
        if self._cached_installed_models and target in self._cached_installed_models:
            self.active_model = target
            logger.info("Selected model '%s' (cached exact match).", self.active_model)
            return self.active_model

        installed = self.refresh_installed_models(auto_start=False)

        if not installed:
            # If Ollama is offline or has no models, retain target name
            self.active_model = target
            return self.active_model

        # 1. Exact match with target (user requested or configured)
        if target in installed:
            self.active_model = target
            logger.info("Selected model '%s' (exact match).", self.active_model)
            return self.active_model

        # 2. Tag-less match for target (e.g. 'llama3.2:latest' -> 'llama3.2:3b', 'qwen3:1.7b' -> 'qwen3.5:4b')
        target_base = target.split(":")[0]
        for m in installed:
            if m == target_base or m.startswith(target_base + ":") or m.startswith(target_base):
                self.active_model = m
                logger.info("Selected model '%s' (matched base '%s').", m, target_base)
                return self.active_model

        # Prefer local companion models over remote cloud-only models for offline local AI friend
        local_installed = [m for m in installed if not m.endswith(":cloud")]
        selection_pool = local_installed if local_installed else installed

        # 3. Preference priority match
        for pref in PREFERRED_MODELS:
            pref_base = pref.split(":")[0]
            for m in selection_pool:
                if m == pref or m.startswith(pref_base + ":") or m == pref_base:
                    self.active_model = m
                    logger.info("Auto-selected preferred model '%s'.", m)
                    return self.active_model

        # 4. Fallback to first available model
        self.active_model = selection_pool[0]
        logger.info("Fallback to first available model '%s'.", self.active_model)
        return self.active_model

    def set_configured_model(self, model_name: str) -> None:
        """Update configured model and re-evaluate selection."""
        cleaned = model_name.strip()
        if not cleaned:
            return
        if cleaned == self.active_model and cleaned == self._configured_model:
            return
        self._configured_model = cleaned
        self.select_active_model(self._configured_model)

    def set_model(self, model_name: str) -> None:
        """Alias for set_configured_model to switch active model."""
        self.set_configured_model(model_name)

    # ─── Lifecycle & Activity Tracking ─────────────────────────────────

    def warmup_model(self) -> None:
        """Preload active model weights into GPU VRAM in background so first user query is instant."""
        if not self.is_available():
            return

        def _warmup_worker() -> None:
            try:
                url = f"{self.client.base_url}/api/generate"
                payload = {
                    "model": self.active_model,
                    "keep_alive": self.model_keep_alive,
                }
                if getattr(self.client, "_is_open_patched", False):
                    import json
                    import urllib.request
                    data_bytes = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=data_bytes,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.client._open(req, timeout=45.0) as resp:
                        if getattr(resp, "status", getattr(resp, "status_code", None)) == 200:
                            self._is_model_loaded = True
                            logger.info("Successfully pre-warmed model '%s' in GPU VRAM.", self.active_model)
                else:
                    resp = self.client._session.post(url, json=payload, timeout=45.0)
                    if resp.status_code == 200:
                        self._is_model_loaded = True
                        logger.info("Successfully pre-warmed model '%s' in GPU VRAM.", self.active_model)
            except Exception as e:
                logger.debug("Background model warmup note: %s", e)

        import threading
        t = threading.Thread(target=_warmup_worker, daemon=True)
        t.start()

    def touch_activity(self) -> None:
        """Record model activity to prevent premature inactivity unloading."""
        self._last_activity_time = time.time()
        self._is_model_loaded = True
        try:
            self.capability_registry.record_usage(self.active_model)
        except Exception:
            pass

    # ─── Capability Inspection Helpers ─────────────────────────────────

    def get_model_profile(self, model_id: Optional[str] = None) -> Optional[ModelProfile]:
        """Fetch verified profile for specified model or current active model."""
        target = model_id or self.active_model
        return self.capability_registry.get_model(target)

    def get_capabilities(self, model_id: Optional[str] = None) -> List[ModelCapability]:
        """Fetch verified capabilities list for specified model or active model."""
        prof = self.get_model_profile(model_id)
        return list(prof.capabilities) if prof else []

    def is_vision_capable(self, model_id: Optional[str] = None) -> bool:
        """Check if target model (or active model) supports verified multimodal vision."""
        target = model_id or self.active_model
        return self.capability_registry.is_vision_capable(target)

    def is_reasoning_capable(self, model_id: Optional[str] = None) -> bool:
        """Check if target model (or active model) supports verified reasoning."""
        target = model_id or self.active_model
        return self.capability_registry.is_reasoning_capable(target)

    def is_coding_capable(self, model_id: Optional[str] = None) -> bool:
        """Check if target model (or active model) supports verified coding."""
        target = model_id or self.active_model
        return self.capability_registry.is_coding_capable(target)

    def get_context_limit(self, model_id: Optional[str] = None) -> int:
        """Get native context window limit for model or active model."""
        target = model_id or self.active_model
        return self.capability_registry.get_context_limit(target)

    def get_best_model_for_task(
        self,
        capability: ModelCapability,
        max_memory_mb: Optional[int] = None,
        prefer_local: bool = True,
    ) -> Optional[str]:
        """Find the best installed model tag for a given capability category."""
        prof = self.capability_registry.get_best_model_for_task(
            capability=capability,
            max_memory_mb=max_memory_mb,
            prefer_local=prefer_local,
        )
        return prof.model_id if prof else None

    # ─── Benchmark Controls (Phase 3) ───────────────────────────────────

    def start_benchmark(
        self,
        models: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> bool:
        """Launch controlled background benchmark across installed models."""
        return self.benchmark_runner.start_benchmark(
            models=models,
            categories=categories,
            on_progress=on_progress,
        )

    def cancel_benchmark(self) -> bool:
        """Cancel ongoing benchmark run."""
        return self.benchmark_runner.cancel()

    def get_benchmark_progress(self) -> Dict[str, Any]:
        """Fetch current benchmark execution status."""
        return self.benchmark_runner.get_progress()

    def get_benchmark_results(
        self,
        model_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch historical benchmark records from SQLite repository."""
        records = self.benchmark_runner.repository.get_records(
            model_id=model_id,
            category=category,
            limit=limit,
        )
        return [r.to_dict() for r in records]

    def get_benchmark_recommendations(self) -> Dict[str, Any]:
        """Fetch evidenced task recommendations based on benchmark performance."""
        return self.capability_registry.get_benchmark_recommendations()

    # ─── Intelligent Automatic Routing & Fallbacks (Phases 4 & 5) ───────

    def record_model_failure(self, model_id: str, error: str = "") -> None:
        """Record model load/generation failure to avoid repeated failure loops."""
        self._recent_failures[model_id] = time.time()
        logger.warning("[FAILURE RECORDED] Model '%s' recorded as failed (error: %s).", model_id, error)

    def clear_model_failure(self, model_id: str) -> None:
        """Clear recorded failure for model upon successful inference or recovery."""
        self._recent_failures.pop(model_id, None)

    def get_failed_models(self, cooldown_seconds: float = 300.0) -> List[str]:
        """Return list of models that failed within cooldown period."""
        now = time.time()
        stale = [m for m, t in self._recent_failures.items() if now - t > cooldown_seconds]
        for m in stale:
            self._recent_failures.pop(m, None)
        return list(self._recent_failures.keys())

    def is_model_installed(self, model_id: str) -> bool:
        """Check if target model tag is currently installed in Ollama."""
        installed = self.get_installed_models()
        return model_id in installed

    def get_compatible_models_by_task(self) -> Dict[str, List[str]]:
        """Return compatible installed models for each user-configurable task."""
        if hasattr(self.router, "get_compatible_models_by_task"):
            return self.router.get_compatible_models_by_task()
        return {
            "general_conversation": self.get_installed_models(),
            "complex_reasoning": self.get_installed_models(),
            "coding": self.get_installed_models(),
            "document_summarization": self.get_installed_models(),
            "vision": [m for m in self.get_installed_models() if self.is_vision_capable(m)],
        }

    def route_and_select_model(
        self,
        prompt: str,
        context_history: Optional[List[Dict[str, str]]] = None,
        images: Optional[List[Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        is_voice: bool = False,
        format_json: bool = False,
        auto_routing_enabled: Optional[bool] = None,
        max_allowed_ram_mb: Optional[int] = None,
        model_selection_mode: Optional[str] = None,
        response_priority: Optional[str] = None,
        task_preferences: Optional[Dict[str, str]] = None,
        failed_models: Optional[List[str]] = None,
    ) -> RoutingDecision:
        """Deterministically route incoming request to optimal installed model and switch if needed."""
        cfg = getattr(self, "config_manager", None)
        if auto_routing_enabled is None:
            auto_routing_enabled = (
                bool(cfg.get("ai.auto_model_routing", True))
                if cfg
                else True
            )
        if model_selection_mode is None:
            model_selection_mode = (
                str(cfg.get("ai.model_selection_mode", "auto"))
                if cfg
                else ("auto" if auto_routing_enabled else "manual")
            )
        if response_priority is None:
            response_priority = (
                str(cfg.get("ai.response_priority", "balanced"))
                if cfg
                else "balanced"
            )
        if task_preferences is None:
            task_preferences = (
                dict(cfg.get("ai.task_preferred_models", {}))
                if cfg
                else {}
            )
        if failed_models is None:
            failed_models = self.get_failed_models()

        decision = self.router.route_request(
            prompt=prompt,
            current_active_model=self.active_model,
            context_history=context_history,
            images=images,
            attachments=attachments,
            is_voice=is_voice,
            format_json=format_json,
            auto_routing_enabled=auto_routing_enabled,
            max_allowed_ram_mb=max_allowed_ram_mb,
            model_selection_mode=model_selection_mode,
            response_priority=response_priority,
            task_preferences=task_preferences,
            failed_models=failed_models,
        )

        if decision.switched and decision.selected_model != self.active_model:
            logger.info(
                "[ROUTER SWITCH] Switching active model from '%s' to '%s' for task '%s'.",
                self.active_model,
                decision.selected_model,
                decision.detected_task.value,
            )
            self.select_active_model(decision.selected_model)

        return decision

    def get_last_routing_decision(self) -> Optional[RoutingDecision]:
        """Fetch the most recent routing evaluation."""
        return self.router.get_last_decision()

    def check_inactivity_and_unload(self) -> bool:
        """Unload model if inactivity threshold has elapsed to reclaim system RAM/VRAM.
        
        Returns:
            True if model was unloaded, False otherwise.
        """
        if not self._is_model_loaded:
            return False

        idle_duration = time.time() - self._last_activity_time
        if idle_duration >= self.inactivity_timeout:
            logger.info(
                "Model '%s' idle for %.1fs (timeout: %.1fs). Unloading from memory...",
                self.active_model,
                idle_duration,
                self.inactivity_timeout,
            )
            success = self.client.unload_model(self.active_model)
            if success:
                self._is_model_loaded = False
            return success

        return False

    def unload_immediately(self) -> bool:
        """Explicitly unload active model from memory if loaded."""
        if not self._is_model_loaded:
            return True
        success = self.client.unload_model(self.active_model)
        if success:
            self._is_model_loaded = False
        return success

    # ─── Diagnostics & Status ──────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive status for UI displays or health checks."""
        online = self.is_available()
        installed = self.get_installed_models() if online else []

        status_msg = "Ready"
        error_msg = None

        if not online:
            status_msg = "Ollama Offline"
            error_msg = (
                "Ollama is not running. Please launch Ollama from your desktop or start the service."
            )
        elif not installed:
            status_msg = "No Models Found"
            error_msg = (
                f"No suitable models found in Ollama. Pull one with: ollama pull {self._configured_model}"
            )
        elif self.active_model not in installed and not any(
            m.startswith(self.active_model.split(":")[0]) for m in installed
        ):
            status_msg = "Model Not Found"
            error_msg = f"Model '{self.active_model}' is not installed in Ollama."

        return {
            "online": online,
            "status": status_msg,
            "error": error_msg,
            "active_model": self.active_model,
            "installed_models": installed,
            "is_loaded": self._is_model_loaded,
            "endpoint": self.client.base_url,
            "capabilities": [m.to_dict() for m in self.capability_registry.get_installed_models()],
            "benchmark_status": self.benchmark_runner.get_progress(),
        }
