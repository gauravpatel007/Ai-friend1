# AI Desktop Friend — Tauri + React Migration Plan

> **Stack:** Tauri 2 (Rust shell) · React 19 + TypeScript · Vite 6 · Vanilla CSS Variables  
> **Backend:** Python backend kept 100% intact, exposed as a local FastAPI + WebSocket server  
> **Strategy:** Hybrid — Python backend runs as a subprocess sidecar managed by Tauri

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  TAURI 2 (RUST SHELL)               │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │        React 19 + TypeScript + Vite           │   │
│  │  ┌──────┐ ┌─────────────┐ ┌──────────────┐  │   │
│  │  │Sidebar│ │  Chat View  │ │  Right Panel │  │   │
│  │  └──────┘ └─────────────┘ └──────────────┘  │   │
│  └──────────────────────────────────────────────┘   │
│                        │                            │
│              Tauri IPC (invoke / events)             │
│                        │                            │
│  ┌──────────────────────────────────────────────┐   │
│  │      Tauri Commands (Rust → Python Bridge)    │   │
│  └──────────────────────────────────────────────┘   │
│                        │                            │
│              HTTP REST + WebSocket                   │
│                        │                            │
└────────────────────────┼────────────────────────────┘
                         │  (localhost:8765)
          ┌──────────────▼──────────────────┐
          │     Python FastAPI Server        │
          │  ┌─────────┐ ┌───────────────┐  │
          │  │AI Service│ │Voice Service  │  │
          │  └─────────┘ └───────────────┘  │
          │  ┌─────────┐ ┌───────────────┐  │
          │  │ Memory  │ │Config Manager │  │
          │  └─────────┘ └───────────────┘  │
          │        (All existing Python)     │
          └─────────────────────────────────┘
```

---

## Color Design Tokens (Vanilla CSS Variables)

```css
:root {
  /* Backgrounds */
  --color-bg-primary:    #080F20;
  --color-bg-secondary:  #0D1930;
  --color-bg-sidebar:    #101D35;
  --color-bg-card:       #172540;
  --color-bg-hover:      #203555;

  /* Brand */
  --color-blue:          #1674FF;
  --color-cyan:          #00D4FF;
  --color-purple:        #7558FF;

  /* Text */
  --color-text-primary:  #F4F7FF;
  --color-text-secondary:#9CAFCB;

  /* Utilities */
  --color-border:        #263A5B;
  --color-success:       #00DC8C;
  --color-error:         #EF4444;
  --color-rose:          #F43F5E;

  /* Radii */
  --radius-window:  20px;
  --radius-card:    14px;
  --radius-pill:    999px;
  --radius-sm:       8px;

  /* Shadows */
  --shadow-window:  0 8px 48px 0 rgba(0,212,255,0.12), 0 2px 24px 0 rgba(0,0,0,0.7);
  --shadow-card:    0 2px 12px 0 rgba(0,0,0,0.4);
  --shadow-glow-blue: 0 0 16px 2px rgba(22,116,255,0.35);
  --shadow-glow-cyan: 0 0 14px 2px rgba(0,212,255,0.28);
}
```

---

## Phase 1 — Python Backend: FastAPI HTTP + WebSocket Server

**Files to create inside `app/api/`:**

### 1.1 `app/api/server.py` — FastAPI Application
Endpoints to expose:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/config` | Full config JSON |
| `PUT` | `/api/config` | Update setting key |
| `GET` | `/api/conversations` | List all conversations |
| `POST` | `/api/conversations` | Create new conversation |
| `DELETE` | `/api/conversations/{id}` | Delete conversation |
| `GET` | `/api/conversations/{id}/messages` | Get messages |
| `POST` | `/api/conversations/{id}/messages` | Send user message |
| `GET` | `/api/models` | List available Ollama models |
| `POST` | `/api/voice/toggle` | Toggle voice on/off |
| `POST` | `/api/voice/stop` | Stop voice |
| `POST` | `/api/voice/mute` | Mute toggle |
| `GET` | `/api/companion/state` | Current character state |
| `POST` | `/api/chat/export` | Export chat as markdown |

### 1.2 `app/api/websocket.py` — Real-time WebSocket Events
WebSocket at `ws://localhost:8765/ws`

**Server → Client Events (JSON):**
```jsonc
{ "type": "ai_chunk",        "data": { "text": "Hello " } }
{ "type": "ai_complete",     "data": { "text": "Hello there!", "msg_id": 42 } }
{ "type": "ai_error",        "data": { "message": "Timeout" } }
{ "type": "voice_state",     "data": { "state": "listening" } }
{ "type": "char_state",      "data": { "state": "thinking" } }
{ "type": "transcription",   "data": { "text": "What is Python?" } }
{ "type": "memory_stored",   "data": { "memory": {...} } }
```

