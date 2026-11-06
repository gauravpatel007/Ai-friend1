"""End-to-End Chat and Voice Command Diagnostic Test."""
import sys
import os
import time
import threading
import json
import urllib.request

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
project_root = r"g:\Languages\Projects\AI Friend\AI Friend A1"
os.chdir(project_root)
sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.settings.config_manager import ConfigManager
from app.core.controller import ApplicationController

cm = ConfigManager()
ctrl = ApplicationController(app=app, config_manager=cm)
ok = ctrl.initialize()
print(f"Controller initialized: {ok}")

client_results = {}

def client_worker():
    time.sleep(2.5)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        # 1. Health check
        with opener.open("http://127.0.0.1:8765/api/health", timeout=2.0) as resp:
            health = json.loads(resp.read().decode())
        print("Health OK:", health)
        client_results["health"] = health

        # 2. Create conversation
        req = urllib.request.Request(
            "http://127.0.0.1:8765/api/conversations",
            data=json.dumps({"title": "E2E Test Chat"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(req, timeout=2.0) as resp:
            conv = json.loads(resp.read().decode())
        conv_id = conv["id"]
        print(f"Created conversation: {conv_id}")
        client_results["conv_id"] = conv_id

        # 3. Send message
        msg_req = urllib.request.Request(
            f"http://127.0.0.1:8765/api/conversations/{conv_id}/messages",
            data=json.dumps({"content": "Hello there, are you working?"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(msg_req, timeout=3.0) as resp:
            send_res = json.loads(resp.read().decode())
        print("Send response:", send_res)
        client_results["send_res"] = send_res

        # 4. Wait a bit for inference worker
        time.sleep(2.0)

        # 5. Fetch messages
        with opener.open(f"http://127.0.0.1:8765/api/conversations/{conv_id}/messages", timeout=2.0) as resp:
            msgs = json.loads(resp.read().decode())
        print(f"Fetched {len(msgs)} messages:")
        for m in msgs:
            print(f"  [{m['role']}] ({m['status']}): {m['content'][:60]}")
        client_results["messages"] = msgs

    except Exception as e:
        print(f"CLIENT ERROR: {e}")
        import traceback
        traceback.print_exc()
        client_results["error"] = str(e)

threading.Thread(target=client_worker, daemon=True).start()

from PySide6.QtCore import QTimer
QTimer.singleShot(9000, lambda: (ctrl.shutdown(), app.quit()))
app.exec()
print("FINAL RESULTS:", json.dumps(client_results, indent=2, default=str))
