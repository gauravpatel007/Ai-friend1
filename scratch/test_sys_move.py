import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

app = QApplication(sys.argv)
win = QMainWindow()
win.resize(400, 300)
win.show()

def test_start_system_move():
    print("Calling startSystemMove...")
    handle = win.windowHandle()
    if handle:
        res = handle.startSystemMove()
        print("startSystemMove returned:", res)
    else:
        print("No windowHandle!")
    QTimer.singleShot(500, app.quit)

QTimer.singleShot(200, test_start_system_move)
app.exec()
