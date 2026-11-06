import ctypes
from ctypes import wintypes
user32 = ctypes.windll.user32

hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0000037F)
if hwinsta:
    user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

def callback(hwnd, extra):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 6988:
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        is_visible = bool(user32.IsWindowVisible(hwnd))
        style = user32.GetWindowLongW(hwnd, -16)
        ex_style = user32.GetWindowLongW(hwnd, -20)
        cls_buff = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buff, 256)
        print(f"PID 6988: HWND: {hwnd:#x} | Visible: {is_visible} | Class: '{cls_buff.value}' | Title: '{buff.value}' | Rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom}) | Style: {style:#x} | ExStyle: {ex_style:#x}")
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(callback), 0)
