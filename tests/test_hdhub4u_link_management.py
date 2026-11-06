"""Unit and Integration Tests for HDHub4u Link and Mirror Management.

Tests template formatting, title replacement, history tracking, persistence,
deduplication, and FastAPI endpoints.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.hdhub4u_manager import (
    DEFAULT_HDHUB4U_URL,
    HDHub4uManager,
)
from app.api.movie_routes import router
from fastapi import FastAPI


@pytest.fixture(autouse=True)
def mock_network_probes(monkeypatch):
    """Ensure network calls do not block or timeout during tests."""
    class MockResp:
        status_code = 200

    monkeypatch.setattr("requests.head", lambda *args, **kwargs: MockResp())
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockResp())


@pytest.fixture
def temp_hdhub_manager(tmp_path: Path) -> HDHub4uManager:
    """Create isolated HDHub4uManager using temporary config file."""
    cfg_file = tmp_path / "hdhub4u_test_config.json"
    return HDHub4uManager(config_path=cfg_file)


def test_default_hdhub4u_status(temp_hdhub_manager: HDHub4uManager):
    status = temp_hdhub_manager.get_status()
    assert status["active_url"] == DEFAULT_HDHUB4U_URL
    assert status["default_url"] == DEFAULT_HDHUB4U_URL
    assert status["is_custom"] is False
    assert status["active_id"] == "default"
    assert status["history"] == []


def test_build_search_url_replacement(temp_hdhub_manager: HDHub4uManager):
    # Case 1: Default template with 'pixels' keyword
    url1 = temp_hdhub_manager.build_search_url("Premalu")
    assert url1 == "https://new10.hdhub4u.cl/search.html?q=premalu"

    # Case 2: Multi-word title with punctuation (clean space boundary encoded as +)
    url2 = temp_hdhub_manager.build_search_url("Avengers: Endgame")
    assert url2 == "https://new10.hdhub4u.cl/search.html?q=avengers+endgame"

    # Case 3: Title is literally "Pixels"
    url3 = temp_hdhub_manager.build_search_url("Pixels")
    assert url3 == "https://new10.hdhub4u.cl/search.html?q=pixels"

    # Case 4: Custom template with {query} placeholder
    custom_tmpl = "https://mirror1.hdhub4u.tv/search?query={query}"
    url4 = temp_hdhub_manager.build_search_url("Interstellar", template=custom_tmpl)
    assert url4 == "https://mirror1.hdhub4u.tv/search?query=interstellar"

    # Case 5: Custom template with uppercase PIXELS
    custom_tmpl2 = "https://mirror2.hdhub4u.me/search.html?q=PIXELS&ref=friend"
    url5 = temp_hdhub_manager.build_search_url("Dune", template=custom_tmpl2)
    assert url5 == "https://mirror2.hdhub4u.me/search.html?q=dune&ref=friend"

    # Case 6: Empty title fallback
    url6 = temp_hdhub_manager.build_search_url("")
    assert "pixels" not in url6.lower()

    # Case 7: Doubled concatenated URL sanitization
    doubled = "https://new10.hdhub4u.cl/search.html?q=pixelshttps://new10.hdhub4u.cl/search.html?q=pixels"
    url7 = temp_hdhub_manager.build_search_url("Premalu", template=doubled)
    assert url7 == "https://new10.hdhub4u.cl/search.html?q=premalu"

    # Case 8: Existing parameter replacement (avoiding duplicate &q=)
    existing_q = "https://new10.hdhub4u.cl/search.html?q=avatar"
    url8 = temp_hdhub_manager.build_search_url("Premalu", template=existing_q)
    assert url8 == "https://new10.hdhub4u.cl/search.html?q=premalu"
    assert "&q=" not in url8

    # Case 9: WordPress search format (?s=...)
    wp_format = "https://ghdhub.org/?s=pixels"
    url9 = temp_hdhub_manager.build_search_url("Premalu", template=wp_format)
    assert url9 == "https://ghdhub.org/?s=premalu"

    # Case 10: Google Search template format
    google_tmpl = "https://www.google.com/search?q=hdhub4u+pixels"
    url10 = temp_hdhub_manager.build_search_url("Premalu", template=google_tmpl)
    assert url10 == "https://www.google.com/search?q=hdhub4u+premalu"


def test_auto_heal_corrupted_config(tmp_path: Path):
    """Verify that if user config contains a doubled URL, manager automatically heals it on load."""
    cfg_file = tmp_path / "corrupted_config.json"
    corrupted_data = {
        "active_url": "https://new10.hdhub4u.cl/search.html?q=pixelshttps://new10.hdhub4u.cl/search.html?q=pixels",
        "active_id": "test_id",
        "history": [
            {
                "id": "test_id",
                "url_template": "https://new10.hdhub4u.cl/search.html?q=pixelshttps://new10.hdhub4u.cl/search.html?q=pixels",
                "label": "HDHub4u Doubled",
                "created_at": 123456.0,
                "last_status": "valid",
            }
        ],
    }
    cfg_file.write_text(json.dumps(corrupted_data), encoding="utf-8")

    mgr = HDHub4uManager(config_path=cfg_file)
    status = mgr.get_status()
    assert status["active_url"] == "https://new10.hdhub4u.cl/search.html?q=pixels"
    assert status["history"][0]["url_template"] == "https://new10.hdhub4u.cl/search.html?q=pixels"


def test_save_and_activate_url(temp_hdhub_manager: HDHub4uManager):
    new_url = "https://new11.hdhub4u.tv/search.html?q=pixels"
    success, msg, status = temp_hdhub_manager.save_and_activate_url(
        new_url, label="Mirror 11 TV"
    )
    assert success is True
    assert status["active_url"] == new_url
    assert status["is_custom"] is True
    assert len(status["history"]) == 1
    assert status["history"][0]["url_template"] == new_url
    assert status["history"][0]["label"] == "Mirror 11 TV"
    assert status["history"][0]["is_active"] is True

    # Check persistence
    mgr2 = HDHub4uManager(config_path=temp_hdhub_manager.config_path)
    status2 = mgr2.get_status()
    assert status2["active_url"] == new_url
    assert len(status2["history"]) == 1


def test_deduplication_and_switch(temp_hdhub_manager: HDHub4uManager):
    url_a = "https://mirror-a.hdhub4u.net/search.html?q=pixels"
    url_b = "https://mirror-b.hdhub4u.net/search.html?q=pixels"

    temp_hdhub_manager.save_and_activate_url(url_a, label="Mirror A")
    temp_hdhub_manager.save_and_activate_url(url_b, label="Mirror B")

    status = temp_hdhub_manager.get_status()
    assert len(status["history"]) == 2
    assert status["active_url"] == url_b

    # Saving url_a again updates its label and activates it, without duplicating
    temp_hdhub_manager.save_and_activate_url(url_a, label="Mirror A (Updated)")
    status2 = temp_hdhub_manager.get_status()
    assert len(status2["history"]) == 2
    assert status2["active_url"] == url_a

    # Switch back to default
    temp_hdhub_manager.activate_url_by_id("default")
    status3 = temp_hdhub_manager.get_status()
    assert status3["active_url"] == DEFAULT_HDHUB4U_URL
    assert status3["is_custom"] is False


def test_delete_history_item(temp_hdhub_manager: HDHub4uManager):
    url_a = "https://mirror-a.hdhub4u.net/search.html?q=pixels"
    temp_hdhub_manager.save_and_activate_url(url_a, label="Mirror A")
    status = temp_hdhub_manager.get_status()
    item_id = status["history"][0]["id"]

    temp_hdhub_manager.delete_history_item(item_id)
    status_after = temp_hdhub_manager.get_status()
    assert len(status_after["history"]) == 0
    # Active was deleted, so reverts to default
    assert status_after["active_url"] == DEFAULT_HDHUB4U_URL


def test_invalid_urls(temp_hdhub_manager: HDHub4uManager):
    # Missing scheme
    valid, msg, code, _ = temp_hdhub_manager.validate_and_test_url("hdhub4u.com/search")
    assert valid is False

    # Missing domain
    valid2, msg2, code2, _ = temp_hdhub_manager.validate_and_test_url("https://")
    assert valid2 is False


def test_fastapi_hdhub4u_endpoints(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "hdhub4u_api_test.json"
    mgr = HDHub4uManager(config_path=cfg_file)

    # Mock requests.head and requests.get to return immediately
    class MockResp:
        status_code = 200

    monkeypatch.setattr("requests.head", lambda *args, **kwargs: MockResp())
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockResp())

    app = FastAPI()
    app.include_router(router)
    app.state.hdhub4u_manager = mgr

    client = TestClient(app)

    # 1. GET status
    resp = client.get("/api/movies/hdhub4u/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_url"] == DEFAULT_HDHUB4U_URL

    # 2. Test URL
    resp = client.post(
        "/api/movies/hdhub4u/test-url",
        json={"url": "https://mirror99.hdhub4u.org/search.html?q=pixels", "sample_title": "Interstellar"},
    )
    assert resp.status_code == 200
    test_res = resp.json()
    assert test_res["valid"] is True
    assert "interstellar" in test_res["preview_url"]

    # 3. Save URL
    resp = client.post(
        "/api/movies/hdhub4u/save-url",
        json={"url": "https://mirror99.hdhub4u.org/search.html?q=pixels", "label": "Mirror 99 Org"},
    )
    assert resp.status_code == 200
    save_data = resp.json()
    assert save_data["active_url"] == "https://mirror99.hdhub4u.org/search.html?q=pixels"
    saved_id = save_data["history"][0]["id"]

    # 4. Resolve search URL
    resp = client.get("/api/movies/hdhub4u/search-url?title=Premalu")
    assert resp.status_code == 200
    resolve_data = resp.json()
    assert resolve_data["url"] == "https://mirror99.hdhub4u.org/search.html?q=premalu"

    # 5. Reset to default
    resp = client.post("/api/movies/hdhub4u/reset")
    assert resp.status_code == 200
    reset_data = resp.json()
    assert reset_data["active_url"] == DEFAULT_HDHUB4U_URL

    # 6. Delete history item
    resp = client.delete(f"/api/movies/hdhub4u/history/{saved_id}")
    assert resp.status_code == 200
    del_data = resp.json()
    assert len(del_data["history"]) == 0
