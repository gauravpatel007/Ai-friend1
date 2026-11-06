import sys
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

app = QApplication(sys.argv)
win = QMainWindow()
view = QWebEngineView(win)
win.setCentralWidget(view)
win.resize(400, 300)
win.show()

class DragFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.MouseButtonRelease):
            print("Filtered event:", event.type(), event.pos() if hasattr(event, "pos") else "")
        return False

drag_filter = DragFilter()

def setup():
    fp = view.focusProxy()
    if fp:
        fp.installEventFilter(drag_filter)
        print("Installed event filter on focusProxy")
    QTimer.singleShot(1500, app.quit)

QTimer.singleShot(500, setup)
app.exec()
