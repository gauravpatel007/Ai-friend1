"""Build automation script for Inno Setup Windows installer (AI-Desktop-Friend-Setup.exe)."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

# Common installation paths for Inno Setup 6
INNO_PATHS = [
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
]


def find_iscc() -> Path | None:
    """Find the Inno Setup Compiler executable."""
    which_path = shutil.which("ISCC") or shutil.which("iscc.exe")
    if which_path:
        return Path(which_path)

    for path in INNO_PATHS:
        if path.exists() and path.is_file():
            return path
    return None


def build_installer() -> int:
    project_root = Path(__file__).resolve().parent.parent
    packaging_dir = project_root / "packaging"
    iss_file = packaging_dir / "installer.iss"
    dist_app = project_root / "dist" / "AI Desktop Friend"

    print("==================================================")
    print("  AI Desktop Friend — Windows Installer Builder")
    print("==================================================")

    # 1. Check if application has been packaged with PyInstaller first
    if not dist_app.exists() or not (dist_app / "AI Desktop Friend.exe").exists():
        print("Notice: Standalone executable bundle not found in dist/AI Desktop Friend.")
        print("Building standalone executable with PyInstaller first...")
        import sys
        sys.path.insert(0, str(packaging_dir))
        from build_exe import build_executable
        ret = build_executable()
        if ret != 0:
            print("✗ Executable compilation failed. Aborting installer build.")
            return ret

    # 2. Locate Inno Setup Compiler
    iscc = find_iscc()
    if not iscc:
        print("✗ Inno Setup Compiler (ISCC.exe) was not found on this machine.")
        print("  To build the final AI-Desktop-Friend-Setup.exe installer:")
        print("  1. Download Inno Setup 6 from: https://jrsoftware.org/isdl.php")
        print("  2. Run the compiler command:")
        print(f'     ISCC.exe "{iss_file}"')
        print("  Or open packaging/installer.iss in the Inno Setup GUI and press F9.")
        return 2

    print(f"✓ Found Inno Setup Compiler at: {iscc}")
    cmd = [str(iscc), str(iss_file)]
    print(f"Executing: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=str(packaging_dir))
    if result.returncode == 0:
        installer_path = project_root / "dist" / "AI-Desktop-Friend-Setup.exe"
        print("==================================================")
        print("✓ Windows Installer successfully generated!")
        print(f"  Installer: {installer_path}")
        print("==================================================")
    else:
        print(f"✗ Inno Setup compilation failed with code {result.returncode}")

    return result.returncode


if __name__ == "__main__":
    sys.exit(build_installer())
