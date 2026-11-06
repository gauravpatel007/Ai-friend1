"""Modern Chat Window — Host for Tauri/React UI inside PySide6.

Replaces the legacy FloatingChatWindow while preserving full integration
with DesktopPetWindow, StatusHUD, and system signals.
"""

from __future__ import annotations

import os
import sys

# Ensure local loopback bypasses proxy environments (e.g., enterprise proxies, sandbox)
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

from typing import Optional, Tuple

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from app.core.signals import signals
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)


class _DummyInputBar(QObject):
    """Compatibility shim for StatusHUD."""
    mode_changed = Signal(str)


class CustomWebPage(QWebEnginePage):
    """Intercepts pybridge URLs for window control actions and external links for secure browser delegation."""

    def __init__(self, main_window: ModernChatWindow, parent=None):
        super().__init__(parent)
        self.main_window = main_window

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        scheme = url.scheme().lower()
        if scheme == "pybridge":
            action = url.host() or url.path().strip("/")
            if action == "minimize":
                self.main_window.showMinimized()
            elif action == "maximize":
                self.main_window.toggle_maximize()
            elif action == "close":
                self.main_window.hide()
            elif action == "copy":
                try:
                    from urllib.parse import parse_qs
                    query = parse_qs(url.query())
                    text = query.get("text", [""])[0]
                    if text:
                        from PySide6.QtGui import QGuiApplication
                        QGuiApplication.clipboard().setText(text)
                except Exception as e:
                    logger.debug("Bridge copy action note: %s", e)
            return False

        # Allow internal app schemes and loopback hosts
        if scheme in ("qrc", "data", "about", "chrome-extension"):
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        # Never navigate the main chat frame away to blob URLs (which triggers on anchor file downloads)
        if scheme == "blob":
            return False

        if scheme in ("http", "https"):
            host = url.host().lower()
            if host in ("127.0.0.1", "localhost", "tauri.localhost"):
                return super().acceptNavigationRequest(url, nav_type, is_main_frame)

            # Delegate external websites to the system default browser
            logger.info("Delegating external URL to system browser: %s", url.toString())
            QDesktopServices.openUrl(url)
            return False

        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def featurePermissionRequested(self, securityOrigin: QUrl, feature: QWebEnginePage.Feature) -> None:
        try:
            allowed_features = (
                QWebEnginePage.Feature.ClipboardReadWrite,
                QWebEnginePage.Feature.MediaAudioCapture,
            )
            if feature in allowed_features:
                self.setFeaturePermission(securityOrigin, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
                return
        except Exception:
            pass
        super().featurePermissionRequested(securityOrigin, feature)

    def javaScriptAlert(self, securityOrigin: QUrl, msg: str) -> None:
        """Prevent JavaScript alert() from blocking the Qt event loop or hanging the desktop window."""
        logger.warning("Intercepted WebEngine JavaScript alert (non-blocking): %s", msg)

    def javaScriptConfirm(self, securityOrigin: QUrl, msg: str) -> bool:
        """Non-blocking confirm handler."""
        logger.warning("Intercepted WebEngine JavaScript confirm: %s", msg)
        return True

    def javaScriptPrompt(self, securityOrigin: QUrl, msg: str, defaultValue: str) -> Tuple[bool, str]:
        """Non-blocking prompt handler."""
        return False, defaultValue

    def createWindow(self, _type: QWebEnginePage.WebWindowType) -> Optional[QWebEnginePage]:
        """Intercept new-window / target='_blank' links and route through CustomWebPage."""
        return CustomWebPage(self.main_window, self)


class ModernChatWindow(QMainWindow):
    """Modern Frameless Chat Window hosting the React + TypeScript frontend."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        ai_service: Optional[object] = None,
        voice_service: Optional[object] = None,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.ai_service = ai_service
        self.voice_service = voice_service
        self._drag_pos = QPoint()
        self._is_maximized = False

        # Compatibility attribute for controller / status HUD
        self.input_bar = _DummyInputBar()

        companion_name = (
            (self.config_manager.get("ai.companion_name") or self.config_manager.get("companion.name", "Buddy"))
            if self.config_manager
            else "Buddy"
        )
        self.setWindowTitle(f"AI Desktop Friend — Desktop Companion - {companion_name}")
        from app.utils.icon_utils import get_window_title_icon
        self.setWindowIcon(get_window_title_icon())
        self.resize(1040, 660)
        self.setMinimumSize(860, 520)

        if self.config_manager:
            self.config_manager.setting_changed.connect(self._on_setting_changed)

        # Standard desktop application window (allows other apps to cover it when clicked outside)
        self.setWindowFlags(Qt.Window)
        self.setStyleSheet("background-color: #111113; border: none;")

        # Initialize Chromium WebEngineView
        self.browser = QWebEngineView(self)
        self.browser.page().setBackgroundColor(QColor("#070E1F"))
        self.browser.titleChanged.connect(self._on_title_changed)
        self.browser.loadFinished.connect(self._on_load_finished)

        # Enable clipboard access in WebEngine
        try:
            from PySide6.QtWebEngineCore import QWebEngineSettings
            settings = self.browser.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, True)
        except Exception as e:
            logger.debug("WebEngine clipboard settings note: %s", e)

        # Setup custom page with bridge
        self.custom_page = CustomWebPage(self, self.browser)
        self.browser.setPage(self.custom_page)

        # Wire safe Chromium file downloads to user Downloads directory without dialog freezes
        try:
            self.custom_page.profile().downloadRequested.connect(self._on_download_requested)
        except Exception as e:
            logger.debug("DownloadRequested connection note: %s", e)

        # Inject pybridge shim so React Header controls work
        bridge_script = QWebEngineScript()
        bridge_script.setName("PyBridgeShim")
        bridge_script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        bridge_script.setWorldId(QWebEngineScript.MainWorld)
        bridge_script.setSourceCode("""
            window.pywebview = {
                api: {
                    minimize: function() { window.location.href = "pybridge://minimize"; },
                    maximize: function() { window.location.href = "pybridge://maximize"; },
                    close: function() { window.location.href = "pybridge://close"; },
                    copy: function(text) { window.location.href = "pybridge://copy?text=" + encodeURIComponent(text); }
                }
            };
        """)
        self.browser.page().scripts().insert(bridge_script)

        # Inject global selectable text styles cleanly on the root document body
        selection_script = QWebEngineScript()
        selection_script.setName("GlobalTextSelection")
        selection_script.setInjectionPoint(QWebEngineScript.DocumentReady)
        selection_script.setWorldId(QWebEngineScript.MainWorld)
        selection_script.setRunsOnSubFrames(False)
        selection_script.setSourceCode("""
            (function() {
                if (document.getElementById('force-text-selectable')) return;
                var el = document.createElement('style');
                el.id = 'force-text-selectable';
                el.innerHTML = 'body { -webkit-user-select: text; user-select: text; }';
                if (document.head) {
                    document.head.appendChild(el);
                }
            })();
        """)
        self.browser.page().scripts().insert(selection_script)

        self.setCentralWidget(self.browser)

        # Show elegant Apple-styled loading placeholder while server initializes
        loading_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {
              margin: 0; background: #000000; color: #ffffff;
              font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
              display: flex; flex-direction: column; align-items: center; justify-content: center;
              height: 100vh; overflow: hidden; -webkit-user-select: text; user-select: text;
            }
            .spinner {
              width: 32px; height: 32px; border: 3px solid rgba(255,255,255,0.12);
              border-top: 3px solid #0071e3; border-radius: 50%;
              animation: spin 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
              margin-bottom: 18px;
            }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            .title { font-size: 15px; font-weight: 500; letter-spacing: -0.2px; opacity: 0.92; }
            .sub { font-size: 12px; color: rgba(255,255,255,0.45); margin-top: 6px; }
          </style>
        </head>
        <body>
          <div class="spinner"></div>
          <div class="title">AI Desktop Friend</div>
          <div class="sub">Connecting to companion engine...</div>
        </body>
        </html>
        """
        self.browser.setHtml(loading_html)

        # Poll backend readiness before loading UI
        self._target_url = "http://127.0.0.1:8765"
        self._retry_count = 0
        self._max_retries = 35  # 35 * 200ms = 7.0 seconds
        self._ready_timer = QTimer(self)
        self._ready_timer.setInterval(200)
        self._ready_timer.timeout.connect(self._check_server_ready)
        self._ready_timer.start()

    def _check_server_ready(self) -> None:
        """Poll the local backend health endpoint until it is accepting connections."""
        self._retry_count += 1
        is_ready = False
        target_to_load = self._target_url

        try:
            import urllib.request
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            # First, check if Vite dev server is running on 5173 for hot-reloading
            try:
                with opener.open("http://127.0.0.1:5173", timeout=0.2) as resp:
                    if resp.status == 200:
                        target_to_load = "http://127.0.0.1:5173"
                        is_ready = True
            except Exception:
                pass

            # Otherwise verify FastAPI backend health on 8765
            if not is_ready:
                with opener.open(f"{self._target_url}/api/health", timeout=0.3) as resp:
                    if resp.status == 200:
                        is_ready = True
        except Exception:
            pass

        if is_ready:
            self._ready_timer.stop()
            self._target_url = target_to_load
            logger.info("Server is ready. Loading interface: %s", self._target_url)
            self.browser.load(QUrl(self._target_url))
        elif self._retry_count >= self._max_retries:
            self._ready_timer.stop()
            logger.warning("Backend readiness timeout reached. Loading fallback: %s", self._target_url)
            self.browser.load(QUrl(self._target_url))

    def show_chat(self) -> None:
        """Show and bring the chat window to the foreground."""
        if self.isMinimized():
            self.showNormal()

        # Bounds safety check before presenting: ensure window is within screen boundaries
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            curr_x = self.x()
            curr_y = self.y()
            min_x = geo.left() + 10
            max_x = max(min_x, geo.right() - self.width() - 10)
            min_y = geo.top() + 10
            max_y = max(min_y, geo.bottom() - self.height() - 10)
            if curr_x < min_x or curr_x > max_x or curr_y < min_y or curr_y > max_y:
                self.move(
                    max(min_x, min(curr_x, max_x)),
                    max(min_y, min(curr_y, max_y))
                )

        self.show()
        self.raise_()
        self.activateWindow()
        if hasattr(self, "browser") and self.browser:
            self.browser.setFocus()

        from app.utils.window_elevation import elevate_window_to_front
        elevate_window_to_front(int(self.winId()), keep_topmost=False)

    def open_chat_view(self) -> None:
        """Bring chat window to front and switch to the main Chat conversation view."""
        self.show_chat()
        if hasattr(self, "browser") and self.browser:
            self.browser.page().runJavaScript(
                "window.openChat ? window.openChat() : window.dispatchEvent(new CustomEvent('open-chat'));"
            )

    def open_voice_portal(self) -> None:
        """Bring chat window to front and open the modern React Apple Voice Portal."""
        self.show_chat()
        if hasattr(self, "browser") and self.browser:
            self.browser.page().runJavaScript(
                "window.openVoicePortal ? window.openVoicePortal() : window.dispatchEvent(new CustomEvent('open-voice-portal'));"
            )

    def open_settings(self) -> None:
        """Bring chat window to front and open the modern React Apple Settings Sheet."""
        self.show_chat()
        if hasattr(self, "browser") and self.browser:
            self.browser.page().runJavaScript(
                "window.openSettings ? window.openSettings() : window.dispatchEvent(new CustomEvent('open-settings'));"
            )

    def hide_chat(self) -> None:
        """Hide the chat window."""
        self.hide()

    def toggle_chat(self) -> None:
        """Toggle chat window visibility."""
        if self.isVisible():
            self.hide()
        else:
            self.show_chat()

    def position_near_pet(self, pet_rect: QRect) -> None:
        """Position the chat window intelligently relative to the floating pet, ensuring 100% on-screen visibility."""
        screen = QApplication.screenAt(pet_rect.center())
        if not screen:
            screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        win_w = self.width()
        win_h = self.height()

        # Available clearance on both horizontal sides of pet
        space_left = pet_rect.left() - geo.left()
        space_right = geo.right() - pet_rect.right()
        margin = 16

        # Prefer side with adequate clearance; fall back to side with larger space
        if space_left >= win_w + margin:
            target_x = pet_rect.left() - win_w - margin
        elif space_right >= win_w + margin:
            target_x = pet_rect.right() + margin
        else:
            if space_left >= space_right:
                target_x = pet_rect.left() - win_w - margin
            else:
                target_x = pet_rect.right() + margin

        # Align vertically with pet, keeping within vertical bounds
        target_y = pet_rect.top()
        if target_y + win_h > geo.bottom() - 10:
            target_y = pet_rect.bottom() - win_h
            if target_y < geo.top() + 10:
                target_y = geo.bottom() - win_h - 10

        # Absolute screen bounds clamping (guarantees the window is NEVER pushed off-screen)
        min_x = geo.left() + 10
        max_x = max(min_x, geo.right() - win_w - 10)
        clamped_x = max(min_x, min(target_x, max_x))

        min_y = geo.top() + 10
        max_y = max(min_y, geo.bottom() - win_h - 10)
        clamped_y = max(min_y, min(target_y, max_y))

        self.move(clamped_x, clamped_y)

    def toggle_maximize(self) -> None:
        if self._is_maximized:
            self.showNormal()
            self._is_maximized = False
        else:
            self.showMaximized()
            self._is_maximized = True

    # ─── Window Dragging (Top 84px Header Area) ─────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 84:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self._drag_pos.isNull() and not self._is_maximized:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()
        event.accept()

    def start_drag(self) -> None:
        """Initiate native system window dragging."""
        if self._is_maximized:
            self.showNormal()
            self._is_maximized = False
        moved = False
        if self.windowHandle():
            try:
                moved = self.windowHandle().startSystemMove()
            except Exception:
                pass
        if not moved:
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.ReleaseCapture()
                ctypes.windll.user32.SendMessageW(hwnd, 0x0112, 0xF012, 0)
            except Exception:
                pass

    def showEvent(self, event) -> None:
        """Ensure native Windows taskbar icon is applied when the window is shown."""
        super().showEvent(event)
        try:
            from app.utils.icon_utils import apply_windows_taskbar_icon
            apply_windows_taskbar_icon(int(self.winId()))
        except Exception:
            pass

    def move_delta(self, dx: int, dy: int) -> None:
        """Move window by relative pixel delta."""
        if not self._is_maximized:
            self.move(self.x() + dx, self.y() + dy)

    def _on_title_changed(self, title: str) -> None:
        """Keep the native window title synchronized with the web app title."""
        if title and title.strip():
            self.setWindowTitle(title.strip())

    def _on_download_requested(self, download) -> None:
        """Handle Chromium file downloads directly to user Downloads folder without blocking modal freezes."""
        try:
            import os
            downloads_dir = os.path.expanduser("~/Downloads")
            if os.path.exists(downloads_dir):
                download.setDownloadDirectory(downloads_dir)
            download.accept()
            logger.info("Chromium download accepted: %s", download.suggestedFileName())
        except Exception as e:
            logger.debug("Chromium download handler note: %s", e)

    def _on_load_finished(self, ok: bool) -> None:
        """Inject companion name into web UI immediately upon page load completion."""
        if ok:
            companion_name = (
                (self.config_manager.get("ai.companion_name") or self.config_manager.get("companion.name") or self.config_manager.get("character.name") or "Buddy")
                if self.config_manager
                else "Buddy"
            )
            self._apply_companion_name(companion_name)
            QTimer.singleShot(100, lambda: self._apply_companion_name(companion_name))
            QTimer.singleShot(500, lambda: self._apply_companion_name(companion_name))

    @Slot(str, object)
    def _on_setting_changed(self, key: str, val: Any) -> None:
        """React dynamically to configuration updates such as companion name."""
        if key in ("ai.companion_name", "companion.name", "character.name"):
            name = str(val).strip() if val else "Buddy"
            # Ensure GUI and Chromium WebEngine updates run strictly on the Qt GUI main thread
            QTimer.singleShot(0, lambda: self._apply_companion_name(name))

    def _apply_companion_name(self, name: str) -> None:
        """Apply companion name update on Qt GUI main thread and dispatch to web environment."""
        self.setWindowTitle(f"AI Desktop Friend — Desktop Companion - {name}")
        if hasattr(self, "browser") and self.browser:
            import json
            safe_name = json.dumps(name)
            try:
                self.browser.page().runJavaScript(
                    f"(function() {{ "
                    f"window.__INITIAL_COMPANION_NAME__ = {safe_name}; "
                    f"document.title = 'AI Desktop Friend — Desktop Companion - ' + {safe_name}; "
                    f"if (window.dispatchEvent) {{ window.dispatchEvent(new CustomEvent('companion-name-changed', {{ detail: {safe_name} }})); }} "
                    f"}})();"
                )
            except Exception as e:
                logger.debug("Browser dispatch note: %s", e)

    def cleanup(self) -> None:
        """Clean up web engine resources deterministically without triggering new navigations."""
        self.hide()
        if hasattr(self, "_ready_timer") and self._ready_timer:
            try:
                self._ready_timer.stop()
            except Exception:
                pass
        if hasattr(self, "browser") and self.browser:
            try:
                self.browser.stop()
                self.browser.deleteLater()
            except Exception as e:
                logger.debug("Browser cleanup note: %s", e)
            finally:
                self.browser = None

    def closeEvent(self, event) -> None:
        """Handle window close event while preserving intended behavior."""
        from app.core.lifecycle import get_lifecycle_manager
        lifecycle = get_lifecycle_manager()
        if lifecycle.is_shutting_down:
            self.cleanup()
            event.accept()
        else:
            # When closed during normal operation, preserve companion hide-to-pet behavior
            self.hide()
            event.ignore()
