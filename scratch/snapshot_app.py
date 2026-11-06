"""Script to capture a visual snapshot of the desktop pet and floating chat window."""

import os
from pathlib import Path
import sys

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

from app.desktop.chat_window import FloatingChatWindow
from app.desktop.control_bar import FloatingControlBar
from app.desktop.pet_window import DesktopPetWindow
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.settings.config_manager import ConfigManager


def generate_app_preview(output_path: str) -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    # Use in-memory or temp database
    temp_dir = Path("scratch")
    temp_dir.mkdir(exist_ok=True)
    cfg = ConfigManager(config_path=temp_dir / "preview_settings.json")
    db_mgr = DatabaseManager(db_path=temp_dir / "preview_conversations.db")
    repo = ConversationRepository(db_manager=db_mgr)

    # Setup conversation
    conv = repo.create_conversation("Project Assistant")
    repo.add_message(conv.id, "user", "Hey Buddy! How are you doing today?")
    repo.add_message(
        conv.id,
        "assistant",
        "Hey! I'm feeling great and ready to hang out on your desktop! What are we working on today? 🤖",
    )
    repo.add_message(conv.id, "user", "Can you help me code my project offline?")
    repo.add_message(
        conv.id,
        "assistant",
        "Definitely! I run locally on your machine with Ollama, so everything we discuss stays 100% private. Just ask away! 🚀",
    )

    # 1. Desktop Pet Window
    pet_window = DesktopPetWindow(config_manager=cfg)
    pet_window.show()
    app.processEvents()

    # 2. Control bar
    control_bar = pet_window.control_bar
    control_bar.show_bar(pet_window.frameGeometry())
    app.processEvents()

    # 3. Chat Window
    chat_window = FloatingChatWindow(config_manager=cfg, repository=repo)
    chat_window.switch_conversation(conv.id)
    chat_window.show()
    app.processEvents()

    # Grab pixel buffers of the widgets
    pet_pixmap = pet_window.grab()
    control_bar_pixmap = control_bar.grab()
    chat_pixmap = chat_window.grab()

    # Create high-res preview canvas (e.g., 1024x720 representing desktop space)
    canvas_w, canvas_h = 1040, 720
    canvas = QPixmap(canvas_w, canvas_h)
    canvas.fill(Qt.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # Desktop wallpaper gradient (dark cyberpunk / sleek obsidian wallpaper)
    bg_grad = QLinearGradient(0, 0, canvas_w, canvas_h)
    bg_grad.setColorAt(0.0, QColor("#0F172A"))   # deep slate
    bg_grad.setColorAt(0.4, QColor("#1E1B4B"))   # deep indigo
    bg_grad.setColorAt(1.0, QColor("#090D16"))   # dark obsidian
    painter.fillRect(0, 0, canvas_w, canvas_h, bg_grad)

    # Subtle ambient glow
    glow_grad = QLinearGradient(300, 200, 900, 600)
    glow_grad.setColorAt(0.0, QColor(99, 102, 241, 40))
    glow_grad.setColorAt(1.0, QColor(59, 130, 246, 0))
    painter.fillRect(0, 0, canvas_w, canvas_h, glow_grad)

    # Mock desktop windows in background for realistic context (VS Code / Browser backdrop)
    mock_bg_rect = QRect(40, 50, 480, 580)
    painter.setBrush(QColor(15, 23, 42, 190))
    painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
    painter.drawRoundedRect(mock_bg_rect, 10, 10)

    # Mock code editor header
    painter.fillRect(40, 50, 480, 32, QColor(30, 41, 59, 210))
    painter.setPen(QColor(148, 163, 184))
    painter.setFont(QFont("Segoe UI", 10))
    painter.drawText(60, 72, "📄 main.py - Visual Studio Code")

    # Mock code lines
    painter.setPen(QColor(100, 116, 139, 160))
    painter.setFont(QFont("Consolas", 10))
    code_snippets = [
        "import asyncio",
        "from app.core import ApplicationController",
        "",
        "# Starting AI Desktop Companion",
        "controller = ApplicationController()",
        "controller.initialize()",
        "print('Pet online! 🤖')",
    ]
    for idx, line in enumerate(code_snippets):
        painter.drawText(60, 115 + (idx * 24), line)

    # Draw Chat Window (placed on right)
    chat_x = 560
    chat_y = 70
    painter.drawPixmap(chat_x, chat_y, chat_pixmap)

    # Draw Pet Character (floating between windows)
    pet_x = 420
    pet_y = 380
    painter.drawPixmap(pet_x, pet_y, pet_pixmap)

    # Draw Control Bar (just below pet)
    bar_x = pet_x + (pet_pixmap.width() - control_bar_pixmap.width()) // 2
    bar_y = pet_y + pet_pixmap.height() + 10
    painter.drawPixmap(bar_x, bar_y, control_bar_pixmap)

    # Taskbar at the bottom
    taskbar_h = 44
    painter.fillRect(0, canvas_h - taskbar_h, canvas_w, taskbar_h, QColor(15, 23, 42, 235))
    painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
    painter.drawLine(0, canvas_h - taskbar_h, canvas_w, canvas_h - taskbar_h)

    # Windows Start button hint
    painter.setPen(QColor(255, 255, 255, 200))
    painter.setFont(QFont("Segoe UI", 11))
    painter.drawText(24, canvas_h - 16, "⊞")
    painter.drawText(56, canvas_h - 16, "Search")

    # Tray robot icon
    painter.drawText(canvas_w - 70, canvas_h - 16, "🤖 🔊 📶")

    painter.end()

    # Save output image
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    print(f"Preview saved successfully to: {output_path}")

    pet_window.close()
    chat_window.close()


if __name__ == "__main__":
    out_file = (
        r"C:\Users\Gaurav Patel\.gemini\antigravity-ide\brain\df0bb43c-e4a9-44d0-8eed-fb0bd63f7f70\desktop_companion_preview.png"
    )
    generate_app_preview(out_file)
