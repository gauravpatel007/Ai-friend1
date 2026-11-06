import sys
import os
import traceback
sys.path.insert(0, os.path.abspath("."))

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.desktop.modern_chat_window import ModernChatWindow
    from app.settings.config_manager import ConfigManager

    app = QApplication(sys.argv)
    cfg = ConfigManager()
    chat = ModernChatWindow(config_manager=cfg)
    chat.show_chat()
    print("Chat window successfully shown!")
    print("Geometry:", chat.geometry())
    print("IsVisible:", chat.isVisible())
    QTimer.singleShot(1000, app.quit)
    app.exec()
    print("Exited cleanly.")
except Exception as e:
    with open("scratch/chat_err.txt", "w") as f:
        f.write(traceback.format_exc())
    print("Error:", e)
