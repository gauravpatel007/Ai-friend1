import numpy as np
from PIL import Image

im = Image.open("scratch/test_cropped_squircle.png")
arr = np.array(im)
w, h = im.size
print(f"Cropped image size: {w} x {h}")

# The mask was:
# rounded_rectangle([10, 10, 696, 696], radius=175)
# Let's check non-zero alpha bounding box:
alphas = arr[:, :, 3]
y_idx, x_idx = np.where(alphas > 0)
print(f"Non-zero alpha bounding box: X=[{x_idx.min()}, {x_idx.max()}], Y=[{y_idx.min()}, {y_idx.max()}]")
print(f"Width = {x_idx.max() - x_idx.min() + 1}, Height = {y_idx.max() - y_idx.min() + 1}")
print(f"Left margin: {x_idx.min()}, Right margin: {w - 1 - x_idx.max()}")
print(f"Top margin: {y_idx.min()}, Bottom margin: {h - 1 - y_idx.max()}")
