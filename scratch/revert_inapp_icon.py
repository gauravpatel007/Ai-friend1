from pathlib import Path
from PIL import Image

workspace = Path("g:/Languages/Projects/AI Friend/AI Friend A1")
app_icon_png = workspace / "assets" / "icons" / "app_icon.png"
app_icon_ico = workspace / "assets" / "icons" / "app_icon.ico"

im = Image.open(app_icon_png)
print(f"Loaded {app_icon_png}: {im.size}, {im.mode}")

# Save as app_icon.ico with multi-resolution frames
sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)]
im.save(app_icon_ico, format="ICO", sizes=sizes)
print(f"Saved {app_icon_ico} ({app_icon_ico.stat().st_size} bytes)")
