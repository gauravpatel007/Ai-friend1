import os
import sys
import io
import struct
import shutil
import tempfile
import subprocess
import ctypes
from ctypes import wintypes
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

def create_gold_standard_ico(pil_rgba: Image.Image, output_path: str):
    sizes = [16, 32, 48, 64, 128, 256]
    entries = []

    for size in sizes:
        resized = pil_rgba.resize((size, size), Image.Resampling.LANCZOS)
        if size == 256:
            png_io = io.BytesIO()
            resized.save(png_io, format="PNG")
            blob = png_io.getvalue()
            bWidth = 0
            bHeight = 0
            wPlanes = 1
            wBitCount = 32
        else:
            w = size
            h = size
            arr = np.array(resized)
            bgra = np.zeros_like(arr)
            bgra[:, :, 0] = arr[:, :, 2] # B
            bgra[:, :, 1] = arr[:, :, 1] # G
            bgra[:, :, 2] = arr[:, :, 0] # R
            bgra[:, :, 3] = arr[:, :, 3] # A
            bgra_flipped = np.flipud(bgra)
            xor_bytes = bgra_flipped.tobytes()

            row_bytes_and = (w + 31) // 32 * 4
            and_mask = b"\x00" * (row_bytes_and * h)

            biSize = 40
            biWidth = w
            biHeight = h * 2
            biPlanes = 1
            biBitCount = 32
            biCompression = 0
            biSizeImage = len(xor_bytes) + len(and_mask)
            biXPelsPerMeter = 0
            biYPelsPerMeter = 0
            biClrUsed = 0
            biClrImportant = 0

            header = struct.pack(
                "<IIIHHIIIIII",
                biSize, biWidth, biHeight, biPlanes, biBitCount,
                biCompression, biSizeImage, biXPelsPerMeter, biYPelsPerMeter,
                biClrUsed, biClrImportant
            )
            blob = header + xor_bytes + and_mask
            bWidth = w
            bHeight = h
            wPlanes = 1
            wBitCount = 32

        entries.append({
            "bWidth": bWidth,
            "bHeight": bHeight,
            "bColorCount": 0,
            "bReserved": 0,
            "wPlanes": wPlanes,
            "wBitCount": wBitCount,
            "dwBytesInRes": len(blob),
            "blob": blob
        })

    current_offset = 6 + len(entries) * 16
    for entry in entries:
        entry["dwImageOffset"] = current_offset
        current_offset += entry["dwBytesInRes"]

    header = struct.pack("<HHH", 0, 1, len(entries))
    dir_entries = b""
    for entry in entries:
        dir_entries += struct.pack(
            "<BBBBHHII",
            entry["bWidth"], entry["bHeight"], entry["bColorCount"], entry["bReserved"],
            entry["wPlanes"], entry["wBitCount"], entry["dwBytesInRes"], entry["dwImageOffset"]
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(dir_entries)
        for entry in entries:
            f.write(entry["blob"])
    print(f"Saved Windows ICO: {output_path} ({os.path.getsize(output_path)} bytes)")


def main():
    workspace = Path("g:/Languages/Projects/AI Friend/AI Friend A1")
    src_jpg = Path(r"C:\Users\Gaurav Patel\.gemini\antigravity\brain\09bdeb56-bc59-4426-9163-d3d27b805827\.user_uploaded\media_1793726654244_28d2d1c4.jpg")

    if not src_jpg.exists():
        print(f"Error: {src_jpg} does not exist!")
        return 1

    print(f"Loading source Cyber Pet image: {src_jpg}")
    im = Image.open(src_jpg).convert("RGBA")

    # Crop tightly to badge with symmetric 10px margin: [158, 158, 864, 864] (706x706)
    crop_box = (158, 158, 864, 864)
    cropped = im.crop(crop_box)
    w, h = cropped.size

    # Create 4x supersampled mask for ultra-smooth anti-aliased curved angles (squircle)
    scale = 4
    mask = Image.new("L", (w * scale, h * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [10 * scale, 10 * scale, 696 * scale, 696 * scale],
        radius=175 * scale,
        fill=255
    )
    mask = mask.resize((w, h), Image.Resampling.LANCZOS)
    cropped.putalpha(mask)

    # Destination paths
    assets_dir = workspace / "assets" / "icons"
    appdata_dir = Path(r"C:\Users\Gaurav Patel\AppData\Local\AIDesktopFriend")
    appdata_dir.mkdir(parents=True, exist_ok=True)

    squircle_png_paths = [
        assets_dir / "cyber_pet_squircle.png",
        assets_dir / "shortcut_cyber_pet.png",
        appdata_dir / "cyber_pet_squircle.png",
        Path(r"C:\Users\Gaurav Patel\.gemini\antigravity\brain\09bdeb56-bc59-4426-9163-d3d27b805827\cyber_pet_squircle_preview.png")
    ]
    for p in squircle_png_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(p, "PNG")
        print(f"Saved PNG: {p}")

    # Build and save multi-resolution ICOs
    ico_destinations = [
        assets_dir / "cyber_pet_desktop.ico",
        assets_dir / "cyber_pet_squircle.ico",
        assets_dir / "shortcut_cyber_pet.ico",
        appdata_dir / "cyber_pet_desktop.ico",
        appdata_dir / "cyber_pet_squircle.ico",
    ]
    for ico_path in ico_destinations:
        create_gold_standard_ico(cropped, str(ico_path))

    # Update Desktop Shortcut
    desktop_dir = Path(r"C:\Users\Gaurav Patel\OneDrive\Desktop")
    shortcut_path = desktop_dir / "AI Desktop Friend.lnk"

    target_cmd = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    python_exe = workspace / ".venv" / "Scripts" / "python.exe"
    run_desktop = workspace / "run_desktop.py"
    target_ico = appdata_dir / "cyber_pet_squircle.ico"

    # Remove existing shortcut so Windows Explorer completely invalidates old cache
    if shortcut_path.exists():
        try:
            shortcut_path.unlink()
            print(f"Removed old shortcut to bust cache: {shortcut_path}")
        except Exception as e:
            print(f"Warning removing old shortcut: {e}")

    # Create new shortcut with VBScript
    vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'Set oShortcut = WshShell.CreateShortcut("{shortcut_path}")\n'
        f'oShortcut.TargetPath = "{target_cmd}"\n'
        f'oShortcut.Arguments = "/c " & Chr(34) & "title AI Desktop Friend & " & Chr(34) & "{python_exe}" & Chr(34) & " " & Chr(34) & "{run_desktop}" & Chr(34) & " --keep-terminal" & Chr(34)\n'
        f'oShortcut.WorkingDirectory = "{workspace}"\n'
        f'oShortcut.IconLocation = "{target_ico},0"\n'
        'oShortcut.Description = "AI Desktop Friend Companion (Interactive Terminal)"\n'
        'oShortcut.WindowStyle = 1\n'
        'oShortcut.Save\n'
    )
    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False) as tf:
        tf.write(vbs)
        vbs_path = tf.name

    try:
        subprocess.run(["cscript", "//nologo", vbs_path], check=True)
        print(f"Successfully re-created desktop shortcut: {shortcut_path}")
    finally:
        if os.path.exists(vbs_path):
            os.remove(vbs_path)

    # Notify Windows Shell
    print("Flushing Windows Explorer Shell Icon Cache...")
    # SHCNE_ASSOCCHANGED = 0x08000000, SHCNF_IDLIST = 0
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    # SHCNE_UPDATEITEM = 0x00002000, SHCNF_PATHW = 0x0005
    ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(shortcut_path), None)

    # ie4uinit.exe -show
    try:
        subprocess.run(["ie4uinit.exe", "-show"], timeout=5)
        print("Invoked ie4uinit.exe -show successfully")
    except Exception as e:
        print(f"ie4uinit note: {e}")

    print("\n--- ALL TASKS COMPLETED SUCCESSFULLY ---")

if __name__ == "__main__":
    sys.exit(main())
