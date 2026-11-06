# 🚨 AI Desktop Friend — Broken Features List

This document lists all features and subsystems in **AI Desktop Friend** that are **broken, missing, or failing to work as expected**. Working features are strictly omitted.

---

### 1. 🎤 Voice Commands / Hands-Free Intent Execution (Missing)
- **Category:** Voice / Automation
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Saying voice commands (such as *"open settings"*, *"hide pet"*, *"change model"*, *"mute voice"*, *"clear conversation"*, *"minimize"*, *"exit"*) did not trigger any actions and were forwarded directly to the LLM chat pipeline.
- **Root Cause:** There was no voice command parser or intent dispatcher in the application. Any speech transcribed by Whisper STT was unconditionally forwarded directly into the LLM chat pipeline (`ai_service.ask`).
- **Fix Implemented:**
  1. Built [VoiceCommandParser](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/command_dispatcher.py) with multilingual support (English, Hindi, Gujarati), punctuation/conversational prefix stripping, and intelligent rejection of long/informational LLM questions.
  2. Implemented [VoiceCommandDispatcher](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/command_dispatcher.py) with desktop action dispatching via Qt signals, verbal TTS audio acknowledgment, and deduplication guard.
  3. Integrated command interception in [VoiceConversationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py) (`_on_transcription_completed`), [VoiceService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_service.py), and [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py) to prevent command transcriptions from being saved to the chat database or triggering LLM generation.
  4. Verified with 66 comprehensive tests in [test_voice_commands.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_voice_commands.py) (All 66 passed; 80/80 voice regression suite tests passing).

---

### 2. 🦻 "Hey Buddy" Wake-Word Detection & Standby Mode
- **Category:** Voice / Wake-Word
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Uttering the wake phrase *"Hey Buddy"* (or Hindi/Gujarati wake phrases) reliably wakes the companion from low-power standby mode into active listening.
- **Root Cause:** `WakeWordEngine` searched for openWakeWord models via `openwakeword.model.Model(wakeword_models=['hey_buddy'])`, which are not bundled or cached. The fallback acoustic trigger lacked phonetic keyword alignment and required impossible acoustic energy (`rms >= 0.25`). Furthermore, `VoiceService` defaulted to continuous listening or off mode rather than wake-word standby.
- **Fix Implemented:**
  1. Built phonetic speech keyword spotting in [WakeWordEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/wake_word_engine.py) using Faster-Whisper and VAD speech chunking.
  2. Implemented multilingual regex (`WAKE_WORD_PATTERN`) supporting English, Hindi, and Gujarati activation phrases (*"Hey Buddy"*, *"Buddy"*, *"Hi Buddy"*, *"Hello Buddy"*, *"Ok Buddy"*, *"Hey Bud"*, *"हे बडी"*, *"सुनो बडी"*, *"બડી"*, *"હે બડી"*, *"એલા બડી"*, *"સાંભળ બડી"*).
  3. Integrated `whisper_engine` and `vad_engine` in `WakeWordEngine` initialization inside [VoiceConversationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py).
  4. Updated [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py) startup and `_on_voice_toggle` to respect user-configured `voice.mode` (defaulting to `"wake_word"`).
  5. Connected `signals.wake_word_detected` to `_on_wake_word_detected` in `ApplicationController` to immediately set character visual state to `LISTENING` and pop up a greeting speech bubble (*"I'm listening..."*).
  6. Preserved backward compatibility for acoustic bursts (`rms >= 0.25`) and debounce protection.
  7. Verified with 15 passing tests in [test_interruption_and_wake_word.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_interruption_and_wake_word.py).

---

### 3. ⚙️ Stale Configuration Import in VoiceService (`app.core.config_manager`)
- **Category:** Voice / Configuration
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** User-configured Whisper model size (`whisper_model`) and speech recognition language (`language`) in `settings.json` are now reliably loaded on startup.
- **Root Cause:** `app/voice/voice_service.py` attempted to import `from app.core.config_manager import get_config_manager`, which did not exist after refactoring into `app.settings.config_manager`.
- **Fix Implemented:**
  1. Corrected import in [VoiceService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_service.py) to `from app.settings.config_manager import get_config_manager`.
  2. Added `get_category()` method to [ConfigManager](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/settings/config_manager.py) to return category key-value dictionaries.
  3. Verified with 5 passing tests in [test_voice_service.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_voice_service.py).

---

### 4. 🔊 Missing `tts_engine` Property Attribute on `VoiceService`
- **Category:** Voice / Text-To-Speech Interface
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** External callers and profilers referencing `voice_service.tts_engine` now access the active TTS engine without errors.
- **Root Cause:** `VoiceService` defined `self.active_tts_engine` internally without exposing the public `tts_engine` property expected by subsystem interfaces.
- **Fix Implemented:**
  1. Added `@property def tts_engine(self) -> BaseTTSEngine:` and setter to [VoiceService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_service.py).
  2. Cleaned up typing annotations (`Optional[Callable]`) in TTS background workers.

---

### 5. 🔄 Acoustic Feedback Echo Loop in Continuous Hands-Free Mode
- **Category:** Voice / Audio Playback
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** In continuous voice conversation mode, when the companion speaks its response aloud through PC speakers, the microphone captures the companion's own voice and re-transcribes it.
- **Root Cause:**
  1. `_last_assistant_response` was previously updated only when the full AI stream completed. During streaming sentence generation, intermediate sentences actively playing through PC speakers were not recorded in history, completely bypassing echo rejection.
  2. The previous check relied on naive substring match `norm_text in norm_assistant`. Any dropped word, room reverb noise, or Whisper phonetic variation (e.g., "whether" vs "weather") caused the check to fail.
  3. Residual reverberation frames remained in the VAD buffer because `reset_states()` was invoked prematurely rather than at the exact moment listening resumed after speaker playback drain.
