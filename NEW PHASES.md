You're right! The previous plan had **too much explanation in Phase 0**, while the actual development phases were comparatively short.

For a project like your **AI Desktop Friend**, the implementation phases should contain significantly more technical detail than the planning phase.

I'll restructure the roadmap with these rules:

* **Phase 0:** Short project overview, requirements, architecture, and technology stack. No coding.
* **Phases 1–12:** Detailed technical implementation, including what to build, how to build it, which libraries to use, how components communicate, and how to test each feature.
* **Every phase:** Clear development tasks, expected functionality, and completion criteria.
* **Strictly native Windows application**, not a website.
* **No cloud API keys**, with local AI models and speech processing.
* **Target:** A draggable, animated, always-on-top desktop pet with continuous voice conversations.

# 🤖 AI DESKTOP FRIEND

## Complete Technical Implementation Roadmap — Version 2.0

**Project type:** Windows Desktop AI Companion
**Architecture:** Python + PySide6 + Local AI
**Development phases:** 0–12
**Primary goal:** Build an animated AI desktop pet capable of real-time, natural voice conversations.

---

# 🟢 PHASE 0 — REQUIREMENTS & PROJECT PLANNING

**Objective:** Define what we are building before development starts.

### 0.1 Project Concept

Create a small, animated AI companion inspired by the Codex Pet in your screenshot.

The character floats on the Windows desktop, can be dragged anywhere, listens to the user, and responds through natural speech.

It should continue working while the user uses other applications.

### 0.2 Main Requirements

| Category      | Features                                     |
| ------------- | -------------------------------------------- |
| Desktop       | Floating, draggable, transparent character   |
| Animation     | Idle, talking, listening, thinking, sleeping |
| AI            | Natural conversation using a local LLM       |
| Voice         | Continuous listening and spoken responses    |
| Interruptions | Stop AI speech when the user interrupts      |
| Memory        | Remember conversations and preferences       |
| Personality   | Customizable AI name and personality         |
| Background    | System tray and sleep mode                   |
| Privacy       | Local processing without cloud APIs          |
| Deployment    | Windows `.exe` installer                     |

### 0.3 Final Technology Stack

| Component                | Technology                |
| ------------------------ | ------------------------- |
| Language                 | Python 3.11               |
| Desktop Application      | PySide6                   |
| Character Animation      | Qt + PNG Sprite Sheets    |
| AI Model Runtime         | Ollama                    |
| AI Model                 | Qwen3 1.7B                |
| Speech Recognition       | Faster-Whisper            |
| Voice Activity Detection | Silero VAD                |
| Voice Generation         | Piper TTS / Kokoro TTS    |
| Wake Word                | openWakeWord              |
| Audio Capture            | sounddevice               |
| Memory                   | SQLite + FTS5             |
| Background Workers       | QThread / multiprocessing |
| Packaging                | PyInstaller               |
| Installer                | Inno Setup                |

### 0.4 Main Architecture

```text
Windows Desktop
      |
      ▼
Floating Animated Pet
      |
      ▼
Application Controller
      |
      ├── AI Engine (Ollama)
      |
      ├── Voice Engine
      |     ├── Microphone
      |     ├── VAD
      |     ├── Whisper
      |     └── TTS
      |
      ├── Memory System
      |
      └── Background Manager
```

**Phase 0 deliverable:** Finalized requirements, stack, architecture, and development roadmap.

**No implementation in Phase 0.**

---

# 🔵 PHASE 1 — PROJECT SETUP & APPLICATION FOUNDATION

**Objective:** Establish the complete foundation of the native Windows application.

## 1.1 Development Environment

Create a Python 3.11 virtual environment.

Install the initial dependencies:

```bash
pip install PySide6
pip install psutil
pip install platformdirs
pip install pytest pytest-qt
```

The project must use a clean dependency environment, not the system Python installation.

Create a `pyproject.toml` for dependency management.

Use Git for version control.

## 1.2 Establish Project Architecture

Create the following modules:

```text
AI-Desktop-Friend/
│
├── main.py
│
├── app/
│   ├── core/
│   ├── desktop/
│   ├── character/
│   ├── ai/
│   ├── voice/
│   ├── memory/
│   ├── settings/
│   └── utils/
│
├── assets/
│   ├── characters/
│   ├── animations/
│   ├── icons/
│   └── sounds/
│
├── config/
├── tests/
├── packaging/
│
├── pyproject.toml
└── README.md
```

Each component must remain independent.

For example, changing the AI model should not require modifying the desktop character implementation.

## 1.3 Create Main Application Controller

Implement a central `ApplicationController`.

Responsibilities:

1. Initialize the desktop application.
2. Load saved settings.
3. Initialize the character.
4. Initialize the system tray.
5. Start background services when required.
6. Coordinate application events.
7. Handle clean shutdown.

Use Qt signals and slots for communication between the GUI and background workers.

## 1.4 Implement Single-Instance Protection

Prevent multiple copies of the application from running simultaneously.

Use a Qt local socket/server mechanism or another reliable Windows-compatible single-instance approach.

