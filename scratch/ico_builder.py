import struct
import io
import numpy as np
from PIL import Image

def create_windows_ico(pil_image_rgba: Image.Image, output_path: str):
    """Create a gold-standard Windows ICO with uncompressed DIB frames for standard sizes
    and PNG for 256x256, ensuring 100% compatibility with Windows Explorer shell icon cache.
    """
    sizes = [16, 32, 48, 64, 128, 256]
    entries = []
    image_blobs = []

    for size in sizes:
        resized = pil_image_rgba.resize((size, size), Image.Resampling.LANCZOS)
        
        if size == 256:
            # PNG encoded
            png_io = io.BytesIO()
            resized.save(png_io, format="PNG")
            blob = png_io.getvalue()
            bWidth = 0
            bHeight = 0
            wPlanes = 1
            wBitCount = 32
        else:
            # Standard Windows ICO DIB format
            w = size
            h = size
            # BGRA bottom-to-top
            arr = np.array(resized) # (h, w, 4)
            # convert RGBA to BGRA
            bgra = np.zeros_like(arr)
            bgra[:, :, 0] = arr[:, :, 2] # B
            bgra[:, :, 1] = arr[:, :, 1] # G
            bgra[:, :, 2] = arr[:, :, 0] # R
            bgra[:, :, 3] = arr[:, :, 3] # A
            # Flip vertically (bottom-to-top)
            bgra_flipped = np.flipud(bgra)
            xor_bytes = bgra_flipped.tobytes()

            # AND mask: 1 bit per pixel, row padded to 32 bits (4 bytes)
            row_bytes_and = (w + 31) // 32 * 4
            and_mask = b"\x00" * (row_bytes_and * h)

            biSize = 40
            biWidth = w
            biHeight = h * 2 # doubled for XOR + AND
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

    # Calculate offsets
    # Header is 6 bytes
    # Each directory entry is 16 bytes
    current_offset = 6 + len(entries) * 16
    for entry in entries:
        entry["dwImageOffset"] = current_offset
        current_offset += entry["dwBytesInRes"]

    # Assemble file
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

    print(f"Successfully generated gold-standard Windows ICO: {output_path} ({current_offset} bytes)")

# Test with cropped squircle
im = Image.open("scratch/test_cropped_squircle.png")
create_windows_ico(im, "scratch/gold_standard_test.ico")
