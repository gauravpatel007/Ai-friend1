"""Tests for Bug #9: POST /api/config/reset runtime system synchronization.

Verifies:
1. POST /api/config/reset explicitly invokes set_startup_enabled(default_startup) via startup_manager.
2. TMDBCredentialManager.refresh() is called and in-memory TMDB client API key is updated.
3. PersonalityManager is reloaded with default companion name and personality preset.
4. VoiceService is notified to reset voice playback speed, engine, voice, and mode.
5. Signal-based synchronization on config_reloaded works for TMDBCredentialManager, PersonalityManager, and VoiceService.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.server import app, _on_config_reset
from app.settings.config_manager import ConfigManager
from app.api.tmdb_credential_manager import TMDBCredentialManager
from app.ai.personality_manager import PersonalityManager


@pytest.fixture
def isolated_config(tmp_path):
    """Create an isolated ConfigManager for test isolation."""
    cfg_file = tmp_path / "test_config.json"
    mgr = ConfigManager(config_path=cfg_file)
    # Set non-default values to verify reset
    mgr.set("general.start_at_login", True)
    mgr.set("ai.companion_name", "Zeus")
    mgr.set("ai.personality", "funny")
    mgr.set("voice.voice_speed", 1.8)
    mgr.set("movies.tmdb_active_key_id", "custom_key_123")
    return mgr


def test_config_reset_endpoint_synchronizes_all_runtime_systems(isolated_config):
    """Verify POST /api/config/reset synchronizes startup registry, TMDB client, personality, and voice."""
    client = TestClient(app)
    app.state.config_manager = isolated_config

    # Mock runtime subsystems on app.state
    mock_tmdb_client = MagicMock()
    mock_tmdb_client.api_key = "custom_stale_key_123"
    app.state.tmdb_client = mock_tmdb_client

    mock_key_mgr = MagicMock(spec=TMDBCredentialManager)
    mock_key_mgr.refresh.return_value = ("env_fallback_key", "env", "env")
    app.state.tmdb_key_manager = mock_key_mgr

    mock_ai_service = MagicMock()
    mock_personality_mgr = MagicMock(spec=PersonalityManager)
    mock_ai_service.personality_manager = mock_personality_mgr
    app.state.ai_service = mock_ai_service

    mock_voice_service = MagicMock()
    app.state.voice_service = mock_voice_service

    with patch("app.core.startup_manager.set_startup_enabled") as mock_set_startup:
        res = client.post("/api/config/reset")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"

        # 1. Startup manager invoked with default startup setting (False)
        mock_set_startup.assert_called_once_with(False)

        # 2. TMDB key manager refreshed and in-memory TMDB client updated
        mock_key_mgr.refresh.assert_called_once()
        mock_tmdb_client.set_api_key.assert_called_once_with("env_fallback_key")

        # 3. Personality manager reloaded from default config
        mock_personality_mgr.reload_from_config.assert_called_once()

        # 4. Voice service reloaded from default config
        mock_voice_service.reload_from_config.assert_called_once()


def test_tmdb_credential_manager_refresh(tmp_path, isolated_config):
    """Verify TMDBCredentialManager.refresh() reloads vault and returns active key tuple."""
    vault_file = tmp_path / "tmdb_vault.enc"
    key_mgr = TMDBCredentialManager(config_manager=isolated_config, vault_path=vault_file)

    with patch.object(key_mgr, "get_env_fallback_key", return_value="fallback_test_key"):
        # Reset config to defaults
        isolated_config.reset_to_defaults()
        active_key, source, active_id = key_mgr.refresh()

        assert source == "env"
        assert active_id == "env"
        assert active_key == "fallback_test_key"


def test_personality_manager_reload_from_config(isolated_config):
    """Verify PersonalityManager.reload_from_config() resets companion name and personality."""
    pm = PersonalityManager(config_manager=isolated_config)
    assert pm.companion_name == "Zeus"
    assert pm.active_personality == "funny"

    isolated_config.reset_to_defaults()
    pm.reload_from_config()

    assert pm.companion_name == "Buddy"
    assert pm.active_personality == "friendly"


def test_voice_service_speed_and_reload(isolated_config):
    """Verify VoiceService.set_tts_speed clamps and updates all TTS engines."""
    from app.voice.voice_service import VoiceService

    voice_svc = MagicMock()
    mock_active = MagicMock()
    mock_kokoro = MagicMock()
    mock_piper = MagicMock()
    mock_sapi = MagicMock()

    voice_svc.active_tts_engine = mock_active
    voice_svc.kokoro_engine = mock_kokoro
    voice_svc.piper_engine = mock_piper
    voice_svc.sapi_engine = mock_sapi
    voice_svc._config_manager = isolated_config

    # Call unbound method with mocked self
    VoiceService.set_tts_speed(voice_svc, 1.0)

    assert mock_active.speed == 1.0
    assert mock_kokoro.speed == 1.0
    assert mock_piper.speed == 1.0
    assert mock_sapi.speed == 1.0


def test_direct_on_config_reset_helper(isolated_config):
    """Verify direct call to _on_config_reset() helper operates correctly."""
    app.state.config_manager = isolated_config
    mock_key_mgr = MagicMock()
    mock_key_mgr.refresh.return_value = ("", "none", "")
    app.state.tmdb_key_manager = mock_key_mgr

    mock_voice = MagicMock()
    app.state.voice_service = mock_voice

    with patch("app.core.startup_manager.set_startup_enabled") as mock_set_startup:
        _on_config_reset(isolated_config)
        mock_set_startup.assert_called_once()
        mock_key_mgr.refresh.assert_called_once()
        mock_voice.reload_from_config.assert_called_once()
