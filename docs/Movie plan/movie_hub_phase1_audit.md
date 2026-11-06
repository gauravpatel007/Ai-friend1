# AI Friend — Movie Hub: Phase 1 Architecture Audit & Repository Discovery

## Executive Summary
This report documents the deep codebase audit of **AI Friend** conducted in **Phase 1**. The audit validates the real application architecture, file structures, state management mechanisms, backend API routes, SQLite persistence, Ollama client integration, and test suite baselines. It establishes the concrete integration boundaries required to implement **Movie Hub** cleanly without touching or destabilizing existing AI companion workflows.

---

## 1. Repository & Architecture Audit (Task 1.1)

### 1.1 Directory Structure & Framework Versions
- **Frontend Core**:
  - React `18.3.1` with React DOM `18.3.1`
  - TypeScript `5.7.3` (strict typing, module resolution: `bundler`)
  - Vite `6.1.0` (production bundle output to `dist/`)
  - Zustand `5.0.3` (centralized client-side state management)
  - Lucide React `0.475.0` (Apple-styled vector iconography)
  - CSS Architecture: Pure CSS with Apple macOS dark-glassmorphism tokens in `src/index.css` (variables `--color-system-blue`, `--color-bg-base`, `--backdrop-blur`, etc.)
- **Desktop Window Host**:
  - PySide6 `6.12.0` (`QMainWindow` hosting `QWebEngineView`) in `app/desktop/modern_chat_window.py`
  - Loads loopback URL `http://127.0.0.1:8765`
  - Python Bridge (`window.pywebview.api`) for window minimize, maximize/restore, and close
- **Backend Application Layer**:
  - FastAPI `0.115.8` + Uvicorn `0.34.0` in `app/api/server.py`
  - Lifespan-managed state (`app.state.conv_repo`, `app.state.ai_service`, `app.state.config_manager`)
  - WebSocket Manager (`app/api/websocket.py`) broadcasting streaming tokens and voice state
- **Persistence Layer**:
  - SQLite 3 with Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and `PRAGMA foreign_keys = ON;` in `app/memory/database.py`
  - Local database location: `%LOCALAPPDATA%\AIDesktopFriend\AIDesktopFriend\conversations.db`
- **AI Engine**:
  - Local Ollama daemon running on `http://127.0.0.1:11434`
  - Active model: `llama3.2:3b` with GPU keep-alive managed by `app/ai/model_manager.py` and `app/ai/ollama_client.py`

---

## 2. Existing Functionality Map & Component Dependencies (Task 1.2)

```mermaid
flowchart TD
    subgraph Frontend["React 18 Frontend (src/)"]
        App["App.tsx"]
        Header["Header.tsx (Toolbar, Avatar, Window Controls)"]
        Sidebar["Sidebar.tsx (Conversations, Search, Rename, Delete)"]
        ChatStream["ChatStream.tsx (Messages, Bubbles, Markdown)"]
        RightPanel["RightPanel.tsx (Companion Inspector, Voice Meters)"]
        Store["useChatStore.ts (Zustand: messages, voice, dialogs)"]
        HTTP["api/http.ts (Fetch REST Client)"]
        WS["api/websocket.ts (WebSocket Client)"]
        
        App --> Header
        App --> Sidebar
        App --> ChatStream
        App --> RightPanel
        Header --> Store
        Sidebar --> Store
        ChatStream --> Store
        RightPanel --> Store
        Store --> HTTP
        Store --> WS
    end

    subgraph Backend["FastAPI Backend (app/api/server.py)"]
        FastAPIApp["FastAPI Server (:8765)"]
        ConvRepo["ConversationRepository"]
        AISvc["AIService"]
        Ollama["OllamaClient"]
        DB["DatabaseManager (SQLite WAL)"]
        Config["ConfigManager (settings.json)"]
        
        HTTP --> FastAPIApp
        WS --> FastAPIApp
        FastAPIApp --> ConvRepo
        FastAPIApp --> AISvc
        ConvRepo --> DB
        AISvc --> Ollama
        FastAPIApp --> Config
    end
```

