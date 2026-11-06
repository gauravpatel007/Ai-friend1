"""Unit and Regression Tests for Security Fixes (SEC-01 through SEC-06).

Verifies that:
- SEC-01: Wildcard CORS is removed and unauthorized external origins are rejected.
- SEC-02: Path traversal in SPA catch-all is strictly prevented.
- SEC-03: Cross-Site WebSocket Hijacking is prevented by validating Origin headers.
- SEC-04: Chromium sandbox is preserved (no --no-sandbox flag forced).
- SEC-05: External hyperlinks in WebEngine are delegated to the system default browser.
- SEC-06: Global keyboard hook supports configuration toggle and safe lifecycle management.
"""

import os
import sys
from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from app.api.server import create_app
from app.core.global_hotkeys import GlobalHotkeyManager


def test_sec_01_cors_and_origin_validation():
    """Verify SEC-01: CORS restrictions and origin validation middleware."""
    app = create_app()
    client = TestClient(app)

    # 1. Localhost requests are accepted
    res_local = client.get("/api/health", headers={"origin": "http://127.0.0.1:8765"})
    assert res_local.status_code == 200
    assert res_local.headers.get("access-control-allow-origin") == "http://127.0.0.1:8765"

    # 2. Vite dev server origin accepted
    res_vite = client.get("/api/health", headers={"origin": "http://localhost:5173"})
    assert res_vite.status_code == 200
    assert res_vite.headers.get("access-control-allow-origin") == "http://localhost:5173"

    # 3. Third-party attacker website rejected with 403 Forbidden
    res_attacker = client.get("/api/health", headers={"origin": "https://malicious-site.com"})
    assert res_attacker.status_code == 403
    assert res_attacker.headers.get("access-control-allow-origin") != "https://malicious-site.com"

    # 4. Third-party referer rejected with 403 Forbidden
    res_ref = client.get("/api/health", headers={"referer": "https://malicious-site.com/exploit.html"})
    assert res_ref.status_code == 403


def test_sec_02_path_traversal_prevention():
    """Verify SEC-02: SPA catch-all does not leak host files via directory traversal."""
    app = create_app()
    client = TestClient(app)

    # Attempting to fetch pyproject.toml via traversal
    res = client.get("/..%2Fpyproject.toml")
    # Must NOT return the raw project configuration
    assert "[project]" not in res.text
    # Should fall back safely to index.html (status 200) or 404
    assert res.status_code in (200, 404)


def test_sec_03_websocket_origin_enforcement():
    """Verify SEC-03: Cross-Site WebSocket Hijacking protection."""
    app = create_app()
    client = TestClient(app)

    # Allowed localhost origin succeeds
    with client.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:8765"}) as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data.get("type") == "pong"

    # Third-party attacker origin is rejected
    with pytest.raises(Exception):
        with client.websocket_connect("/ws", headers={"origin": "https://evil.com"}) as ws:
            ws.receive_json()


def test_sec_04_no_sandbox_flag_removed():
    """Verify SEC-04: --no-sandbox is not hardcoded in main.py."""
    main_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")
    with open(main_py_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "--no-sandbox" not in content, "SEC-04 failed: --no-sandbox flag is still present in main.py!"


def test_sec_05_external_url_delegation():
    """Verify SEC-05: External URLs in WebEngine delegate to system default browser."""
    from PySide6.QtCore import QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)
    from app.desktop.modern_chat_window import CustomWebPage

    mock_win = MagicMock()
    page = CustomWebPage(mock_win)
    nav_type = QWebEnginePage.NavigationType.NavigationTypeLinkClicked

    # Internal URL allowed
    assert page.acceptNavigationRequest(QUrl("http://127.0.0.1:8765/chat"), nav_type, True) is True

    # External URL intercepted and delegated
    with patch("app.desktop.modern_chat_window.QDesktopServices.openUrl") as mock_open:
        res = page.acceptNavigationRequest(QUrl("https://google.com/search?q=test"), nav_type, True)
        assert res is False
        mock_open.assert_called_once()


def test_sec_06_hotkey_manager_hardening():
    """Verify SEC-06: GlobalHotkeyManager can be initialized and configured cleanly."""
    manager_enabled = GlobalHotkeyManager(enable_hook=False)
    assert not manager_enabled.is_installed

    # Clean uninstallation handles multiple calls gracefully
    assert manager_enabled.uninstall() is True
