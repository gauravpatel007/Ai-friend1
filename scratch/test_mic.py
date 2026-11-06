import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
import numpy as np
from PySide6.QtCore import QCoreApplication
from app.voice.microphone_manager import MicrophoneManager

app = QCoreApplication.instance() or QCoreApplication(sys.argv)

frames = []
def on_frame(chunk):
    frames.append(chunk)

mic = MicrophoneManager()
print("Initialized MicrophoneManager")
ok = mic.start_recording()
print(f"start_recording returned: {ok}")
mic.subscribe(on_frame)

start = time.time()
while time.time() - start < 2.0:
    app.processEvents()
    time.sleep(0.05)

mic.stop_recording()

print(f"Captured {len(frames)} frames")
if frames:
    full = np.concatenate(frames)
    rms = float(np.sqrt(np.mean(np.square(full))))
    print(f"Total samples: {len(full)}, Duration: {len(full)/16000:.2f}s, RMS: {rms:.5f}")