- **Fix Implemented:**
  1. Created [AcousticEchoSuppressor](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/echo_suppressor.py) supporting multi-tier echo detection:
     - Exact & Substring containment
     - Token intersection and containment (>=50% word overlap)
     - Fuzzy sequence similarity (`SequenceMatcher.ratio >= 0.65`)
     - 3-word n-gram phrase shingles for partial echoes
     - Unicode-safe normalization preserving Gujarati, Hindi, and Latin diacritics
     - Immediate duplicate query suppression
  2. Integrated into [VoiceConversationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py):
     - Hooked `AudioPlayer` state callbacks (`playback_started`, `playback_finished`, `playback_stopped`).
     - Recorded assistant speech across streaming sentence generation, chunk playback, and direct TTS speech.
     - Extended acoustic decay cooldown to 600ms and added `vad_engine.reset_states()` on listening resumption.
  3. Added unit and integration test suite [test_acoustic_echo_suppression.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_acoustic_echo_suppression.py) with 9 comprehensive tests (all passing).
  4. Full regression suite of 97 tests passed without errors.

---

### 6. 🎙️ Kokoro TTS Engine Missing Models & Availability Check
- **Category:** Voice / Speech Synthesis
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Selecting the Kokoro TTS engine in settings causes synthesis to fail or fall back to synthetic beeps/silence.
- **Root Cause:**
  1. `KokoroTTSEngine.download_model_if_needed()` previously pointed to an invalid Hugging Face repo (`thewh1teagle/kokoro-onnx`), which caused 403 Forbidden / 404 Not Found errors on download attempts.
  2. When Kokoro model files were not present, `KokoroTTSEngine.synthesize()` generated synthetic sine wave beeps (`_generate_fallback_audio`) instead of gracefully delegating to a working neural speech engine (Piper).
  3. `BaseTTSEngine`, `PiperTTSEngine`, and `KokoroTTSEngine` all lacked an `is_available()` method, preventing callers, controllers, and recovery services from querying engine readiness.
- **Fix Implemented:**
  1. Implemented `is_available() -> bool` on [BaseTTSEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/tts_base.py), [PiperTTSEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/piper_engine.py), and [KokoroTTSEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/kokoro_engine.py).
  2. Implemented multi-source automated model downloading in [KokoroTTSEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/kokoro_engine.py):
     - `kokoro-v0_19.onnx`: downloads from Hugging Face `hexgrad/Kokoro-82M` with fallback to GitHub releases.
     - `voices.bin`: downloads from canonical GitHub release asset `thewh1teagle/kokoro-onnx` with streaming chunk writes and fallback to Hugging Face.
  3. Added `fallback_engine: Optional[BaseTTSEngine] = None` to `KokoroTTSEngine`. When Kokoro models are unavailable (e.g. offline first run), synthesis cleanly delegates to Piper so the user hears real spoken speech instead of synthetic beeps.
  4. Wired `fallback_engine=self.piper_engine` in [VoiceService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_service.py), added startup `voice.tts_engine` configuration loading, and exposed `is_tts_available()`.
  5. Added comprehensive test coverage in [test_tts_engines.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_tts_engines.py) (8/8 passed, 105/105 voice regression suite passed).

---

### 7. 💬 Simple Chat Failure Without Manual Ollama Launch
- **Category:** AI / Chat Interface & Process Supervision
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Sending a message in the chat interface fails or produces no response when the user hasn't manually started the Ollama background daemon in terminal first.
- **Root Cause:**
  1. The application strictly depended on an active HTTP server at `http://127.0.0.1:11434` without any background process supervisor to detect and auto-launch `ollama serve`.
  2. When Ollama was offline and offline fallback was disabled, `AIService.ask()` aborted early and called `_handle_error()`, but `_handle_error()` only emitted `character_state_changed("error")` and never emitted `signals.generation_started`, `signals.ai_response_chunk`, or `signals.ai_response_complete`. As a result, the desktop/web chat UI bubble remained frozen indefinitely on animated loading dots or blank without any explanation to the user.
- **Fix Implemented:**
  1. Built [OllamaSupervisor](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ollama_supervisor.py) to automatically locate the Ollama binary across common Windows directories (`%LOCALAPPDATA%\Programs\Ollama\ollama.exe`, `%ProgramFiles%\Ollama\ollama.exe`, `PATH`, etc.) and POSIX environments.
  2. Implemented detached, windowless background process execution (`CREATE_NO_WINDOW`, `DETACHED_PROCESS` on Windows) with server readiness polling (`/api/version`), lifecycle tracking, and clean process termination registered via `atexit`.
  3. Integrated `OllamaSupervisor` into [ModelManager](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/model_manager.py) and [AIService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ai_service.py):
     - Automatically verifies server reachability and triggers background startup before initiating chat requests or model discovery.
     - When Ollama is missing or cannot be started (and offline fallback is disabled), `AIService` formats actionable, friendly markdown guidance and streams it directly to the chat interface via `signals.generation_started`, `signals.ai_response_chunk`, and `signals.ai_response_complete`, preventing UI freezes and guiding the user on how to install or launch Ollama.
  4. Added comprehensive test suite in [test_ollama_supervisor.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_ollama_supervisor.py) (9/9 tests passed).
  5. Verified AI test suite (27/27 tests passed: `test_ollama_supervisor.py`, `test_ai_service.py`, `test_model_manager.py`, `test_ollama_client.py`).

---

### 8. 🧠 ThinkingFilter Missing Synchronous `.filter()` Method
- **Category:** AI / Text Filtering
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Code attempting to filter thinking tags via `ThinkingFilter().filter(text)` fails with `AttributeError`.
- **Root Cause:** `app/ai/thinking_filter.py` defined `StreamingThinkingFilter` (with streaming `.process_chunk()` and `.flush()`), but lacked a synchronous `.filter()` method on filter instances and class definitions for single-string or batch reasoning removal.
- **Fix Implemented:**
  1. Added `@classmethod def filter(cls, text: str) -> str` to [StreamingThinkingFilter](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/thinking_filter.py) and `ThinkingFilter`. Supports both instance method calls (`ThinkingFilter().filter(text)`) and direct class calls (`ThinkingFilter.filter(text)`).
  2. Added synchronous alias `filter_text(self, text: str)` and `__call__(self, text: str)` so filter instances can also be directly invoked as callable transforms.
  3. Upgraded `strip_thinking_tags()` to handle case-insensitive `<think>` tags (`<THINK>`, `<Think>`) and tags with custom HTML/XML attributes (`<think class="...">`) without leaving unclosed reasoning artifacts.
  4. Preserved streaming isolation: synchronous filtering is completely stateless and does not disturb or corrupt ongoing streaming buffers.
  5. Exported `ThinkingFilter` in [app/ai/__init__.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/__init__.py).
  6. Added 8 new test cases to [tests/test_thinking_filter.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_thinking_filter.py) (14/14 tests passing).

