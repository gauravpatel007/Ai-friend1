import os
import sys
import ctypes
from pathlib import Path
import tempfile
import subprocess
import shutil

project_dir = Path(__file__).resolve().parent.parent
ico_path = (project_dir / "assets" / "icons" / "shortcut_cyber_pet.ico").resolve()
app_ico_path = (project_dir / "assets" / "icons" / "app_icon.ico").resolve()

# Also update app_icon.ico with the cyber pet icon
shutil.copyfile(ico_path, app_ico_path)

print(f"[*] Icon Path: {ico_path}")
print(f"[*] Icon Exists: {ico_path.exists()}")

desktop_paths = [
    Path.home() / "OneDrive" / "Desktop",
    Path.home() / "Desktop",
    Path("C:/Users/Gaurav Patel/OneDrive/Desktop"),
    Path("C:/Users/Gaurav Patel/Desktop"),
]

unique_desktops = []
for d in desktop_paths:
    if d.exists() and d not in unique_desktops:
        unique_desktops.append(d)

updated_shortcuts = []

for dp in unique_desktops:
    for lnk_name in ["AI Desktop Friend.lnk", "AI_Desktop_Friend - Shortcut.lnk", "AI_Desktop_Friend - Shortcut (2).lnk"]:
        lnk_file = dp / lnk_name
        if lnk_file.exists():
            vbs = (
                'Set WshShell = CreateObject("WScript.Shell")\n'
                f'Set oShortcut = WshShell.CreateShortcut("{lnk_file}")\n'
                'WScript.Echo "Target: " & oShortcut.TargetPath\n'
                'WScript.Echo "Old Icon: " & oShortcut.IconLocation\n'
                f'oShortcut.IconLocation = "{ico_path}, 0"\n'
                'oShortcut.Save\n'
                'WScript.Echo "New Icon: " & oShortcut.IconLocation\n'
            )
            with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False) as tf:
                tf.write(vbs)
                vbs_path = tf.name
            try:
                res = subprocess.run(["cscript", "//nologo", vbs_path], capture_output=True, text=True)
                print(f"[+] Updated: {lnk_file}")
                print(res.stdout)
                updated_shortcuts.append(lnk_file)
            finally:
                if os.path.exists(vbs_path):
                    os.remove(vbs_path)

# Also check shortcuts directly in project root
for lnk in project_dir.glob("*.lnk"):
    vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'Set oShortcut = WshShell.CreateShortcut("{lnk.resolve()}")\n'
        f'oShortcut.IconLocation = "{ico_path}, 0"\n'
        'oShortcut.Save\n'
    )
    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False) as tf:
        tf.write(vbs)
        vbs_path = tf.name
    try:
        subprocess.run(["cscript", "//nologo", vbs_path], capture_output=True, text=True)
        print(f"[+] Updated project shortcut: {lnk.name}")
    finally:
        if os.path.exists(vbs_path):
            os.remove(vbs_path)

# Re-run packaging/create_shortcut.py via subprocess to ensure clean execution
print("\n[*] Running packaging/create_shortcut.py:")
subprocess.run([sys.executable, str(project_dir / "packaging" / "create_shortcut.py")])

# Notify Windows Explorer Shell to refresh icon cache
try:
    # SHCNE_ASSOCCHANGED = 0x08000000 (SHCNE_ASSOCCHANGED tells Windows that file associations and icons changed)
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    print("\n[+] Successfully notified Windows Shell (SHChangeNotify) to refresh desktop icon cache.")
except Exception as e:
    print(f"[-] SHChangeNotify error: {e}")
