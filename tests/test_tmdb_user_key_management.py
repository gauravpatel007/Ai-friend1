import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.settings.config_manager import ConfigManager
from app.api.tmdb_credential_manager import (
    TMDBCredentialManager,
    mask_api_key,
    _hash_fingerprint,
)
from app.api.tmdb_client import TMDBClient
from app.api.server import create_app


@pytest.fixture
def temp_env(tmp_path: Path, monkeypatch):
    """Set up temporary config and vault paths with dummy .env fallback."""
    cfg_file = tmp_path / "settings.json"
    vault_file = tmp_path / "tmdb_credentials.enc"
    monkeypatch.setenv("TMDB_API_KEY", "env_fallback_key_1234567890abcdef")

    cfg = ConfigManager(config_path=cfg_file)
    key_mgr = TMDBCredentialManager(config_manager=cfg, vault_path=vault_file)
    return cfg, key_mgr, vault_file


def test_mask_api_key():
    assert mask_api_key("") == ""
    assert mask_api_key("short") == "••••"
    assert mask_api_key("1234567890abcdef") == "••••••••••••cdef"
    assert "1234567890" not in mask_api_key("1234567890abcdef")


def test_initial_env_fallback(temp_env):
    """1. The existing .env key works when no custom key is configured."""
    cfg, key_mgr, _ = temp_env
    active_key, source, active_id = key_mgr.get_active_api_key()
    assert active_key == "env_fallback_key_1234567890abcdef"
    assert source == "env"
    assert active_id == "env"

    status = key_mgr.get_key_status()
    assert status["configured"] is True
    assert status["source"] == "env"
    assert status["has_env_fallback"] is True
    assert status["env_masked_key"].endswith("cdef")


def test_invalid_key_does_not_replace_active(temp_env):
    """3. An invalid key does not replace the working active key."""
    cfg, key_mgr, _ = temp_env

    # Mock TMDB returning 401 Unauthorized for invalid key
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        success, msg, status = key_mgr.save_and_activate_key("bad_unauthorized_key_999")
        assert success is False
        assert "401" in msg or "Authentication failed" in msg

        # Working key must still be .env key!
        active_key, source, _ = key_mgr.get_active_api_key()
        assert active_key == "env_fallback_key_1234567890abcdef"
        assert source == "env"


def test_valid_user_provided_key_and_persistence(temp_env):
    """2 & 5. A valid user-provided key connects successfully and persists after restart."""
    cfg, key_mgr, vault_file = temp_env
    valid_key = "user_valid_key_9876543210fedcba"

    # Mock TMDB returning 200 OK
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        success, msg, status = key_mgr.save_and_activate_key(valid_key, label="Personal Key")
        assert success is True
        assert status["source"] == "custom"
        assert status["masked_key"].endswith("dcba")

        # Verify active key is now the custom key
        active_key, source, active_id = key_mgr.get_active_api_key()
        assert active_key == valid_key
        assert source == "custom"

        # Verify plaintext key is NOT stored in settings.json
        with open(cfg.config_path, "r", encoding="utf-8") as f:
            cfg_text = f.read()
        assert valid_key not in cfg_text, "Plaintext API key must never be stored in settings.json!"

    # Simulate app restart: re-create TMDBCredentialManager with same files
    new_cfg = ConfigManager(config_path=cfg.config_path)
    restarted_mgr = TMDBCredentialManager(config_manager=new_cfg, vault_path=vault_file)

    restarted_key, restarted_source, restarted_id = restarted_mgr.get_active_api_key()
    assert restarted_key == valid_key
    assert restarted_source == "custom"
    assert restarted_id == active_id

    restarted_status = restarted_mgr.get_key_status()
    assert len(restarted_status["history"]) == 1
    assert restarted_status["history"][0]["label"] == "Personal Key"
    assert restarted_status["history"][0]["is_active"] is True


