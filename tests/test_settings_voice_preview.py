"""Automated tests for Voice Preview in Settings Dialog and Voice inner tab.

Verifies:
1. Previewing all 5 companion voices (Arjun, Kabir, Ananya, Mira, Zara) in English, Hindi, and Gujarati.
2. FastAPI /api/voice/test and /api/voice/preview endpoints properly trigger voice previews even when Buddy is sleeping.
3. AudioPlayer is unmuted and audible during explicit preview.
4. Qt SettingsDialog preview buttons invoke play_voice_preview correctly.
"""

import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from app.settings.config_manager import ConfigManager
from app.voice.voice_service import VoiceService
from app.voice.voice_registry import list_voice_profiles, get_voice_profile
from app.core.buddy_state_manager import get_buddy_state_manager


@pytest.fixture
def voice_service(qapp):
    vs = VoiceService()
    return vs


def test_voice_registry_five_profiles():
    """Verify exactly 5 distinct voice profiles are defined in the registry."""
    profiles = list_voice_profiles()
    assert len(profiles) == 5
    profile_ids = [p.profile_id for p in profiles]
    assert "arjun" in profile_ids
    assert "kabir" in profile_ids
    assert "ananya" in profile_ids
    assert "mira" in profile_ids
    assert "zara" in profile_ids


def test_voice_service_play_voice_preview_unmutes_and_plays(voice_service):
    """Verify play_voice_preview unmuts muted player and starts speak worker."""
    voice_service.audio_player.set_muted(True)
    voice_service.audio_player.set_volume(0.0)

    with patch.object(voice_service._thread_pool, "start") as mock_start:
        voice_service.play_voice_preview("arjun", language="en")
        # AudioPlayer must be unmuted and volume restored
        assert not voice_service.audio_player.is_muted
        assert voice_service.audio_player.volume >= 0.5
        assert mock_start.called


@pytest.mark.parametrize("profile_id", ["arjun", "kabir", "ananya", "mira", "zara"])
@pytest.mark.parametrize("lang", ["en", "hi", "gu"])
def test_all_five_voices_preview_worker(voice_service, profile_id, lang):
    """Verify play_voice_preview prepares worker for all 5 voices across EN, HI, GU."""
    with patch.object(voice_service._thread_pool, "start") as mock_start:
        voice_service.play_voice_preview(profile_id, language=lang)
        assert mock_start.called
        worker = mock_start.call_args[0][0]
        assert worker.text  # Non-empty spoken text
        assert worker.voice_kwargs.get("speed") > 0


def test_api_voice_test_endpoint_works_while_sleeping():
    """Verify /api/voice/test executes voice preview without suppression when Buddy is sleeping."""
    from app.api.server import create_app

    app = create_app()
    mock_vs = MagicMock()
    mock_vs.selected_voice_profile = "arjun"
    app.state.voice_service = mock_vs

    buddy_sm = get_buddy_state_manager()
    buddy_sm.set_state("sleeping")
    assert not buddy_sm.can_speak

    client = TestClient(app)
    resp = client.post("/api/voice/test", json={"profile_id": "kabir", "language": "hi"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["profile_id"] == "kabir"
    assert data["language"] == "hi"
    assert mock_vs.play_voice_preview.called
    mock_vs.play_voice_preview.assert_called_with("kabir", language="hi", text=None)


def test_api_voice_preview_endpoint():
    """Verify dedicated /api/voice/preview endpoint."""
    from app.api.server import create_app

    app = create_app()
    mock_vs = MagicMock()
    app.state.voice_service = mock_vs

    client = TestClient(app)
    resp = client.post("/api/voice/preview", json={"profile_id": "zara", "language": "gu"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["profile_id"] == "zara"
    assert data["language"] == "gu"
    mock_vs.play_voice_preview.assert_called_with("zara", language="gu", text=None)


def test_api_voice_profiles_endpoint():
    """Verify /api/voice/profiles returns all 5 voice profiles."""
    from app.api.server import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/voice/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["profiles"]) == 5
    ids = [p["profile_id"] for p in data["profiles"]]
    assert set(ids) == {"arjun", "kabir", "ananya", "mira", "zara"}


def test_settings_dialog_preview_trigger(qapp):
    """Verify SettingsDialog triggers play_voice_preview on VoiceProfileCard preview_requested."""
    from app.desktop.settings_dialog import SettingsDialog

    cfg = ConfigManager()
    mock_vs = MagicMock()

    dialog = SettingsDialog(
        config_manager=cfg,
        voice_service=mock_vs,
    )

    # Simulate preview request for all 5 profiles
    for pid in ["arjun", "kabir", "ananya", "mira", "zara"]:
        dialog._on_voice_profile_preview_requested(pid, "en")
        mock_vs.play_voice_preview.assert_called_with(pid, language="en")

    dialog.close()
