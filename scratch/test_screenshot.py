import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer, QSize

print("PySide6 WebEngine test...")
app = QApplication.instance() or QApplication(sys.argv)
view = QWebEngineView()
view.resize(1440, 900)

def on_load_finished(ok):
    print("Loaded:", ok)
    if ok:
        def capture():
            pixmap = view.grab()
            pixmap.save("scratch/test_reelipse.png", "PNG")
            print("Saved scratch/test_reelipse.png, size:", pixmap.size())
            app.quit()
        QTimer.singleShot(2500, capture)
    else:
        print("Failed to load")
        app.quit()

view.loadFinished.connect(on_load_finished)
view.load(QUrl("https://reelipse.com/"))
app.exec()