If the application is already running, a second launch should activate the existing instance instead of opening another.

## 1.5 Create Configuration Manager

Implement persistent settings using JSON.

Example:

```json
{
  "pet": {
    "size": 120,
    "always_on_top": true
  },
  "ai": {
    "model": "qwen3:1.7b",
    "personality": "friendly"
  },
  "voice": {
    "enabled": false,
    "mode": "push_to_talk"
  }
}
```

Store user settings in the Windows application-data directory.

Do not store mutable configuration inside the installed application directory.

## 1.6 Logging & Error Handling

Implement application logging.

Capture:

* Application startup errors.
* Configuration failures.
* Background worker failures.
* Unexpected shutdowns.

Use rotating log files and avoid storing private conversation content in logs.

### ✅ Phase 1 Completion Criteria

The application launches successfully, loads settings, initializes the application controller, and closes without leaving orphaned processes.

---

# 🔵 PHASE 2 — FLOATING DESKTOP PET SYSTEM

**Objective:** Implement the actual desktop character, similar to your reference screenshot.

This phase is entirely focused on desktop interaction.

## 2.1 Create Transparent Desktop Window

Use `QWidget` as the character container.

Configure:

```python
Qt.FramelessWindowHint
Qt.WindowStaysOnTopHint
Qt.Tool
```

Enable transparency:

```python
self.setAttribute(Qt.WA_TranslucentBackground)
```

Expected result:

The user sees only the character, not a rectangular application window.

The transparent parts should not unnecessarily block other applications.

## 2.2 Create Character Rendering Engine

Use `QPainter` and transparent PNG assets.

The renderer should support:

* Transparent images.
* Smooth scaling.
* High-DPI displays.
* Character replacement.
* Dynamic animation frames.

Initially, use one custom robot character inspired by Codex Pet.

Later phases will introduce additional characters.

## 2.3 Implement Drag-and-Drop Movement

The character must move naturally when dragged.

Implementation:

1. Detect mouse press on the character.
2. Store the cursor-to-window offset.
3. Update the character position during movement.
4. Stop movement when the mouse button is released.
5. Save the final position.

Ensure dragging works correctly across displays with different DPI scaling settings.

## 2.4 Character Position Persistence

Save the last position using the configuration manager.

When the application restarts:

* Restore the saved position.
* Check whether the position belongs to an active monitor.
* Reposition the character if its previous display is unavailable.

The character must never become permanently inaccessible off-screen.

## 2.5 Character Size Customization

Implement a scalable character.

Supported controls:

* Small.
* Medium.
* Large.
* Custom size.

Example sizes:

| Size   | Height |
| ------ | -----: |
| Small  |  80 px |
| Medium | 120 px |
| Large  | 160 px |

These are initial design values, not fixed limitations.

## 2.6 Character Mouse Interactions

Define the following behavior:

| Action       | Result            |
| ------------ | ----------------- |
| Single click | Open compact chat |
| Double-click | Toggle voice mode |
| Right-click  | Open context menu |
| Drag         | Move character    |
| Hover        | Display controls  |

Dragging must take priority over click actions once the cursor moves beyond a small threshold.

## 2.7 Floating Control Bar

Develop a compact floating toolbar similar to the one in your screenshot.

The toolbar appears below or beside the character.

Controls:

* 💬 Open Chat
* 🎤 Voice
* ⚙️ Settings
* ✕ Hide

The toolbar must automatically reposition itself when the character moves near a screen edge.

## 2.8 Always-on-Top Management

Allow users to toggle between:

**Always On Top:** Character remains above ordinary application windows.

**Normal:** Character behaves like a regular desktop overlay.

**Click-Through:** Mouse events pass through the character window when explicitly enabled.

Click-through mode must provide another way to regain control, such as a system tray command.

### ✅ Phase 2 Completion Criteria

The user can:

* See the character directly on the desktop.
* Move it anywhere.
* Resize it.
* Interact with its controls.
* Restore its last position after restarting.
* Use Chrome, VS Code, and other applications without the overlay interfering unnecessarily.

---

# 🔵 PHASE 3 — CHARACTER ANIMATION & BACKGROUND APPLICATION MANAGEMENT

**Objective:** Transform the static character into an animated desktop companion that continues running in the background.

## 3.1 Define Character States

Create an animation state machine.

Required states:

```text
IDLE
LISTENING
THINKING
SPEAKING
HAPPY
SLEEPING
ERROR
DRAGGING
```

Each state should have its own animation assets.

## 3.2 Create Animation Assets

Use transparent PNG sprite sheets or individual animation frames.

Each animation should have:

* Consistent character dimensions.
* Transparent background.
* Defined frame order.
* Configurable frame rate.
* Looping configuration.

Suggested animations:

| State     | Animation              |
| --------- | ---------------------- |
| Idle      | Blinking and breathing |
| Listening | Head movement          |
| Thinking  | Looking around         |
| Speaking  | Mouth movement         |
| Happy     | Jumping                |
| Sleeping  | Closed eyes            |
| Error     | Confused expression    |

Keep the initial character 2D to minimize resource usage.

