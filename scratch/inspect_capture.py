import sys
from PySide6.QtGui import QImage, QColor

img = QImage("scratch/full_desktop.png")
print(f"Full desktop image loaded: {img.width()}x{img.height()} format={img.format()}")

# Pet logical rect: (1375, 619, 120, 120)
# DPI is 1.25 -> Physical pixels: x: 1375*1.25 = 1718.75 to 1718.75 + 150 = 1868.75; y: 619*1.25 = 773.75 to 923.75
# Let's crop the pet area from full_desktop.png and save it:
pet_crop = img.copy(int(1375 * 1.25), int(619 * 1.25), 150, 150)
pet_crop.save("scratch/desktop_pet_area.png", "PNG")
print("Saved scratch/desktop_pet_area.png")

# Chat logical rect: (319, 145, 1040, 690)
# Physical pixels: x: 319*1.25 = 398, y: 145*1.25 = 181, w: 1040*1.25 = 1300, h: 690*1.25 = 862
chat_crop = img.copy(int(319 * 1.25), int(145 * 1.25), 200, 200)
chat_crop.save("scratch/desktop_chat_area.png", "PNG")
print("Saved scratch/desktop_chat_area.png")

# Also let's inspect the bottom-right taskbar area where tray icons are located:
# Taskbar is y=816*1.25=1020 to 1080, x from 1400*1.25=1750 to 1920
tray_crop = img.copy(int(1300 * 1.25), int(816 * 1.25), int((1536-1300)*1.25), int((864-816)*1.25))
tray_crop.save("scratch/desktop_tray_area.png", "PNG")
print("Saved scratch/desktop_tray_area.png")
