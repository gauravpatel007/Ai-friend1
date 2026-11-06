import numpy as np
from PIL import Image

img_path = "C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793726654244_28d2d1c4.jpg"
im = Image.open(img_path)
arr = np.array(im)

print("Image shape:", arr.shape)
print("Corner (0,0) RGB:", arr[0, 0])
print("Corner (0, 1023) RGB:", arr[0, 1023])
print("Corner (1023, 0) RGB:", arr[1023, 0])
print("Corner (1023, 1023) RGB:", arr[1023, 1023])

# Find center row and col
center_y = 512
center_x = 512
print("Center RGB:", arr[center_y, center_x])

# Trace horizontally along center_y from left to right
row = arr[center_y]
# Let's inspect where the dark background transitions to the badge border
diff_from_bg = np.linalg.norm(arr.astype(float) - arr[10, 10].astype(float), axis=2)

# Along center row:
row_diff = diff_from_bg[center_y]
badge_cols = np.where(row_diff > 30)[0]
print("Badge cols at center y:", badge_cols[0], "to", badge_cols[-1])

# Along center col:
col_diff = diff_from_bg[:, center_x]
badge_rows = np.where(col_diff > 30)[0]
print("Badge rows at center x:", badge_rows[0], "to", badge_rows[-1])
