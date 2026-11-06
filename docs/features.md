# AI Desktop Friend — Complete Project Feature Matrix & Architecture Map

> **Document Purpose**: This document provides a comprehensive inventory of all existing features, architectural subsystems, technologies, APIs, and interaction patterns currently built into the **AI Desktop Friend** project. Use this document as direct context for an LLM to understand the current capabilities and suggest new, non-redundant, innovative features.

---

## 1. Project Overview & Design Philosophy

- **Application Name**: AI Desktop Friend
- **Core Vision**: An intelligent, interactive, animated desktop companion that lives directly on the Windows desktop, providing local conversational AI, full-duplex hands-free voice interactions, persistent memory, and character animations.
- **Privacy & Execution Model**: **100% Local and Offline**. Zero cloud API keys, zero cloud subscriptions, zero telemetry, and zero remote data transmission.
- **Hardware Profile**: Designed to run efficiently on Windows 11 hardware with modest resources (CPU-only friendly, ~8 GB RAM, optional GPU acceleration).

### Technology Stack
| Layer | Technologies Used |
| :--- | :--- |
| **Desktop GUI / Windowing** | Python 3.11–3.13, PySide6 6.12 (Qt 6.12), Frameless transparent windows, QPainter graphics |
| **Alternative / Modern UI** | React 18, TypeScript, Vite 6, Tailwind/Vanilla CSS, QWebEngineView / Tauri bridge |
| **Local API & IPC** | FastAPI, Uvicorn, Duplex WebSockets, Qt Signals & Slots, `QLocalServer` single-instance IPC |
| **Local AI Engine** | Ollama (`http://127.0.0.1:11434`), supports LLaMA 3.2, Qwen 2.5 / Qwen 3, DeepSeek-R1, Mistral |
| **Speech-to-Text (STT)** | Faster-Whisper (INT8 quantized, CPU-optimized, auto-detect language) |
| **Voice Activity Detection** | Silero VAD (ONNX runtime, real-time voice probability evaluation) |
| **Text-to-Speech (TTS)** | Triple-engine fallback: Kokoro-82M (neural ONNX) → Piper (neural ONNX) → Windows SAPI5 (offline OS) |
| **Audio I/O** | PortAudio via `sounddevice`, `numpy` audio processing |
| **Persistence & Memory** | SQLite with WAL (Write-Ahead Logging), FTS5 (Full-Text Search), JSON config files |

---

## 2. Desktop Companion & Visual Character System

### 2.1. Floating Desktop Pet Window (`DesktopPetWindow`)
- **Frameless & Transparent**: Stays directly on the desktop with transparent background, no OS borders, and rounded corners.
- **Always-on-Top Toggle**: Can float above all normal full-screen and maximized applications or be placed in standard z-order.
- **Draggable Anywhere**: Click and drag with mouse to reposition anywhere on the desktop.
- **Persistent Screen Placement**: Remembers last desktop coordinates across restarts; automatically clamps within visible display bounds upon multi-monitor changes.
- **Ambient Floor Glow**: Dynamic soft cyan floor ellipse rendered beneath the character's feet with anti-aliasing.
- **Dynamic Lip-Sync Mouth Animation**: Real-time mouth openness modulation driven by speech synthesis audio amplitude.
- **Click-Through Mode**: Optional click-through flag allowing mouse clicks to pass through to underlying applications.

### 2.2. Character Animation State Machine (`CharacterRenderer` & `AnimationController`)
- **8 Distinct Animated Character States**:
  1. `IDLE`: Gentle breathing and subtle ambient motion (30 FPS default, throttled in sleep).
  2. `LISTENING`: Attentive pose with glowing indicator when microphone captures user speech.
  3. `THINKING`: Concentrated animation while local LLM processes or reasons.
  4. `SPEAKING`: Talking animation with mouth sync tied to audio playback.
  5. `HAPPY`: Celebratory reaction when compliments or positive emotions are detected.
  6. `SLEEPING`: Low-power resting animation (nightcap / Zzz) with reduced tick rate.
  7. `ERROR`: Puzzled / apologetic expression when network, model, or audio issues occur.
  8. `DRAGGING`: Reactive hovering state while character is being moved across the screen.
- **Multi-Character Support**: Includes sprite presets (`robot`, `companion`, etc.) with runtime switching via context menu or API.
- **State Transition Guardrails**: Priority-based transition rules preventing invalid jumps (e.g., `SLEEPING` cannot immediately jump to `SPEAKING` without waking).

