from PySide6.QtGui import QImage

img = QImage(r"C:\Users\Gaurav Patel\.gemini\antigravity\brain\b09d8994-baae-4b62-8eb8-dd78b29c0561\.user_uploaded\media_1792583973015_121ec1d8.png")

# Let's crop right side where the terminal and text are
term = img.copy(img.width() // 2, 0, img.width() // 2, img.height() - 80)
term.save("scratch/user_term.png", "PNG")
print("Saved scratch/user_term.png")

# Also let's crop the whole window to understand the layout
full_thumb = img.scaled(800, 450)
full_thumb.save("scratch/user_full_thumb.png", "PNG")
print("Saved scratch/user_full_thumb.png")