---

### 9. 🎭 PersonalityManager Constructor Parameter Incompatibility
- **Category:** AI / Personality & Configuration Sync
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Initializing `PersonalityManager(config_manager=cm)` raises `TypeError: PersonalityManager.__init__() got an unexpected keyword argument 'config_manager'`.
- **Root Cause:** `PersonalityManager.__init__` strictly accepted only `(default_personality, companion_name, user_name)` as positional arguments. When caller services (e.g. `AIService`, setup wizards, or dependency injectors) passed `config_manager=cm`, Python raised an unexpected keyword argument `TypeError`. Furthermore, runtime personality changes were not automatically synced back into the application's persistent configuration store.
- **Fix Implemented:**
  1. Updated [PersonalityManager](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/personality_manager.py) constructor to accept `config_manager: Optional[Any] = None` (both as keyword argument and positional fallback) and `**kwargs: Any` for forward compatibility.
  2. Implemented automatic initialization synchronization: when `config_manager` is provided, `default_personality`, `companion_name`, and `user_name` automatically load from `ai.personality`, `companion.name`, and `user.name` unless explicitly overridden.
  3. Added bi-directional persistence: `set_personality()`, `set_companion_name()`, `set_user_name()`, and `set_custom_prompt()` automatically write changes back to `config_manager`.
  4. Added helper properties `@property def personality(self) -> str` and `get_personality() -> str`.
  5. Updated [AIService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ai_service.py) to inject `config_manager=self.config_manager` on instantiation.
  6. Added comprehensive test coverage in [tests/test_personality_manager.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_personality_manager.py) (8/8 tests passed). Verified full memory/personality regression suite [tests/test_memory_personality_emotion.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_memory_personality_emotion.py) (12/12 tests passed).

---

### 10. 🔌 Rigid Constructor Signature in VoiceConversationController
- **Category:** Voice / Architecture & Dependency Injection
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Instantiating `VoiceConversationController()` without passing 5 mandatory positional arguments (`mic_manager`, `vad_engine`, `whisper_engine`, `audio_player`, `tts_engine`) fails immediately with a `TypeError`.
- **Root Cause:** `VoiceConversationController.__init__` required 5 mandatory positional arguments with zero default initializers. Callers attempting to instantiate the controller standalone (e.g. for testing, modular pipelines, or GUI overlays) or pass only custom parameters (like `tts_engine` or `language`) encountered immediate `TypeError: missing required positional arguments`.
- **Fix Implemented:**
  1. Made all 5 positional engine arguments optional in [VoiceConversationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py):
     - `mic_manager`: defaults to `MicrophoneManager(parent=self)`.
     - `vad_engine`: defaults to `VADEngine(parent=self)`.
     - `whisper_engine`: defaults to `WhisperEngine(parent=self)`.
     - `audio_player`: defaults to `AudioPlayer(parent=self)`.
     - `tts_engine`: defaults to `PiperTTSEngine(parent=self)` with stub audio synthesis fallback.
  2. Added `**kwargs: Any` for forward compatibility and changed `ai_service` parameter annotation to `Optional[Any] = None` to smoothly accommodate mocks and test doubles.
  3. Added `set_tts_engine(self, engine: BaseTTSEngine)` method to dynamically swap TTS engines at runtime and sync with the internal `StreamingAudioQueue`.
  4. Added unit tests in [tests/test_voice_conversation_controller.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_voice_conversation_controller.py) verifying zero-argument instantiation, partial kwargs instantiation, and dynamic `set_tts_engine` synchronization (12/12 tests passed).

---

### 11. 🔄 Triple-Toggle Signal Inversion on Voice Toggle (`/api/voice/toggle`)
- **Category:** Voice / API & State Management
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Clicking the Voice Toggle button in the React UI or calling `POST /api/voice/toggle` fails to activate voice listening; the voice engine immediately turns off or remains inactive.
- **Root Cause:** In `app/api/server.py`, `toggle_voice()` called `signals.voice_toggle_requested.emit()`. Both `main_api.on_voice_toggle` and `ApplicationController._on_voice_toggle` were connected to this signal and flipped `voice_service.mode` from `OFF` to active. Execution then returned to `server.py`, which inspected `voice_service.mode` directly, saw that it was now active, and entered the `else:` branch, executing `voice_service.set_mode(VoiceMode.OFF)`. This immediately cancelled the toggle and deactivated voice on every request.
- **Fix Implemented:**
  1. Updated `toggle_voice()` in [app/api/server.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py) to capture `initial_mode` before emitting `signals.voice_toggle_requested.emit()`. If any connected Qt signal handler performed the transition, `toggle_voice()` respects the transition without inverting, syncs config, broadcasts the new state over WebSocket, and returns `{"status": "ok", "mode": curr_mode_str}`.
  2. Implemented direct toggle fallback in `toggle_voice()` so that in headless or standalone environments without signal listeners, it transitions between `OFF` and configured voice mode (`continuous`/`wake_word`).
  3. Hardened `get_voice_status()` in [app/api/server.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py) to safely parse both `VoiceMode` enum instances and string values.
  4. Updated `setup_signal_bridges` in [main_api.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main_api.py) to avoid registering or running `on_voice_toggle` when `app.state.controller` is already present, eliminating double-toggle collision.
  5. Connected `voice_toggle_requested` with `Qt.ConnectionType.DirectConnection` in both `ApplicationController` and `main_api` for reliable cross-thread synchronization from FastAPI endpoints.
  6. Added comprehensive unit and integration tests in [tests/test_voice_toggle.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_voice_toggle.py) (5/5 tests passed). Verified full suite [tests/test_backend_api_full.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_backend_api_full.py) (3/3 tests passed, 8/8 passed combined).

---

