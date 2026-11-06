import os
import sys
import ctypes
from pathlib import Path
import tempfile
import subprocess
import shutil
from PIL import Image

project_dir = Path(__file__).resolve().parent.parent

# 1. REVERT APP ICONS BACK TO ORIGINAL
print("--- 1. Reverting App Icons Back to Original ---")
buddy_avatar = project_dir / "assets" / "icons" / "buddy_avatar.png"
app_icon_png = project_dir / "assets" / "icons" / "app_icon.png"
app_icon_ico = project_dir / "assets" / "icons" / "app_icon.ico"
public_app_icon = project_dir / "public" / "assets" / "icons" / "app_icon.png"

# Revert app_icon.png from git
subprocess.run(["git", "checkout", "assets/icons/app_icon.png"], cwd=str(project_dir))

# Restore app_icon.ico from buddy_avatar.png (original companion)
if buddy_avatar.exists():
    orig_img = Image.open(buddy_avatar).convert("RGBA")
    orig_img.save(app_icon_ico, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"[+] Reverted app_icon.ico from buddy_avatar ({app_icon_ico.stat().st_size} bytes)")
    if public_app_icon.parent.exists():
        shutil.copyfile(app_icon_png, public_app_icon)
        print(f"[+] Reverted public/assets/icons/app_icon.png")

# 2. CREATE DESKTOP SHORTCUT CYBER PET ICON
print("\n--- 2. Creating Cyber Pet Desktop Shortcut Icon ---")
cyber_pet_src = Path(r"C:\Users\Gaurav Patel\.gemini\antigravity\brain\09bdeb56-bc59-4426-9163-d3d27b805827\.user_uploaded\media_1793726654244_28d2d1c4.jpg")
pet_img = Image.open(cyber_pet_src).convert("RGBA")

# Save in project
project_cyber_ico = project_dir / "assets" / "icons" / "cyber_pet_desktop.ico"
pet_img.save(project_cyber_ico, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(f"[+] Saved project icon: {project_cyber_ico} ({project_cyber_ico.stat().st_size} bytes)")

# Also save in local app data directory (C: drive) so Windows never has drive/path issues
appdata_dir = Path.home() / "AppData" / "Local" / "AIDesktopFriend"
appdata_dir.mkdir(parents=True, exist_ok=True)
local_cyber_ico = appdata_dir / "cyber_pet_desktop.ico"
shutil.copyfile(project_cyber_ico, local_cyber_ico)
print(f"[+] Saved local appdata icon: {local_cyber_ico} ({local_cyber_ico.stat().st_size} bytes)")

# 3. UPDATE DESKTOP SHORTCUT(S)
print("\n--- 3. Updating Desktop Shortcut ---")
python_exe = project_dir / ".venv" / "Scripts" / "python.exe"
run_desktop = project_dir / "run_desktop.py"
cmd_exe = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")

desktop_dirs = [
    Path.home() / "OneDrive" / "Desktop",
    Path.home() / "Desktop",
    Path("C:/Users/Gaurav Patel/OneDrive/Desktop"),
    Path("C:/Users/Gaurav Patel/Desktop"),
]

unique_desktops = []
for d in desktop_dirs:
    if d.exists() and d not in unique_desktops:
        unique_desktops.append(d)

for d in unique_desktops:
    shortcut_file = d / "AI Desktop Friend.lnk"
    
    # Delete existing shortcut first to clear Windows Explorer cache of this specific .lnk
    if shortcut_file.exists():
        try:
            shortcut_file.unlink()
            print(f"[+] Removed existing {shortcut_file} to bust icon cache")
        except Exception as e:
            print(f"[-] Could not delete {shortcut_file}: {e}")

    # Recreate shortcut with local_cyber_ico
    vbs_script = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'Set oShortcut = WshShell.CreateShortcut("{shortcut_file}")\n'
        f'oShortcut.TargetPath = "{cmd_exe}"\n'
        f'oShortcut.Arguments = "/c " & Chr(34) & "title AI Desktop Friend & " & Chr(34) & "{python_exe}" & Chr(34) & " " & Chr(34) & "{run_desktop}" & Chr(34) & " --keep-terminal" & Chr(34)\n'
        f'oShortcut.WorkingDirectory = "{project_dir}"\n'
        f'oShortcut.IconLocation = "{local_cyber_ico},0"\n'
        'oShortcut.Description = "AI Desktop Friend Companion (Interactive Terminal)"\n'
        'oShortcut.WindowStyle = 1\n'
        'oShortcut.Save\n'
    )

    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False) as tf:
        tf.write(vbs_script)
        vbs_path = tf.name

    try:
        res = subprocess.run(["cscript", "//nologo", vbs_path], capture_output=True, text=True)
        if shortcut_file.exists():
            print(f"[+] Recreated shortcut with Cyber Pet icon at: {shortcut_file}")
            print(f"    IconLocation: {local_cyber_ico},0")
    finally:
        if os.path.exists(vbs_path):
            os.remove(vbs_path)

# 4. Refresh Windows Shell and Icon Cache
print("\n--- 4. Refreshing Windows Shell Icon Cache ---")
try:
    # SHCNE_ASSOCCHANGED = 0x08000000, SHCNF_IDLIST = 0x0000
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    print("[+] Invoked SHChangeNotify(SHCNE_ASSOCCHANGED)")
except Exception as e:
    print(f"[-] SHChangeNotify error: {e}")

# Also touch and notify for the specific desktop item
for d in unique_desktops:
    shortcut_file = d / "AI Desktop Friend.lnk"
    if shortcut_file.exists():
        try:
            # SHCNE_UPDATEITEM = 0x00002000, SHCNF_PATHW = 0x0005
            ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(shortcut_file), None)
            print(f"[+] Invoked SHChangeNotify(SHCNE_UPDATEITEM) for {shortcut_file.name}")
        except Exception:
            pass

print("\nAll completed successfully!")
