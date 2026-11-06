import numpy as np
from PIL import Image, ImageDraw, ImageFilter

img_path = "C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793726654244_28d2d1c4.jpg"
im = Image.open(img_path).convert("RGBA")
arr = np.array(im)

# Let's crop the badge:
# The badge is roughly from (168, 168) to (856, 856), size ~ 688x688
# Let's test cropping box [160, 160, 864, 864] (size 704x704)
# Or let's see where the squircle's actual boundary is.

# Let's check the pixel values across diagonals from corners to center:
# Top-left corner (0,0) to center (512, 512):
for i in range(150, 260, 5):
    # diagonal (i, i)
    p = arr[i, i]
    print(f"Diag ({i},{i}): {p[:3]}")
