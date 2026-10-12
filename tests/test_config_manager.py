"""Tests for ConfigManager."""

import json
from pathlib import Path
import pytest

from app.settings.config_manager import ConfigManager


def test_config_manager_defaults(tmp_path: Path):
    """Test initializing config manager and reading default values."""
    config_file = tmp_path / "settings.json"
    manager = ConfigManager(config_path=config_file)

    assert manager.get("pet.size") == 120
    assert manager.get("pet.always_on_top") is True
    assert manager.get("ai.model") == "qwen3:1.7b"
    assert manager.get("voice.enabled") is False
    assert manager.get("nonexistent.key", "fallback") == "fallback"


def test_config_manager_set_and_persist(tmp_path: Path):
    """Test setting nested keys and verifying persistence across reloads."""
    config_file = tmp_path / "settings.json"
    manager = ConfigManager(config_path=config_file)

    signal_received = []
    manager.setting_changed.connect(lambda k, v: signal_received.append((k, v)))

    # Modify settings
    manager.set("pet.size", 160)
    manager.set("ai.companion_name", "Sparky")

    assert len(signal_received) == 2
    assert signal_received[0] == ("pet.size", 160)
    assert signal_received[1] == ("ai.companion_name", "Sparky")

    # Reload from disk in a fresh instance
    reloaded_manager = ConfigManager(config_path=config_file)
    assert reloaded_manager.get("pet.size") == 160
    assert reloaded_manager.get("ai.companion_name") == "Sparky"
    # Unmodified defaults must be preserved
    assert reloaded_manager.get("pet.always_on_top") is True


def test_config_manager_reset_to_defaults(tmp_path: Path):
    """Test resetting modified settings back to defaults."""
    config_file = tmp_path / "settings.json"
    manager = ConfigManager(config_path=config_file)

    manager.set("pet.size", 200)
    assert manager.get("pet.size") == 200

    manager.reset_to_defaults()
    assert manager.get("pet.size") == 120