### 2.3. Character Desktop Interactions
| Trigger | Executed Behavior |
| :--- | :--- |
| **Left Click (Single)** | Spawns / raises the Floating Chat Window anchored near the pet. |
| **Left Click (Double)** | Toggles Voice Mode (turns microphone on or off). |
| **Left Click & Drag** | Enters `DRAGGING` state and moves the companion across screens. |
| **Mouse Hover** | Automatically slides out the floating 4-button capsule dock and speech bubble. |
| **Right Click** | Opens the sleek dark-themed context menu with full app controls. |

### 2.4. Desktop Floating Capsule Dock (`FloatingControlBar`)
- Sleek white capsule pill dock with drop shadow anchored right beneath the character.
- **Quick Action Buttons**:
  - 💬 **Chat**: Opens or focuses the chat conversation window.
  - 🎙 **Voice**: Toggles voice listening on or off.
  - ⚙ **Settings**: Opens the 10-category settings dialog.
  - ✕ **Hide**: Minimizes the desktop character to the system tray.
- **Speech Bubble (`SpeechBubbleWidget`)**: Animated tooltip bubble displaying contextual greetings ("Hey! 👋 I'm your AI Friend!", "Need anything?") with auto-dismiss timer.

### 2.5. Character Context Menu (Right-Click)
- 💬 **Open Chat**: Displays main conversation window.
- 🎙️ **Voice Window**: Opens dedicated concentric audio portal visualizer.
- 🎙 **Enable Voice**: Switches microphone listening on/off.
- ⚙ **Settings**: Opens configuration settings.
- 📌 **Always on Top**: Checkable toggle to lock companion above all windows.
- 👤 **Change Character**: Submenu to swap avatar skins at runtime.
- 🌙 **Sleep Mode**: Low-power standby mode (pauses heavy polling, dims animations).
- ✕ **Hide Character**: Hides pet widget while keeping background services alive in tray.
- ⏻ **Exit**: Clean, graceful shutdown of all processes, services, and windows.

---

## 3. Conversational AI Engine & LLM Integration

### 3.1. Local Ollama Integration (`OllamaClient` & `AIService`)
- **Direct HTTP API Integration**: Talks to local Ollama instance on `http://127.0.0.1:11434/api/chat`.
- **Zero Cloud Leakage**: All prompts, history, and completions stay entirely on localhost.
- **Ollama Process Supervisor (`OllamaSupervisor`)**:
  - Automatically verifies if Ollama is running on startup.
  - Searches standard Windows paths (`%LOCALAPPDATA%\Programs\Ollama\ollama.exe`) and auto-launches the daemon if offline.
- **Dynamic Model Discovery & Validation (`ModelManager`)**:
  - Discovers all locally pulled Ollama models (`llama3.2`, `qwen2.5`, `mistral`, `deepseek-r1`, etc.).
  - Filters out embedding models (`nomic-embed-text`) from conversational selection.
  - Dynamic runtime model switching without restarting the application.
- **VRAM / Memory Auto-Unload**:
  - Configurable `model_keep_alive` (e.g., `"5m"` or `"0s"`) to unload model from GPU VRAM during periods of inactivity.

### 3.2. Real-Time Streaming & Thinking Tag Suppression (`StreamingThinkingFilter`)
- **Live Word-by-Word Token Streaming**: Stream chunks emit via Qt signals and WebSockets immediately as generated.
- **Advanced 14-Case Reasoning Suppression**:
  - Seamlessly cleanses internal `<think>...</think>` reasoning tags from chain-of-thought models (e.g. DeepSeek-R1, Qwen3) before text reaches chat bubbles or TTS.
  - Handles edge cases: tags split across incoming packet boundaries (`<th` + `ink>`), uppercase tags (`<THINK>`), nested tags, orphan tags, and preserving math expressions (`5 < 10 and 10 > 2`).
- **Cooperative Generation Cancellation (`CancellationToken`)**:
  - Instant non-blocking cancellation when the user clicks **Stop** or interrupts via voice.
  - Aborts the HTTP connection to Ollama immediately, freeing GPU/CPU cycles without thread lockups.

### 3.3. Conversation Intelligence & Persona System
- **Companion Personality Manager (`PersonalityManager`)**:
  - Configurable personas: "Friendly Companion" (warm, cheerful), "Jarvis" (efficient, precise, executive assistant), "Mentor/Tutor" (instructive, patient), "Custom".
  - Dynamic system prompt injection shaping voice tone, length, and demeanor.