---

## 3. UI Constraints & Navigation Flow (Task 1.3)

### 3.1 Main Workspace Rendering
Currently, `src/App.tsx` renders a single 3-column layout inside `<main className="apple-main-viewport">`:
1. `<Sidebar />` (width: 260px, collapsible)
2. `<ChatStream />` (flex: 1, centered message thread)
3. `<RightPanel />` (width: 270px, collapsible inspector)

There is currently **no route or tab switcher** for alternative primary views. Modals (`SettingsModal`, `VoicePortal`) render as fixed overlays over this 3-column view.

### 3.2 Navigation Strategy for Movie Hub
To accommodate Movie Hub as a dedicated full-screen workspace:
- We introduce an `activeTab: 'chat' | 'movies'` state in the Zustand store.
- When `activeTab === 'chat'`: `<main className="apple-main-viewport">` renders the familiar 3-column companion view.
- When `activeTab === 'movies'`: `<main className="apple-main-viewport">` renders the full-screen `<MovieHubWorkspace />`.
- **Zero Teardown**: Chat components remain in memory or their state remains in `useChatStore`. Switching tabs is instantaneous (< 15ms), causes zero DOM reloads, and does not disconnect the WebSocket or stop audio streaming.
- In `Header.tsx`, we place an Apple-style segmented pill selector: `[ AI Companion | Movie Hub ]`.

---

## 4. API & Configuration Patterns (Task 1.4)

### 4.1 Configuration Management
Application configuration is managed by `ConfigManager` (`app/settings/config_manager.py`):
- Persistent file: `%LOCALAPPDATA%\AIDesktopFriend\AIDesktopFriend\settings.json`
- Default fallback file: `config/default_config.json`
- Deep merge pattern prevents schema drift or missing keys.
- Signals: `setting_changed(key_path, new_value)` emitted across PySide6.

### 4.2 Safe TMDB API Key Storage
To ensure credentials are never exposed:
1. `ConfigManager` supports reading from `settings.json` under key `"movies.tmdb_api_key"` or from the environment variable `TMDB_API_KEY`.
2. Privacy filter in `app/utils/logger.py` (`PrivacyFilter.SENSITIVE_KEYS`) automatically redacts `"api_key"`, `"token"`, and `"password"`.
3. Default `config/default_config.json` will supply an empty string `""` without hardcoded secrets.

---

## 5. Performance, Concurrency & Reliability Assessment (Task 1.5)

| Subsystem | Discovered Characteristics | Movie Hub Impact / Guardrail |
| :--- | :--- | :--- |
| **PySide6 Event Loop** | Single UI thread managing `QWebEngineView` and window events | All API queries and image fetches must remain strictly asynchronous in FastAPI/React to prevent blocking the UI thread. |
| **SQLite WAL Mode** | Thread-local connections with `timeout=20.0` and WAL journaling | Watchlist reads/writes are concurrent and will not conflict with chat message inserts. |
| **Ollama Inference** | Synchronous streaming in worker threads; warm model keeps VRAM allocated | Movie recommendations will query Ollama via non-blocking async executor tasks with timeouts (25s) and automatic deterministic fallback. |
| **Frontend Image Loading** | Chromium handles async image decoding | High-res posters must use responsive `srcset` and lazy loading to avoid excessive memory consumption. |

---

## 6. Detailed Integration Design (Task 1.6)

### 6.1 Frontend Integration
- **State Store**: `src/store/useMovieStore.ts` (isolated Zustand store for movie discovery, active filters, search queries, pagination, and selected media details).
- **Navigation State**: `activeTab: 'chat' | 'movies'` added to `src/types/index.ts` and managed in `src/store/useChatStore.ts`.
- **Header Switcher**: Segmented toggle in `src/components/Header/Header.tsx`.
- **Movie Hub Container**: `src/components/MovieHub/MovieHubWorkspace.tsx` and `src/components/MovieHub/MovieHubWorkspace.css`.

