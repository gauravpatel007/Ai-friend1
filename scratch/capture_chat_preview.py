import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.settings.config_manager import ConfigManager
from app.desktop.chat_window import FloatingChatWindow

def capture_preview():
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = ConfigManager()
    
    # 1. Capture empty welcome state
    win = FloatingChatWindow(config_manager=cfg)
    win.resize(680, 520)
    win.show()
    app.processEvents()
    
    out_welcome = Path("BIN/preview_chat_welcome.png")
    out_welcome.parent.mkdir(parents=True, exist_ok=True)
    win.grab().save(str(out_welcome))
    print(f"Saved welcome preview to {out_welcome}")
    
    # 2. Add sample messages matching Section 4 showcase
    win._add_bubble_to_view(
        role="assistant",
        content="Hello! I'm Buddy, your AI desktop companion. How can I assist you today?",
        timestamp="04:05 PM",
        status="completed"
    )
    win._add_bubble_to_view(
        role="user",
        content="Can you help me write a Python script?",
        timestamp="04:05 PM",
        status="completed"
    )
    win._add_bubble_to_view(
        role="assistant",
        content="Certainly! I'd be happy to help. What kind of Python script are you looking to create?",
        timestamp="04:06 PM",
        status="completed"
    )
    app.processEvents()
    
    out_populated = Path("BIN/preview_chat_populated.png")
    win.grab().save(str(out_populated))
    print(f"Saved populated preview to {out_populated}")
    
    win.close()

if __name__ == "__main__":
    capture_preview()
