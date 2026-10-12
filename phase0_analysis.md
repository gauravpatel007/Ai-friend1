# 🟢 Phase 0 — Analysis & Understanding

> No implementation in this phase. This is my read-back of the full requirement to confirm I understand exactly what we're building.

---

## What We're Building

An **AI Desktop Companion** — a floating, animated character that lives on the Windows desktop.
- No browser window, no big app window
- A small cute robot character floats on screen (always on top)
- Fully **local** — no cloud API required
- Talks back via voice, remembers conversations, expresses emotions

---

## The 4 Core Modules

### 1. 🖥️ Desktop Pet (UI Layer — PySide6)
| Interaction | Result |
|---|---|
| Left-click | Quick chat window |
| Right-click | Options menu |
| Drag | Move character anywhere |
| Double-click | Toggle voice mode |
| Hover | Show mini control panel |

Critical requirements: transparent window, always-on-top, draggable, system tray, no click interference outside character bounds.

---

### 2. 🎙️ Voice System (Three Modes)

| Mode | How it works |
|---|---|
| Push-to-Talk | Click mic → speak |
| Wake Word | Say "Hey Buddy" → AI wakes up |
| Continuous | AI listens automatically, natural back-and-forth |

**Continuous conversation is the ultimate goal.**

Key voice requirements:
- Interruption support (stop AI mid-speech)
- Silence detection (Silero VAD)
- Noise filtering
- English + Hindi (Gujarati = future)
- Audio device selection

---

### 3. 🧠 AI Intelligence Layer (Ollama + SQLite Memory)

Not just a chatbot — a **companion**. Key behaviors:
- Short, casual, natural replies (not formal walls of text)
- **Short-term memory**: current conversation context
- **Long-term memory**: SQLite FTS5 for searching past sessions
- Remembers things across days (e.g., "Last time you were learning LangChain")
- Consistent personality
- Emotional awareness
- Streaming responses (text appears progressively)
- User can give the companion a custom name

---

### 4. 🎭 Character Animation System (Sprite Sheets)

| State | Animation |
|---|---|
| Idle | Breathing + blinking |
| Listening | Alert look, subtle movement |
| Thinking | Looking around |
| Speaking | Mouth + body movement |
| Happy | Small jump or smile |
| Confused | Head tilt |
| Sleeping | Eyes closed |
| Dragging | Follows mouse |
| Waking Up | Activation animation |
| Muted | Muted indicator shown |
| Error | Confused/error expression |

**Design**: Original small cute robot, rounded body, expressive face, 2D sprites (not 3D — saves resources).

---

## Technology Stack (Locked In)

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Desktop UI | PySide6 + Qt Style Sheets |
| Animations | Qt + Sprite Sheets |
| LLM Runtime | Ollama (local HTTP API) |
| AI Model | Qwen3 1.7B (default), Qwen3 4B (better) |
| STT | Faster-Whisper (CTranslate2) |
| VAD | Silero VAD (ONNX) |
| TTS | Piper TTS (start), Kokoro TTS (upgrade) |
| Wake Word | openWakeWord |
| Audio Capture | sounddevice |
| Audio Processing | NumPy + soundfile |
| Storage | SQLite + FTS5 |
| Config | JSON |
| Threading | QThread + worker processes |
| Packaging | PyInstaller + Inno Setup |
| Testing | pytest + pytest-qt |

> ⚠️ **Licensing Note**: Piper is GPL-3.0-or-later. Some openWakeWord models are non-commercial. Must review before distribution.

---

## Hardware Target

- **Your machine**: Windows 11, ~8 GB RAM, CPU-only (no GPU)
- Initial config prioritizes low RAM footprint:
  - Qwen3 1.7B (not 4B)
  - Faster-Whisper Tiny/Base
  - Piper TTS
  - Silero ONNX VAD
- **Expectation**: Will NOT match ChatGPT voice speed. Architecture must gracefully degrade.

---

## System Architecture (Simplified)

```
Windows Desktop
    └── AI Desktop Friend (PySide6)
         ├── Desktop Pet UI
         │    ├── Animations (Sprite Sheets)
         │    └── Controls (click, drag, hover)
         └── Application Core
              ├── AI Manager
              │    ├── Ollama → Qwen3
              │    └── Memory → SQLite
              └── Voice Manager
                   ├── Faster-Whisper (STT)
                   └── Silero VAD
                        └── → Response Manager
                                  └── Piper TTS → Audio Playback → Character Speaking
```

---

## Performance Targets

| Requirement | Target |
|---|---|
| Animations | 30 FPS |
| UI | Never block during AI processing |
| Streaming | Show text before full response done |
| Audio | Start playing first TTS chunk early |
| Mic interrupt | Stop AI playback immediately |
| Offline | Full functionality after initial setup |

---

## Privacy Requirements (Non-Negotiable)

- Mic must be **explicitly enabled** by user
- Always show a **visible indicator** when listening
- Instant **mute button** always accessible
- No raw audio stored by default
- All data stays **local only**
- User can delete conversations and memories at any time
- Ollama bound to localhost only
- No keylogging, no screenshots, no silent mic reactivation

---

## 4 UI Interfaces

1. **Desktop Pet** — the character itself (frameless, transparent)
2. **Quick Chat Window** — compact panel next to character
3. **Settings Window** — General / AI / Voice / Privacy tabs
4. **System Tray** — Show/Hide, Voice, Sleep, Chat, Settings, Exit

---

## ✅ My Understanding — Ready for Phase 1

Phase 0 is complete on the planning side. I have a clear picture of:
- What we're building (animated AI companion on Windows desktop)
- How each module works and interacts
- The exact tech stack with rationale
- Hardware constraints and performance expectations
- Privacy requirements

**Waiting for you to share Phase 1 before writing a single line of code.**
