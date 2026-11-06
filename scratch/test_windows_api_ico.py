import ctypes
from ctypes import wintypes
import os

ico_path = os.path.abspath("scratch/gold_standard_test.ico")

# IMAGE_ICON = 1, LR_LOADFROMFILE = 0x0010
hicon = ctypes.windll.user32.LoadImageW(None, ico_path, 1, 48, 48, 0x0010)
print("LoadImageW 48x48 handle:", hicon)
if hicon:
    ctypes.windll.user32.DestroyIcon(hicon)

hicon256 = ctypes.windll.user32.LoadImageW(None, ico_path, 1, 256, 256, 0x0010)
print("LoadImageW 256x256 handle:", hicon256)
if hicon256:
    ctypes.windll.user32.DestroyIcon(hicon256)

# Test ExtractIconExW
hicon_large = wintypes.HICON()
hicon_small = wintypes.HICON()
res = ctypes.windll.shell32.ExtractIconExW(ico_path, 0, ctypes.byref(hicon_large), ctypes.byref(hicon_small), 1)
print(f"ExtractIconExW returned {res}, large={hicon_large.value}, small={hicon_small.value}")
if hicon_large.value:
    ctypes.windll.user32.DestroyIcon(hicon_large)
if hicon_small.value:
    ctypes.windll.user32.DestroyIcon(hicon_small)
