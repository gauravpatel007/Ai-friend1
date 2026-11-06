from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

import pytest
from app.core.performance_profiles import (
    MIN_RAM_FOR_QUALITY_GB,
    PROFILES,
    PerformanceProfile,
    PerformanceProfileManager,
)
from app.settings.config_manager import ConfigManager

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def temp_config_mgr():
    config_file = SCRATCH_DIR / f"test_cfg_{uuid.uuid4().hex}.json"
    mgr = ConfigManager(config_path=str(config_file))
    yield mgr
    try:
        if config_file.exists():
            config_file.unlink()
    except Exception:
        pass


def test_profile_presets_integrity():
    """Verify all profiles have required fields and sensible parameters."""
    for profile in (PerformanceProfile.ECO, PerformanceProfile.BALANCED, PerformanceProfile.QUALITY):
        assert profile in PROFILES
        cfg = PROFILES[profile]
        assert cfg.name == profile.value
        assert cfg.llm_model
        assert cfg.whisper_model in ("tiny", "base", "small")
        assert cfg.tts_engine in ("piper", "kokoro")
        assert cfg.animation_fps in (15, 30, 60)
        assert cfg.idle_unload_minutes > 0
        assert cfg.max_context_tokens > 0


def test_quality_mode_hardware_guard(temp_config_mgr):
    manager = PerformanceProfileManager(config_manager=temp_config_mgr)

    # 1. Test 8 GB RAM system -> Quality mode rejected
    with patch.object(manager._perf_monitor, "get_total_ram_gb", return_value=7.8):
        can_use, reason = manager.can_use_quality_mode()
        assert can_use is False
        assert "requires at least 12 GB" in reason

        # Applying Quality mode fails
        success, msg = manager.apply_profile(PerformanceProfile.QUALITY, force=False)
        assert success is False
        assert "requires at least 12 GB" in msg
        # Current profile remains unchanged
        assert manager.current_profile != PerformanceProfile.QUALITY

    # 2. Test 16 GB RAM system with sufficient available RAM -> Quality mode permitted
    with patch.object(manager._perf_monitor, "get_total_ram_gb", return_value=16.0):
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value = MagicMock(available=8.0 * (1024 ** 3))
            can_use, reason = manager.can_use_quality_mode()
            assert can_use is True

            # Applying Quality mode succeeds
            success, msg = manager.apply_profile(PerformanceProfile.QUALITY, force=False)
            assert success is True
            assert manager.current_profile == PerformanceProfile.QUALITY


def test_profile_recommendation(temp_config_mgr):
    manager = PerformanceProfileManager(config_manager=temp_config_mgr)

    # 8 GB or less -> ECO
    with patch.object(manager._perf_monitor, "get_total_ram_gb", return_value=7.9):
        assert manager.recommend_profile() == PerformanceProfile.ECO

    # 10 GB -> BALANCED
    with patch.object(manager._perf_monitor, "get_total_ram_gb", return_value=10.0):
        assert manager.recommend_profile() == PerformanceProfile.BALANCED

    # 16 GB -> QUALITY
    with patch.object(manager._perf_monitor, "get_total_ram_gb", return_value=16.0):
        assert manager.recommend_profile() == PerformanceProfile.QUALITY


def test_apply_profile_propagates_settings(temp_config_mgr):
    manager = PerformanceProfileManager(config_manager=temp_config_mgr)

    # Apply ECO profile
    success, _ = manager.apply_profile(PerformanceProfile.ECO)
    assert success is True
    assert manager.current_profile == PerformanceProfile.ECO

    # Check that settings propagated into config manager
    assert temp_config_mgr.get("performance.profile") == "eco"
    assert temp_config_mgr.get("performance.idle_unload_minutes") == 2
    assert temp_config_mgr.get("performance.model_keep_alive") == "2m"
    assert temp_config_mgr.get("pet.animation_fps") == 15
    assert temp_config_mgr.get("voice.whisper_model") == "tiny"
    assert temp_config_mgr.get("voice.tts_engine") == "piper"

    # Apply BALANCED profile
    success, _ = manager.apply_profile(PerformanceProfile.BALANCED)
    assert success is True
    assert manager.current_profile == PerformanceProfile.BALANCED
    assert temp_config_mgr.get("pet.animation_fps") == 30
    assert temp_config_mgr.get("performance.model_keep_alive") == "5m"
    assert temp_config_mgr.get("voice.whisper_model") == "base"
