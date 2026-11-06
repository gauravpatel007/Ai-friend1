# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for AI Desktop Friend.

Builds a standalone, windowed Windows distribution including:
- PySide6 runtime and Qt platform/style/multimedia plugins
- Embedded character assets, icons, and fonts
- Default JSON configurations
- Faster-Whisper, Kokoro, Piper, and Ollama client integration
"""

import os
from pathlib import Path
import PySide6

block_cipher = None

# Root paths
spec_root = Path(SPECPATH).resolve()
project_root = spec_root.parent if spec_root.name == "packaging" else spec_root

pyside6_dir = Path(PySide6.__file__).parent
plugins_dir = pyside6_dir / "plugins"

# Assets and configurations to bundle
datas = [
    (str(project_root / "assets"), "assets"),
    (str(project_root / "config"), "config"),
]

# Additional PySide6 Qt plugins
binaries = []
for plugin_folder in ["platforms", "styles", "tls", "multimedia", "imageformats", "iconengines"]:
    p_path = plugins_dir / plugin_folder
    if p_path.exists():
        binaries.append((str(p_path), f"PySide6/plugins/{plugin_folder}"))

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtMultimedia",
    "sqlite3",
    "sounddevice",
    "numpy",
    "psutil",
    "platformdirs",
    "app.core.controller",
    "app.core.signals",
    "app.core.single_instance",
    "app.core.performance_monitor",
    "app.core.performance_profiles",
    "app.core.windows_integration",
    "app.core.error_recovery",
    "app.core.ollama_installer",
    "app.core.startup_manager",
    "app.desktop.setup_wizard",
    "app.desktop.pet_window",
    "app.desktop.chat_window",
    "app.desktop.settings_dialog",
    "app.desktop.tray_icon",
    "app.desktop.status_hud",
    "app.desktop.speech_bubble",
    "app.desktop.jarvis_theme",
    "app.ai.ai_service",
    "app.ai.ollama_client",
    "app.ai.model_manager",
    "app.ai.conversation_context",
    "app.ai.personality_manager",
    "app.ai.emotion_classifier",
    "app.voice.voice_service",
    "app.voice.voice_conversation_controller",
    "app.voice.whisper_engine",
    "app.voice.audio_player",
    "app.voice.vad_engine",
    "app.voice.wake_word_engine",
    "app.voice.interruption_manager",
    "app.memory.database",
    "app.memory.conversation_repository",
    "app.memory.memory_manager",
    "app.memory.models",
]

excludes = [
    "matplotlib",
    "tkinter",
    "IPython",
    "jupyter",
    "scipy.spatial.qhull",
]

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_path = str(project_root / "assets" / "icons" / "app_icon.ico")
if not os.path.exists(icon_path):
    icon_path = None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI Desktop Friend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed desktop application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AI Desktop Friend",
)
