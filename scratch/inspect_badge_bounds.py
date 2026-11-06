import numpy as np
from PIL import Image

img_path = "C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793726654244_28d2d1c4.jpg"
im = Image.open(img_path)
arr = np.array(im)

# Let's inspect the edges
# The background color is approximately [33, 36, 43]
# Let's check brightness or distance from bg along multiple rays or slices
bg_color = np.array([33.0, 36.0, 43.0])
dist = np.linalg.norm(arr.astype(float) - bg_color, axis=2)

# Where dist > 20 is the foreground badge
fg = dist > 20
y_indices, x_indices = np.where(fg)

print("Bounding box of badge:")
print(f"X min: {x_indices.min()}, X max: {x_indices.max()}, Width: {x_indices.max() - x_indices.min() + 1}")
print(f"Y min: {y_indices.min()}, Y max: {y_indices.max()}, Height: {y_indices.max() - y_indices.min() + 1}")

# Let's check the center of the bounding box
center_x = (x_indices.min() + x_indices.max()) / 2
center_y = (y_indices.min() + y_indices.max()) / 2
print(f"Badge center: ({center_x:.1f}, {center_y:.1f})")

# Let's check pixel values around the outer boundary
print("Top edge around center:", arr[y_indices.min():y_indices.min()+10, 512])
print("Bottom edge around center:", arr[y_indices.max()-10:y_indices.max(), 512])
print("Left edge around center:", arr[512, x_indices.min():x_indices.min()+10])
print("Right edge around center:", arr[512, x_indices.max()-10:x_indices.max()])