- **User Emotion Classifier (`EmotionClassifier`)**:
  - Real-time classification of user sentiment (happy, sad, excited, frustrated, calm, confused).
  - Triggers companion emotional reactions (e.g., character triggers `HAPPY` animation when user shares good news).
- **Safe Deterministic Math Tool (`MathEvaluator`)**:
  - Built-in safe AST parser for arithmetic queries to prevent LLM hallucination on exact mathematical computations.
- **Offline Fallback Companion (`OfflineCompanion`)**:
  - Heuristic offline dialog engine providing polite status messages and guidance when Ollama is offline or uninstalled.

---

## 4. Voice & Speech Intelligence Pipeline (Full Duplex)

### 4.1. Voice Modes
1. **Push-to-Talk (PTT)**: Hold down a button in the UI or press a global hotkey to record; release to transcribe and answer.
2. **Wake Word Detection**: Background listening for trigger phrases ("Hey Buddy", "Jarvis") powered by `WakeWordEngine`.
3. **Continuous Hands-Free Mode**: Natural conversational turn-taking using voice activity detection.

### 4.2. Audio Ingestion & VAD
- **Microphone Manager (`MicrophoneManager`)**:
  - Mono/Stereo capture at 16kHz via PortAudio (`sounddevice`).
  - Audio device enumeration, input gain control, and live RMS amplitude calculation.
- **Silero VAD Engine (`VADEngine`)**:
  - Neural voice activity detection on ONNX runtime.
  - Evaluates voice probabilities every 30ms frame.
  - Dynamic silence thresholding (default: 1200ms) to detect natural pauses before completing turns.

### 4.3. Speech-to-Text (STT) (`WhisperEngine`)
- **Faster-Whisper Local INT8 Inference**:
  - Runs local Whisper models (`tiny`, `base`, `small`) quantized to INT8 on CPU.
  - Multilingual support with automatic language detection or forced language lock.
  - **Hallucination Suppression**: Rejects audio buffers shorter than 0.3s or with high `no_speech_prob` (>0.7) to eliminate phantom transcriptions.

### 4.4. Resilient Triple-Engine Text-to-Speech (TTS)
1. **Primary Engine — Kokoro-82M ONNX (`KokoroTTSEngine`)**: Ultra-fast, highly natural lightweight neural TTS running locally.
2. **Secondary Engine — Piper TTS (`PiperTTSEngine`)**: High-performance open-source neural voice synthesizer fallback.
3. **Tertiary Engine — Windows SAPI5 (`Sapi5TTSEngine`)**: Native Windows speech synthesizer with zero downloads required.
- **"Never Silent" Guarantee**: If a neural model runs out of RAM or crashes, speech synthesis instantly falls back to the next engine without failing.

### 4.5. Low-Latency Streaming TTS Pipeline
- **Sentence Chunker (`SentenceChunker`)**:
  - As Ollama streams tokens, the chunker groups them into natural sentence fragments (`.`, `!`, `?`, `;`).
  - Sends the first completed sentence to TTS synthesis immediately while Ollama is still generating subsequent tokens.
- **Streaming Audio Queue (`StreamingAudioQueue`)**:
  - Seamlessly sequences synthesized PCM chunks into `AudioPlayer` for smooth, uninterrupted speech playback without latency.

### 4.6. Conversational Voice Control & Safety
- **Barge-in / Voice Interruption (`InterruptionManager`)**:
  - If the user starts speaking while the assistant is talking, the AI immediately halts playback, clears the audio queue, and listens to the user.
- **Acoustic Echo Suppression (`AcousticEchoSuppressor`)**:
  - Prevents the assistant from hearing its own speech from speakers through fuzzy Levenshtein and token shingle comparison.
- **Emergency Stop & Mute**:
  - Instant hardware mute toggle and emergency audio cutoff hotkey.
- **Natural Voice Command Dispatcher (`CommandDispatcher`)**:
  - Built-in regex and intent patterns for voice commands:
    - *"Open chat"* / *"Show chat"* → Displays the conversation window.
    - *"Sleep mode"* / *"Go to sleep"* → Transitions companion to sleeping state.
    - *"Mute"* / *"Unmute"* → Toggles audio output.
    - *"Clear chat"* / *"New conversation"* → Resets conversation context.
    - *"Exit application"* / *"Close program"* → Initiates clean shutdown.

---

## 5. Dual Chat Interfaces & User Experience

