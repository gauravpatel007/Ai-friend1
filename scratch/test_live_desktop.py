import sys
import os
import time

sys.path.insert(0, os.path.abspath("."))

from PySide6.QtCore import QTimer, Qt, QRect
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QScreen

from app.core.controller import ApplicationController
from app.settings.config_manager import ConfigManager
from app.utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger("test_live_desktop")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from app.desktop.jarvis_theme import get_global_stylesheet, load_jarvis_fonts
load_jarvis_fonts()
app.setStyleSheet(get_global_stylesheet())

config_manager = ConfigManager()

controller = ApplicationController(app=app, config_manager=config_manager)
print("Initializing controller...")
success = controller.initialize()
print(f"Controller initialize result: {success}")

def capture_screen():
    print("--- Capturing Desktop Screen ---")
    screen = QApplication.primaryScreen()
    print(f"Primary screen: {screen.name()} geometry={screen.geometry()} available={screen.availableGeometry()} dpr={screen.devicePixelRatio()}")
    
    pet = controller.pet_window
    chat = controller.chat_window
    tray = controller.tray_manager
    
    print(f"Pet window: isVisible={pet.isVisible()} isHidden={pet.isHidden()} geo={pet.geometry()} frameGeo={pet.frameGeometry()} winId={int(pet.winId()):#x}")
    print(f"Chat window: isVisible={chat.isVisible()} isHidden={chat.isHidden()} geo={chat.geometry()} frameGeo={chat.frameGeometry()} winId={int(chat.winId()):#x}")
    print(f"Tray manager: tray_icon={tray.tray_icon} isVisible={tray.tray_icon.isVisible() if tray.tray_icon else None}")

    # Full desktop screenshot
    full_pixmap = screen.grabWindow(0)
    full_pixmap.save("scratch/full_desktop.png", "PNG")
    print(f"Full desktop captured: {full_pixmap.width()}x{full_pixmap.height()} saved to scratch/full_desktop.png")

    # Pet grab
    pet_pixmap = pet.grab()
    pet_pixmap.save("scratch/pet_grab.png", "PNG")
    print(f"Pet widget grab: {pet_pixmap.width()}x{pet_pixmap.height()} saved to scratch/pet_grab.png")

    # Chat grab
    chat_pixmap = chat.grab()
    chat_pixmap.save("scratch/chat_grab.png", "PNG")
    print(f"Chat widget grab: {chat_pixmap.width()}x{chat_pixmap.height()} saved to scratch/chat_grab.png")

    # Stop and shutdown
    QTimer.singleShot(1000, lambda: (controller.shutdown(), app.quit()))

QTimer.singleShot(4000, capture_screen)
app.exec()
print("Test completed.")
