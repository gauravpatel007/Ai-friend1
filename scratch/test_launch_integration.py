import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.controller import ApplicationController
from app.settings.config_manager import ConfigManager
from app.utils.logger import setup_logging, get_logger

def test_launch():
    setup_logging()
    logger = get_logger("test_launch")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    cfg = ConfigManager()
    ctrl = ApplicationController(app=app, config_manager=cfg)
    success = ctrl.initialize()
    print("Initialize success:", success)
    assert success, "Controller initialization failed!"
    
    # Check pet window
    assert ctrl.pet_window is not None, "pet_window is None!"
    print("Pet visible:", ctrl.pet_window.isVisible())
    print("Pet pos:", ctrl.pet_window.pos(), "size:", ctrl.pet_window.size())
    print("Pet always on top flag:", bool(ctrl.pet_window.windowFlags() & ctrl.pet_window.windowFlags().WindowStaysOnTopHint))
    
    # Check speech bubble
    print("Speech bubble visible:", ctrl.pet_window.speech_bubble.isVisible())
    
    # Check chat window
    assert ctrl.chat_window is not None, "chat_window is None!"
    print("Chat window visible:", ctrl.chat_window.isVisible())
    print("Chat window pos:", ctrl.chat_window.pos(), "size:", ctrl.chat_window.size())
    
    # Grab screenshot of desktop area containing pet
    pix = ctrl.pet_window.grab()
    pix.save("scratch/test_pet_live.png")
    print("Saved scratch/test_pet_live.png")
    
    # Clean shutdown
    ctrl.shutdown()
    print("Shutdown completed successfully!")

if __name__ == "__main__":
    test_launch()
