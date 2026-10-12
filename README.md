# AI Desktop Friend 🤖

An intelligent, animated, offline AI companion that floats on the user's Windows desktop.

## Features
- **Desktop Companion**: Transparent, draggable, always-on-top animated pet.
- **Privacy-First & Local**: Operates completely offline without cloud-based AI services.
- **Voice Interaction**: Push-to-talk, wake word activation, and continuous conversation.
- **Long-Term Memory**: Remembers past conversations and user preferences.
- **Native Windows Foundation**: Built with Python 3.11+ and PySide6 (Qt6).

## Architecture (Phase 1)
```
AI-Desktop-Friend/
├── main.py
├── app/
│   ├── core/           # Central controller, single-instance, signal bus
│   ├── desktop/        # Window management, desktop pet overlay
│   ├── character/      # Animations, sprite sheets, pet state
│   ├── ai/             # Ollama local LLM integration
│   ├── voice/          # Whisper STT, Piper TTS, Silero VAD
│   ├── memory/         # SQLite FTS5 conversation memory
│   ├── settings/       # JSON configuration manager
│   └── utils/          # Logging, helpers
├── assets/
│   ├── characters/
│   ├── animations/
│   ├── icons/
│   └── sounds/
├── config/
├── tests/
└── packaging/
```

## Running the Application
```bash
# Activate virtual environment
.\.venv\Scripts\activate

# Run application
python main.py
```
