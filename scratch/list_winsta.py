import ctypes
from ctypes import wintypes
user32 = ctypes.windll.user32

hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0000037F)
print("hwinsta:", hwinsta)
if hwinsta:
    user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
print("hdesk:", hdesk)
if hdesk:
    user32.SetThreadDesktop(hdesk)

def callback(hwnd, extra):
    if user32.IsWindowVisible(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            print(f"PID: {pid.value} | HWND: {hwnd:#x} | Title: '{buff.value}'")
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(callback), 0)
