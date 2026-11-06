import time, threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path('dist').resolve()), **kwargs)
    def log_message(self, *args): pass

server = ThreadingHTTPServer(('127.0.0.1', 54323), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

app = QApplication.instance() or QApplication([])
view = QWebEngineView()
view.resize(1180, 780)
view.load(QUrl('http://127.0.0.1:54323/index.html'))
view.show()

loaded = [False]
view.loadFinished.connect(lambda ok: loaded.__setitem__(0, True))
start = time.time()
while not loaded[0] and time.time() - start < 6.0:
    app.processEvents(); time.sleep(0.05)

# Wait for React mount
for _ in range(30):
    app.processEvents(); time.sleep(0.05)

# Click the voice portal button or call window.openVoicePortal
view.page().runJavaScript('if (window.openVoicePortal) { window.openVoicePortal(); }')

# Wait for portal render
for _ in range(30):
    app.processEvents(); time.sleep(0.05)

res_portal = []
view.page().runJavaScript("Boolean(document.querySelector('.voice-portal-card'))", lambda r: res_portal.append(r))
start = time.time()
while not res_portal and time.time() - start < 3.0:
    app.processEvents(); time.sleep(0.05)

print("Has Voice Portal:", res_portal)
out_png = Path('scratch/verified_voice_portal.png')
view.grab().save(str(out_png))
print("Saved verified_voice_portal.png:", out_png.stat().st_size)

# Now open settings
view.page().runJavaScript("""
  const scrim = document.querySelector('.voice-portal-scrim');
  if (scrim) scrim.click();
  setTimeout(() => {
    if (window.openSettings) window.openSettings();
  }, 100);
""")
for _ in range(30):
    app.processEvents(); time.sleep(0.05)

res_settings = []
view.page().runJavaScript("Boolean(document.querySelector('.apple-settings-window'))", lambda r: res_settings.append(r))
start = time.time()
while not res_settings and time.time() - start < 3.0:
    app.processEvents(); time.sleep(0.05)

print("Has Settings Modal:", res_settings)
out_settings_png = Path('scratch/verified_settings_modal.png')
view.grab().save(str(out_settings_png))
print("Saved verified_settings_modal.png:", out_settings_png.stat().st_size)

view.close()