## 3.3 Develop Animation Controller

Create:

`animation_controller.py`

Responsibilities:

1. Load animation assets.
2. Cache decoded frames.
3. Advance animation frames.
4. Transition between states.
5. Control playback speed.
6. Stop unnecessary animations.

Use `QTimer` or an equivalent Qt animation mechanism.

Target approximately 30 FPS for character animations.

## 3.4 Implement Animation Transitions

Example:

```text
Idle
  ↓
Listening
  ↓
Thinking
  ↓
Speaking
  ↓
Idle
```

Transitions must be event-driven.

The UI should not directly determine whether the AI is thinking or speaking.

Instead, the application controller should emit the corresponding state change.

## 3.5 Implement System Tray Integration

Use `QSystemTrayIcon`.

Menu options:

```text
AI Desktop Friend
--------------------
Show Character
Open Chat
Enable Voice
Sleep Mode
Settings
--------------------
Exit
```

The system tray remains available when the character is hidden.

## 3.6 Background Execution

Implement three primary operating states.

### Active

* Character visible.
* AI available.
* Voice mode can be enabled.
* Animations running.

### Sleeping

* Character visible.
* Microphone capture disabled.
* Speech processing stopped.
* Heavy AI models may be unloaded.

### Hidden

* Character invisible.
* Application remains in the system tray.
* No voice capture by default.

## 3.7 Windows Startup

Add an optional setting:

**Launch AI Friend when Windows starts.**

When enabled, register a per-user startup entry.

Do not require administrator privileges.

## 3.8 Background Resource Optimization

Ensure:

* Animations stop when invisible.
* Hidden windows do not continuously repaint.
* Microphone resources are released when disabled.
* Heavy AI services do not initialize unnecessarily.
* Workers shut down cleanly.

### ✅ Phase 3 Completion Criteria

A fully animated character runs reliably in the background and can be controlled through the system tray.

---

# 🟣 PHASE 4 — LOCAL AI ENGINE & LLM INTEGRATION

**Objective:** Give the desktop character its own locally running AI brain.

## 4.1 Install Ollama

Use Ollama as the local inference engine.

Download the initial model:

```bash
ollama pull qwen3:1.7b
```

Test the model:

```bash
ollama run qwen3:1.7b
```

For 8 GB RAM, begin with a smaller quantized model.

Benchmark larger models before enabling them.

## 4.2 Develop Ollama Client

Create:

`ollama_client.py`

Responsibilities:

* Connect to the local Ollama endpoint.
* Send messages.
* Stream generated responses.
* Handle errors.
* Check installed models.
* Cancel requests.

Use the local HTTP API or an appropriate Python client.

No cloud API key is required.

## 4.3 Implement AI Model Manager

Create:

`model_manager.py`

Features:

* Detect whether Ollama is available.
* List installed models.
* Select active model.
* Load model on demand.
* Unload model after inactivity.
* Report model errors.

The application should display a useful error when Ollama is unavailable instead of crashing.

## 4.4 Design AI Personality System

Create:

`personality_manager.py`

The companion must behave naturally, not like a formal assistant.

Example personality rules:

```text
You are a friendly desktop AI companion.

Speak naturally, like a friend.

Use short conversational responses during voice chat.

Avoid unnecessary explanations.

Maintain conversation context.

Ask relevant follow-up questions.

Be warm, casual, and engaging.

Do not pretend to have human experiences.
```

Allow users to customize the AI's personality.

## 4.5 Implement Conversation Context

Maintain a conversation context containing:

* System instructions.
* Recent user messages.
* Recent AI responses.
* Relevant stored memories when available.

Set a configurable context budget.

Older conversations can be summarized later to reduce token usage.

## 4.6 Implement Response Streaming

The AI should not wait for the complete response before displaying text.

Example:

```text
User: Hey!

AI streaming:

"Hey"
"Hey!"
"Hey! How"
"Hey! How are"
"Hey! How are you?"
```

Only the generated answer should appear in the UI, not any internal reasoning output.

## 4.7 Add Generation Controls

Implement configurable:

* Temperature.
* Maximum response length.
* Context size.
* Model selection.
* Response style.

For voice conversations, default to concise responses.

## 4.8 AI Cancellation

Implement a cancellation mechanism.

If the user presses Stop or starts a new conversation turn, the previous generation must be canceled.

Any late output from a canceled request must be ignored.

## 4.9 AI Engine Testing

Test:

1. Short questions.
2. Multi-turn conversations.
3. Long conversations.
4. Model switching.
5. Streaming cancellation.
6. Ollama unavailable.
7. Model not installed.
8. Insufficient memory.

### ✅ Phase 4 Completion Criteria

The desktop application can communicate with a locally running AI model and generate natural text responses without an API key.

---

# 🟣 PHASE 5 — CHAT INTERFACE & CONVERSATION HISTORY

**Objective:** Implement a complete native chat interface connected to the desktop character.

## 5.1 Create Floating Chat Window

Use PySide6 to build a compact chat window.

The chat should appear near the desktop pet.

Design:

