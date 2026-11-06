"""Create Windows Desktop Shortcut for AI Desktop Friend.

Creates a shortcut on the user's Desktop that:
1. Launches the application in an interactive terminal.
2. Keeps the terminal open and visible with live logs.
3. Completely terminates the project when the terminal is closed or Ctrl+C is pressed.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile


def create_desktop_shortcut():
    project_dir = Path(__file__).resolve().parent.parent
    python_exe = project_dir / ".venv" / "Scripts" / "python.exe"
    run_desktop = project_dir / "run_desktop.py"
    target_cmd = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    appdata_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "AIDesktopFriend"
    appdata_dir.mkdir(parents=True, exist_ok=True)
    appdata_ico = appdata_dir / "cyber_pet_squircle.ico"

    icon_path = project_dir / "assets" / "icons" / "cyber_pet_squircle.ico"
    if not icon_path.exists():
        icon_path = project_dir / "assets" / "icons" / "cyber_pet_desktop.ico"
    if not icon_path.exists():
        icon_path = project_dir / "assets" / "icons" / "app_icon.ico"

    # Ensure local AppData copy exists for reliable Windows Explorer shell rendering
    if icon_path.exists():
        try:
            import shutil
            shutil.copy2(str(icon_path), str(appdata_ico))
        except Exception:
            pass

    shortcut_icon = appdata_ico if appdata_ico.exists() else icon_path

    if not python_exe.exists():
        print(f"[ERROR] Virtual environment python not found at: {python_exe}")
        return 1

    if not run_desktop.exists():
        print(f"[ERROR] run_desktop.py not found at: {run_desktop}")
        return 1

    # Find Desktop paths
    desktop_paths = []

    # 1. Query WScript.Shell SpecialFolders("Desktop")
    query_vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        'WScript.Echo WshShell.SpecialFolders("Desktop")\n'
    )
    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False) as tf:
        tf.write(query_vbs)
        query_vbs_path = tf.name

    try:
        res = subprocess.run(["cscript", "//nologo", query_vbs_path], capture_output=True, text=True)
        out = res.stdout.strip()
        if out and Path(out).exists():
            desktop_paths.append(Path(out))
    except Exception as e:
        print(f"[WARN] Failed to query WScript.Shell: {e}")
    finally:
        if os.path.exists(query_vbs_path):
            os.remove(query_vbs_path)

    # 2. Check standard user profile desktop
    home_desktop = Path.home() / "Desktop"
    if home_desktop.exists() and home_desktop not in desktop_paths:
        desktop_paths.append(home_desktop)

    # 3. Check OneDrive desktop
    onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
    if onedrive_desktop.exists() and onedrive_desktop not in desktop_paths:
        desktop_paths.append(onedrive_desktop)

    if not desktop_paths:
        print("[ERROR] Could not find any Desktop directory.")
        return 1

    bat_launcher = project_dir / "AI_Desktop_Friend.bat"
    created_any = False
    for desk in desktop_paths:
        shortcut_file = desk / "AI Desktop Friend.lnk"

        # Build VBScript targeting cmd.exe so Windows Shell always displays the custom icon
        vbs_script = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'Set oShortcut = WshShell.CreateShortcut("{shortcut_file}")\n'
            f'oShortcut.TargetPath = "{target_cmd}"\n'
            f'oShortcut.Arguments = "/c " & Chr(34) & Chr(34) & "{bat_launcher}" & Chr(34) & Chr(34)\n'
            f'oShortcut.WorkingDirectory = "{project_dir}"\n'
        )

        if shortcut_icon.exists():
            vbs_script += f'oShortcut.IconLocation = "{shortcut_icon},0"\n'

        vbs_script += (
            'oShortcut.Description = "AI Desktop Friend Companion (Interactive Terminal)"\n'
            'oShortcut.WindowStyle = 1\n'  # 1 = Normal window
            'oShortcut.Save\n'
        )

        with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False) as tf:
            tf.write(vbs_script)
            vbs_file = tf.name

        try:
            res = subprocess.run(["cscript", "//nologo", vbs_file], capture_output=True, text=True)
            if res.returncode == 0 and shortcut_file.exists():
                print(f"[SUCCESS] Created shortcut: {shortcut_file}")
                created_any = True
            else:
                print(f"[ERROR] Failed creating shortcut at {shortcut_file}: {res.stderr or res.stdout}")
        except Exception as e:
            print(f"[ERROR] Exception creating shortcut at {shortcut_file}: {e}")
        finally:
            if os.path.exists(vbs_file):
                os.remove(vbs_file)

    if created_any:
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
            subprocess.run(["ie4uinit.exe", "-show"], timeout=5, capture_output=True)
        except Exception:
            pass

        print("\nAll done! The shortcut is now available on your Desktop.")
        # Verify shortcut details
        verify_vbs = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'Set oShortcut = WshShell.CreateShortcut("{shortcut_file}")\n'
            'WScript.Echo "Target: " & oShortcut.TargetPath\n'
            'WScript.Echo "Arguments: " & oShortcut.Arguments\n'
            'WScript.Echo "WorkDir: " & oShortcut.WorkingDirectory\n'
            'WScript.Echo "Icon: " & oShortcut.IconLocation\n'
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False) as tf:
            tf.write(verify_vbs)
            vbs_file = tf.name
        try:
            res = subprocess.run(["cscript", "//nologo", vbs_file], capture_output=True, text=True)
            print("\nShortcut Details:")
            print(res.stdout)
        finally:
            if os.path.exists(vbs_file):
                os.remove(vbs_file)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(create_desktop_shortcut())