### 12. 💬 Missing WebSocket Streaming Bridge in `ApplicationController` (Chat UI Frozen on Loading)
- **Category:** AI / Chat UI Integration
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Sending a message in the modern desktop chat window triggers background LLM inference, and streaming text chunks, final response completion, and error states now render in real time.
- **Root Cause:** In `main.py`, the desktop application is orchestrated by `ApplicationController` (`app/core/controller.py`), hosting the React frontend in `ModernChatWindow`. The React frontend (`useChatStore.ts`) listens for WebSocket events (`ai_chunk`, `ai_complete`, `ai_error`, `ai_cancelled`, `char_state`, `voice_state`). While `main_api.py` (the standalone headless test harness) wired signals, `ApplicationController` **never connected `signals.ai_response_chunk`, `signals.ai_error_occurred`, or `signals.ai_generation_cancelled` to the WebSocket manager `ws_manager`**. `signals.ai_response_complete` was only hooked to TTS spoken audio playback. As a result, streaming chunks and completions were silently dropped, and message status in SQLite remained perpetually stuck in `"streaming"`, leaving the React UI frozen on animated loading dots.
- **Fix Implemented:**
  1. Connected `signals.ai_response_chunk`, `signals.ai_response_complete`, `signals.ai_error_occurred`, `signals.ai_generation_cancelled`, `signals.character_state_changed`, `signals.voice_state_changed`, and `signals.memory_stored` in [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py) (`initialize()`).
  2. Implemented dedicated Qt `@Slot` event bridges in [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py):
     - `_on_ai_chunk(chunk: str)`: broadcasts `"ai_chunk"` with `chunk` and `message_id` to `ws_manager`.
     - `_on_ai_complete(full_text: str)`: updates SQLite `conv_repo` message status to `"completed"` with final content, broadcasts `"ai_complete"` to `ws_manager`, emits `signals.character_state_changed("idle")`, and resets `current_assistant_msg_id`.
     - `_on_ai_error(error_msg: str)`: updates SQLite `conv_repo` message status to `"error"`, broadcasts `"ai_error"` to `ws_manager`, emits `signals.character_state_changed("idle")`, and resets active message IDs.
     - `_on_ai_cancelled()`: updates SQLite `conv_repo` message status to `"cancelled"`, broadcasts `"ai_cancelled"` to `ws_manager`, and resets active message IDs.
     - `_on_char_state_changed`, `_on_voice_state_changed`, `_on_memory_stored`, and `_on_user_emotion_detected`: broadcast real-time state changes over WebSocket.
  3. Synchronized `current_assistant_msg_id` between `ApplicationController`, `fastapi_app.state`, and the REST dispatch handler `POST /api/conversations/{conv_id}/messages` in [app/api/server.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py) and `_on_voice_transcription_ready` in [app/core/controller.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py).
  4. Updated `cancel_generation()` in [app/ai/ai_service.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ai_service.py) to reliably emit `signals.ai_generation_cancelled.emit()` and reset character state.
  5. Prevented duplicate WebSocket listeners by early returning in `setup_signal_bridges()` in [main_api.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main_api.py) whenever `ApplicationController` is active.
  6. Preserved injected `conv_repo` in `ApplicationController.__init__` and `initialize()` for dependency injection and automated testing.
  7. Created comprehensive unit and integration test suite in [tests/test_controller_streaming_bridge.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_controller_streaming_bridge.py) verifying all streaming bridges, database updates, UI state broadcasts, deduplication, and ID synchronization (7/7 tests passed; 16/16 regression tests passed combined).

---

### 13. 🪟 Orphaned Dedicated Voice Conversation Window (`VoiceWindow`) & Entangled Tray Toggle
- **Category:** Desktop UI / Voice Interface
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Dedicated holographic Voice Conversation portal window (`VoiceWindow`) is fully functional, properly disentangled from voice listening mode, accessible via tray menu, pet context menu, and multi-language voice commands.
- **Root Cause:** In `app/desktop/tray_icon.py`, the "🎙️ Voice Window" menu action was wired directly to `signals.voice_toggle_requested.emit()` instead of opening `self.voice_window`. Because `voice_toggle_requested` was shared between listening mode state changes, legacy chat window toggles, and `VoiceWindow.toggle_window()`, clicking tray items resulted in conflicting, entangled behavior where the holographic portal window never cleanly displayed.
- **Fix Implemented:**
  1. Defined dedicated signals in [app/core/signals.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/signals.py): `open_voice_window_requested`, `close_voice_window_requested`, and `toggle_voice_window_requested`.
  2. Disentangled tray icon actions in [app/desktop/tray_icon.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/tray_icon.py): "🎙️ Voice Window" emits `toggle_voice_window_requested`, while "🎙️ Voice Active" toggles listening mode (`voice_toggle_requested`).
  3. Decoupled [VoiceWindow](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/voice_window.py) from `voice_toggle_requested`: connected dedicated signals to `show_window`, `hide_window`, and `toggle_window`. Added `position_near_pet` and mute toggling functionality.
  4. Orchestrated lifecycle in [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py): connected dedicated slots `_on_open_voice_window`, `_on_close_voice_window`, `_on_toggle_voice_window`, automatic hiding on `enter_sleep_mode()`, and screen change re-positioning.
  5. Added "🎙️ Voice Window" to the right-click context menu in [DesktopPetWindow](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py).
  6. Added voice commands in English, Hindi, and Gujarati to [VoiceCommandDispatcher](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/command_dispatcher.py).
  7. Verified with comprehensive test suite in [tests/test_voice_window_integration.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_voice_window_integration.py) (9/9 passed) and [tests/test_voice_commands.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_voice_commands.py) (75/75 passed).

---

