import sys
from PySide6.QtGui import QImage

img = QImage(r"C:\Users\Gaurav Patel\.gemini\antigravity\brain\b09d8994-baae-4b62-8eb8-dd78b29c0561\.user_uploaded\media_1792583973015_121ec1d8.png")
print("User screenshot loaded:", img.width(), img.height())

# Let's crop the bottom 100px (taskbar area)
taskbar = img.copy(0, img.height() - 80, img.width(), 80)
taskbar.save("scratch/user_taskbar.png", "PNG")
print("Saved scratch/user_taskbar.png")

# Let's crop bottom-right corner (system tray area)
tray = img.copy(img.width() - 400, img.height() - 80, 400, 80)
tray.save("scratch/user_tray.png", "PNG")
print("Saved scratch/user_tray.png")