```text
┌─────────────────────────────┐
│ 🤖 AI Friend           ─  × │
├─────────────────────────────┤
│                             │
│ AI: Hey! How are you?       │
│                             │
│       You: I'm doing good!  │
│                             │
│ AI: That's great!           │
│                             │
├─────────────────────────────┤
│ Type a message...      ➤ 🎤│
└─────────────────────────────┘
```

The chat window must be independently movable and resizable.

## 5.2 Implement Message Components

Create reusable message widgets.

Support:

* User messages.
* AI messages.
* Timestamps.
* Loading indicators.
* Streaming text.
* Error messages.

## 5.3 Integrate AI Streaming

When the user sends a message:

1. Add it to the chat.
2. Display the thinking indicator.
3. Send it to the local AI.
4. Render streamed output.
5. Save the completed response.

The chat must remain responsive during generation.

## 5.4 Design Database Schema

Use SQLite.

Recommended tables:

```text
conversations
-------------
id
title
created_at
updated_at

messages
-------------
id
conversation_id
role
content
created_at
status
```

Use indexes for efficient retrieval.

## 5.5 Conversation Management

Implement:

* Create conversation.
* Rename conversation.
* Open conversation.
* Delete conversation.
* Clear chat.
* Search conversation history.

## 5.6 Conversation Persistence

All conversations should remain available after restarting the application.

Messages should be saved through a dedicated database layer.

Do not let UI components directly execute SQL queries.

## 5.7 Add Text/Voice Mode Controls

The chat window should allow the user to switch between:

* Text mode.
* Push-to-talk.
* Continuous voice mode.

Voice functionality will be connected in later phases.

## 5.8 Integrate Character States

When a message is submitted:

```text
Character: Idle
      ↓
Character: Thinking
      ↓
AI response arrives
      ↓
Character: Responding
      ↓
Character: Idle
```

## 5.9 Chat Testing

Verify that conversations are preserved, streaming is smooth, and closing the chat window does not terminate the desktop companion.

### ✅ Phase 5 Completion Criteria

The user has a fully functional local AI desktop chat application with persistent conversation history.

---

# 🟣 PHASE 6 — MICROPHONE & SPEECH RECOGNITION SYSTEM

**Objective:** Allow the AI friend to understand spoken conversations.

## 6.1 Implement Microphone Manager

Create:

`microphone_manager.py`

Use `sounddevice` to capture audio.

Responsibilities:

* Detect microphones.
* Select input device.
* Start recording.
* Stop recording.
* Handle disconnection.
* Report microphone errors.

## 6.2 Implement Audio Capture Pipeline

Use buffered microphone input.

Recommended initial configuration:

```text
Sample Rate: 16000 Hz
Channels: Mono
Format: Float32 / PCM
Frame Duration: 20–30 ms
```

Use bounded audio buffers to prevent unlimited memory growth.

Keep audio processing outside the GUI thread.

## 6.3 Integrate Faster-Whisper

Install:

```bash
pip install faster-whisper
```

Start with the Tiny or Base model.

Use CPU INT8 inference for the initial implementation.

The STT component should receive audio segments and return transcribed text.

## 6.4 Implement Push-to-Talk

First build a simple, reliable voice interaction.

Flow:

```text
Click Microphone
      ↓
Start Recording
      ↓
User Speaks
      ↓
Stop Recording
      ↓
Whisper Transcription
      ↓
Display Recognized Text
```

This must work before introducing automatic detection.

## 6.5 Integrate Silero VAD

Voice Activity Detection determines whether an audio frame contains speech.

Use Silero VAD to distinguish speech from silence.

Build a dedicated `vad_engine.py`.

## 6.6 Implement Speech Start Detection

When the user begins speaking:

* Detect multiple consecutive speech-positive frames.
* Confirm that speech is present.
* Start collecting the utterance.
* Include a small amount of buffered audio from before detection.

This prevents the beginning of a sentence from being lost.

## 6.7 Implement End-of-Speech Detection

Detect when the user has finished speaking.

Initial configurable threshold:

Approximately 500–900 ms of silence.

This must be tunable because short pauses can occur within sentences.

## 6.8 Implement Transcription Pipeline

The processing flow should be:

```text
Microphone
    ↓
Audio Buffer
    ↓
VAD
    ↓
Speech Segment
    ↓
Faster-Whisper
    ↓
Recognized Text
    ↓
AI Engine
```

## 6.9 Multilingual Speech Recognition

Start with English.

Then evaluate:

* Hindi.
* English-Hindi mixed speech.
* Gujarati.

Whisper supports multilingual transcription, but accuracy depends on language, model size, accent, and microphone quality.

## 6.10 Speech Recognition Testing

Test speech recognition under:

* Quiet conditions.
* Background noise.
* Fast speech.
* Slow speech.
* Short utterances.
* Long sentences.
* Mixed-language speech.

### ✅ Phase 6 Completion Criteria

The character can capture microphone input, detect speech, and accurately convert spoken sentences into text using a local speech recognition model.

---

# 🟣 PHASE 7 — TEXT-TO-SPEECH & SPEAKING ANIMATION

