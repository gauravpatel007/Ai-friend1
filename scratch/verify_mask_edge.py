import numpy as np
from PIL import Image

# Check the cropped image
im = Image.open("scratch/test_cropped_squircle.png")
arr = np.array(im)

# Look at points just inside and outside the mask
# Top edge center: x = 353, y should be around 10
print("Top edge around center (x=353, y=5 to 15):")
for y in range(5, 16):
    print(f"y={y:2d}: RGB={arr[y, 353, :3]} Alpha={arr[y, 353, 3]}")

# Corner (x=80, y=80):
print("\nCorner (x=60 to 90, y=60 to 90 diagonal):")
for d in range(60, 95, 5):
    print(f"d={d:2d}: RGB={arr[d, d, :3]} Alpha={arr[d, d, 3]}")
