import sounddevice as sd

print("Default device:", sd.default.device)
devices = sd.query_devices()
for i, d in enumerate(devices):
    if d.get("max_input_channels", 0) > 0:
        print(f"Input {i}: {d.get('name')} (channels={d.get('max_input_channels')}, rate={d.get('default_samplerate')}, hostapi={d.get('hostapi')})")
