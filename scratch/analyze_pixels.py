import sys
from PySide6.QtGui import QImage, QColor

def analyze(path):
    img = QImage(path)
    colors = set()
    non_transparent = 0
    total = img.width() * img.height()
    for y in range(0, img.height(), 4):
        for x in range(0, img.width(), 4):
            c = img.pixelColor(x, y)
            colors.add((c.red(), c.green(), c.blue(), c.alpha()))
    print(f"File {path}: {img.width()}x{img.height()} unique sampled colors: {len(colors)}")
    # Sample a few colors
    sample = list(colors)[:10]
    print(f"Sample colors: {sample}")

analyze("scratch/pet_grab.png")
analyze("scratch/desktop_pet_area.png")
analyze("scratch/chat_grab.png")
analyze("scratch/desktop_chat_area.png")