### 14. 🤖 AnimationController Disconnected from DesktopPetWindow & Missing `request_state`
- **Category:** Character / Animation Engine
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Desktop pet character dynamically and reactively transitions into speaking, listening, thinking, happy, sleeping, and dragging animation states driven by voice activity, AI inference, and user emotions.
- **Root Cause:** `DesktopPetWindow` (`app/desktop/pet_window.py`) only initialized `CharacterRenderer` and never instantiated `AnimationController`, leaving `hasattr(self.pet_window, "anim_controller")` as `False`. Furthermore, `ApplicationController` and test suites invoked `self.pet_window.anim_controller.request_state(...)` across lifecycle hooks, but `AnimationController` (`app/character/animation_controller.py`) only implemented `set_state()`, not `request_state()`.
- **Fix Implemented:**
  1. Instantiated and exposed `AnimationController` in [DesktopPetWindow](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py) as `self.anim_controller`, wired directly to `self.renderer` with frame and state signal connections.
  2. Implemented `request_state(self, state: Union[CharacterState, str], duration_sec: Optional[float] = None, *, force: bool = False, broadcast_global: bool = True) -> bool` in [AnimationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/character/animation_controller.py):
     - Robust parsing supporting both `CharacterState` enum members and case-insensitive strings.
     - State priority evaluation (`DRAGGING` (10) > `HAPPY` (3) > `SPEAKING` / `THINKING` / `LISTENING` (2) > `SLEEPING` (1) > `IDLE` (0)) preventing low-priority events from overriding high-priority states.
     - Reversion timer supporting `duration_sec` for transient states (automatically reverting to `IDLE` upon expiration, or cancelling gracefully on interrupt).
     - Central signal bus broadcasting (`signals.character_state_changed`) while preventing echo loops.
  3. Expanded logical transition paths in `_TRANSITIONS` within [app/character/states.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/character/states.py) to support speech barge-in interruptions, sleep transitions from any active state, and cancel operations.
  4. Added `set_state()` and `_apply_visual_state()` to [DesktopPetWindow](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py), synchronizing `renderer`, `anim_timer` throttle intervals (500ms in sleep vs 30 FPS active), speech bubbles, and repaints.
  5. Connected dragging start and release in [DesktopPetWindow](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py) to `anim_controller.request_state(CharacterState.DRAGGING, force=True)` and `anim_controller.restore_previous_state()`.
  6. Verified all 8 [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py) hooks (`_on_speech_detected`, `_on_transcription_started`, `_on_speaking_started`, `_on_speaking_finished`, `_on_user_emotion_detected`, `_on_wake_word_detected`, `enter_sleep_mode`, `wake_up`) smoothly drive the character animation states.
  7. Created dedicated comprehensive test suite in [tests/test_animation_controller_integration.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_animation_controller_integration.py) (7/7 passed) and verified full regression suite (50/50 passed combined).

---

### 15. 🔈 AudioPlayer Single-Channel (Mono) Output Failure on Windows WASAPI Sound Cards
- **Category:** Voice / Audio Output Hardware
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Spoken TTS output is universally compatible across all Windows audio configurations (WASAPI, DirectSound, MME, Realtek HD Audio, USB DACs, Bluetooth headsets, HDMI displays) with native stereo upmixing and automatic fallback resampling.
- **Root Cause:** In `app/voice/audio_player.py`, `AudioPlayer.play()` unconditionally configured `sd.OutputStream(channels=1, samplerate=self._sample_rate)` for mono audio output. In Windows WASAPI shared mode, the Windows audio engine strictly requires the endpoint's native channel count (stereo, `channels=2`) and rejects single-channel mono streams without stereo duplication/upmixing. Furthermore, WASAPI endpoints reject custom stream rates (e.g. 22050 Hz or 24000 Hz) if the device's hardware mix format strictly demands its native sample rate (e.g. 48000 Hz).
- **Fix Implemented:**
  1. Updated [AudioPlayer](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/audio_player.py) to inspect the output endpoint's `max_output_channels` via `_determine_output_channels()`, preferring stereo (`channels=2`) for Windows WASAPI / DirectSound / MME compatibility with automatic fallback candidates.
  2. Implemented multi-channel stereo upmixing in `_audio_callback()`: mono TTS waveform chunks are duplicated across both channels using broadcast slicing (`outdata[:valid_len, :] = scaled[:, np.newaxis]`), ensuring balanced left/right playback and zero sound card rejection.
  3. Added `_determine_output_samplerates()` and high-quality resampling via `_resample_audio()` (using `scipy.signal.resample_poly` with `np.interp` fallback): automatically resamples TTS audio to the endpoint's native default sample rate (e.g. 48000 Hz or 44100 Hz) if the device rejects non-native rates.
  4. Added `output_channels` property to [AudioPlayer](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/audio_player.py) for active hardware channel inspection.
  5. Expanded test coverage in [tests/test_audio_player.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_audio_player.py) (11/11 passed) verifying stereo buffer duplication, channel determination, PortAudioError channel fallback, and sample rate fallback.
  6. Verified zero regressions across the voice test suite (124/124 passed combined).

---

### 16. 🎭 Phantom / Non-Existent "Windows SAPI5 Voice" Setting
- **Category:** Voice / TTS Engines
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Selecting the "Windows SAPI5 Voice" option in the inspector sidebar panel immediately activates the Windows native speech synthesizer (Microsoft SAPI5), providing zero-download, ultra-fast offline TTS without depending on external Piper neural weights.
- **Root Cause:** `RightPanel.tsx` offers `<option value="system">Windows SAPI5 Voice</option>`, but `VoiceService.set_tts_engine` in `app/voice/voice_service.py` only handled `"kokoro"` and fell back to `PiperTTSEngine` in its `else` clause. No SAPI5 / WinRT speech synthesis driver existed in `app/voice/`, leading to silent fallback failure when Piper model files were absent.
- **Fix Implemented:**
  1. Implemented native Windows SAPI5 synthesizer [Sapi5TTSEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/sapi5_engine.py) (aliased as `SystemTTSEngine`) inheriting from `BaseTTSEngine`:
     - Discovers installed Windows voices via registry (`SOFTWARE\Microsoft\Speech\Voices\Tokens`, `Speech_OneCore\Voices\Tokens`) and SAPI token categories.
     - Connects `SAPI.SpVoice` output to `SAPI.SpMemoryStream` with standard 22050 Hz 16-bit mono format (`SAFT22kHz16BitMono = 22`).
     - Maps runtime speed multipliers (0.5x to 2.0x) to SAPI Rate (-10 to +10).
     - Renders synchronous `float32` numpy waveforms normalized to `[-1.0, 1.0]` matching `SynthesizedAudio` specifications.
     - Provides instant tone fallback if run off-platform or if COM calls fail.
  2. Integrated `Sapi5TTSEngine` into [VoiceService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_service.py):
     - Instantiated `self.sapi_engine = Sapi5TTSEngine(parent=self)`.
     - Updated `set_tts_engine(engine_name)` to recognize `"system"`, `"sapi"`, `"sapi5"`, and `"windows"`.
     - Synchronized `self.conversation_controller.tts_engine` on switch.
     - Exposed `get_available_tts_engines()` returning `["piper", "kokoro", "system"]` based on runtime availability.
     - Added SAPI model unloading in `unload_models()`.
  3. Exported `Sapi5TTSEngine` and `SystemTTSEngine` in [app/voice/__init__.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/__init__.py).
  4. Added comprehensive test coverage in [tests/test_tts_engines.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_tts_engines.py) verifying voice discovery, speed adjustment, float32 waveform generation, and engine switching (9/9 passed).


