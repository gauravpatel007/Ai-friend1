import sys
import os
sys.path.insert(0, os.path.abspath("."))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.jarvis_theme import get_global_stylesheet
from app.settings.config_manager import ConfigManager

app = QApplication(sys.argv)
app.setStyleSheet(get_global_stylesheet())

cfg = ConfigManager()
pet = DesktopPetWindow(cfg)
print("pet.autoFillBackground():", pet.autoFillBackground())
print("pet stylesheet:", pet.styleSheet())
pix = pet.grab()
print(f"pet.grab() corner color (0,0): {pix.toImage().pixelColor(0, 0).name(QColor.HexArgb)}")
print(f"pet.grab() center color (60,60): {pix.toImage().pixelColor(60, 60).name(QColor.HexArgb)}")
