"""Build automation script for PyInstaller Windows standalone executable."""

import os
from pathlib import Path
import subprocess
import sys


def build_executable() -> int:
    project_root = Path(__file__).resolve().parent.parent
    packaging_dir = project_root / "packaging"
    spec_file = packaging_dir / "ai_desktop_friend.spec"
    icon_png = project_root / "assets" / "icons" / "app_icon.png"
    icon_ico = project_root / "assets" / "icons" / "app_icon.ico"

    print("==================================================")
    print("  AI Desktop Friend — Standalone Executable Builder")
    print("==================================================")

    # 1. Ensure icon.ico exists
    if not icon_ico.exists() and icon_png.exists():
        print(f"Generating {icon_ico.name} from {icon_png.name}...")
        try:
            from PySide6.QtGui import QImage
            img = QImage(str(icon_png))
            img.save(str(icon_ico), "ICO")
            print("✓ Generated app_icon.ico successfully.")
        except Exception as e:
            print(f"Warning: Could not convert icon: {e}")

    # 2. Verify PyInstaller installation
    try:
        import PyInstaller
        print(f"✓ Found PyInstaller version {PyInstaller.__version__}")
    except ImportError:
        print("✗ PyInstaller is not installed in the active environment.")
        print("Run: pip install pyinstaller")
        return 1

    # 3. Execute PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(project_root / "dist"),
        "--workpath",
        str(project_root / "build"),
        str(spec_file),
    ]

    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(project_root))

    if result.returncode == 0:
        dist_app = project_root / "dist" / "AI Desktop Friend"
        print("==================================================")
        print("✓ Standalone build complete!")
        print(f"  Output location: {dist_app}")
        print(f"  Executable: {dist_app / 'AI Desktop Friend.exe'}")
        print("==================================================")
    else:
        print(f"✗ Build failed with exit code {result.returncode}")

    return result.returncode


if __name__ == "__main__":
    sys.exit(build_executable())
