import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication(sys.argv)

w1 = QWidget()
w1.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
print("w1 windowType:", hex(int(w1.windowType())))
print("w1 isWindow:", w1.isWindow())

w2 = QWidget()
w2.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
print("w2 windowType:", hex(int(w2.windowType())))
print("w2 isWindow:", w2.isWindow())

w3 = QWidget()
w3.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
print("w3 windowType:", hex(int(w3.windowType())))
print("w3 isWindow:", w3.isWindow())
