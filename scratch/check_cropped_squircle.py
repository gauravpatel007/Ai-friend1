import numpy as np
from PIL import Image

im = Image.open("scratch/test_cropped_squircle.png")
arr = np.array(im)

print("Size:", im.size)
print("Corners alpha:")
print(" (0,0):", arr[0, 0, 3])
print(" (0, -1):", arr[0, -1, 3])
print(" (-1, 0):", arr[-1, 0, 3])
print(" (-1, -1):", arr[-1, -1, 3])

# Check center
print("Center (353, 353) RGBA:", arr[353, 353])

# Check alpha gradient across top-left corner
diag_alphas = [arr[i, i, 3] for i in range(50, 75)]
print("Diagonal alphas 50 to 74:", diag_alphas)
