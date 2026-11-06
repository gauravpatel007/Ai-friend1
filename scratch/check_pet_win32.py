import sys
import os
import ctypes
from ctypes import wintypes
sys.path.insert(0, os.path.abspath("."))

from PySide6.QtWidgets import QApplication
from app.desktop.pet_window import DesktopPetWindow
from app.settings.config_manager import ConfigManager

user32 = ctypes.windll.user32

hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0000037F)
if hwinsta:
    user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

app = QApplication(sys.argv)
cfg = ConfigManager()
pet = DesktopPetWindow(cfg)
pet.show_pet()

hwnd = int(pet.winId())
cls_buff = ctypes.create_unicode_buffer(256)
user32.GetClassNameW(hwnd, cls_buff, 256)
rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
style = user32.GetWindowLongW(hwnd, -16)
ex_style = user32.GetWindowLongW(hwnd, -20)
is_visible = bool(user32.IsWindowVisible(hwnd))

print(f"PET HWND: {hwnd:#x}")
print(f"Class: {cls_buff.value}")
print(f"Visible: {is_visible}")
print(f"Rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom})")
print(f"Style: {style:#x}")
print(f"ExStyle: {ex_style:#x}")

# Check DWM attribute
DWMWA_EXTENDED_FRAME_BOUNDS = 9
frame_rect = wintypes.RECT()
dwmapi = ctypes.windll.dwmapi
res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(frame_rect), ctypes.sizeof(frame_rect))
print(f"DWM Frame Rect result: {res} -> ({frame_rect.left}, {frame_rect.top}, {frame_rect.right}, {frame_rect.bottom})")