---

### 17. 🚀 Settings Dialog Dead Autostart Toggle Switch
- **Category:** System Integration / Windows Startup
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Toggling "Launch on Windows Startup" in the Settings Dialog successfully persists the configuration and registers/unregisters the application in the Windows Registry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
- **Root Cause:** In `app/desktop/settings_dialog.py` (`_create_startup_page`), `cb_autostart = AnimatedToggleSwitch("Launch on Windows Startup", page)` was instantiated as an unreferenced local variable. It was not saved to `self`, its initial state was never loaded from `app.core.startup_manager.is_startup_enabled()`, and it was never connected to `enable_startup()` or `disable_startup()`.
- **Fix Implemented:**
  1. Stored the toggle switch instance on `self.cb_autostart` in `_create_startup_page` within [SettingsDialog](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/settings_dialog.py).
  2. Loaded startup state in `_load_settings()` by querying `startup_manager.is_startup_enabled()` and `config_manager.get("general.start_at_login")`, using `blockSignals(True/False)` to cleanly set the initial checkbox state without triggering side-effects.
  3. Implemented `@Slot(bool) def _on_autostart_toggled(self, checked: bool)` connecting the toggle signal to `startup_manager.set_startup_enabled(checked)` and updating `config_manager.set("general.start_at_login", checked)`.
  4. Added unit test in [tests/test_settings_startup.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_settings_startup.py) verifying initial state loading, toggle callbacks, configuration updates, and registry synchronization (1/1 passed).


---

