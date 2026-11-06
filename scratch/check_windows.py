import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32

pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name']) if 'python' in (p.info['name'] or '').lower()]
print(f"Python PIDs found: {pids}")

def callback(hwnd, extra):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value in pids:
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        is_visible = bool(user32.IsWindowVisible(hwnd))
        style = user32.GetWindowLongW(hwnd, -16) # GWL_STYLE
        ex_style = user32.GetWindowLongW(hwnd, -20) # GWL_EXSTYLE
        cls_buff = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buff, 256)
        print(f"PID: {pid.value} | HWND: {hwnd:#x} | Visible: {is_visible} | Class: '{cls_buff.value}' | Title: '{buff.value}' | Rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom}) | Style: {style:#x} | ExStyle: {ex_style:#x}")
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(callback), 0)
