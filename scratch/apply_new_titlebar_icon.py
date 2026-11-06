import os
import io
import struct
import shutil
import numpy as np
from PIL import Image

def create_windows_ico(pil_rgba: Image.Image, output_path: str):
    sizes = [16, 24, 32, 48, 64, 128, 256]
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

    with open(output_path, "wb") as f:
        f.write(header)
        f.write(dir_entries)
        for entry in entries:
            f.write(entry["blob"])
    print(f"Saved Windows ICO: {output_path} ({os.path.getsize(output_path)} bytes)")


src_path = r"C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793778784438_c5f55368.png"
im = Image.open(src_path).convert("RGBA")

# Crop tight with 4% padding
arr = np.array(im)
alphas = arr[:, :, 3]
y_idx, x_idx = np.where(alphas > 0)
bbox = (int(x_idx.min()), int(y_idx.min()), int(x_idx.max() + 1), int(y_idx.max() + 1))
bw = bbox[2] - bbox[0]
bh = bbox[3] - bbox[1]
size = max(bw, bh)
margin = int(size * 0.04)
square_size = size + margin * 2

square_im = Image.new("RGBA", (square_size, square_size), (0, 0, 0, 0))
crop = im.crop(bbox)
offset_x = (square_size - bw) // 2
offset_y = (square_size - bh) // 2
square_im.paste(crop, (offset_x, offset_y), crop)

# Save as assets/icons/app_icon.png (high-res 1024x1024)
output_png = "assets/icons/app_icon.png"
square_im.resize((1024, 1024), Image.Resampling.LANCZOS).save(output_png, "PNG")
print(f"Saved PNG: {output_png} ({os.path.getsize(output_png)} bytes)")

# Also save to public/assets/icons/app_icon.png
public_png = "public/assets/icons/app_icon.png"
square_im.resize((1024, 1024), Image.Resampling.LANCZOS).save(public_png, "PNG")
print(f"Saved Public PNG: {public_png} ({os.path.getsize(public_png)} bytes)")

# Save as assets/icons/app_icon.ico
output_ico = "assets/icons/app_icon.ico"
create_windows_ico(square_im, output_ico)

# Copy a preview to the artifact directory
art_preview = r"C:\Users\Gaurav Patel\.gemini\antigravity\brain\09bdeb56-bc59-4426-9163-d3d27b805827\new_titlebar_icon_preview.png"
square_im.resize((512, 512), Image.Resampling.LANCZOS).save(art_preview, "PNG")
print(f"Saved artifact preview: {art_preview}")
