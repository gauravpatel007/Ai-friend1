# AI Desktop Friend 🤖

An intelligent, animated, offline AI desktop companion that floats on your Windows desktop with native character animations, streaming local LLM intelligence via Ollama, and SQLite conversation history.

![AI Desktop Friend and Floating Chat Interface]

---

## Quick Start

### 🚀 Modern Desktop Chat App (New Interface)
**In PowerShell:**
```powershell
.\.venv\Scripts\python.exe run_desktop.py
```

**In Command Prompt (CMD):**
```cmd
.venv\Scripts\python.exe run_desktop.py
```
*Or double-click `AI_Desktop_Friend.bat` or the **AI Desktop Friend** icon on your Desktop.*

### 🧸 Original Desktop Pet Window
```powershell
.\.venv\Scripts\python.exe main.py
```
  
## 🌟 Key Features

- **Floating Desktop Pet**: Frameless, transparent, draggable character window that stays above your apps.
- **8 Animated Character States**: `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `HAPPY`, `SLEEPING`, `ERROR`, and `DRAGGING`.
- **Local AI Engine**: Powered by Ollama (`qwen3:4b`, `llama3.2`, or quantized models) with zero cloud dependencies or API keys required.
- **Real-Time Streaming & Thinking Filter**: Tokens stream chunk-by-chunk with internal reasoning (`<think>...</think>`) filtered out.
- **Native Floating Chat Window**: Movable, resizable glassmorphic interface with speech bubbles, typing indicators, and search.
- **Persistent Conversation Memory**: Full conversation management (create, rename, clear, delete, search) backed by SQLite with WAL mode.
- **Input Modes**: Supports Text mode, Push-to-Talk, and Continuous Voice mode.
- **System Tray Integration**: Background tray menu to restore pet, toggle visibility, and control application modes.

---

## 📋 Prerequisites

1. **Windows 10 / 11**
2. **Python 3.11+** (Python 3.11, 3.12, or 3.13)
3. **Ollama** installed on your system:
   - Download from [ollama.com](https://ollama.com)
   - Pull a companion model in terminal:
     ```bash
     ollama pull qwen3:4b
     # or a smaller model:
     ollama pull llama3.2:latest
     ```

---

## 🚀 Step-by-Step Run Instructions

### 1. Open Terminal & Navigate to Project
```powershell
cd "g:\Languages\Projects\AI Friend"
```

### 2. Activate Virtual Environment
If using PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` or activate with `.\.venv\Scripts\activate.bat` in CMD).*

### 3. Install Dependencies (if not already installed)
```bash
pip install PySide6 psutil platformdirs pytest pytest-qt
```

### 4. Verify Local Ollama Engine
Ensure Ollama is running in the background:
```powershell
ollama list
```
The application will automatically detect your local endpoint at `http://127.0.0.1:11434` and select your installed model (e.g. `qwen3:4b`).

### 5. Launch the Application
```powershell
python main.py
```

### 6. Quick Smoke Test (Runs for 1 second and exits cleanly)
```powershell
python main.py --test-run
```

### 7. Run Test Suite
```powershell
pytest
```

---

## 🎮 Desktop Character Interactions

| Action | Description |
| :--- | :--- |
| **Left-Click (Single)** | Opens the compact floating chat window near the character. |
| **Left-Click (Double)** | Toggles voice mode. |
| **Left-Click & Drag** | Drags the character anywhere on your desktop. Position is automatically remembered. |
| **Hover Mouse** | Reveals the sleek floating toolbar (💬 Chat, 🎤 Voice, ⚙️ Settings, ✕ Hide). |
| **Right-Click** | Opens the context menu (Size presets: Small 80px / Medium 120px / Large 160px, Always-on-top, Click-through). |
| **System Tray** | Right-click the robot icon in the Windows notification area to show/hide or exit cleanly. |

---

## 💬 Chat Window Features

- **Send Message**: Type text and press <kbd>Enter</kbd> (use <kbd>Shift</kbd>+<kbd>Enter</kbd> for multi-line).
- **Streaming & Stop**: Live word-by-word streaming; click the red **■ Stop** button at any time to cancel generation.
- **Conversations Menu (📋)**: Switch between past conversation sessions, rename, or clear messages.
- **Search (🔍)**: Search all past message history across all conversations.
- **Independent Window**: The chat window can be moved and resized freely without closing the companion pet.

---

## 📁 Project Architecture & Documentation

Comprehensive technical documentation, architecture plans, system reports, and test specifications are located in the [`docs/`](docs/README.md) directory:

- **[Master Feature Matrix & Architecture Map](docs/features.md)**: Full breakdown of desktop pet systems, local Ollama streaming, SQLite memory, Silero VAD, Faster-Whisper STT, and Kokoro/Piper TTS engines.
- **[Full System & Backend Audit Report](docs/reports/AI_Friend_Full_System_Audit_Report.md)**: Comprehensive verification of thinking tag suppression, cancellation mechanics, and thread-safe WAL database persistence across 465 automated tests.
- **[Hybrid Security Audit Report](docs/reports/SECURITY_AUDIT_REPORT.md)**: Full security evaluation covering local REST endpoints, CORS boundaries, CSWSH protections, and WebEngine sandbox boundaries.
- **[Voice Engine Technical Report](docs/reports/AI_Friend_Voice_Bug_Fix_Report.md)**: Deep dive into the audio capture, VAD sensitivity, Faster-Whisper parameters, and state machine turn lifecycle.
- **[Defect & Bug Master Tracker](docs/reports/broken_features.md)**: Catalog of 22 verified solutions to UI focus trapping, hands-free continuous listening, speech bubbles, and memory extraction.
- **[Tauri Migration Blueprint](docs/plans/tauri_migration_plan.md)**: Architecture roadmap for the lightweight Rust + Tauri desktop frontend.
- **[QA Test Specifications](docs/notes/Test1.md)**: Verification criteria and automated test matrices across 19 sections and 14 phases.
- **[Historical Archive (`BIN/`)](BIN/README.md)**: Archived early phase specifications, holographic JARVIS UI plans, and legacy mockups.

