bug_22_text = """

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
"""

with open("docs/reports/broken_features.md", "a", encoding="utf-8") as f:
    f.write(bug_22_text)

print("Successfully appended BUG 22 to docs/reports/broken_features.md")
