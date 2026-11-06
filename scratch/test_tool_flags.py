import sys
import os
import ctypes
from ctypes import wintypes
sys.path.insert(0, os.path.abspath("."))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

user32 = ctypes.windll.user32

app = QApplication(sys.argv)
w = QWidget()
w.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_TranslucentBackground, True)
w.resize(120, 120)
w.show()

hwnd = int(w.winId())
cls_buff = ctypes.create_unicode_buffer(256)
user32.GetClassNameW(hwnd, cls_buff, 256)
rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
style = user32.GetWindowLongW(hwnd, -16)
ex_style = user32.GetWindowLongW(hwnd, -20)
is_visible = bool(user32.IsWindowVisible(hwnd))

print(f"HWND: {hwnd:#x}")
print(f"Class: {cls_buff.value}")
print(f"Visible: {is_visible}")
print(f"Style: {style:#x}")
print(f"ExStyle: {ex_style:#x}")
