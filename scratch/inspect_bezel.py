import numpy as np
from PIL import Image

img_path = "C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793726654244_28d2d1c4.jpg"
im = Image.open(img_path)
arr = np.array(im)

print("Y=512, X from 150 to 215:")
for x in range(150, 215, 5):
    print(f"X={x:3d}: {arr[512, x]}")

print("\nY=512, X from 810 to 875:")
for x in range(810, 875, 5):
    print(f"X={x:3d}: {arr[512, x]}")

print("\nX=512, Y from 140 to 205:")
for y in range(140, 205, 5):
    print(f"Y={y:3d}: {arr[y, 512]}")

print("\nX=512, Y from 810 to 875:")
for y in range(810, 875, 5):
    print(f"Y={y:3d}: {arr[y, 512]}")
