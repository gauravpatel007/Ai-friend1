import numpy as np
from PIL import Image, ImageDraw, ImageFilter

img_path = "C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793726654244_28d2d1c4.jpg"
im = Image.open(img_path).convert("RGBA")

# Center: 511, 511
# Squircle bounds: left=168, top=168, right=854, bottom=854 (size 686x686)
# If we crop with a small 10px margin around the squircle:
crop_box = (158, 158, 864, 864) # 706 x 706
cropped = im.crop(crop_box)

# Now in the cropped coordinate system:
# Squircle rect: (10, 10, 696, 696), size 686x686, radius 175
w, h = cropped.size

# High-res anti-aliased mask using 4x supersampling
scale = 4
mask = Image.new("L", (w * scale, h * scale), 0)
draw = ImageDraw.Draw(mask)

# Rounded rectangle on the 4x mask:
# x0 = 10 * scale, y0 = 10 * scale, x1 = 696 * scale, y1 = 696 * scale
# r = 175 * scale
draw.rounded_rectangle(
    [10 * scale, 10 * scale, 696 * scale, 696 * scale],
    radius=175 * scale,
    fill=255
)

# Downsample mask back to (w, h) with Lanczos for perfect anti-aliasing
mask = mask.resize((w, h), Image.Resampling.LANCZOS)

# Apply mask to cropped
cropped.putalpha(mask)
cropped.save("scratch/test_cropped_squircle.png")
print("Saved scratch/test_cropped_squircle.png:", cropped.size)

# Also test on full 1024x1024 without cropping just to compare
mask_full = Image.new("L", (1024 * scale, 1024 * scale), 0)
draw_full = ImageDraw.Draw(mask_full)
draw_full.rounded_rectangle(
    [168 * scale, 168 * scale, 854 * scale, 854 * scale],
    radius=175 * scale,
    fill=255
)
mask_full = mask_full.resize((1024, 1024), Image.Resampling.LANCZOS)
im_full = im.copy()
im_full.putalpha(mask_full)
im_full.save("scratch/test_full_squircle.png")
print("Saved scratch/test_full_squircle.png:", im_full.size)
