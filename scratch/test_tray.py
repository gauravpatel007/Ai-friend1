import sys
import os
sys.path.insert(0, os.path.abspath("."))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget, QLabel, QVBoxLayout
from app.utils.icon_utils import get_application_icon

app = QApplication(sys.argv)
print("System tray available:", QSystemTrayIcon.isSystemTrayAvailable())

icon = get_application_icon()
print("Icon isNull:", icon.isNull())

tray = QSystemTrayIcon(icon, app)
menu = QMenu()
menu.addAction("Test Item")
menu.addAction("Quit", app.quit)
tray.setContextMenu(menu)
tray.setToolTip("Test AI Desktop Friend")
tray.show()
print("Tray isVisible:", tray.isVisible())
print("Tray geometry:", tray.geometry())

w = QWidget()
w.setWindowTitle("Test Window AI Desktop Friend")
layout = QVBoxLayout(w)
layout.addWidget(QLabel("Hello! Can you see this window?"))
w.resize(400, 300)
w.show()
print("Window isVisible:", w.isVisible())

QTimer.singleShot(2000, lambda: print("2 seconds passed, exiting..."))
QTimer.singleShot(3000, app.quit)

app.exec()
print("Done")