The project provides two interchangeable, synchronized chat interfaces:

### 5.1. Native PySide6 Split Chat Window (`FloatingChatWindow`)
- **3-Panel Glassmorphic Interface**:
  - **Left Panel (Sidebar)**:
    - Search bar with live conversation filtering.
    - **+ New Chat** pill button.
    - Conversation card list with timestamps and message counts.
    - Storage indicator and settings shortcut.
  - **Center Panel (Conversation Stream)**:
    - Date badge separators ("Today • 27 October 2026").
    - Glassmorphic message bubbles (User bubbles in Primary Blue with double checkmarks; AI bubbles with avatar and action bar).
    - Code blocks with syntax highlighting, language headers, and one-click copy.
    - Markdown rendering (bold, italics, lists, tables, blockquotes).
    - Real-time typing indicators and streaming cursor.
    - Bottom pill input bar with Enter-to-send, Shift+Enter for newline, PTT microphone button, attachment button, and Stop button.
  - **Right Panel (Companion & Quick Controls)**:
    - Companion portrait with cyan glow ring and name editing pencil.
    - Online/Offline status card.
    - Voice controls (Voice, Stop, Mute buttons).
    - 2x2 Quick Actions grid: *New Chat*, *View History*, *Clear Chat*, *Export Chat*.
    - Active model selector dropdown and voice settings.

### 5.2. Modern React 18 / TypeScript WebEngine SPA (`ModernChatWindow`)
- Frameless, borderless web application embedded via `QWebEngineView` or standalone browser.
- Full parity with native UI: WebSocket live stream, sidebar conversation switching, settings modal, voice portal visualizer.
- Served directly by the local FastAPI server from `dist/` or Vite dev server.

### 5.3. Dedicated Voice Portal Window (`VoiceWindow`)
- Floating circular dialog featuring a futuristic glowing concentric audio portal.
- Animated multi-bar waveform equalizer reacting to real-time audio volume.
- Status indicator pill (`Listening...`, `Thinking...`, `Speaking...`, `Muted`).
- Centered controls for instant mute, stop, and settings.

### 5.4. Live JARVIS Telemetry HUD (`JarvisTelemetryHUD`)
- Transparent floating widget attached near the companion displaying real-time system metrics:
  - CPU & RAM usage percentages.
  - Model inference speed (Tokens per second).
  - VAD speech probability meter.
  - Voice engine state and animation FPS.

---

## 6. Memory, Context & Persistence (SQLite WAL)

### 6.1. Thread-Safe SQLite WAL Architecture (`DatabaseManager`)
- **Location**: `%LOCALAPPDATA%\AIDesktopFriend\AIDesktopFriend\conversations.db`.
- **Concurrency**: Configured with `PRAGMA journal_mode = WAL` (Write-Ahead Logging) and `PRAGMA synchronous = NORMAL`, allowing concurrent background writes during active UI reading.
- **Data Integrity**: Foreign keys with `ON DELETE CASCADE` prevent orphaned records when conversations are deleted.
- **Thread Isolation**: `threading.local()` connection pooling prevents cross-thread lock contention.
- **SQL Injection Prevention**: 100% parameterized SQL queries (`?` bindings).

### 6.2. Conversation Management (`ConversationRepository`)
- Full CRUD for conversations: create, rename, auto-generate title, list sorted by recency, and delete.
- Message history tracking: role (`user`, `assistant`, `system`), text content, timestamp, status (`streaming`, `completed`, `error`).
- Clear message history within an existing conversation thread.
- Markdown export: Exports entire conversation session into formatted Markdown files.

### 6.3. 3-Tier Memory Architecture (`MemoryManager`)
1. **Short-Term Context**: Recent messages formatted into the active prompt window.
2. **Long-Term Memory Facts**: Extracted facts, preferences, and details stored persistently in SQLite:
   - Categories: `preference`, `project`, `goal`, `learning`, `interest`, `fact`, `custom`.
3. **Conversation Summaries**: Background periodic summarization of extended conversations to maintain continuity without exceeding LLM context windows.

### 6.4. FTS5 Search & Smart Context Budgeting
- **Full-Text Search (FTS5)**: SQLite virtual tables provide instant token search across all message histories and stored memories.
- **Automated Memory Extraction**: Heuristic keyword & syntactic analysis extracts user preferences automatically (e.g., *"I prefer dark mode"*, *"I work in Python"*).
- **Context Budget Manager (`ConversationContextManager`)**:
  - Dynamically calculates token counts.
  - Reserves guaranteed budget for system prompt, long-term memories, and latest exchanges, intelligently pruning older middle turns.