**Objective:** Make the desktop character speak naturally.

## 7.1 Implement TTS Engine Interface

Create an abstract speech engine interface.

Suggested methods:

```python
load_model()
synthesize(text)
stop()
unload_model()
```

This allows us to switch between TTS implementations later.

## 7.2 Integrate Piper TTS

Begin with Piper because of its relatively lightweight resource requirements.

Install:

```bash
pip install piper-tts
```

Download a supported voice model.

Store voice assets in an application-managed model directory.

## 7.3 Create Audio Playback Manager

Create:

`audio_player.py`

Responsibilities:

* Receive synthesized audio.
* Play through the selected output device.
* Control volume.
* Stop playback.
* Report playback progress.
* Handle device errors.

## 7.4 Connect AI Output to TTS

The initial pipeline:

```text
User Message
      ↓
Ollama
      ↓
AI Text
      ↓
Piper TTS
      ↓
Audio Playback
      ↓
User Hears AI
```

## 7.5 Implement Speaking Animation

When audio starts:

```text
Character → SPEAKING
```

When audio finishes:

```text
Character → IDLE
```

The animation must reflect actual playback, not merely the completion of text generation.

## 7.6 Implement Basic Lip Synchronization

Use audio amplitude to animate mouth movement.

Process:

1. Read short audio samples.
2. Calculate amplitude.
3. Map amplitude to mouth openness.
4. Update the character's mouth sprite.
5. Synchronize with playback.

This is simpler than phoneme-level lip synchronization and sufficient for the initial character.

## 7.7 Implement Speech Controls

Include:

* Voice selection.
* Speech speed.
* Volume.
* Mute.
* Stop speaking.
* Enable/disable spoken responses.

## 7.8 Add Kokoro TTS Support

After Piper works, implement Kokoro as an alternative.

Compare both engines on:

| Metric           | What to Measure        |
| ---------------- | ---------------------- |
| Voice quality    | Naturalness            |
| Latency          | Time to first audio    |
| CPU usage        | Processing load        |
| RAM usage        | Memory consumption     |
| Language support | Available voices       |
| Reliability      | Long-session stability |

## 7.9 Playback Testing

Verify that:

* Voice is audible.
* Animation starts and stops correctly.
* Playback can be stopped immediately.
* Audio does not freeze the interface.
* Switching output devices works correctly.

### ✅ Phase 7 Completion Criteria

The AI can respond verbally, and the desktop character animates in synchronization with its voice.

---

# 🔴 PHASE 8 — ADVANCED REAL-TIME VOICE CONVERSATION

**Objective:** Implement continuous, hands-free conversations.

This is the project's most important technical phase.

## 8.1 Develop Voice Conversation Orchestrator

Create:

`voice_conversation_controller.py`

This component coordinates:

* Microphone.
* VAD.
* Speech recognition.
* Ollama.
* TTS.
* Audio playback.
* Character animation.

It must manage the entire voice conversation lifecycle.

## 8.2 Define Conversation States

Create a state machine:

```text
DISABLED
    ↓
LISTENING
    ↓
USER_SPEAKING
    ↓
TRANSCRIBING
    ↓
AI_THINKING
    ↓
AI_SPEAKING
    ↓
LISTENING
```

Include cancellation, timeout, and error states.

## 8.3 Automatic Conversation Flow

When continuous voice mode is enabled:

1. Activate microphone capture.
2. Wait for speech detection.
3. Record the user's utterance.
4. Detect the end of the utterance.
5. Transcribe the speech.
6. Send text to the AI.
7. Begin generating a response.
8. Convert generated text into speech.
9. Play audio.
10. Return to listening.

All steps must operate automatically.

## 8.4 Implement Streaming LLM Output

Configure Ollama to stream generated text.

Instead of waiting for the complete answer, process incoming text incrementally.

## 8.5 Implement Sentence-Based TTS Chunking

Collect streamed text into suitable speech segments.

Example:

```text
LLM Output:

"Hey! That's actually a really
interesting idea. What made
you think about building it?"
```

Split into:

```text
Chunk 1:
"Hey!"

Chunk 2:
"That's actually a really
interesting idea."

Chunk 3:
"What made you think
about building it?"
```

Generate speech for each chunk.

Avoid sending incomplete words or extremely short fragments to TTS.

## 8.6 Implement Streaming Audio Queue

Create an audio queue.

```text
LLM Streaming
      ↓
Sentence Chunker
      ↓
TTS Worker
      ↓
Audio Queue
      ↓
Audio Player
```

While one audio chunk is playing, the next chunk can be synthesized.

Preserve sentence order.

## 8.7 Implement Asynchronous Workers

Separate heavy components.

Recommended structure:

| Worker        | Responsibility    |
| ------------- | ----------------- |
| Audio Capture | Read microphone   |
| VAD           | Detect speech     |
| STT           | Transcribe audio  |
| LLM           | Generate text     |
| TTS           | Synthesize speech |
| Playback      | Play queued audio |

Use background processes for expensive CPU inference where beneficial.

The Qt GUI thread must remain dedicated to the interface.

