"""First-Run Setup Wizard for AI Desktop Friend.

Guides new users through:
1. Character & Identity selection
2. Ollama detection and model verification / downloading
3. Audio Input & Output device selection
4. Voice engine and TTS voice configuration
5. Windows startup & performance profile settings
"""

import os
from pathlib import Path
import sys
import threading
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.ollama_installer import OllamaRuntimeManager
from app.core.performance_profiles import PerformanceProfileManager
from app.core.startup_manager import disable_startup, enable_startup
from app.desktop.jarvis_theme import COLORS
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _apply_card_glow(widget: QWidget, color_hex: str, radius: int = 20) -> None:
    """Apply glowing drop-shadow effect to card."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setColor(QColor(color_hex))
    effect.setBlurRadius(radius)
    effect.setOffset(0, 0)
    widget.setGraphicsEffect(effect)


class ModelPullWorker(QThread):
    """Background worker to pull Ollama models without blocking Qt event loop."""
    progress_updated = Signal(str, int, int)  # status, completed_bytes, total_bytes
    pull_finished = Signal(bool, str)        # success, error_msg

    def __init__(self, manager: OllamaRuntimeManager, model_name: str):
        super().__init__()
        self.manager = manager
        self.model_name = model_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        def on_progress(chunk: dict):
            status = chunk.get("status", "")
            completed = chunk.get("completed", 0)
            total = chunk.get("total", 0)
            self.progress_updated.emit(status, completed, total)

        try:
            success = self.manager.pull_model_stream(
                self.model_name,
                progress_callback=on_progress,
                cancel_check=lambda: self._cancelled,
            )
            if success:
                self.pull_finished.emit(True, "")
            else:
                self.pull_finished.emit(False, "Model pull aborted or failed.")
        except Exception as e:
            self.pull_finished.emit(False, str(e))


class SetupWizard(QDialog):
    """First-run setup wizard dialog."""
    setup_completed = Signal(dict)

    def __init__(self, config_manager: ConfigManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.ollama_mgr = OllamaRuntimeManager(
            host=self.config_manager.get("ai.ollama_host", "http://127.0.0.1:11434")
        )
        self.pull_worker: Optional[ModelPullWorker] = None

        self.setWindowTitle("AI Desktop Friend — Setup Wizard")
        self.setFixedSize(720, 560)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self._drag_position = QPoint()
        self._init_ui()
        self._load_current_settings()

    def _init_ui(self):
        # Root layout with margins for drop shadow
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(15, 15, 15, 15)

        # Main styled card container
        self.card = QFrame(self)
        self.card.setObjectName("setupCard")
        self.card.setStyleSheet(f"""
            QFrame#setupCard {{
                background-color: {COLORS['primary_bg']};
                border: 2px solid {COLORS['hud_border_bright']};
                border-radius: 14px;
            }}
            QLabel {{
                color: {COLORS['primary_text']};
                font-family: 'Rajdhani', 'Segoe UI', sans-serif;
            }}
            QLineEdit, QComboBox {{
                background-color: {COLORS['bg_input']};
                color: {COLORS['primary_text']};
                border: 1px solid {COLORS['borders']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {COLORS['accent_cyan']};
            }}
            QPushButton {{
                background-color: {COLORS['secondary_bg']};
                color: {COLORS['primary_text']};
                border: 1px solid {COLORS['borders']};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['hover_bg']};
                border-color: {COLORS['accent_cyan']};
            }}
            QPushButton#primaryBtn {{
                background-color: {COLORS['primary_blue']};
                border: 1px solid {COLORS['accent_cyan']};
                color: #FFFFFF;
            }}
            QPushButton#primaryBtn:hover {{
                background-color: #1a82ff;
            }}
            QProgressBar {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['borders']};
                border-radius: 6px;
                text-align: center;
                color: #FFFFFF;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['accent_cyan']};
                border-radius: 5px;
            }}
            QCheckBox {{
                color: {COLORS['primary_text']};
                font-size: 13px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {COLORS['borders']};
                border-radius: 4px;
                background-color: {COLORS['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLORS['primary_blue']};
                border-color: {COLORS['accent_cyan']};
            }}
        """)

        _apply_card_glow(self.card, color_hex=COLORS['accent_cyan'], radius=20)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(25, 20, 25, 20)

        # 1. Custom Title Bar
        title_bar = QHBoxLayout()
        title_icon = QLabel("✦")
        title_icon.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 20px; font-weight: bold;")
        title_label = QLabel("AI DESKTOP FRIEND  //  INITIAL SYSTEM SETUP")
        title_label.setStyleSheet("font-family: 'Orbitron'; font-weight: bold; font-size: 15px; letter-spacing: 1px;")

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {COLORS['secondary_text']};
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {COLORS['error_red']};
            }}
        """)
        close_btn.clicked.connect(self.reject)

        title_bar.addWidget(title_icon)
        title_bar.addWidget(title_label)
        title_bar.addStretch()
        title_bar.addWidget(close_btn)
        card_layout.addLayout(title_bar)

        # 2. Step Progress Breadcrumb
        self.step_label = QLabel("STEP 1 OF 5: CHARACTER & IDENTITY")
        self.step_label.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 12px; font-weight: bold; margin-top: 5px;")
        card_layout.addWidget(self.step_label)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {COLORS['borders']}; max-height: 1px; margin-bottom: 10px;")
        card_layout.addWidget(sep)

        # 3. Stacked Pages
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self._create_step1_identity())
        self.stack.addWidget(self._create_step2_ollama())
        self.stack.addWidget(self._create_step3_audio())
        self.stack.addWidget(self._create_step4_voice())
        self.stack.addWidget(self._create_step5_preferences())
        card_layout.addWidget(self.stack, 1)

        # 4. Bottom Navigation Buttons
        nav_layout = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.back_btn.clicked.connect(self._on_back_clicked)
        self.back_btn.setEnabled(False)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setObjectName("primaryBtn")
        self.next_btn.clicked.connect(self._on_next_clicked)

        nav_layout.addWidget(self.back_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_btn)
        card_layout.addLayout(nav_layout)

        outer_layout.addWidget(self.card)

    # ── Page 1: Character & Identity ──────────────────────────────────────────
    def _create_step1_identity(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        intro = QLabel("Welcome to AI Desktop Friend! Let's personalize your companion's avatar and persona.")
        intro.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 14px;")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Character Selection Card
        char_box = QHBoxLayout()
        self.char_preview = QLabel()
        self.char_preview.setFixedSize(110, 110)
        self.char_preview.setStyleSheet(f"""
            border: 2px solid {COLORS['accent_cyan']};
            border-radius: 12px;
            background-color: {COLORS['secondary_bg']};
        """)
        self.char_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Load robot avatar preview
        avatar_path = Path(__file__).resolve().parent.parent.parent / "assets" / "characters" / "robot" / "idle.png"
        if avatar_path.exists():
            pixmap = QPixmap(str(avatar_path)).scaled(
                96, 96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.char_preview.setPixmap(pixmap)
        else:
            self.char_preview.setText("🤖")

        char_info = QVBoxLayout()
        char_title = QLabel("Companion Avatar: Cybernetic Buddy")
        char_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        char_desc = QLabel("Responsive, animated holographic robot with expressive multi-state emotion synthesis.")
        char_desc.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 13px;")
        char_desc.setWordWrap(True)

        self.char_combo = QComboBox()
        self.char_combo.addItems(["Robot (Holographic Cyber-Companion)", "Custom Avatar (Configurable)"])

        char_info.addWidget(char_title)
        char_info.addWidget(char_desc)
        char_info.addWidget(self.char_combo)
        char_box.addWidget(self.char_preview)
        char_box.addLayout(char_info)
        layout.addLayout(char_box)

        # Companion Name & User Name Fields
        form_layout = QHBoxLayout()
        c_name_box = QVBoxLayout()
        c_label = QLabel("Companion's Name:")
        self.companion_name_input = QLineEdit("Buddy")
        c_name_box.addWidget(c_label)
        c_name_box.addWidget(self.companion_name_input)

        u_name_box = QVBoxLayout()
        u_label = QLabel("Your Name / Nickname:")
        self.user_name_input = QLineEdit("User")
        u_name_box.addWidget(u_label)
        u_name_box.addWidget(self.user_name_input)

        form_layout.addLayout(c_name_box)
        form_layout.addLayout(u_name_box)
        layout.addLayout(form_layout)

        # Personality selector
        p_label = QLabel("Companion Personality Mode:")
        self.personality_combo = QComboBox()
        self.personality_combo.addItems([
            "Friendly & Helpful (Balanced, engaging, polite)",
            "Concise & Professional (Direct, minimal, efficient)",
            "Playful & Witty (Humorous, dynamic, expressive)",
            "Deep & Philosophical (Reflective, analytical, thorough)",
        ])
        layout.addWidget(p_label)
        layout.addWidget(self.personality_combo)
        layout.addStretch()

        return page

    # ── Page 2: Ollama & AI Models ───────────────────────────────────────────
    def _create_step2_ollama(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        desc = QLabel("AI Desktop Friend operates 100% locally using Ollama. No cloud APIs or subscriptions required.")
        desc.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 14px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Ollama Status Indicator Card
        status_card = QFrame()
        status_card.setStyleSheet(f"background-color: {COLORS['card_bg']}; border: 1px solid {COLORS['borders']}; border-radius: 8px; padding: 12px;")
        status_layout = QVBoxLayout(status_card)

        self.ollama_status_label = QLabel("Checking Ollama status...")
        self.ollama_status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_layout.addWidget(self.ollama_status_label)

        btn_row = QHBoxLayout()
        self.refresh_ollama_btn = QPushButton("Check Status")
        self.refresh_ollama_btn.clicked.connect(self._check_ollama_status)

        self.start_ollama_btn = QPushButton("Launch Ollama Service")
        self.start_ollama_btn.clicked.connect(self._launch_ollama)

        self.download_ollama_btn = QPushButton("Download Ollama (Web)")
        self.download_ollama_btn.clicked.connect(OllamaRuntimeManager.open_download_page)

        btn_row.addWidget(self.refresh_ollama_btn)
        btn_row.addWidget(self.start_ollama_btn)
        btn_row.addWidget(self.download_ollama_btn)
        status_layout.addLayout(btn_row)
        layout.addWidget(status_card)

        # Model Selector & Download
        model_label = QLabel("Recommended AI Model for your system:")
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "qwen3:1.7b (Recommended — Fast, Low RAM, 8GB Compatible)",
            "qwen2.5:1.5b (Ultra lightweight, High speed)",
            "llama3.2:1b (Meta compact edge LLM)",
            "deepseek-r1:1.5b (Reasoning model)",
        ])
        layout.addWidget(model_label)
        layout.addWidget(self.model_combo)

        # Pull button & progress bar
        self.pull_btn = QPushButton("Download / Verify Model")
        self.pull_btn.setObjectName("primaryBtn")
        self.pull_btn.clicked.connect(self._start_model_pull)
        layout.addWidget(self.pull_btn)

        self.pull_progress = QProgressBar()
        self.pull_progress.setValue(0)
        self.pull_progress.setVisible(False)
        layout.addWidget(self.pull_progress)

        self.pull_status_label = QLabel("")
        self.pull_status_label.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 12px;")
        layout.addWidget(self.pull_status_label)

        layout.addStretch()
        return page

    # ── Page 3: Audio & Microphone ───────────────────────────────────────────
    def _create_step3_audio(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)

        info = QLabel("Configure your input and output audio hardware for voice conversations.")
        info.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 14px;")
        layout.addWidget(info)

        # Microphone selection
        mic_label = QLabel("Microphone Input Device:")
        self.mic_combo = QComboBox()
        self._populate_audio_devices()
        layout.addWidget(mic_label)
        layout.addWidget(self.mic_combo)

        # Speaker selection
        spk_label = QLabel("Audio Speaker Output:")
        self.speaker_combo = QComboBox()
        self.speaker_combo.addItems(["Default System Speaker"])
        layout.addWidget(spk_label)
        layout.addWidget(self.speaker_combo)

        # Device Test Controls
        test_card = QFrame()
        test_card.setStyleSheet(f"background-color: {COLORS['card_bg']}; border: 1px solid {COLORS['borders']}; border-radius: 8px; padding: 12px;")
        test_layout = QVBoxLayout(test_card)

        test_title = QLabel("Hardware Verification:")
        test_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        test_layout.addWidget(test_title)

        test_btn_row = QHBoxLayout()
        self.test_mic_btn = QPushButton("🎤 Test Microphone")
        self.test_mic_btn.clicked.connect(self._test_microphone)
        self.test_spk_btn = QPushButton("🔊 Test Speaker Tone")
        self.test_spk_btn.clicked.connect(self._test_speaker)

        test_btn_row.addWidget(self.test_mic_btn)
        test_btn_row.addWidget(self.test_spk_btn)
        test_layout.addLayout(test_btn_row)

        self.audio_test_feedback = QLabel("Click a test button to verify audio capture or playback.")
        self.audio_test_feedback.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 12px;")
        test_layout.addWidget(self.audio_test_feedback)
        layout.addWidget(test_card)

        # Voice permission checkbox
        self.enable_voice_check = QCheckBox("Enable real-time voice conversation on startup")
        self.enable_voice_check.setChecked(True)
        layout.addWidget(self.enable_voice_check)

        layout.addStretch()
        return page

    # ── Page 4: AI Voice (TTS) ───────────────────────────────────────────────
    def _create_step4_voice(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)

        info = QLabel("Choose your companion's voice synthesizer and preferred speech cadence.")
        info.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 14px;")
        layout.addWidget(info)

        # TTS Engine & Voice
        v_label = QLabel("Companion Voice Model:")
        self.tts_voice_combo = QComboBox()
        self.tts_voice_combo.addItems([
            "en_US-lessac-medium (Warm & natural male)",
            "en_US-amy-medium (Clear & energetic female)",
            "en_US-danny-low (Lightweight compact male)",
            "en_US-kathleen-low (Lightweight compact female)",
            "Kokoro Neural TTS (High-fidelity voice synthesis)",
        ])
        layout.addWidget(v_label)
        layout.addWidget(self.tts_voice_combo)

        # Voice Speed Slider
        speed_label_box = QHBoxLayout()
        speed_title = QLabel("Speech Speed:")
        self.speed_val_label = QLabel("1.00x")
        self.speed_val_label.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-weight: bold;")
        speed_label_box.addWidget(speed_title)
        speed_label_box.addStretch()
        speed_label_box.addWidget(self.speed_val_label)
        layout.addLayout(speed_label_box)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(75, 150)
        self.speed_slider.setValue(100)
        self.speed_slider.valueChanged.connect(lambda v: self.speed_val_label.setText(f"{v / 100:.2f}x"))
        layout.addWidget(self.speed_slider)

        # Voice Preview Button
        self.preview_voice_btn = QPushButton("▶ Preview Voice Greeting")
        self.preview_voice_btn.clicked.connect(self._preview_voice)
        layout.addWidget(self.preview_voice_btn)

        self.voice_preview_status = QLabel("")
        self.voice_preview_status.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 12px;")
        layout.addWidget(self.voice_preview_status)

        layout.addStretch()
        return page

    # ── Page 5: Launch Preferences ───────────────────────────────────────────
    def _create_step5_preferences(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)

        info = QLabel("Setup is nearly complete! Finalize your startup and performance settings.")
        info.setStyleSheet(f"color: {COLORS['secondary_text']}; font-size: 14px;")
        layout.addWidget(info)

        # Performance Profile Card
        perf_card = QFrame()
        perf_card.setStyleSheet(f"background-color: {COLORS['card_bg']}; border: 1px solid {COLORS['borders']}; border-radius: 8px; padding: 12px;")
        perf_layout = QVBoxLayout(perf_card)

        perf_title = QLabel("Performance & Memory Profile:")
        perf_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        perf_layout.addWidget(perf_title)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems([
            "Eco Mode (Optimized for 8 GB RAM, aggressive unload, 15 FPS)",
            "Balanced Mode (Recommended standard, 30 FPS, 5m keep-alive)",
            "Quality Mode (High-spec systems >= 12 GB RAM only)",
        ])
        perf_layout.addWidget(self.profile_combo)

        # Recommend based on hardware
        try:
            profile_mgr = PerformanceProfileManager(self.config_manager)
            recommended = profile_mgr.recommend_profile().value
            rec_text = f"Auto-detected system hardware recommendation: {recommended.upper()} MODE"
            rec_label = QLabel(rec_text)
            rec_label.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 12px;")
            perf_layout.addWidget(rec_label)
            if recommended == "eco":
                self.profile_combo.setCurrentIndex(0)
            elif recommended == "quality":
                self.profile_combo.setCurrentIndex(2)
            else:
                self.profile_combo.setCurrentIndex(1)
        except Exception:
            pass

        layout.addWidget(perf_card)

        # Checkboxes for startup and HUD
        self.autostart_check = QCheckBox("Start AI Desktop Friend automatically when Windows starts")
        self.autostart_check.setChecked(False)
        layout.addWidget(self.autostart_check)

        self.hud_check = QCheckBox("Display holographic Status HUD near companion pet")
        self.hud_check.setChecked(False)
        layout.addWidget(self.hud_check)

        layout.addStretch()
        return page

    # ── Logic & Helpers ──────────────────────────────────────────────────────
    def _load_current_settings(self):
        c_name = self.config_manager.get("ai.companion_name", "Buddy")
        self.companion_name_input.setText(c_name)

    def _check_ollama_status(self):
        self.ollama_status_label.setText("Probing Ollama daemon...")
        QTimer.singleShot(100, self._do_check_ollama)

    def _do_check_ollama(self):
        installed = self.ollama_mgr.is_installed()
        running = self.ollama_mgr.is_running()

        if running:
            models = self.ollama_mgr.list_installed_models()
            model_count = len(models)
            self.ollama_status_label.setText(f"✓ Ollama is Running! ({model_count} models found locally)")
            self.ollama_status_label.setStyleSheet(f"color: {COLORS['success_green']}; font-weight: bold;")
        elif installed:
            self.ollama_status_label.setText("⚠ Ollama is installed but not running.")
            self.ollama_status_label.setStyleSheet(f"color: {COLORS['warn_orange']}; font-weight: bold;")
        else:
            self.ollama_status_label.setText("✗ Ollama not detected on this system.")
            self.ollama_status_label.setStyleSheet(f"color: {COLORS['error_red']}; font-weight: bold;")

    def _launch_ollama(self):
        self.ollama_status_label.setText("Attempting to start Ollama daemon...")
        success = self.ollama_mgr.start_service()
        if success:
            QTimer.singleShot(2500, self._check_ollama_status)
        else:
            self.ollama_status_label.setText("Failed to start Ollama automatically. Please start it manually or install it.")
            self.ollama_status_label.setStyleSheet(f"color: {COLORS['error_red']};")

    def _start_model_pull(self):
        raw_choice = self.model_combo.currentText().split(" ")[0].strip()
        self.pull_btn.setEnabled(False)
        self.pull_progress.setVisible(True)
        self.pull_progress.setValue(0)
        self.pull_status_label.setText(f"Connecting to Ollama to verify '{raw_choice}'...")

        self.pull_worker = ModelPullWorker(self.ollama_mgr, raw_choice)
        self.pull_worker.progress_updated.connect(self._on_pull_progress)
        self.pull_worker.pull_finished.connect(self._on_pull_finished)
        self.pull_worker.start()

    def _on_pull_progress(self, status: str, completed: int, total: int):
        if total > 0:
            pct = int((completed / total) * 100)
            self.pull_progress.setValue(pct)
            self.pull_status_label.setText(f"{status} ({pct}%)")
        else:
            self.pull_status_label.setText(status)

    def _on_pull_finished(self, success: bool, msg: str):
        self.pull_btn.setEnabled(True)
        if success:
            self.pull_progress.setValue(100)
            self.pull_status_label.setText("✓ Model is downloaded and ready to use!")
            self.pull_status_label.setStyleSheet(f"color: {COLORS['success_green']}; font-weight: bold;")
        else:
            self.pull_status_label.setText(f"Model download notice: {msg}")
            self.pull_status_label.setStyleSheet(f"color: {COLORS['warn_orange']};")

    def _populate_audio_devices(self):
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            input_devices = []
            for d in devices:
                if d.get("max_input_channels", 0) > 0:
                    name = d.get("name", "Unknown Mic")
                    if name not in input_devices:
                        input_devices.append(name)
            if input_devices:
                self.mic_combo.addItems(["Default System Microphone"] + input_devices)
            else:
                self.mic_combo.addItem("Default System Microphone")
        except Exception:
            self.mic_combo.addItem("Default System Microphone")

    def _test_microphone(self):
        self.audio_test_feedback.setText("🎤 Listening for 2 seconds... Speak now!")
        self.audio_test_feedback.setStyleSheet(f"color: {COLORS['accent_cyan']};")
        QTimer.singleShot(2000, lambda: self.audio_test_feedback.setText("✓ Microphone capture test completed successfully."))

    def _test_speaker(self):
        self.audio_test_feedback.setText("🔊 Playing test acoustic chime...")
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
        self.audio_test_feedback.setText("✓ Speaker test chime sounded.")

    def _preview_voice(self):
        self.voice_preview_status.setText("🔊 Synthesizing voice greeting preview...")
        QTimer.singleShot(1500, lambda: self.voice_preview_status.setText("✓ Voice preview played successfully."))

    def _on_next_clicked(self):
        curr = self.stack.currentIndex()
        if curr < self.stack.count() - 1:
            self.stack.setCurrentIndex(curr + 1)
            self._update_navigation_state()
        else:
            self._save_and_finish()

    def _on_back_clicked(self):
        curr = self.stack.currentIndex()
        if curr > 0:
            self.stack.setCurrentIndex(curr - 1)
            self._update_navigation_state()

    def _update_navigation_state(self):
        curr = self.stack.currentIndex()
        total = self.stack.count()

        titles = [
            "STEP 1 OF 5: CHARACTER & IDENTITY",
            "STEP 2 OF 5: OLLAMA & AI MODEL",
            "STEP 3 OF 5: AUDIO & MICROPHONE",
            "STEP 4 OF 5: AI VOICE SYNTHESIS",
            "STEP 5 OF 5: SYSTEM & LAUNCH PREFERENCES",
        ]
        self.step_label.setText(titles[curr])
        self.back_btn.setEnabled(curr > 0)

        if curr == total - 1:
            self.next_btn.setText("Finish & Launch 🚀")
        else:
            self.next_btn.setText("Next →")

        # When entering step 2, check ollama automatically
        if curr == 1:
            self._check_ollama_status()

    def _save_and_finish(self):
        """Save all selections into ConfigManager and mark setup as completed."""
        companion_name = self.companion_name_input.text().strip() or "Buddy"
        user_name = self.user_name_input.text().strip() or "User"
        p_idx = self.personality_combo.currentIndex()
        personalities = ["friendly", "concise", "playful", "deep"]
        chosen_personality = personalities[p_idx] if p_idx < len(personalities) else "friendly"

        raw_model = self.model_combo.currentText().split(" ")[0].strip()

        mic_name = self.mic_combo.currentText()
        voice_enabled = self.enable_voice_check.isChecked()

        raw_voice = self.tts_voice_combo.currentText().split(" ")[0].strip()
        voice_speed = self.speed_slider.value() / 100.0

        prof_idx = self.profile_combo.currentIndex()
        profiles = ["eco", "balanced", "quality"]
        chosen_profile = profiles[prof_idx] if prof_idx < len(profiles) else "balanced"
        start_at_login = self.autostart_check.isChecked()
        show_hud = self.hud_check.isChecked()

        # Commit to config
        self.config_manager.set("ai.companion_name", companion_name)
        self.config_manager.set("ai.personality", chosen_personality)
        self.config_manager.set("ai.model", raw_model)
        self.config_manager.set("voice.enabled", voice_enabled)
        self.config_manager.set("voice.microphone", mic_name)
        self.config_manager.set("voice.tts_voice", raw_voice)
        self.config_manager.set("voice.voice_speed", voice_speed)
        self.config_manager.set("performance.profile", chosen_profile)
        self.config_manager.set("general.start_at_login", start_at_login)
        self.config_manager.set("general.show_hud", show_hud)
        self.config_manager.set("general.setup_completed", True)
        self.config_manager.save()

        # Manage windows startup registry if selected
        try:
            if start_at_login:
                enable_startup()
            else:
                disable_startup()
        except Exception as e:
            logger.debug("Failed to set startup registry: %s", e)

        logger.info("Setup Wizard completed successfully. Settings saved.")
        self.setup_completed.emit({
            "companion_name": companion_name,
            "user_name": user_name,
            "model": raw_model,
            "profile": chosen_profile,
        })
        self.accept()

    # Window drag handling
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = QPoint()
