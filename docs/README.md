# Documentation Index — AI Desktop Friend

This directory contains the technical documentation, architecture plans, bug reports, and project history for AI Desktop Friend.

## 📁 Directory Structure

```text
docs/
├── features.md                            # Complete Project Feature Matrix & Architecture Map
├── reports/
│   ├── AI_Friend_Full_System_Audit_Report.md  # Full system & backend quality audit report (465 tests, 100% pass)
│   ├── SECURITY_AUDIT_REPORT.md           # Comprehensive hybrid SAST, CORS, and desktop sandbox security audit
│   ├── AI_Friend_Voice_Bug_Fix_Report.md  # Technical report on voice pipeline, VAD, Whisper & turn lifecycle fixes
│   └── broken_features.md                 # Master tracker of fixed bugs, regressions, and architectural root causes
├── plans/
│   └── tauri_migration_plan.md            # Architecture roadmap for Tauri migration
├── notes/
│   ├── Test1.md                           # QA automation, software architecture, and test specifications
│   └── Try1.md                            # Historical execution prompts, testing requirements, and task logs
└── screenshots/
    ├── latest 4 AI Desktop Friend Chat Interface.png  # Multi-state chat UI demonstration
    └── latest_chat_window_preview.png                 # Standalone chat window preview
```

## 📋 Document Summaries

### 1. Feature Matrix & Architecture (`docs/features.md`)
- **[features.md](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/docs/features.md)**: Master inventory of all architectural subsystems, technologies, local APIs, interaction patterns, and companion pet features.

### 2. Reports (`docs/reports/`)
- **[AI_Friend_Full_System_Audit_Report.md](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/docs/reports/AI_Friend_Full_System_Audit_Report.md)**: Full backend and system audit report verifying Ollama streaming, SQLite WAL concurrency, thinking tag suppression, and TTS fallbacks.
- **[SECURITY_AUDIT_REPORT.md](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/docs/reports/SECURITY_AUDIT_REPORT.md)**: Comprehensive security assessment examining local REST APIs, CORS boundaries, CSWSH protections, and Chromium WebEngine sandbox settings.
- **[AI_Friend_Voice_Bug_Fix_Report.md](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/docs/reports/AI_Friend_Voice_Bug_Fix_Report.md)**: Comprehensive deep dive into audio capture, VAD sensitivity, Faster-Whisper parameters, WebSocket streaming, and state machine transitions.
- **[broken_features.md](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/docs/reports/broken_features.md)**: Catalog of 22 identified issues across UI focus trapping, hands-free continuous listening, speech bubbles, memory extraction, and performance optimization with verified solutions.

### 3. Plans (`docs/plans/`)
- **[tauri_migration_plan.md](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/docs/plans/tauri_migration_plan.md)**: Complete blueprint for transitioning the desktop frontend from PySide6 web engine to lightweight Tauri + Rust with native Windows IPC.

### 4. Notes & Specifications (`docs/notes/`)
- **[Test1.md](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/docs/notes/Test1.md)**: Detailed QA automation role requirements, test matrices across 19 sections/14 phases, and validation criteria.
- **[Try1.md](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/docs/notes/Try1.md)**: Historical execution prompts, testing requirements, and task logs.

### 5. Screenshots (`docs/screenshots/`)
- **latest 4 AI Desktop Friend Chat Interface.png**: High-resolution visual showcase of the companion pet and frameless chat interface.
- **latest_chat_window_preview.png**: Visual preview of the chat window.

### 6. Historical Analysis (`BIN/`)
- Additional phase analysis, UI specs, and early mockups are archived in the [BIN/](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/BIN/) directory.

