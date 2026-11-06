import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.settings.config_manager import ConfigManager
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.modern_chat_window import ModernChatWindow
from app.desktop.jarvis_theme import get_global_stylesheet, load_jarvis_fonts
import ctypes
from ctypes import wintypes

app = QApplication(sys.argv)
load_jarvis_fonts()
app.setStyleSheet(get_global_stylesheet())
app.setQuitOnLastWindowClosed(False)

cfg = ConfigManager()
pet = DesktopPetWindow(cfg)
pet.show_pet()

chat = ModernChatWindow(cfg)
chat.position_near_pet(pet.frameGeometry())
chat.show_chat()

def diagnostic_check():
    print("=== SELF-CHECK DIAGNOSTIC ===")
    print("1. Qt Windows:")
    for w in app.allWindows():
        print(f"   Window: {w.title()} | Visible: {w.isVisible()} | Geometry: {w.geometry().getRect()} | WinID: {w.winId()}")
    
    print("\n2. Pet Widget:")
    print(f"   Visible: {pet.isVisible()} | Pos: {pet.pos().x()},{pet.pos().y()} | Size: {pet.size().width()}x{pet.size().height()}")
    print(f"   WindowFlags: {pet.windowFlags()}")
    
    print("\n3. Chat Widget:")
    print(f"   Visible: {chat.isVisible()} | Pos: {chat.pos().x()},{chat.pos().y()} | Size: {chat.size().width()}x{chat.size().height()}")
    print(f"   WindowFlags: {chat.windowFlags()}")

    print("\n4. Screens:")
    for s in app.screens():
        print(f"   Screen {s.name()}: {s.geometry().getRect()} (Avail: {s.availableGeometry().getRect()})")

    # Save grabs
    os.makedirs("scratch", exist_ok=True)
    pet.grab().save("scratch/self_pet.png")
    chat.grab().save("scratch/self_chat.png")
    print("\nGrabs saved to scratch/self_pet.png and scratch/self_chat.png")
    
    app.quit()

QTimer.singleShot(2000, diagnostic_check)
app.exec()
