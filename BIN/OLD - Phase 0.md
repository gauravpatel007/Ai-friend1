🟢 PHASE 0 — PROJECT PLANNING & REQUIREMENT ANALYSIS

Goal: Finalize what we are building, how it should behave, the technologies required, and the overall system architecture.

No implementation in this phase.

0.1 Project Overview

We want to build an intelligent AI desktop companion that lives on the user's Windows desktop.

Unlike ChatGPT or other traditional chatbots, this application will not require users to open a browser or a large application window.

Instead, a small animated character will float on the desktop, similar to Codex Pet.

The AI character will have the ability to:

Communicate through natural voice conversations.
Listen and respond without requiring constant button clicks.
Remember previous conversations.
Express emotions through character animations.
Stay visible above other applications.
Move anywhere on the desktop.
Continue running in the background.
Operate locally without cloud-based AI services.
Main Project Objective

Create an experience where users feel they have a conversational AI companion living on their computer.

The AI should be responsive, conversational, customizable, and resource-efficient.

0.2 Core Application Requirements
A. Desktop Pet System

The desktop companion must support the following functionality:

ID	Requirement	Priority
DP-01	Transparent desktop character	Critical
DP-02	Draggable character	Critical
DP-03	Always-on-top functionality	Critical
DP-04	Background operation	Critical
DP-05	System tray integration	Critical
DP-06	Show/hide character	Critical
DP-07	Character animation system	High
DP-08	Remember character position	High
DP-09	Multiple character selection	Medium
DP-10	Adjustable character size	High
DP-11	Multi-monitor support	High
DP-12	Optional Windows startup	Medium
DP-13	Optional click-through mode	Medium

Expected behavior:

Users can drag the character to the bottom-right, top-left, or any other screen location.

The character remains visible while users work in Chrome, VS Code, File Explorer, or other applications.

It should not interfere with normal mouse interactions outside its visible area.

B. Advanced Real-Time Voice System

This is one of the project's most important modules.

ID	Requirement	Priority
VO-01	Microphone input	Critical
VO-02	Speech-to-text conversion	Critical
VO-03	AI-generated voice replies	Critical
VO-04	Automatic speech detection	Critical
VO-05	Continuous conversation mode	Critical
VO-06	Interrupt AI while speaking	High
VO-07	Wake-word activation	High
VO-08	Male/female voice selection	Medium
VO-09	Microphone mute/unmute	Critical
VO-10	Voice speed adjustment	Medium
VO-11	Silence detection	High
VO-12	Noise filtering	High
VO-13	English/Hindi conversation	Medium
VO-14	Gujarati support	Future
VO-15	Audio device selection	High
Voice Activation Modes

The application will have three configurable modes.

Mode 1: Push-to-Talk

The user clicks the microphone button and begins talking.

This mode is useful during early development and in noisy environments.

Mode 2: Wake Word

The application listens for a predefined activation phrase.

Example:

You: "Hey Buddy."

AI: "Hey! What's up?"

The user can then start a conversation.

Custom wake words require a suitable trained model. We should not assume that arbitrary names will work automatically.

Mode 3: Continuous Conversation

The application automatically detects speech after voice mode has been enabled.

Example:

You: "Hey, what should I do today?"

AI: "Well, do you have any plans?"

You: "Not really."

AI: "Then how about working on something fun?"

The user can speak again naturally, including while the AI is responding.

This is our ultimate voice interaction goal.

0.3 AI Companion Intelligence Requirements

The application should behave like a friendly companion rather than an ordinary question-answering chatbot.

Required Intelligence Features
Feature	Expected Behavior
Context Awareness	Understand the current conversation
Conversation Memory	Remember previous discussions
Long-Term Memory	Retain selected important information
Personality	Respond with a consistent personality
Casual Conversation	Talk naturally instead of giving lengthy formal answers
Emotional Awareness	Adapt responses based on emotional cues
Conversation Continuity	Continue previous discussions
Multilingual Chat	Support multiple languages
Response Streaming	Generate responses progressively
Custom AI Name	Allow users to name their companion
Example