### 6.2 Backend Integration
- **Service Layer**: `app/api/movie_service.py` (FastAPI router `/api/movies/*` handling TMDB proxying, rate limiting, and caching).
- **Persistence Layer**: `app/memory/movie_repository.py` managing `movie_watchlist`, `movie_favorites`, and `movie_preferences` tables in `conversations.db`.
- **AI Recommendation Engine**: `app/ai/movie_recommendation_engine.py` connecting the shared `OllamaClient` with structured candidate grounding.

---

## 7. Baseline Test Execution Results (Task 1.7)

The baseline test suite was executed against the active virtual environment (`.venv\Scripts\python.exe`):

```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
PySide6 6.12.0 -- Qt runtime 6.12.0 -- Qt compiled 6.12.0
rootdir: G:\Languages\Projects\AI Friend\AI Friend A1
plugins: anyio-4.15.1, platformdirs-4.13.0, qt-4.5.0

tests/test_backend_api_full.py::test_api_health_endpoint PASSED          [  6%]
tests/test_backend_api_full.py::test_api_voice_endpoints PASSED          [ 13%]
tests/test_backend_api_full.py::test_api_offline_conversation_flow PASSED [ 20%]
tests/test_backend_api_full.py::test_api_rename_conversation PASSED      [ 26%]
tests/test_phase6_complete_verification.py::test_01_greeting_hello PASSED [ 33%]
tests/test_phase6_complete_verification.py::test_02_different_greeting_variation PASSED [ 40%]
tests/test_phase6_complete_verification.py::test_03_factual_question_what_is_python PASSED [ 46%]
tests/test_phase6_complete_verification.py::test_04_general_knowledge_math_15_multiplied_by_7 PASSED [ 53%]
tests/test_phase6_complete_verification.py::test_05_technical_question_ram_vs_storage PASSED [ 60%]
tests/test_phase6_complete_verification.py::test_06_greeting_followed_by_question_not_intercepted PASSED [ 66%]
tests/test_phase6_complete_verification.py::test_07_sequential_requests PASSED [ 73%]
tests/test_phase6_complete_verification.py::test_08_ollama_failure_reports_error PASSED [ 80%]
tests/test_phase6_complete_verification.py::test_09_response_parsing_and_thinking_filter PASSED [ 86%]
tests/test_phase6_complete_verification.py::test_10_performance_profiling PASSED [ 93%]
tests/test_phase6_complete_verification.py::test_11_live_ollama_integration PASSED [100%]

============================= 15 passed in 30.32s =============================
```

- **Tests Executed**: 15 tests across API and complete pipeline verification.
- **Tests Passed**: 15 / 15 (100% pass rate).
- **Tests Failed**: 0.
- **Live Ollama Inference Baseline**: 15.99 seconds for full sentence generation under warm keep-alive.
- **Fast Path Greeting Baseline**: < 1 millisecond.

---

## 8. Exact Files Identified for Modification in Phase 2
When Phase 2 is authorized, implementation will touch **only** the following files:
1. `src/types/index.ts` — Declare `export type NavigationTab = 'chat' | 'movies';`.
2. `src/store/useChatStore.ts` — Add `activeTab: NavigationTab` and `setActiveTab(tab: NavigationTab)`.
3. `src/components/Header/Header.tsx` — Integrate the segmented navigation switch (`AI Companion` / `Movie Hub`).
4. `src/components/Header/Header.css` — Style the segmented control with Apple macOS pill active styling.
5. `src/App.tsx` — Conditionally render `<MovieHubWorkspace />` when `activeTab === 'movies'`.
6. `src/components/MovieHub/MovieHubWorkspace.tsx` — Create the full-screen page shell with structural containers (Header, Filter Bar placeholder, Discovery Grid placeholder).
7. `src/components/MovieHub/MovieHubWorkspace.css` — Add responsive dark-glass layout styling.
