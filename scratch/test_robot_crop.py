import numpy as np
from PIL import Image

src_path = r"C:/Users/Gaurav Patel/.gemini/antigravity/brain/09bdeb56-bc59-4426-9163-d3d27b805827/.user_uploaded/media_1793778784438_c5f55368.png"
im = Image.open(src_path).convert("RGBA")

# Let's test cropping tight to the robot vs keeping full canvas:
arr = np.array(im)
alphas = arr[:, :, 3]
y_idx, x_idx = np.where(alphas > 0)
bbox = (x_idx.min(), y_idx.min(), x_idx.max() + 1, y_idx.max() + 1)
print("Tight bbox:", bbox, "w=", bbox[2] - bbox[0], "h=", bbox[3] - bbox[1])

# If we pad tight bbox to a square:
bw = bbox[2] - bbox[0] # 748
bh = bbox[3] - bbox[1] # 882
size = max(bw, bh) # 882
# add 4% margin:
margin = int(size * 0.04) # ~35px
square_size = size + margin * 2

square_im = Image.new("RGBA", (square_size, square_size), (0, 0, 0, 0))
crop = im.crop(bbox)
offset_x = (square_size - bw) // 2
offset_y = (square_size - bh) // 2
square_im.paste(crop, (offset_x, offset_y), crop)

print(f"Created square cropped image: {square_im.size}")
square_im.save("scratch/test_robot_square.png")
