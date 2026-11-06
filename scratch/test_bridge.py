import sys
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
view = QWebEngineView()

class TestPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        print("acceptNavigationRequest called with:", url.toString())
        QTimer.singleShot(50, app.quit)
        return False

page = TestPage()
view.setPage(page)
view.setHtml("<html><body><h1>Test</h1></body></html>")

def trigger():
    print("Triggering JS navigation...")
    view.page().runJavaScript("window.location.href = 'pybridge://minimize';")

QTimer.singleShot(500, trigger)
QTimer.singleShot(2000, app.quit)
app.exec()
