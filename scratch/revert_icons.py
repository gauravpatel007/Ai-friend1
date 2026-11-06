import shutil
import os
import sys
from pathlib import Path

# 1. Restore app_icon.png from git
os.system("git checkout assets/icons/app_icon.png")

# 2. Restore app_icon.ico from scratch/test_ico_standing.ico
if os.path.exists("scratch/test_ico_standing.ico"):
    shutil.copyfile("scratch/test_ico_standing.ico", "assets/icons/app_icon.ico")
    print("Copied test_ico_standing.ico to assets/icons/app_icon.ico")

# 3. Restore cyber_pet_squircle.ico, cyber_pet_desktop.ico, shortcut_cyber_pet.ico from scratch/gold_standard_test.ico
if os.path.exists("scratch/gold_standard_test.ico"):
    shutil.copyfile("scratch/gold_standard_test.ico", "assets/icons/cyber_pet_squircle.ico")
    shutil.copyfile("scratch/gold_standard_test.ico", "assets/icons/cyber_pet_desktop.ico")
    shutil.copyfile("scratch/gold_standard_test.ico", "assets/icons/shortcut_cyber_pet.ico")
    print("Restored gold standard ICOs")

# 4. Restore cyber_pet_squircle.png from scratch/test_cropped_squircle.png
if os.path.exists("scratch/test_cropped_squircle.png"):
    shutil.copyfile("scratch/test_cropped_squircle.png", "assets/icons/cyber_pet_squircle.png")
    shutil.copyfile("scratch/test_cropped_squircle.png", "assets/icons/shortcut_cyber_pet.png")
    print("Restored PNG icons")

# 5. Remove scripts/apply_buddy_avatar_icon.py if it exists
if os.path.exists("scripts/apply_buddy_avatar_icon.py"):
    os.remove("scripts/apply_buddy_avatar_icon.py")
    print("Removed apply_buddy_avatar_icon.py")

# 6. Update desktop shortcut
desktop_shortcut = Path(r"C:\Users\Gaurav Patel\OneDrive\Desktop\AI Desktop Friend.lnk")
if desktop_shortcut.exists():
    os.system("python packaging/create_shortcut.py")
    print("Updated desktop shortcut")

# 7. Notify Windows Shell of icon change
if sys.platform == "win32":
    import ctypes
    SHCNE_ASSOCCHANGED = 0x08000000
    SHCNF_IDLIST = 0x0000
    ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    print("Notified Windows Shell")

print("Finished revert successfully!")

