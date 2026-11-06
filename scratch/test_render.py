import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from app.settings.config_manager import ConfigManager
from app.desktop.modern_chat_window import ModernChatWindow
import uvicorn
from app.api.server import app as fastapi_app

def run_srv():
    config = uvicorn.Config(app=fastapi_app, host='127.0.0.1', port=8765, log_level='error')
    srv = uvicorn.Server(config)
    srv.run()

t = threading.Thread(target=run_srv, daemon=True)
t.start()
time.sleep(1.0)

qt_app = QApplication(sys.argv)
cfg = ConfigManager()
chat = ModernChatWindow(cfg)

class DebugPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        print(f'[JS {level}] {source_id}:{line_number} -> {message}')

dbg_page = DebugPage(chat.browser)
chat.browser.setPage(dbg_page)
chat.browser.load(QUrl('http://127.0.0.1:8765'))
chat.show_chat()

def check_dom():
    def cb(res):
        print('DOM #root innerHTML length:', len(str(res)))
        print('DOM #root innerHTML start:', str(res)[:200])
        pix = chat.grab()
        os.makedirs('scratch', exist_ok=True)
        pix.save('scratch/chat_react_fixed.png')
        from PySide6.QtGui import QImage
        im = QImage('scratch/chat_react_fixed.png')
        colors = set()
        for y in range(0, im.height(), 15):
            for x in range(0, im.width(), 15):
                colors.add(im.pixelColor(x, y).name())
        print('Rendered unique colors after fix:', len(colors))
        qt_app.quit()
    chat.browser.page().runJavaScript("document.getElementById('root').innerHTML", cb)

QTimer.singleShot(4000, check_dom)
qt_app.exec()
