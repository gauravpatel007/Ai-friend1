"""Packaging and Inno Setup configuration verification tests (Phase 12.6 & 12.9)."""

from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = PROJECT_ROOT / "packaging"


def test_pyinstaller_spec_integrity():
    """Verify ai_desktop_friend.spec exists, contains correct entry points and assets."""
    spec_path = PACKAGING_DIR / "ai_desktop_friend.spec"
    assert spec_path.exists(), "ai_desktop_friend.spec is missing"

    content = spec_path.read_text(encoding="utf-8")
    assert "main.py" in content
    assert "assets" in content
    assert "config" in content
    assert "PySide6" in content
    assert "AI Desktop Friend" in content
    assert "console=False" in content  # Windowed application


def test_inno_setup_script_integrity():
    """Verify installer.iss exists and contains proper Inno Setup 6 configurations."""
    iss_path = PACKAGING_DIR / "installer.iss"
    assert iss_path.exists(), "installer.iss is missing"

    content = iss_path.read_text(encoding="utf-8")
    assert 'MyAppName "AI Desktop Friend"' in content
    assert "OutputBaseFilename=AI-Desktop-Friend-Setup" in content
    assert "{autopf}\\{#MyAppName}" in content
    assert "{autoprograms}\\{#MyAppName}" in content
    assert "{autodesktop}\\{#MyAppName}" in content
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in content
    assert "SetupIconFile=" in content


def test_application_ico_icon_exists():
    """Verify app_icon.ico is present for Windows executables and shortcuts."""
    icon_path = PROJECT_ROOT / "assets" / "icons" / "app_icon.ico"
    assert icon_path.exists(), "app_icon.ico is missing"
    assert icon_path.stat().st_size > 0


def test_build_scripts_callable():
    """Verify packaging automation scripts are present and valid Python code."""
    build_exe = PACKAGING_DIR / "build_exe.py"
    build_installer = PACKAGING_DIR / "build_installer.py"

    assert build_exe.exists()
    assert build_installer.exists()

    compile(build_exe.read_text(encoding="utf-8"), str(build_exe), "exec")
    compile(build_installer.read_text(encoding="utf-8"), str(build_installer), "exec")