def test_switch_between_saved_keys_and_env(temp_env):
    """4. Switching between previously saved keys and env works."""
    cfg, key_mgr, _ = temp_env
    key1 = "custom_key_1111111111111111aaaa"
    key2 = "custom_key_2222222222222222bbbb"

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        # Save key 1
        key_mgr.save_and_activate_key(key1, label="Key 1")
        # Save key 2
        key_mgr.save_and_activate_key(key2, label="Key 2")

        status = key_mgr.get_key_status()
        assert len(status["history"]) == 2
        id1 = next(item["id"] for item in status["history"] if item["label"] == "Key 1")
        id2 = next(item["id"] for item in status["history"] if item["label"] == "Key 2")

        # Key 2 is active
        active_key, _, _ = key_mgr.get_active_api_key()
        assert active_key == key2

        # Switch back to Key 1
        s1, _, _ = key_mgr.activate_key_by_id(id1)
        assert s1 is True
        active_key, _, _ = key_mgr.get_active_api_key()
        assert active_key == key1

        # Switch to .env fallback
        s_env, _, _ = key_mgr.activate_key_by_id("env")
        assert s_env is True
        active_key, source, _ = key_mgr.get_active_api_key()
        assert active_key == "env_fallback_key_1234567890abcdef"
        assert source == "env"


def test_deduplication_and_delete_history(temp_env):
    """Avoid duplicate entries and allow removal of individual history items."""
    cfg, key_mgr, _ = temp_env
    key1 = "custom_key_unique_1234567890abcd"

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        key_mgr.save_and_activate_key(key1, label="First Attempt")
        # Save exact same key again with different label
        key_mgr.save_and_activate_key(key1, label="Updated Attempt")

        status = key_mgr.get_key_status()
        assert len(status["history"]) == 1
        assert status["history"][0]["label"] == "Updated Attempt"
        key_id = status["history"][0]["id"]

        # Delete key
        del_success, _, del_status = key_mgr.delete_key_by_id(key_id)
        assert del_success is True
        assert len(del_status["history"]) == 0
        # Should have fallen back to env
        active_key, source, _ = key_mgr.get_active_api_key()
        assert source == "env"
        assert active_key == "env_fallback_key_1234567890abcdef"


def test_api_routes_end_to_end(temp_env):
    """6 & 7. FastApi endpoints update TMDBClient at runtime without exposing keys."""
    cfg, key_mgr, _ = temp_env
    app = create_app()
    app.state.config_manager = cfg
    app.state.tmdb_key_manager = key_mgr

    client = TestClient(app)

    # 1. GET status
    res = client.get("/api/movies/tmdb/key-status")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "env"
    assert data["has_env_fallback"] is True

    # 2. POST test key
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        test_res = client.post("/api/movies/tmdb/test-key", json={"api_key": "some_test_key_1234"})
        assert test_res.status_code == 200
        assert test_res.json()["valid"] is True

    # 3. POST save key
    new_user_key = "user_api_key_3333333333333333cccc"
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        save_res = client.post(
            "/api/movies/tmdb/save-key",
            json={"api_key": new_user_key, "label": "Client Key"},
        )
        assert save_res.status_code == 200
        save_data = save_res.json()
        assert save_data["source"] == "custom"
        assert save_data["masked_key"].endswith("cccc")

        # Verify running TMDBClient on app state was updated immediately
        tmdb_cli = getattr(app.state, "tmdb_client", None)
        assert tmdb_cli is not None
        assert tmdb_cli.api_key == new_user_key

    # 4. Attempt to save invalid key -> 400 error and retained active key
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        bad_save = client.post("/api/movies/tmdb/save-key", json={"api_key": "bad_key_fail"})
        assert bad_save.status_code == 400
        assert "401" in bad_save.json()["detail"] or "Authentication failed" in bad_save.json()["detail"]

        # Ensure active key is STILL new_user_key
        assert app.state.tmdb_client.api_key == new_user_key

