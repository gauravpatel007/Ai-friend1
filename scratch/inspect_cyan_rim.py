import numpy as np
from PIL import Image

img_path = "C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793726654244_28d2d1c4.jpg"
im = Image.open(img_path)
arr = np.array(im)

# Cyan border: high B and G, low R, e.g., B > 120 and G > 80 and B > R + 40
cyan_mask = (arr[:, :, 2] > 100) & (arr[:, :, 1] > 60) & (arr[:, :, 2] > arr[:, :, 0] + 30)
# Exclude the face (face is around center x: 300 to 700, y: 300 to 700)
# Look at the outer perimeter
y_indices, x_indices = np.where(cyan_mask)
print(f"Cyan pixels bounding box: X=[{x_indices.min()}, {x_indices.max()}], Y=[{y_indices.min()}, {y_indices.max()}]")

# Let's inspect along center horizontal and vertical lines where the outer cyan rim is:
print("Center Y=512 cyan cols:", np.where(cyan_mask[512])[0])
print("Center X=512 cyan rows:", np.where(cyan_mask[:, 512])[0])