## 8.8 Implement Turn Management

Only one active AI response should control speech output at a time.

Assign a unique generation ID to every conversation turn.

If a turn is canceled, discard remaining text and audio associated with its ID.

This prevents old responses from playing after a new question.

## 8.9 Optimize Conversation Latency

Measure:

* Speech-end detection latency.
* STT processing time.
* Time to first LLM token.
* Time to first TTS audio.
* Time to playback.

Focus on reducing the delay between the user finishing speaking and the AI beginning its reply.

## 8.10 Prevent Resource Overload

On an 8 GB RAM PC:

* Limit concurrent inference jobs.
* Use bounded audio queues.
* Avoid loading unnecessary models.
* Reduce context size when required.
* Fall back to lightweight voice settings.

### ✅ Phase 8 Completion Criteria

The user can enable continuous mode and have an ongoing voice conversation without manually clicking the microphone for every question.

---

# 🔴 PHASE 9 — AI INTERRUPTION, WAKE WORD & HANDS-FREE CONTROL

**Objective:** Make the voice experience feel significantly more natural.

## 9.1 Implement Speech Detection During AI Playback

The microphone must remain capable of detecting user speech while the AI is talking.

This introduces the possibility that the microphone will hear the AI's own voice.

Therefore, input processing needs to distinguish actual user speech from playback feedback as reliably as possible.

## 9.2 Implement Interruption Controller

Create:

`interruption_manager.py`

When valid user interruption is detected:

1. Stop audio playback.
2. Clear pending TTS audio.
3. Cancel current AI generation.
4. Discard stale responses.
5. Switch character animation to listening.
6. Capture the new user utterance.

Example:

**AI:** "I think the best way to implement this would be—"

**You:** "Wait, I have another idea!"

**AI:** *Stops speaking and listens.*

## 9.3 Handle False Interruptions

Use interruption confidence logic.

Consider:

* Speech duration.
* VAD confidence.
* Background noise.
* Playback timing.
* Repeated speech detections.

A single keyboard click or background sound should not stop the AI.

## 9.4 Implement Echo Handling

Initially prioritize headset support.

Later evaluate acoustic echo cancellation for normal speakers.

This is important because VAD alone cannot reliably determine whether detected speech came from the user or the application's own speakers.

## 9.5 Integrate Wake-Word Detection

Use a local wake-word detector such as openWakeWord.

Example activation phrase:

"Hey Buddy."

A custom wake phrase may require training or obtaining a compatible model.

## 9.6 Implement Wake-Word Standby

While waiting for activation:

* Keep the lightweight wake-word engine active.
* Avoid running continuous full speech recognition.
* Keep heavier models unloaded when possible.
* Display a standby indicator.

## 9.7 Wake-Word Conversation Lifecycle

```text
Wake-Word Standby
        ↓
"Hey Buddy"
        ↓
Wake Word Detected
        ↓
Active Listening
        ↓
Conversation
        ↓
Inactivity Timeout
        ↓
Wake-Word Standby
```

## 9.8 Configurable Activation Modes

Settings should include:

| Mode         | Behavior                           |
| ------------ | ---------------------------------- |
| Push-to-Talk | Manual microphone activation       |
| Wake Word    | Activate when phrase detected      |
| Continuous   | Listen automatically while enabled |

Users can switch modes without restarting the application.

## 9.9 Implement Emergency Stop

Provide an immediate way to stop listening.

Options:

* Microphone button.
* System tray.
* Configurable keyboard shortcut.

Disabling listening must actually stop microphone capture and processing.

## 9.10 Voice Interaction Testing

Test:

* Normal conversation.
* Interruptions.
* Background noise.
* False wake-word detections.
* AI playback echo.
* Long silences.
* Rapid consecutive questions.

### ✅ Phase 9 Completion Criteria

The user can activate the AI hands-free, interrupt its responses, and switch between voice activation modes.

---

# 🟠 PHASE 10 — INTELLIGENT MEMORY, PERSONALITY & EMOTIONAL RESPONSES

**Objective:** Make the AI feel like a consistent companion rather than a chatbot that forgets everything.

## 10.1 Design Memory Architecture

Use three memory layers.

### Short-Term Memory

Contains recent messages from the active conversation.

### Long-Term Memory

Stores selected important information about the user.

### Conversation Summaries

Stores compact summaries of older discussions.

This prevents the AI from needing the entire chat history in every prompt.

## 10.2 Create Memory Database

Recommended tables:

```text
memories
--------
id
category
content
source_conversation_id
created_at
updated_at

conversation_summaries
--------
id
conversation_id
summary
created_at
```

Use SQLite FTS5 for searching stored information.

## 10.3 Implement Memory Extraction

After a conversation, identify useful information.

Examples:

* User preferences.
* Ongoing projects.
* Learning goals.
* Repeated interests.
* Explicit requests to remember something.

Do not permanently save every message.

Provide controls over automatic memory extraction.

## 10.4 Implement Memory Retrieval

When the user asks something, search for relevant stored memories.

Example:

**You:** "What was I learning last week?"

