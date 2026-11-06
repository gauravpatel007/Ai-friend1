import os
import sys
import time
import threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

class CustomHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).resolve().parent.parent / "dist"), **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress console spam

def start_server(port=54321):
    server = ThreadingHTTPServer(("127.0.0.1", port), CustomHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

def capture_web_views():
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
    app = QApplication.instance() or QApplication(sys.argv)

    project_root = Path(__file__).resolve().parent.parent
    server = start_server(54321)
    target_url = "http://127.0.0.1:54321/index.html"

    out_dir = project_root / "scratch"
    out_dir.mkdir(parents=True, exist_ok=True)

    view = QWebEngineView()
    view.resize(1180, 780)
    view.page().setBackgroundColor(QColor("#0B0E17"))

    print(f"Loading {target_url}...")
    view.load(QUrl(target_url))
    view.show()

    state = {"loaded": False}

    def on_load_finished(ok):
        print(f"Load finished: {ok}")
        state["loaded"] = True

    view.loadFinished.connect(on_load_finished)

    # Pump Qt events until loaded
    start_time = time.time()
    while not state["loaded"] and time.time() - start_time < 8.0:
        app.processEvents()
        time.sleep(0.05)

    # Wait extra 2.5 seconds for React to mount, load fonts, and populate UI
    start_render = time.time()
    while time.time() - start_render < 2.5:
        app.processEvents()
        time.sleep(0.05)

    # Inject mock messages so the chat looks lively and realistic
    mock_setup_js = """
    (function() {
      const store = window.useChatStore ? window.useChatStore.getState() : null;
      // Add visual sample messages to DOM if store not global
      const viewport = document.querySelector('.stream-centered-column');
      if (viewport && !document.querySelector('.bubble-user')) {
        viewport.innerHTML = `
          <div class="stream-date-header">
            <span class="apple-date-pill">Today, Oct 27</span>
          </div>
          <div class="message-thread-item thread-ai">
            <div class="message-avatar-wrap">
              <img src="/assets/characters/robot/idle.png" alt="Buddy" class="msg-avatar-media">
            </div>
            <div class="message-body-wrap">
              <div class="message-meta-row">
                <span class="msg-sender-name">Buddy</span>
                <span class="msg-timestamp">01:28 PM</span>
              </div>
              <div class="apple-bubble bubble-assistant">
                <div class="bubble-markdown-text">Hello! I'm Buddy, your personal AI companion. Everything runs 100% locally on your machine with Ollama and neural speech synthesis. How can I help you today?</div>
              </div>
            </div>
          </div>
          <div class="message-thread-item thread-user">
            <div class="message-avatar-wrap">
              <div style="width:100%;height:100%;background:linear-gradient(135deg,#0A84FF,#0066D6);border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-weight:700;font-size:12px;">U</div>
            </div>
            <div class="message-body-wrap">
              <div class="message-meta-row">
                <span class="msg-sender-name">You</span>
                <span class="msg-timestamp">01:28 PM</span>
              </div>
              <div class="apple-bubble bubble-user">
                <div class="bubble-markdown-text">Can you summarize my offline tasks and start voice mode?</div>
              </div>
            </div>
          </div>
          <div class="message-thread-item thread-ai">
            <div class="message-avatar-wrap">
              <img src="/assets/characters/robot/happy.png" alt="Buddy" class="msg-avatar-media">
            </div>
            <div class="message-body-wrap">
              <div class="message-meta-row">
                <span class="msg-sender-name">Buddy</span>
                <span class="msg-timestamp">01:29 PM</span>
              </div>
              <div class="apple-bubble bubble-assistant">
                <div class="bubble-markdown-text">You've got 3 tasks lined up today! Voice mode is ready whenever you are—just tap the microphone or say "Hey Buddy" to talk hands-free. 🎙️</div>
              </div>
            </div>
          </div>
        `;
      }
    })();
    """
    view.page().runJavaScript(mock_setup_js)

    start_wait = time.time()
    while time.time() - start_wait < 1.0:
        app.processEvents()
        time.sleep(0.05)

    # 1. Capture Redesigned Apple Chat View
    chat_png = out_dir / "redesigned_apple_chat_window.png"
    pixmap = view.grab()
    pixmap.save(str(chat_png))
    print(f"Saved: {chat_png} ({pixmap.width()}x{pixmap.height()}, {chat_png.stat().st_size} bytes)")

    # 2. Open Apple Voice Portal
    view.page().runJavaScript("window.openVoicePortal && window.openVoicePortal();")
    start_portal = time.time()
    while time.time() - start_portal < 1.5:
        app.processEvents()
        time.sleep(0.05)

    voice_png = out_dir / "redesigned_apple_voice_portal.png"
    pixmap_voice = view.grab()
    pixmap_voice.save(str(voice_png))
    print(f"Saved: {voice_png} ({pixmap_voice.width()}x{pixmap_voice.height()}, {voice_png.stat().st_size} bytes)")

    # 3. Close Voice Portal & Open Apple Settings Window
    view.page().runJavaScript("""
      const scrim = document.querySelector('.voice-portal-scrim');
      if (scrim) scrim.click();
      setTimeout(() => {
        window.openSettings && window.openSettings();
      }, 200);
    """)
    start_settings = time.time()
    while time.time() - start_settings < 1.5:
        app.processEvents()
        time.sleep(0.05)

    settings_png = out_dir / "redesigned_apple_settings_modal.png"
    pixmap_settings = view.grab()
    pixmap_settings.save(str(settings_png))
    print(f"Saved: {settings_png} ({pixmap_settings.width()}x{pixmap_settings.height()}, {settings_png.stat().st_size} bytes)")

    view.close()
    print("Done capturing screenshots.")

if __name__ == "__main__":
    capture_web_views()
