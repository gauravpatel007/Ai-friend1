import subprocess, time, ctypes, os
from ctypes import wintypes

code = 'from PySide6.QtWidgets import QApplication, QMainWindow; a = QApplication([]); w = QMainWindow(); w.setWindowTitle("TEST_GUI"); w.show(); a.exec()'
p = subprocess.Popen(['.\\.venv\\Scripts\\python.exe', '-c', code])
time.sleep(2.5)
print('Spawned PID:', p.pid)

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
found = []
def cb(hwnd, lparam):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == p.pid:
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        found.append((hwnd, buf.value))
    return True

user32.EnumWindows(WNDENUMPROC(cb), 0)
print('Found windows for spawned PID:', found)
p.terminate()