Day 1

You: "I am currently learning Generative AI."

AI: "Nice! What are you learning right now?"

You: "LangChain."

AI: "That's interesting! Are you building something with it?"

Day 5

You: "Hey, what should I study today?"

AI: "Last time you were learning LangChain. Want to continue with that?"

This requires a dedicated memory system, not simply a system prompt.

0.4 Animated Character Requirements

The AI character must respond visually to its internal state.

State	Animation
Idle	Breathing and blinking
Listening	Alert expression and subtle movement
Thinking	Looking around or thinking animation
Speaking	Mouth movement and body animation
Happy	Small jump or smile
Confused	Tilt head
Sleeping	Close eyes
Dragging	Follow mouse movement
Waking Up	Short activation animation
Muted	Display muted indicator
Error	Display confused/error expression
Character Design Requirements

The design should be inspired by the screenshot you uploaded.

Initial character:

Small, cute robot.
Rounded body.
Expressive face.
Smooth animations.
Transparent background.
Adjustable size.
Minimal floating controls.

We'll create an original character rather than copying proprietary Codex Pet artwork.

Recommended approach: Start with 2D animated sprites rather than a real-time 3D model.

This will consume fewer system resources and be easier to integrate into a transparent desktop overlay.

0.5 Application Interface Requirements

The application will contain four main interface components.

Interface 1 — Desktop Pet

The main character appears directly on the desktop.

It should not display a conventional application window border.

Interactions:

Interaction	Action
Left-click	Open quick chat
Right-click	Open options menu
Drag	Move character
Double-click	Toggle voice conversation
Hover	Show small control panel
Interface 2 — Quick Chat Window

A compact window appears beside the character.

Features:

Text input.
AI messages.
Conversation history.
Voice button.
Close/minimize controls.
Streaming response display.
Interface 3 — Settings Window

Settings should include:

General

Launch at Windows startup.
Always on top.
Character size.
Character position.
Appearance.

AI

Select local model.
Companion name.
Personality.
Response length.
Memory controls.

Voice

Select microphone.
Select speaker.
Select AI voice.
Enable continuous listening.
Enable wake word.
Voice speed.

Privacy

Microphone permission.
Delete conversations.
Clear memories.
Local data storage controls.
Interface 4 — System Tray

The application remains accessible from the Windows system tray.

Options:

Show AI Friend.
Enable Voice.
Sleep Mode.
Open Chat.
Open Settings.
Exit Application.
🧰 0.6 COMPLETE TECHNOLOGY STACK

This will be our planned stack.

Layer	Technology	Purpose
Programming Language	Python 3.11	Core development
Desktop UI	PySide6	Native Windows interface
Styling	Qt Style Sheets	Desktop UI styling
Animations	Qt + Sprite Sheets	Character animations
Local LLM Runtime	Ollama	Run AI models locally
AI Model	Qwen3 1.7B	Main conversational intelligence
Alternative Model	Qwen3 4B	Higher-quality responses
Speech Recognition	Faster-Whisper	Speech-to-text
Voice Detection	Silero VAD	Detect user speech
Voice Generation	Piper TTS	Lightweight offline speech
Improved Voice	Kokoro TTS	More natural speech
Wake Word	openWakeWord	Local voice activation
Audio Capture	sounddevice	Microphone recording
Audio Processing	NumPy + soundfile	Audio handling
Conversation Storage	SQLite	Store conversations
Memory Retrieval	SQLite FTS5	Search stored memories
AI Communication	Ollama Local HTTP API	Send messages to local model
Background Processing	QThread + worker processes	Nonblocking execution
Configuration	JSON	Application settings
Logging	Python logging	Debugging and diagnostics
Windows Packaging	PyInstaller	Create executable
Installer	Inno Setup	Build Windows installer
Testing	pytest + pytest-qt	Automated testing
Why these technologies?

PySide6: Provides native desktop windows, animation support, and system tray integration. No browser or web frontend is required.

