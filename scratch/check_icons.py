import os
from pathlib import Path
from PIL import Image

workspace = Path("g:/Languages/Projects/AI Friend/AI Friend A1")
assets_icons = workspace / "assets" / "icons"

print("Assets/icons directory contents:")
for f in assets_icons.iterdir():
    size_bytes = f.stat().st_size
    print(f"  {f.name} ({size_bytes} bytes)")

desktop_dir = Path("C:/Users/Gaurav Patel/OneDrive/Desktop")
if desktop_dir.exists():
    print("\nDesktop shortcuts matching AI:")
    for f in desktop_dir.glob("*AI*"):
        print(f"  {f.name} ({f.stat().st_size} bytes)")

cyber_pet_img = Path("C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793726654244_28d2d1c4.jpg")
if cyber_pet_img.exists():
    im = Image.open(cyber_pet_img)
    print(f"\nCyber pet image: {im.size}, {im.mode}, {im.format}")
