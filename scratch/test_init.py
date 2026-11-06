import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from app.settings.config_manager import ConfigManager
from app.core.controller import ApplicationController

app = QApplication.instance() or QApplication([])
cfg = ConfigManager()
c = ApplicationController(app=app, config_manager=cfg)

import traceback
try:
    print("Initializing controller...")
    res = c.initialize()
    print("controller.initialize returned:", res)
except Exception as e:
    traceback.print_exc()