- **Contradiction Avoidance**: Detects and updates existing memories when the user's preferences change rather than storing contradictory facts.

---

## 7. Windows System Integration & Lifecycle

### 7.1. Windows System Tray (`TrayIconManager`)
- Resides in the Windows notification area with companion robot icon.
- **System Tray Menu Options**:
  - 🤖 **Show / Hide Character**: Toggles companion visibility.
  - 💬 **Open Chat**: Restores or opens conversation window.
  - 🎙️ **Voice Window**: Opens voice visualizer dialog.
  - 🎙 **Voice Mode**: Submenu with radio selection (Continuous, Push-to-Talk, Off).
  - 🛑 **Emergency Stop**: Immediately kills speech synthesis and listening.
  - 🌙 **Sleep Mode**: Puts companion to sleep.
  - ⚙️ **Settings...**: Launches configuration dialog.
  - ⏻ **Exit AI Friend**: Coordinated graceful shutdown.

### 7.2. Global Windows Hotkeys (`GlobalHotkeyManager`)
- System-wide keyboard shortcuts active even when the application is unfocused or minimized:
  - **Emergency Stop**: Instantly cuts off audio output.
  - **Voice Toggle**: Toggles microphone listening.
  - **Push-to-Talk**: Global push-to-talk key.
  - **Chat Toggle**: Quick summon hotkey to raise the chat window.

### 7.3. Single-Instance Mutex Guard (`SingleInstanceGuard`)
- Uses `QLocalServer` / named local socket mutex to enforce a single running application instance.
- Launching a second instance passes CLI parameters to the active instance, raises the companion to the foreground, and exits cleanly.

### 7.4. Windows Startup & Registry Integration (`StartupManager`)
- Configurable toggle in settings to launch AI Desktop Friend on Windows login.
- Writes / removes registry entry cleanly in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

### 7.5. Multi-Monitor & DPI Safety (`WindowsIntegration`)
- **DPI Scaling**: Uses Qt per-monitor High-DPI scaling (`HighDpiScaleFactorRoundingPolicy.PassThrough`).
- **Screen Bounds Revalidation**: Listens to Windows display change events; automatically relocates companion if a monitor is disconnected so the widget is never lost off-screen.

### 7.6. Floating Toast Notifications (`NotificationToast`)
- Non-intrusive floating toast notifications with slide-in/fade animations in the bottom-right corner for background alerts, reminders, and system status updates.

---

## 8. Backend API & Real-Time WebSocket Infrastructure

### 8.1. Local FastAPI HTTP Server (`app/api/server.py` on port `8765`)
The backend provides a comprehensive RESTful surface:
- **System & Diagnostics**: `GET /api/health`, `GET /api/diagnostic/status`, `POST /api/diagnostic/toggle`.
- **Settings & Config**: `GET /api/config`, `PUT /api/config`.
- **Conversations**: `GET /api/conversations`, `POST /api/conversations`, `PATCH /api/conversations/{id}`, `DELETE /api/conversations/{id}`.
- **Messages & Streaming**: `GET /api/conversations/{id}/messages`, `POST /api/conversations/{id}/messages`, `DELETE /api/conversations/{id}/messages`.
- **AI Control**: `POST /api/ai/cancel`, `GET /api/models`, `POST /api/models/select`.
- **Voice Engine**: `GET /api/voice/status`, `POST /api/voice/toggle`, `POST /api/voice/mode`, `POST /api/voice/ptt/start`, `POST /api/voice/ptt/stop`, `POST /api/voice/engine`, `POST /api/voice/speed`, `POST /api/voice/volume`, `GET /api/voice/devices`, `POST /api/voice/stop`, `POST /api/voice/mute`, `POST /api/voice/test`.
- **Memory Management**: `GET /api/memories`, `POST /api/memories`, `DELETE /api/memories/{id}`.
- **Desktop Windowing**: `GET /api/pet/status`, `POST /api/pet/topmost`, `POST /api/pet/show`, `POST /api/pet/hide`, `POST /api/pet/reset_position`, `POST /api/window/minimize`, `POST /api/window/maximize`, `POST /api/window/close`, `POST /api/window/drag`, `POST /api/window/move_delta`.
- **Export**: `POST /api/chat/export`.

