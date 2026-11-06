"""Performance Profiles Manager.

Defines and coordinates performance profiles (Eco, Balanced, Quality)
tailored for different hardware tiers, especially 8 GB RAM machines.
Enforces resource guards to prevent Quality mode on low-memory systems.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import psutil
from PySide6.QtCore import QObject, Signal

from app.core.performance_monitor import get_performance_monitor
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Hardware thresholds
MIN_RAM_FOR_QUALITY_GB = 11.5  # Requires at least ~12 GB physical RAM for Quality Mode


class PerformanceProfile(str, Enum):
    """Available application performance profiles."""
    ECO = "eco"
    BALANCED = "balanced"
    QUALITY = "quality"


@dataclass(frozen=True)
class ProfileConfig:
    """Settings bundle for a specific performance profile."""
    name: str
    display_title: str
    description: str
    llm_model: str
    whisper_model: str
    tts_engine: str
    animation_fps: int
    idle_unload_minutes: int
    model_keep_alive: str
    max_context_tokens: int
    max_context_memories: int
    min_ram_required_gb: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Built-in profile presets
PROFILES: Dict[PerformanceProfile, ProfileConfig] = {
    PerformanceProfile.ECO: ProfileConfig(
        name="eco",
        display_title="🌱 Eco Mode (Low Resource / 8 GB)",
        description="Lightweight models and reduced animation updates. Designed for multitasking on 8 GB RAM.",
        llm_model="qwen3:1.7b",
        whisper_model="tiny",
        tts_engine="piper",
        animation_fps=15,
        idle_unload_minutes=2,
        model_keep_alive="2m",
        max_context_tokens=180,
        max_context_memories=3,
        min_ram_required_gb=4.0,
    ),
    PerformanceProfile.BALANCED: ProfileConfig(
        name="balanced",
        display_title="⚖️ Balanced Mode (Recommended)",
        description="Optimal balance between intelligence, voice fidelity, and responsiveness.",
        llm_model="qwen3:1.7b",
        whisper_model="base",
        tts_engine="piper",
        animation_fps=30,
        idle_unload_minutes=5,
        model_keep_alive="5m",
        max_context_tokens=250,
        max_context_memories=5,
        min_ram_required_gb=7.5,
    ),
    PerformanceProfile.QUALITY: ProfileConfig(
        name="quality",
        display_title="✨ Quality Mode (High Performance / 16 GB+)",
        description="Larger compatible LLM, Whisper Small transcription, and Kokoro natural neural TTS.",
        llm_model="llama3.2:latest",
        whisper_model="small",
        tts_engine="kokoro",
        animation_fps=30,
        idle_unload_minutes=15,
        model_keep_alive="15m",
        max_context_tokens=500,
        max_context_memories=10,
        min_ram_required_gb=MIN_RAM_FOR_QUALITY_GB,
    ),
}


class PerformanceProfileManager(QObject):
    """Manages active performance profile, hardware qualification, and settings propagation."""

    # Emitted when profile is successfully changed: (profile_name, ProfileConfig)
    profile_applied = Signal(str, object)
    # Emitted when quality mode request is denied due to insufficient hardware: reason_msg
    quality_mode_denied = Signal(str)

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager or ConfigManager(parent=self)
        self._perf_monitor = get_performance_monitor()

        # Load active profile from config or default
        saved_profile_str = self.config_manager.get("performance.profile", "balanced")
        try:
            self._current_profile = PerformanceProfile(saved_profile_str.lower())
        except ValueError:
            self._current_profile = PerformanceProfile.BALANCED

        # Validate hardware on startup
        if self._current_profile == PerformanceProfile.QUALITY:
            can_use, reason = self.can_use_quality_mode()
            if not can_use:
                logger.warning("Quality mode not suitable for hardware on boot: %s. Falling back to Balanced.", reason)
                self._current_profile = PerformanceProfile.BALANCED
                self.config_manager.set("performance.profile", "balanced")

    @property
    def current_profile(self) -> PerformanceProfile:
        return self._current_profile

    @property
    def current_config(self) -> ProfileConfig:
        return PROFILES[self._current_profile]

    def get_profile_config(self, profile: PerformanceProfile | str) -> ProfileConfig:
        """Retrieve profile configuration preset."""
        if isinstance(profile, str):
            profile = PerformanceProfile(profile.lower())
        return PROFILES[profile]

    def can_use_quality_mode(self) -> Tuple[bool, str]:
        """Check if hardware resources (especially RAM) meet Quality Mode requirements."""
        total_ram_gb = self._perf_monitor.get_total_ram_gb()
        if total_ram_gb < MIN_RAM_FOR_QUALITY_GB:
            msg = (
                f"Quality Mode requires at least 12 GB system RAM (detected {total_ram_gb:.1f} GB). "
                f"On an 8 GB system, Quality Mode could cause excessive paging or out-of-memory errors. "
                f"Please use Balanced or Eco Mode."
            )
            return False, msg

        # Also check current available RAM
        try:
            avail_ram_gb = psutil.virtual_memory().available / (1024 ** 3)
            if avail_ram_gb < 3.5:
                msg = (
                    f"Available system RAM is currently low ({avail_ram_gb:.1f} GB available). "
                    f"Quality Mode requires at least 4.0 GB free memory."
                )
                return False, msg
        except Exception:
            pass

        return True, "Hardware resources are sufficient for Quality Mode."

    def recommend_profile(self) -> PerformanceProfile:
        """Recommend optimal profile based on detected physical hardware."""
        total_ram_gb = self._perf_monitor.get_total_ram_gb()
        if total_ram_gb <= 8.5:
            # 8 GB or less
            return PerformanceProfile.ECO
        elif total_ram_gb < MIN_RAM_FOR_QUALITY_GB:
            # 8 - 12 GB
            return PerformanceProfile.BALANCED
        else:
            # 16 GB+
            return PerformanceProfile.QUALITY

    def apply_profile(self, profile: PerformanceProfile | str, force: bool = False) -> Tuple[bool, str]:
        """Apply a performance profile across application configuration and subsystems."""
        if isinstance(profile, str):
            try:
                profile = PerformanceProfile(profile.lower())
            except ValueError:
                return False, f"Unknown profile: {profile}"

        if profile == PerformanceProfile.QUALITY and not force:
            can_use, reason = self.can_use_quality_mode()
            if not can_use:
                logger.warning("Rejected switch to Quality Mode: %s", reason)
                self.quality_mode_denied.emit(reason)
                return False, reason

        target_cfg = PROFILES[profile]
        self._current_profile = profile

        # Update persistent settings
        self.config_manager.set("performance.profile", profile.value)
        self.config_manager.set("performance.idle_unload_minutes", target_cfg.idle_unload_minutes)
        self.config_manager.set("performance.model_keep_alive", target_cfg.model_keep_alive)
        self.config_manager.set("pet.animation_fps", target_cfg.animation_fps)
        self.config_manager.set("ai.max_tokens", target_cfg.max_context_tokens)
        self.config_manager.set("memory.max_context_memories", target_cfg.max_context_memories)

        # Update models if not customized
        self.config_manager.set("ai.model", target_cfg.llm_model)
        self.config_manager.set("voice.whisper_model", target_cfg.whisper_model)
        self.config_manager.set("voice.tts_engine", target_cfg.tts_engine)

        logger.info("Successfully applied performance profile '%s' (%s).", profile.value, target_cfg.display_title)
        self.profile_applied.emit(profile.value, target_cfg)
        return True, f"Applied {target_cfg.display_title}"