The system retrieves relevant learning-related memories and includes them in the AI context.

## 10.5 Implement Memory Update Logic

If the user corrects previously saved information, the system should update the memory rather than blindly adding contradictory information.

## 10.6 Create Memory Management UI

Add a Memory section in Settings.

Features:

* View saved memories.
* Add memory.
* Edit memory.
* Delete memory.
* Clear all memories.
* Disable automatic memory storage.

## 10.7 Personality Customization

Create configurable personality profiles.

Examples:

| Personality  | Behavior               |
| ------------ | ---------------------- |
| Friendly     | Casual and supportive  |
| Funny        | Playful and humorous   |
| Calm         | Relaxed responses      |
| Energetic    | Enthusiastic responses |
| Professional | Direct and informative |

Store personality settings separately from conversation history.

## 10.8 Emotional Response System

Implement text-based emotion classification or LLM-assisted tone analysis.

Possible categories:

* Happy.
* Excited.
* Sad.
* Frustrated.
* Neutral.

Use these as contextual indicators, not definitive emotional assessments.

## 10.9 Connect Emotion to Animation

Example:

```text
User Sounds Excited
        ↓
Emotion Signal
        ↓
Response Style Adjustment
        ↓
AI Generates Response
        ↓
Character Happy Animation
```

## 10.10 Context and Privacy Testing

Verify:

* Important memories can be recalled.
* Deleted memories are excluded from future retrieval.
* Incorrect memories can be corrected.
* Personality remains consistent.
* Conversations remain functional when memory is disabled.

### ✅ Phase 10 Completion Criteria

The AI can remember relevant information across sessions, adapt to user preferences, and maintain a consistent conversational personality.

---

# 🟠 PHASE 11 — PERFORMANCE OPTIMIZATION & WINDOWS INTEGRATION

**Objective:** Make the application efficient enough for regular use, especially on an 8 GB RAM system.

## 11.1 Implement Performance Monitoring

Create:

`performance_monitor.py`

Track:

* Process CPU usage.
* RAM consumption.
* Model load time.
* AI response latency.
* Speech recognition duration.
* TTS synthesis duration.
* Audio queue length.

## 11.2 Optimize AI Model Lifecycle

Avoid keeping expensive models loaded unnecessarily.

Implement:

* Lazy model initialization.
* Inactivity-based unloading.
* Configurable model keep-alive.
* Recovery after model failure.

## 11.3 Implement Performance Profiles

### Eco Mode

* Qwen3 1.7B.
* Whisper Tiny.
* Piper TTS.
* Reduced animation updates.
* Aggressive idle unloading.

### Balanced Mode

* Qwen3 1.7B or suitable alternative.
* Whisper Base.
* Piper or Kokoro.
* Standard animations.

### Quality Mode

* Larger compatible LLM.
* Higher-quality speech recognition.
* More natural TTS.
* Longer conversational context.

Quality mode should only be offered when hardware resources are sufficient.

## 11.4 Optimize CPU & RAM Consumption

Consider:

* Model quantization.
* Worker process reuse.
* Shared audio buffers where appropriate.
* Bounded queues.
* Lazy loading.
* Avoiding duplicate model instances.

## 11.5 Optimize Desktop Rendering

Use cached animation frames.

Avoid decoding images every frame.

Pause animations when the character is hidden.

Reduce unnecessary window repaint operations.

## 11.6 Implement Robust Error Recovery

Handle:

* Ollama service stopping.
* Missing AI model.
* Microphone disconnection.
* Speaker disconnection.
* TTS failure.
* STT timeout.
* Invalid configuration.
* Worker crash.

Provide meaningful user-facing error messages.

## 11.7 Windows Integration

Implement:

* System tray recovery.
* Launch at startup.
* Notification permissions where relevant.
* Multiple-monitor support.
* Display scaling compatibility.
* Windows sleep/resume handling.

After Windows resumes from sleep, audio devices and background services should be revalidated.

## 11.8 Implement Resource-Saving Sleep Mode

When the companion sleeps:

* Stop microphone capture.
* Stop active inference.
* Cancel pending audio generation.
* Unload heavy models where appropriate.
* Continue displaying a lightweight sleeping animation.

## 11.9 Performance Testing

Test the application during:

* Chrome browsing.
* VS Code usage.
* Multiple open programs.
* Extended conversations.
* Windows sleep and resume.
* Multiple monitor changes.

### ✅ Phase 11 Completion Criteria

The application remains responsive, uses resources efficiently, and recovers gracefully from common operating-system and model errors.

---

# 🔴 PHASE 12 — COMPLETE TESTING, WINDOWS EXE & INSTALLER

**Objective:** Convert the finished application into a reliable Windows desktop product.

## 12.1 Unit Testing

Use pytest.

Test individual components:

* Configuration manager.
* Conversation database.
* Memory retrieval.
* AI request cancellation.
* Voice state transitions.
* Audio queue management.

## 12.2 Integration Testing

Test complete interaction pipelines.

### AI Chat

```text
Text Input
    ↓
Ollama
    ↓
AI Response
    ↓
Chat Display
    ↓
SQLite Storage
```

