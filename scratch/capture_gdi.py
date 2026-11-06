import ctypes
from ctypes import wintypes
from PySide6.QtGui import QImage

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

width = user32.GetSystemMetrics(0)
height = user32.GetSystemMetrics(1)
print(f"System metrics: {width}x{height}")

hdc_screen = user32.GetDC(0)
hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
gdi32.SelectObject(hdc_mem, hbitmap)

# BitBlt
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
res = gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, SRCCOPY | CAPTUREBLT)
print(f"BitBlt result: {res}")

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD)
    ]

bmi = BITMAPINFOHEADER()
bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
bmi.biWidth = width
bmi.biHeight = -height # top-down
bmi.biPlanes = 1
bmi.biBitCount = 32
bmi.biCompression = 0

buffer = ctypes.create_string_buffer(width * height * 4)
lines = gdi32.GetDIBits(hdc_mem, hbitmap, 0, height, buffer, ctypes.byref(bmi), 0)
print(f"GetDIBits lines: {lines}")

img = QImage(buffer, width, height, QImage.Format_ARGB32)
img.save("scratch/real_screen.png", "PNG")
print(f"Saved scratch/real_screen.png ({img.width()}x{img.height()})")

colors = set()
for y in range(0, height, 20):
    for x in range(0, width, 20):
        c = img.pixelColor(x, y)
        colors.add((c.red(), c.green(), c.blue()))
print(f"Real screen colors count: {len(colors)}")
print(f"Sample: {list(colors)[:10]}")

user32.ReleaseDC(0, hdc_screen)
gdi32.DeleteDC(hdc_mem)
gdi32.DeleteObject(hbitmap)