Ollama: Runs language models locally. It supports streaming responses and controlling how long models remain loaded in memory. Its local HTTP API does not require a cloud API key.

Faster-Whisper: Efficient local transcription using CTranslate2.

Silero VAD: Local speech activity detection, with an ONNX Runtime option that can help reduce dependencies.

Kokoro: An 82-million-parameter local TTS model supporting languages including English and Hindi.

Important licensing consideration: The maintained Piper package is GPL-3.0-or-later, while some openWakeWord pretrained models have noncommercial licensing restrictions. This matters if we distribute the application commercially. We will review software and model licenses before packaging.

0.7 Hardware Requirements

We should plan for your Windows 11 system with approximately 8 GB RAM.

Component	Minimum Target	Preferred
RAM	8 GB	16 GB+
CPU	Modern 64-bit processor	Strong multicore CPU
GPU	Not required	Dedicated GPU
Storage	Approximately 5–10 GB free initially	15 GB+ free
Microphone	Required	Headset microphone
Speaker	Required	Headphones initially
OS	Windows 10/11 64-bit	Windows 11

For the initial implementation:

LLM: Qwen3 1.7B
STT: Faster-Whisper Tiny/Base
TTS: Piper
VAD: Silero ONNX

We will benchmark memory and response latency before enabling all components simultaneously.

An 8 GB CPU-only system may not provide the responsiveness of ChatGPT's cloud-based voice mode. Our architecture will therefore prioritize low overhead and graceful performance degradation.

0.8 Proposed System Architecture
                     WINDOWS DESKTOP
                            |
                            ▼
                  AI DESKTOP FRIEND
                     (PySide6)
                            |
              ┌─────────────┴─────────────┐
              |                           |
              ▼                           ▼
       DESKTOP PET UI              APPLICATION CORE
              |                           |
       ┌──────┴──────┐          ┌─────────┴─────────┐
       |             |          |                   |
   Animations     Controls   AI Manager        Voice Manager
                                |                   |
                          ┌─────┴─────┐       ┌─────┴──────┐
                          |           |       |            |
                       Ollama       Memory  Whisper      Silero VAD
                          |           |       |            |
                        Qwen3       SQLite    └─────┬──────┘
                          |                         |
                          └──────────┬──────────────┘
                                     |
                                     ▼
                              RESPONSE MANAGER
                                     |
                                     ▼
                                 PIPER TTS
                                     |
                                     ▼
                               AUDIO PLAYBACK
                                     |
                                     ▼
                             CHARACTER SPEAKING

All AI processing happens on the user's computer.

The initial model downloads and application installation will require internet access, but normal conversations should work completely offline.

0.9 Performance Requirements
Requirement	Target
Desktop animations	Smooth 30 FPS
UI responsiveness	No blocking during AI processing
Speech detection	Low-latency detection
Response streaming	Start displaying text before completion
Audio playback	Begin when first speech chunk is available
Microphone interruption	Stop playback promptly
Offline operation	Full core functionality after setup
Background mode	Reduced resource consumption
Privacy	No external transmission of conversations
Reliability	Recover from model/audio errors

Response latency must be measured on the actual hardware. We should not commit to an unrealistic sub-second conversational response before testing.

0.10 Privacy and Security Requirements

Because this application can listen through the microphone, privacy is essential.

Requirements:

Microphone access must be explicitly enabled.
Always display a visible listening indicator.
Provide an immediate microphone mute control.
Do not store raw audio by default.
Store conversations locally.
Allow users to delete stored conversations and memories.
Keep Ollama accessible only on the local machine by default.
Never silently enable the microphone after the user has disabled it.
Do not collect screenshots, keystrokes, or other application data without separate explicit permission.
✅ Phase 0 Deliverables

At the end of Phase 0, we should have:

Final feature requirements.
Confirmed technology stack.
System architecture.
Voice interaction design.
Character animation specification.
UI layout specification.
Hardware compatibility targets.
Development milestones.
Testing and acceptance criteria.
Initial performance and privacy requirements.

Phase 0 is now conceptually defined.

The following phases describe how we will implement everything.