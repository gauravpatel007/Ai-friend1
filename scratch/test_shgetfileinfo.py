import ctypes
from ctypes import wintypes
import os

class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]

# SHGFI_ICON = 0x000000100, SHGFI_LARGEICON = 0x000000000
SHGFI_ICON = 0x100
SHGFI_LARGEICON = 0x0

sfi = SHFILEINFO()
shortcut_path = r"C:\Users\Gaurav Patel\OneDrive\Desktop\AI Desktop Friend.lnk"
res = ctypes.windll.shell32.SHGetFileInfoW(
    shortcut_path,
    0,
    ctypes.byref(sfi),
    ctypes.sizeof(sfi),
    SHGFI_ICON | SHGFI_LARGEICON
)

print(f"SHGetFileInfoW result: {res}")
print(f"hIcon handle: {sfi.hIcon}")
print(f"iIcon index: {sfi.iIcon}")
print(f"Display Name: {sfi.szDisplayName}")
print(f"Type Name: {sfi.szTypeName}")

if sfi.hIcon:
    ctypes.windll.user32.DestroyIcon(sfi.hIcon)
