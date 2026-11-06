"""AI Desktop Friend — Desktop Application Launcher.

Launches the complete AI Desktop Friend ecosystem:
- Floating Animated Desktop Pet character (DesktopPetWindow)
- Live JARVIS Telemetry Status HUD
- Modern Frameless React 19 Chat Interface (zero white borders)
- FastAPI + WebSocket Local AI inference & Voice daemon
"""

import os
import subprocess
import sys

if sys.stdout is None:
    import io
    sys.stdout = io.StringIO()
if sys.stderr is None:
    import io
    sys.stderr = io.StringIO()

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 1. Virtual Environment Auto-Detection & Self-Correction
# Ensures running `python run_desktop.py` in PowerShell or CMD uses the project venv
project_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(project_dir, ".venv", "Scripts", "python.exe")

if (
    os.path.isfile(venv_python)
    and os.path.normcase(sys.executable) != os.path.normcase(venv_python)
    and "--no-reexec" not in sys.argv
):
    print(f"[*] Switching to virtual environment interpreter: {venv_python}")
    cmd = [venv_python, os.path.abspath(__file__), "--no-reexec"] + sys.argv[1:]
    try:
        res = subprocess.run(cmd)
        os._exit(res.returncode)
    except KeyboardInterrupt:
        os._exit(0)

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("antigravity.bond.aidesktopfriend.v2")
    except Exception:
        pass

import main

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  [AI Desktop Friend] Starting companion...")
    print("  - Desktop Pet: Floating on screen (Always-on-top)")
    print("  - Modern Chat Window: Elevating to foreground")
    print("  - System Tray: AI Friend icon in taskbar tray")
    print("  (Press Ctrl+C in this terminal anytime to exit)")
    print("=" * 60 + "\n")

    # If launched from an interactive terminal (PowerShell / Windows Terminal),
    # minimize the console window so the desktop is clear and Buddy is front-and-center.
    # User can pass --keep-terminal to keep the console visible.
    if (
        "--keep-terminal" not in sys.argv
        and "--no-minimize" not in sys.argv
        and "--test-run" not in sys.argv
    ):
        try:
            from app.utils.window_elevation import minimize_console_window
            minimize_console_window()
        except Exception:
            pass

    # Single-instance enforcement:
    # If already running, main.py brings the existing instance to the foreground and exits.
    # To intentionally start a fresh instance, the user can pass --force explicitly.

    exit_code = main.main()
    sys.stdout.flush()
    sys.stderr.flush()
    if "PYTEST_CURRENT_TEST" in os.environ:
        sys.exit(exit_code)
    os._exit(exit_code)
