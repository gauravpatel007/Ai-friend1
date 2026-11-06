import sys
import os
sys.path.insert(0, os.path.abspath("."))
from app.voice.vad_engine import VADEngine
import numpy as np

vad = VADEngine()
print("VAD backend:", vad._backend_type)
dummy_silence = np.zeros(512, dtype=np.float32)
print("Silence prob:", vad.get_speech_probability(dummy_silence))

# Create a synthetic 300Hz tone with speech-like amplitude 0.02
t = np.linspace(0, 512/16000, 512, endpoint=False)
speech_frame = (0.02 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
print("Speech prob:", vad.get_speech_probability(speech_frame))