### Voice Conversation

```text
Microphone
    ↓
Speech Detection
    ↓
Whisper
    ↓
Ollama
    ↓
TTS
    ↓
Audio Playback
```

### Interruption

```text
AI Speaking
    ↓
User Interrupts
    ↓
Cancel Generation
    ↓
Stop Audio
    ↓
Start Listening
```

## 12.3 Desktop UI Testing

Verify:

* Character dragging.
* Character resizing.
* Character animations.
* Floating toolbar.
* Chat window.
* Settings.
* System tray.
* Multi-monitor behavior.

## 12.4 Offline Testing

Disconnect the internet.

Verify that:

* AI responses work.
* Speech recognition works.
* Voice generation works.
* Memory works.
* Desktop animations work.

All required models must already be installed locally.

## 12.5 Long-Session Stability Testing

Run extended conversations.

Monitor:

* Memory leaks.
* CPU usage.
* Audio failures.
* Inference crashes.
* Database reliability.
* Application responsiveness.

## 12.6 Package Application with PyInstaller

Generate a standalone application executable.

Example:

```bash
pyinstaller --onedir --windowed main.py
```

The final packaging configuration will need to explicitly include PySide6 plugins, character assets, and other required runtime files.

A simple PyInstaller command alone is not sufficient for the complete application.

## 12.7 Handle AI Runtime Dependencies

Ollama and the local AI models require special handling.

Possible distribution strategy:

* Bundle the desktop application.
* Detect whether Ollama is installed.
* Guide the user through Ollama installation.
* Download the selected model during first-run setup.

This avoids embedding several gigabytes of model data directly into the application executable.

## 12.8 Create First-Run Setup Wizard

The installer experience should guide the user through:

1. Selecting a character.
2. Setting the AI companion's name.
3. Installing or detecting Ollama.
4. Downloading the AI model.
5. Selecting a microphone.
6. Selecting a speaker.
7. Choosing an AI voice.
8. Testing voice conversation.
9. Choosing startup behavior.

## 12.9 Create Windows Installer

Use Inno Setup.

Target output:

```text
AI-Desktop-Friend-Setup.exe
```

The installer should:

* Install application files.
* Create Start Menu shortcuts.
* Optionally create a desktop shortcut.
* Register the uninstaller.
* Preserve user data during updates.

Review dependency and model licenses before distribution.

## 12.10 Final Validation

Test installation on a separate Windows machine or clean virtual environment.

Verify the complete setup process rather than only testing on the development computer.

### ✅ Phase 12 Completion Criteria

The final application can be installed on Windows, configured through a setup wizard, and used for local AI conversations without opening a browser or supplying a cloud API key.

---

# 📊 FINAL DEVELOPMENT MILESTONES

| Milestone                      | Phases | Expected Result                               |
| ------------------------------ | ------ | --------------------------------------------- |
| **M1 — Desktop Foundation**    | 0–3    | Functional animated desktop pet               |
| **M2 — AI Intelligence**       | 4–5    | Working local AI text chatbot                 |
| **M3 — Voice Foundation**      | 6–7    | AI listens and speaks                         |
| **M4 — Advanced Voice**        | 8–9    | Continuous, interruptible voice conversations |
| **M5 — Intelligent Companion** | 10     | Memory, personality, emotional responses      |
| **M6 — Final Application**     | 11–12  | Optimized, installable Windows application    |

## ⚙️ Important Implementation Principles

Throughout the project, we must follow several architectural rules.

**1. Modular development:** Character rendering, AI inference, voice processing, and memory must remain separate components.

**2. No API keys:** All conversational AI, speech recognition, and voice generation must run locally. Initial software and model downloads may require internet access.

**3. Native desktop experience:** No Electron, browser frontend, or hosted backend. Ollama operates as a local inference service.

**4. Existing feature preservation:** Each phase should extend the application without unnecessarily rewriting previously completed modules.

**5. Nonblocking interface:** Never run expensive AI inference or transcription directly in the PySide6 GUI thread.

**6. Resource awareness:** Optimize for the 8 GB RAM target before moving to larger models.

**7. Explicit microphone control:** Voice capture must never silently restart after the user has disabled it.

**8. Phase validation:** Each phase must pass its acceptance tests before implementation proceeds to the next.

---

### 🎯 Final Project Outcome

After completing all 13 phases, you will have a **native Windows AI Desktop Friend** with:

✅ Movable sticker-style character, like Codex Pet
✅ Transparent, always-on-top desktop overlay
✅ Animated character expressions and speaking animations
✅ Local AI conversations without cloud API keys
✅ Continuous real-time voice interaction
✅ Ability to interrupt the AI while speaking
✅ Wake-word activation
✅ Persistent conversation history and long-term memory
✅ Customizable personality, voices, and characters
✅ Background execution with system tray controls
✅ Windows installer and startup integration

**The major technical challenge will be Phases 8–9**, where we integrate continuous listening, streaming inference, low-latency speech synthesis, and interruption handling. Those features will determine how natural the final AI companion feels.
