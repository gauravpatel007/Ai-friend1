"""Unit and integration tests for character state assets (BUG 19).

Validates presence, integrity, multi-directory fallback serving, and automatic
synchronization of robot character state assets including thinking.png.
"""

import os
from pathlib import Path
import shutil
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.api.server import app, sync_character_assets, MultiDirStaticFiles

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
REQUIRED_STATES = ["idle", "thinking", "speaking", "listening", "happy", "sleeping"]


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


def test_robot_assets_exist_in_source_directory():
    """Verify all 6 character state PNG files exist in assets/characters/robot/."""
    project_root = Path(__file__).resolve().parent.parent
    robot_dir = project_root / "assets" / "characters" / "robot"
    assert robot_dir.is_dir(), f"Source character directory not found: {robot_dir}"

    for state in REQUIRED_STATES:
        asset_path = robot_dir / f"{state}.png"
        assert asset_path.is_file(), f"Missing character state asset: {asset_path}"
        assert asset_path.stat().st_size > 10_000, f"Asset file too small: {asset_path}"
        with open(asset_path, "rb") as f:
            header = f.read(8)
            assert header == PNG_MAGIC, f"Asset {asset_path} is not a valid PNG"


def test_thinking_asset_specifically():
    """Verify thinking.png specifically exists and has substantial content."""
    project_root = Path(__file__).resolve().parent.parent
    thinking_path = project_root / "assets" / "characters" / "robot" / "thinking.png"
    assert thinking_path.is_file(), f"thinking.png is missing from {thinking_path}"
    file_size = thinking_path.stat().st_size
    assert file_size > 100_000, f"thinking.png size {file_size} is unexpectedly small"
    with open(thinking_path, "rb") as f:
        header = f.read(8)
        assert header == PNG_MAGIC, "thinking.png has invalid PNG magic header"


def test_public_and_dist_character_assets_present():
    """Verify public/assets and dist/assets (if built) both contain all state assets."""
    project_root = Path(__file__).resolve().parent.parent
    public_robot = project_root / "public" / "assets" / "characters" / "robot"
    assert public_robot.is_dir(), f"public assets directory not found: {public_robot}"

    for state in REQUIRED_STATES:
        p_asset = public_robot / f"{state}.png"
        assert p_asset.is_file(), f"public asset missing: {p_asset}"
        assert p_asset.stat().st_size > 10_000

    dist_robot = project_root / "dist" / "assets" / "characters" / "robot"
    if dist_robot.parent.parent.is_dir():  # If dist/assets exists
        assert dist_robot.is_dir(), f"dist character directory not found: {dist_robot}"
        for state in REQUIRED_STATES:
            d_asset = dist_robot / f"{state}.png"
            assert d_asset.is_file(), f"dist asset missing: {d_asset}"
            assert d_asset.stat().st_size > 10_000


def test_sync_character_assets_logic(monkeypatch):
    """Verify sync_character_assets successfully copies missing assets to targets."""
    copied = []

    def fake_copy2(src, dst):
        copied.append((src, dst))

    monkeypatch.setattr("shutil.copy2", fake_copy2)
    monkeypatch.setattr("os.path.isdir", lambda p: True)
    monkeypatch.setattr("os.makedirs", lambda p, exist_ok=True: None)
    monkeypatch.setattr("os.listdir", lambda p: ["thinking.png", "idle.png", "ignore.txt"])

    # Simulate thinking.png missing in target, idle.png already existing
    monkeypatch.setattr(
        "os.path.exists",
        lambda p: False if "thinking.png" in p and ("public" in p or "dist" in p) else True,
    )

    sync_character_assets("/dummy/project/root")

    assert len(copied) == 2
    assert any("thinking.png" in dst for src, dst in copied)


def test_fastapi_serves_thinking_png(client: TestClient):
    """Verify GET /assets/characters/robot/thinking.png returns 200 with image/png."""
    resp = client.get("/assets/characters/robot/thinking.png")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "image/png" in resp.headers.get("content-type", "")
    assert len(resp.content) > 100_000
    assert resp.content[:8] == PNG_MAGIC


def test_fastapi_serves_all_robot_states(client: TestClient):
    """Verify all character states return 200 OK from the FastAPI static mount."""
    for state in REQUIRED_STATES:
        resp = client.get(f"/assets/characters/robot/{state}.png")
        assert resp.status_code == 200, f"Failed for state {state}: status {resp.status_code}"
        assert "image/png" in resp.headers.get("content-type", "")
        assert resp.content[:8] == PNG_MAGIC


def test_fastapi_character_fallback_resilience(client: TestClient):
    """Verify requesting an unknown state falls back to idle.png rather than 404."""
    resp_fallback = client.get("/assets/characters/robot/unknown_emotion_state.png")
    assert resp_fallback.status_code == 200
    assert "image/png" in resp_fallback.headers.get("content-type", "")
    assert resp_fallback.content[:8] == PNG_MAGIC

    # Check non-character unknown static files still properly return 404
    resp_404 = client.get("/assets/nonexistent_file_abc123.js")
    assert resp_404.status_code == 404