### 8.2. Real-Time WebSocket Channel (`/ws`)
- Bi-directional broadcast channel pushing events:
  - `ai_chunk`: Live streaming token chunks.
  - `ai_complete`: Finished response payload.
  - `ai_cancelled`: Immediate cancellation signal.
  - `voice_state`: Voice state changes (`listening`, `processing`, `speaking`, `off`).
  - `audio_level`: Live microphone RMS amplitude (for UI visualizers).
  - `message_added`: Instant sync when messages are posted.
  - `character_state`: Avatar animation state transitions.
  - `config_updated`: Instant multi-window setting synchronization.

---

## 9. Configuration, Diagnostics & First-Run Setup

### 9.1. Persistent Settings (`ConfigManager`)
- Stored as JSON in `%LOCALAPPDATA%\AIDesktopFriend\AIDesktopFriend\settings.json`.
- Thread-safe access with deep-merged default fallbacks (`default_config.json`).
- Dynamic change signals: `setting_changed(key_path, new_value)`.

### 9.2. Settings Dialog (`SettingsDialog` — 10 Categories)
1. **General**: App name, dark theme, run on Windows startup, minimize to tray.
2. **AI**: Active Ollama model selection, companion name, personality style, temperature slider, max tokens, response verbosity.
3. **Voice**: Voice mode (Continuous, PTT, Wake Word, Off), wake word custom phrase, silence detection delay.
4. **Audio**: Input microphone device selector, output speaker selector, volume slider, speech rate slider, test voice button.
5. **Appearance**: Companion size presets (Small 80px, Medium 120px, Large 150px, Custom slider), opacity, animation FPS target.
6. **Character**: Character avatar selector (`robot`, `companion`, etc.), idle animation behaviors.
7. **Memory**: Long-term memory toggle, auto-extraction toggle, table view of stored memories with search and deletion.
8. **Shortcuts**: Global hotkey custom key combination assignments.
9. **Startup**: First-run tutorial launch, default display positioning reset.
10. **Privacy**: Audio storage policy (never store raw audio), local database reset, memory purge button.

### 9.3. Onboarding Setup Wizard (`SetupWizard`)
- Multi-step wizard shown on initial launch:
  - Step 1: Welcome & feature overview.
  - Step 2: Ollama check & automatic model download / validation.
  - Step 3: Microphone selection & live volume test.
  - Step 4: Speaker selection & audio playback check.
  - Step 5: Companion customization (naming and personality selection).

### 9.4. Diagnostic Mode (`DiagnosticTracker`)
- Comprehensive diagnostic pipeline tracking latency and success metrics across all stages:
  - Audio capture latency → VAD detection → STT transcription → LLM prompt dispatch → Time-to-first-token → Sentence chunking → TTS synthesis → Audio playback.
- Visual inspection via developer tools or telemetry HUD.

---

## 10. Summary Matrix: Where to Suggest New Features

When prompting an LLM to propose new features for this project, consider suggesting extensions in these open domains:

| Domain | What Is Built | High-Value Opportunities for New Features |
| :--- | :--- | :--- |
| **System Automations & OS Tools** | Basic Windows integration, tray, startup registry | Windows tool execution (open app, launch URL, check battery, volume controls, file searching, window management). |
| **Local RAG & Document Intelligence** | Conversation history, FTS5 memory database | Local file reading (PDF, TXT, DOCX), desktop search, code snippet analysis, workspace awareness. |
| **Vision & Screen Awareness** | Speech and text input only | Local multimodal vision models (screen analysis, screenshot questions, webcam companion reactions). |
| **Web & Real-Time Information** | 100% offline local knowledge only | Optional local privacy-preserving search (DuckDuckGo / SearXNG / weather tools) through function calling. |
| **Companion Mechanics & Gamification** | 8 animations, states, size presets | Tamagotchi / leveling mechanics, daily streaks, mood meters, customizable outfits, unlockable accessories. |
| **Productivity & Time Management** | Real-time chat & voice commands | Pomodoro timer, desktop voice reminders, calendar alerts, task list integration. |
| **Model & Inference Expansion** | Ollama local HTTP API | Support for vLLM, LM Studio, llama.cpp, or DirectML/WebGPU hardware acceleration. |
| **Voice & Speech Enhancements** | Kokoro, Piper, SAPI5, Faster-Whisper | Voice cloning (via Coqui / Chatterbox / F5-TTS), custom wake word training, emotional voice inflection. |

---
*Generated for AI Desktop Friend (Windows Desktop + FastAPI + React + Ollama).*