**Client → Server Events:**
```jsonc
{ "type": "cancel_generation" }
{ "type": "ping" }
```

### 1.3 `main_api.py` — New Backend Entry Point
- Starts FastAPI via `uvicorn` on `localhost:8765`
- Initializes `AIService`, `VoiceService`, `MemoryManager`, `ConfigManager`
- Bridges Qt signals → WebSocket broadcast
- **No PySide6/Qt desktop windows** (no GUI, pure backend)

---

## Phase 2 — Tauri 2 Shell Setup

### 2.1 Project Structure
```
A1/
├── app/                  # Python backend (unchanged)
├── main.py               # OLD Qt entry (kept for backward compat)
├── main_api.py           # NEW FastAPI entry point
├── src-tauri/            # Tauri Rust shell
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── src/
│   │   ├── main.rs       # Tauri setup + Python sidecar spawn
│   │   ├── commands.rs   # Tauri IPC commands
│   │   └── sidecar.rs    # Python process manager
│   └── icons/            # App icons (copy from assets/)
├── src/                  # React frontend
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css         # Global CSS variables
│   ├── api/
│   │   ├── http.ts       # Fetch wrapper for REST calls
│   │   └── websocket.ts  # WS client with auto-reconnect
│   ├── components/
│   │   ├── Header/
│   │   ├── Sidebar/
│   │   ├── ChatStream/
│   │   ├── RightPanel/
│   │   └── shared/
│   ├── hooks/
│   │   ├── useChat.ts
│   │   ├── useWebSocket.ts
│   │   └── useVoice.ts
│   ├── store/
│   │   └── useChatStore.ts  # Zustand global state
│   └── types/
│       └── index.ts
├── vite.config.ts
├── tsconfig.json
└── package.json
```

### 2.2 `tauri.conf.json` Key Settings
```json
{
  "app": {
    "windows": [{
      "title": "AI Desktop Friend",
      "width": 1040,
      "height": 680,
      "minWidth": 840,
      "minHeight": 520,
      "decorations": false,
      "transparent": true,
      "alwaysOnTop": true,
      "skipTaskbar": false
    }]
  },
  "bundle": {
    "identifier": "com.aidesktopfriend.app",
    "sidecar-binaries": ["binaries/ai-backend"]
  }
}
```

### 2.3 `src-tauri/src/main.rs` — Python Sidecar Launch
```rust
// On app startup: spawn Python backend as child process
fn spawn_python_backend() {
    // Use `python main_api.py` or bundled PyInstaller exe
    // Monitor process health, restart on crash
    // Kill on app exit
}
```

---

## Phase 3 — React Frontend Components

### 3.1 Component Tree
```
App
├── TitleBar            (custom window controls: minimize, maximize, close)
├── Header
│   ├── BuddyAvatar     (animated CSS ring + avatar image)
│   ├── TitleBlock      (title + status dot + subtitle)
│   ├── VoicePill       (mic icon + Voice On/Off toggle)
│   └── ToolbarButtons  (New Chat, History, Settings)
├── MainBody
│   ├── Sidebar
│   │   ├── SearchBar
│   │   ├── NewChatButton
│   │   ├── ConversationList
│   │   │   └── ConversationItem[]
│   │   └── SidebarFooter   (24 Conversations, storage, settings icon)
│   ├── ChatStream
│   │   ├── DateSeparator
│   │   ├── MessageList
│   │   │   ├── AiMessage[]
│   │   │   │   ├── BuddyAvatar (36px)
│   │   │   │   ├── MessageBubble
│   │   │   │   └── MessageActions (copy, regen, like, dislike)
│   │   │   └── UserMessage[]
│   │   │       ├── MessageBubble
│   │   │       └── UserAvatar (36px)
│   │   ├── ThinkingIndicator   (animated dots)
│   │   └── ChatInputBar
│   │       ├── AttachButton
│   │       ├── TextArea (auto-grow)
│   │       ├── EmojiButton
│   │       └── SendButton
│   └── RightPanel
│       ├── CompanionCard
│       │   ├── CompanionAvatar (120px animated)
│       │   ├── CompanionName
│       │   └── CompanionBio
│       ├── StatusCard          (Ready to chat · Local AI)
│       ├── VoiceControls       (Voice, Stop, Mute buttons)
│       ├── QuickActions        (New Chat, View History, Clear, Export)
│       ├── ModelSelector       (dropdown of Ollama models)
│       └── VoiceSettings       (AI Voice, Speed slider, Volume slider, Test Voice)
```

### 3.2 Key React Hooks

```typescript
// useWebSocket.ts — auto-reconnecting WS with event dispatch
// useChat.ts — message list, streaming append, conversation CRUD
// useVoice.ts — voice state, toggle/stop/mute + real-time WS state
// useConversations.ts — sidebar list, active conversation, search
```