### 18. ⌨️ Missing Global Windows Hotkeys & Non-Functional Emergency Audio Stop
- **Category:** Desktop / Hotkeys & Accessibility
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Pressing `Escape` anywhere in Windows (even when another application like a web browser, code editor, or fullscreen game has foreground focus) immediately triggers Emergency Audio / AI Stop, halting ongoing voice speech, cancelling LLM generation, and reverting character animation to idle.
- **Root Cause:** While the Settings dialog listed "Escape: Immediate Emergency Audio / AI Stop" under "Keyboard Hotkeys", the application only handled key presses via local Qt widget focus events. It did not register system-wide global hotkeys via the Windows Win32 API (`RegisterHotKey`) or low-level keyboard hooks (`WH_KEYBOARD_LL`), leaving the companion un-interruptible when running as a background overlay.
- **Fix Implemented:**
  1. Created [GlobalHotkeyManager](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/global_hotkeys.py) implementing a system-wide low-level Windows keyboard hook (`WH_KEYBOARD_LL` = 13 via `SetWindowsHookExW`):
     - Monitors global keystrokes across all processes on the desktop with zero CPU overhead (hook callback dispatched by Qt's Windows message pump).
     - Detects `VK_ESCAPE` (0x1B) with debouncing (250ms) to ignore auto-repeat keypresses.
     - Preserves the `HOOKPROC` delegate reference in Python memory to prevent garbage collection crashes.
     - Never consumes or blocks the Escape key for other applications (transparently calls `CallNextHookEx`).
     - Emits `emergency_stop_triggered` and centralized `signals.emergency_stop_requested`.
     - Supports headless / cross-platform testing via `simulate_hotkey("escape")`.
  2. Integrated `GlobalHotkeyManager` into [WindowsIntegration](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/windows_integration.py) as `self.global_hotkeys`, ensuring clean unhooking and shutdown in `cleanup()`.
  3. Connected `signals.emergency_stop_requested` to dedicated `@Slot() _on_emergency_stop()` in [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py), atomically halting `voice_service.emergency_stop()`, `ai_service.cancel_generation()`, and resetting character animation to idle.
  4. Added comprehensive test coverage in [tests/test_global_hotkeys.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_global_hotkeys.py) (4/4 passed; combined suite 19/19 passed).


---

### 19. 🖼️ Missing Character State Asset (`thinking.png`) in Frontend Dist Assets
- **Category:** Frontend UI / Character Assets
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** When the companion enters the thinking state, the avatar portrait in the right inspector panel flashes a broken image before falling back to `idle.png`.
- **Root Cause:** `dist/assets/characters/robot/` contains `happy.png`, `idle.png`, `listening.png`, `sleeping.png`, and `speaking.png`, but previously lacked `thinking.png`. Furthermore, in `app/api/server.py`, `/assets` was only mounted if `dist_dir/assets` existed, and would strictly 404 for any missing asset without checking `public/assets/` or `assets/` and without fallback to `idle.png`.
- **Fix Implemented:**
  1. Synchronized and verified all 6 character state assets (`idle.png`, `thinking.png`, `speaking.png`, `listening.png`, `happy.png`, `sleeping.png`) across `assets/characters/robot/`, `public/assets/characters/robot/`, and `dist/assets/characters/robot/` (1,090,694 bytes, valid PNG header).
  2. Implemented [sync_character_assets](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py) in `app/api/server.py` that automatically mirrors all character state assets from `assets/characters/robot/` to `public/assets/characters/robot/` and `dist/assets/characters/robot/` at app initialization.
  3. Created [MultiDirStaticFiles](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py) inheriting from Starlette's `StaticFiles`:
     - Checks candidate directories in priority order: `dist/assets`, `public/assets`, and `assets`, ensuring assets are reliably served in development, testing, and production builds.
     - Adds resilient fallback for character avatar states (`/assets/characters/{char}/{state}.png` falls back to `{char}/idle.png`), permanently eliminating 404 broken image flashes in UI avatar portraits.
  4. Added comprehensive test suite in [tests/test_character_assets.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_character_assets.py) verifying asset existence, PNG integrity, synchronization logic, `/assets/characters/robot/thinking.png` 200 OK delivery, and fallback resilience (7/7 passed; combined suite 26/26 passed).

---

### 20. 🔔 Garbage Collection Destruction of Desktop Notification Toasts (`show_buddy_toast`)
- **Category:** Desktop UI / Notifications
- **Status:** **FIXED & VERIFIED** ✅
- **Description:** Notification popups triggered via `show_buddy_toast()` frequently disappear instantly or fail to show at all.
- **Root Cause:** In `app/desktop/notification_toast.py`, `show_buddy_toast` instantiated `toast = NotificationToast(...)` without a parent widget and returned it. Callers such as `SystemTrayManager.show_message` did not store the returned instance reference. Because Python's garbage collector destroys unparented, unreferenced Qt widgets immediately upon function exit, the toast window was destroyed before Qt's window manager could render it.
- **Fix Implemented:**
  1. Implemented a module-level strong reference registry `_active_toasts: Set[NotificationToast] = set()` in [app/desktop/notification_toast.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/notification_toast.py):
     - Added automatic registration on toast creation and `show_toast()` call, permanently preventing garbage collection destruction regardless of whether the caller stores the returned reference.
     - Connected `self.destroyed.connect(self._on_destroyed)` and overrode `closeEvent` to ensure clean automatic deregistration and C++ resource release upon window closure.
     - Added `self.setAttribute(Qt.WA_DeleteOnClose, True)` for proper memory cleanup.
  2. Implemented smooth fade-in and fade-out animations via `QPropertyAnimation(self, b"windowOpacity")`:
     - Added `@Slot() def dismiss(self)` with a 180ms fade-out transition before invoking `close()`.
     - Connected the auto-dismiss timer and close button to `dismiss()`.
     - Provided pause/resume behavior during mouse hover (`enterEvent`/`leaveEvent`).
  3. Added dynamic vertical stacking: multiple concurrent toasts automatically offset upwards based on active visible toasts instead of overlapping in place.
  4. Exposed utility helpers [get_active_toasts()](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/notification_toast.py) and [clear_all_toasts()](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/notification_toast.py) for clean application shutdown and testing.
  5. Updated [SystemTrayManager](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/tray_icon.py) to maintain dual-layer retention on `self._active_toasts`.
  6. Added comprehensive unit & integration tests in [tests/test_notification_toast.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_notification_toast.py) verifying GC retention after `gc.collect()`, active registry tracking, hover pause, click interaction, and tray icon integration (6/6 passed; combined suite 30/30 passed).

---

### 21. 🔇 AI Speech Silence Across Chat & Voice (TTS Engine Fallback Failure & Chat Audio Suppression), Arithmetic Calculation Hallucinations, and Qt Signal Duplication
- **Category:** Voice / TTS Resilient Fallback / Local LLM Arithmetic / Signal Infrastructure
- **Status:** **FIXED & VERIFIED** ✅
- **Description:**
  1. The AI companion remained completely silent when spoken to ("VOICE Command is still not working the AI is silent - even i am talking though") or when asked to speak in chat ("bolo").
  2. Local quantized LLMs produced arithmetic calculation hallucinations on standard math operations (e.g. `100000+5698` was incorrectly calculated as `1009868` instead of `105698`).
  3. Disconnecting or restarting the API server or headless testing accumulated duplicate Qt signal listeners in `main_api.py` due to a missing `QObject` import in `teardown_signal_bridges()`.
- **Root Cause:**
  1. **TTS Engine Fallback Failure:** `PiperTTSEngine` attempts to download neural weights from Hugging Face (`en_US-lessac-medium`). When weights are missing or offline, it had no fallback engine, generating empty audio waveforms and failing speech playback.
  2. **Chat Response Audio Premature Suppression:** In `ApplicationController._on_ai_response_tts`, a guard checked `if conv_ctrl and conv_ctrl.is_enabled and conv_ctrl.ai_service: return`. Because continuous conversation mode is enabled by default in idle standby, every text message sent through the chat interface was silenced unconditionally, preventing the AI from speaking its responses.
  3. **Arithmetic Hallucination in Small Models:** Edge and local quantized models (0.5B to 1.7B parameters) frequently hallucinate arithmetic calculations without symbolic execution tools or AST evaluation grounding.
  4. **Signal Bridge Accumulation:** In `main_api.py`, `teardown_signal_bridges()` invoked `QObject.disconnect(conn)` without importing `QObject`, causing silent `NameError` exceptions caught by `except Exception: pass`, which left zombie Qt signal connections active across restarts and test runs.
- **Fix Implemented:**
  1. **Resilient Native Windows SAPI5 TTS Fallback:**
     - Added `fallback_engine: Optional[BaseTTSEngine] = None` and delegation in `synthesize()` to [PiperTTSEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/piper_engine.py). If Piper weights are uninitialized or download fails, synthesis automatically falls back to Windows native SAPI5 speech synthesis (`Sapi5TTSEngine`), guaranteeing zero-silence speech playback.
     - Wired SAPI5 as the fallback engine for both Piper and Kokoro in [VoiceService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_service.py) (`self.piper_engine.set_fallback_engine(self.sapi_engine)`).
     - Updated `is_tts_available()` to return `True` whenever either neural weights or the native system fallback are operational.
     - Wired SAPI fallback in [VoiceConversationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py) streaming audio queue.
  2. **Unsuppressed Chat Speech Playback:**
     - Refined `ApplicationController._on_ai_response_tts` in [app/core/controller.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py) to check `conv_ctrl.state in (ConversationState.AI_THINKING, ConversationState.AI_SPEAKING)` rather than merely `conv_ctrl.is_enabled`. Completed chat responses now reliably trigger `voice_service.speak(cleaned)`, allowing "bolo" and spoken responses to work seamlessly.
  3. **Deterministic AST Math Expression Evaluator:**
     - Created [MathExpressionEvaluator](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/math_evaluator.py) using Python's `ast` parser (supporting addition, subtraction, multiplication, division, modulo, exponentiation, integer division, and parentheses).
     - Supported multilingual conversational wrappers (English `"calculate 100000+5698"`, Hindi `"100000+5698 kitna hoga"`, Gujarati `"100000+5698 ketla thay"`).
     - Integrated into [OfflineCompanionEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/offline_companion.py) to immediately return exact verified arithmetic answers (e.g. `100000+5698 = 105698`).
     - Integrated ground-truth calculation injection into [AIService](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ai_service.py) system prompt (`[Verified Calculation Ground Truth]: 100000+5698 = 105698`), preventing local LLM hallucination.
  4. **Clean Signal Bridge Lifecycle & Teardown:**
     - Fixed missing `QObject` import in [main_api.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main_api.py).
     - Verified `teardown_signal_bridges()` cleanly unhooks active signal bridges without zombie accumulation.
     - Enhanced [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py) `shutdown()` to unhook `self._signal_connections`.
  5. **Comprehensive Test Verification:**
     - Built [tests/test_never_silent_tts.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_never_silent_tts.py) (4/4 passed).
     - Built [tests/test_math_evaluator.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_math_evaluator.py) (4/4 passed).
     - Updated [tests/test_controller_streaming_bridge.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_controller_streaming_bridge.py) (7/7 passed).
     - Combined regression suite: 18/18 passed in 103s.



---

### 22. 🪟 Chat Window Stays-On-Top Trapping Desktop & Hands-Free Microphone Continuous Voice Listening & Response Failure
- **Category:** Desktop Window Focus & Z-Order Management / Real-time Voice Recognition & Turn-Taking Orchestration / Microphone Sensitivity
- **Status:** **FIXED & VERIFIED** ✅
- **Description:**
  1. **Window Appearance & Focus Trapping:** When the user clicked outside the chat window (e.g. clicking on Chrome, VS Code, File Explorer), the AI Friend chat window stayed stuck on top and would not allow other windows to rise above it, trapping the user and behaving unnaturally compared to normal desktop applications.
  2. **Microphone Voice Listening & Response Failure in Hands-Free / Continuous Mode:** When typing text, AI responses and voice speech worked, but when speaking into the microphone in Continuous (Hands-Free) mode, the assistant never listened or responded.
- **Root Cause:**
  1. **Window Trapping via HWND_TOPMOST & WindowStaysOnTopHint:** `ModernChatWindow` ([app/desktop/modern_chat_window.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py)) set `Qt.WindowStaysOnTopHint` and called Win32 `SetWindowPos(hwnd, HWND_TOPMOST, ...)`, forcing the 1040x660 window permanently into the Windows OS topmost Z-order band above all normal applications.
  2. **Microphone VAD Energy Discard Threshold:** In [VADEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/vad_engine.py), `rms < 0.007` and `min_utterance_ms = 400` discarded genuine human utterances from laptop microphone arrays (empirical ambient/speech RMS on Realtek Audio was ~0.002 to 0.005) as "Utterance without genuine speech discarded".
  3. **Faster-Whisper Redundant VAD & Strict Threshold:** In [WhisperEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/whisper_engine.py), `vad_filter=True` re-filtered audio that was already segmented by `VADEngine`, and `no_speech_prob > 0.45` dropped valid speech segments where Whisper was slightly uncertain.
  4. **Turn Lifecycle Race & Message ID Disconnect:** `VoiceConversationController._on_transcription_completed` ran in a background worker thread and immediately called `_dispatch_to_ai` -> `ai_service.ask()`. This bypassed `ApplicationController`, running before SQLite database messages were registered and before `current_assistant_msg_id` was assigned. As a result, token chunks were broadcast over WebSocket with `message_id: None`, causing the React chat interface to ignore incoming streaming text, while `ApplicationController._on_voice_transcription_ready` skipped `ai_service.ask` due to a flawed check.
  5. **Active Conversation Desynchronization:** When conversations were selected in the React UI, `ai_service.active_conversation_id` was not updated until a message was manually typed, leaving voice turns untracked or assigned to outdated sessions.
- **Fix Implemented:**
  1. **Standard Desktop Application Window Behavior in [ModernChatWindow](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py):**
     - Removed `Qt.WindowStaysOnTopHint` from `self.setWindowFlags(Qt.Window)`.
     - Replaced `HWND_TOPMOST` (-1) with `HWND_NOTOPMOST` (-2) in Win32 `SetWindowPos()`, and used standard Qt activation (`self.show()`, `self.raise_()`, `self.activateWindow()`). Other applications now freely come forward when clicked outside.
  2. **Tuned VAD Sensitivity for Laptop Microphones in [VADEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/vad_engine.py):**
     - Lowered RMS energy discard floor from `0.007` to `0.0015`.
     - Lowered `min_utterance_ms` from `400ms` to `200ms` to capture crisp single-word phrases ("Buddy", "Hello", "Yes", "Bolo").
  3. **Optimized Whisper Speech Recognition in [WhisperEngine](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/whisper_engine.py):**
     - Disabled redundant internal `vad_filter=False` so segmented utterances pass directly to Whisper without clipping.
     - Relaxed `no_speech_prob` threshold from `0.45` to `0.70` to prevent dropping natural accented or soft speech.
  4. **Synchronized Voice Turn Lifecycle & WebSocket Streaming in [ApplicationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py) & [VoiceConversationController](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py):**
     - Set `enable_direct_ai_dispatch = False` on the conversation controller in `ApplicationController.initialize()`.
     - Ensured `_on_voice_transcription_ready` in `ApplicationController` registers `user_msg` (completed) and `assistant_msg` (streaming) in SQLite, assigns `current_assistant_msg_id`, emits `message_added` to WebSocket, and dispatches `ai_service.ask(cleaned, is_voice=True)`.
     - Connected `_on_ai_response_tts` with audio queue checks to provide a guaranteed speech synthesis fallback if the audio queue has no pending chunks.
  5. **Active Conversation Tracking in [app/api/server.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py):**
     - Updated `get_messages(conv_id)` to set `ai_service.active_conversation_id = conv_id`, ensuring voice utterances are always added to the currently viewed chat session.
  6. **Verified with Regression Tests:**
     - [tests/test_voice_service.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_voice_service.py): 7/7 passed.
     - [tests/test_conversation_flow_scenarios.py](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_conversation_flow_scenarios.py): 12/12 passed.