### 3.3 CSS Architecture (Vanilla CSS, no Tailwind)

Each component has a co-located `ComponentName.css` file:
- No utility classes — pure semantic selectors
- All colors from CSS variables only
- Animations in `@keyframes` blocks
- Glassmorphism via `backdrop-filter: blur()`

**Key animations:**
- `@keyframes glow-pulse` — status dot breathing
- `@keyframes thinking-dot` — 3-dot bounce with stagger delay
- `@keyframes bubble-in` — message slide-up + fade-in
- `@keyframes ring-glow` — buddy avatar neon ring shimmer

---

## Phase 4 — State Management (Zustand)

```typescript
// useChatStore.ts
interface ChatStore {
  conversations: Conversation[];
  activeConvId: string | null;
  messages: Record<string, Message[]>;
  isStreaming: boolean;
  streamingText: string;
  voiceState: 'off' | 'listening' | 'thinking' | 'speaking';
  companionState: 'idle' | 'listening' | 'thinking' | 'speaking' | 'happy';
  availableModels: string[];
  selectedModel: string;

  // Actions
  loadConversations(): void;
  selectConversation(id: string): void;
  sendMessage(text: string): void;
  cancelGeneration(): void;
  toggleVoice(): void;
}
```

---

## Phase 5 — Tauri Window Chrome

Since `decorations: false` (frameless), the React `<TitleBar>` component handles:

- **Drag region** via `data-tauri-drag-region` attribute on header
- **Minimize** via `import { getCurrentWindow } from '@tauri-apps/api/window'; win.minimize()`
- **Maximize/Restore** via `win.toggleMaximize()`
- **Close** via `win.close()` (hides to tray vs. fully closes depending on config)
- **Rounded corners** via CSS `border-radius: 20px` on root + `overflow: hidden`
- **Glow shadow** via CSS `box-shadow: var(--shadow-window)` on root container

---

## Implementation Phases — Timeline

| Phase | Work | Est. |
|-------|------|------|
| **P1** | Add FastAPI `app/api/server.py` + all REST routes | 2–3 hrs |
| **P2** | WebSocket bridge (Qt signals → JSON broadcast) | 1–2 hrs |
| **P3** | `main_api.py` entry point (no Qt GUI) | 1 hr |
| **P4** | Tauri 2 project scaffold + Python sidecar in `main.rs` | 1–2 hrs |
| **P5** | `index.css` full CSS variable design system | 1 hr |
| **P6** | Shared components: Avatar, GlowDot, Bubble, DateSeparator | 2 hrs |
| **P7** | Header: BuddyAvatar, TitleBlock, VoicePill, Toolbar, TitleBar | 2 hrs |
| **P8** | Sidebar: Search, NewChat, ConversationList, Footer | 2 hrs |
| **P9** | ChatStream: Messages, ThinkingIndicator, InputBar | 3 hrs |
| **P10** | RightPanel: CompanionCard, VoiceControls, QuickActions, ModelSelector, VoiceSettings | 3 hrs |
| **P11** | Zustand store + WS hooks + HTTP client | 2 hrs |
| **P12** | Wire all real-time streaming (AI chunks → bubble append) | 2 hrs |
| **P13** | System tray (Tauri tray API) + minimize-to-tray behavior | 1 hr |
| **P14** | Desktop Pet companion window (separate Tauri window) | 3 hrs |
| **P15** | Testing, packaging, PyInstaller sidecar bundling | 2 hrs |

**Total: ~30–32 hrs of focused development**

---

## NPM Dependencies

```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "zustand": "^5.0.0",
    "@tauri-apps/api": "^2.0.0",
    "@tauri-apps/plugin-shell": "^2.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.0.0",
    "typescript": "^5.0.0",
    "vite": "^6.0.0",
    "@tauri-apps/cli": "^2.0.0"
  }
}
```

## Python Backend Dependencies (new)

```
fastapi
uvicorn[standard]
websockets
```

---

## Key Design Decisions

> [!IMPORTANT]
> The Python backend (`app/ai`, `app/voice`, `app/memory`, `app/settings`) is **completely untouched**. Only `app/desktop/` (PySide6 UI files) becomes obsolete over time.

> [!TIP]
> The FastAPI server also enables future features: mobile companion app, browser extension, or remote access via tunneling — none of which were possible with the PySide6 architecture.

> [!NOTE]
> During transition, both the old Qt UI (`main.py`) and new Tauri UI (`main_api.py`) can run simultaneously since they share the same Python backend logic.

> [!WARNING]
> The desktop pet companion character animation is the most complex piece. For Phase 14, the animated pet will be a second lightweight Tauri window using a `<canvas>` or CSS sprite animation, replacing the PySide6 `DesktopPetWindow`.
