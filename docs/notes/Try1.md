# CRITICAL BUG FIX: AI FRIEND VOICE CONVERSATION IS NOT WORKING

Message to AI : Do not implement by yourself 
## ROLE

Act as a senior full-stack developer, real-time voice AI engineer, Python/backend engineer, frontend engineer, and debugging specialist.

I have an existing AI Friend application. Currently, when I speak into the microphone, the application does not respond. My spoken words do not appear in the chat as a user message, and the AI does not respond to me.

I suspect that my voice is not being captured, transcribed, or sent correctly to the backend, but you MUST investigate the actual implementation instead of assuming the cause.

**Your immediate priority is to repair voice conversation functionality in the existing application. Do not start a full-project refactor or work on unrelated features.**

## MY REQUIRED BEHAVIOR

When I speak to my AI Friend:

1. The application must capture my voice through the microphone.
2. My speech must be converted into text using the project's configured speech-recognition system.
3. The recognized text must appear in the chat as a USER message.
4. The recognized text must be sent to the correct backend endpoint or conversation handler.
5. The backend must pass the message to my configured LOCAL AI model.
6. The AI must generate a genuine response.
7. The response must appear in the chat as an ASSISTANT message.
8. The assistant's response must be converted into speech using the configured TTS engine.
9. I must hear the AI response through my speakers or headphones.
10. After the response finishes, the application must return to a usable state so I can speak again.

The complete workflow must function end to end.

**Important:** If I speak a sentence, the application must not silently ignore it, display an empty user message, or wait forever. It must either process the sentence successfully or display a clear, actionable error.

---

# PHASE 1 — TRACE THE ENTIRE VOICE PIPELINE

Before modifying code, inspect the existing repository and locate the actual implementations of:

* Microphone initialization.
* Microphone permission handling.
* Recording start and stop.
* Audio capture.
* Audio buffering.
* Speech recognition.
* Voice activity detection, if present.
* Speech endpoint or silence detection.
* Transcription callbacks.
* Frontend chat state.
* User-message submission.
* Backend API routes or WebSocket handlers.
* AI model invocation.
* Assistant-message rendering.
* Text-to-speech.
* Audio playback.
* Conversation state management.

Identify the specific files, functions, events, and communication paths responsible for each stage.

Trace the complete path:

MICROPHONE
→ AUDIO CAPTURE
→ SPEECH RECOGNITION
→ TRANSCRIBED TEXT
→ USER CHAT MESSAGE
→ BACKEND REQUEST
→ LOCAL AI MODEL
→ ASSISTANT RESPONSE
→ CHAT DISPLAY
→ TEXT-TO-SPEECH
→ AUDIO PLAYBACK

Determine exactly where the current workflow breaks.

Do not assume that a microphone animation means audio is being recorded or that a successful transcription means the message reached the backend.

---

# PHASE 2 — FIX MICROPHONE CAPTURE

Investigate and repair the existing microphone implementation.

Check:

* Whether the correct microphone is selected.
* Whether microphone permissions are granted.
* Whether the application is actually receiving audio samples.
* Whether the recording callback is firing.
* Whether the audio stream remains active while needed.
* Whether the sample rate, channel count, encoding, and buffer format are compatible with the speech-recognition engine.
* Whether audio buffers are empty or truncated.
* Whether recording stops before enough speech is captured.
* Whether silence detection finalizes the recording too early.
* Whether recording continues indefinitely without finalizing.
* Whether microphone resources are being closed prematurely.
* Whether exceptions are silently swallowed.
* Whether the frontend is waiting for an event that never arrives.

Add appropriate diagnostic logging and visible status updates.

The application should distinguish between:

* Microphone unavailable.
* Permission denied.
* Recording started.
* Recording in progress.
* Speech detected.
* Recording completed.
* Transcription in progress.
* Transcription completed.
* No speech detected.
* Recognition failed.

Do not display "Listening" unless the microphone is genuinely active.

Do not silently fall back to an unrelated audio input.

---

# PHASE 3 — FIX SPEECH RECOGNITION AND TRANSCRIPTION

Identify the speech-recognition engine already used by the project.

Verify that it is initialized correctly and can process the audio format supplied by the microphone.

Check:

1. Whether the recognition function is actually called.
2. Whether the audio reaches the recognition engine.
3. Whether the correct input format is used.
4. Whether the recognition engine returns partial or final transcription events.
5. Whether final results are handled correctly.
6. Whether asynchronous callbacks are awaited or processed correctly.
7. Whether transcription errors are lost.
8. Whether recognized text is accidentally discarded.
9. Whether the final transcription is incorrectly treated as empty.
10. Whether the recognition engine is compatible with the installed dependencies and operating system.

If the existing engine supports partial transcription, handle partial and final results correctly. Do not submit each partial result as a separate message.

Only submit a finalized, non-empty transcription as a user message.

Trim leading and trailing whitespace and reject empty or meaningless results.

Do not invent text when recognition fails.

If the current speech-recognition engine cannot operate correctly, identify the actual incompatibility and repair the configuration or implementation. Prefer the existing local/offline solution when it meets the requirements.

Do not switch to a cloud API or require a paid service.

---

# PHASE 4 — ENSURE THE TRANSCRIBED TEXT APPEARS IN CHAT

This is one of the most important requirements.

Currently, when I speak, my spoken words do not appear in the chat as a user query.

Find and fix the exact state-management or event-handling problem responsible.

Verify that:

* A finalized transcription is passed to the chat submission handler.
* The recognized text is added to the visible conversation.
* The message is correctly marked as originating from the USER.
* The message appears only once.
* The correct conversation ID or session context is used.
* The message is sent to the correct backend endpoint.
* The backend receives the same text that the frontend displays.
* The chat does not clear or overwrite the message before it is submitted.
* React state updates, if applicable, do not use stale values.
* A callback does not close over outdated conversation state.
* The voice handler does not bypass the normal message-submission path.
* A UI state update is not mistaken for successful backend delivery.

If text submission already works, reuse the same reliable message-processing path for voice input rather than creating a second, inconsistent implementation.

Use the project's existing message schema and API contracts.

**Acceptance criterion:** When I say "Hello, how are you?", the recognized words must appear as a user message in the chat, and the same recognized text must reach the backend.

If recognition produces no usable text, show a clear error or retry option rather than sending an empty request.

---

# PHASE 5 — FIX FRONTEND/BACKEND COMMUNICATION

Inspect the actual API routes, WebSocket handlers, request schemas, and response formats.

Verify:

* The frontend uses the correct backend base URL.
* The requested endpoint actually exists.
* HTTP methods and request payloads are correct.
* The backend expects the same field names the frontend sends.
* The conversation ID is valid when required.
* Authentication or session requirements are satisfied when applicable.
* The request is actually transmitted.
* The backend receives the expected message.
* The backend does not reject the request because of schema validation.
* The response is parsed using the correct response format.
* Streaming responses are handled correctly if the project uses streaming.
* Connection errors and timeouts are visible.
* The frontend does not wait forever for a response event that never arrives.

Add focused logging at important boundaries:

1. Transcription finalized.
2. User message accepted by frontend.
3. Request sent.
4. Request received by backend.
5. Local model generation started.
6. First model output received.
7. Assistant response completed.
8. Response received by frontend.

Do not log sensitive information unnecessarily. Never log credentials or secrets.

If the backend is already receiving the text, do not waste time rewriting microphone capture. Follow the evidence to the actual failure.

---

# PHASE 6 — ENSURE THE LOCAL AI ACTUALLY RESPONDS

Inspect the configured AI model and its invocation path.

The application is intended to use a local AI model. Preserve the existing local model architecture.

Verify:

* The configured model runtime is available.
* The correct model name is used.
* The model can process the user message.
* The correct conversation context is supplied.
* The generation task is actually awaited or streamed.
* The generated response is not discarded.
* The response is returned using the expected schema.
* Model exceptions are not swallowed.
* The frontend receives the actual model-generated output.

If the application uses Ollama, verify its availability and the configured model before making assumptions about the cause.

Do not hardcode a fake response to simulate success.

Do not require a cloud AI API.

If the local model is unavailable, display a clear error explaining what must be started or configured.

---

# PHASE 7 — FIX ASSISTANT CHAT DISPLAY

Ensure that a successful AI response appears in the conversation.

Verify that:

* The response is added as an ASSISTANT message.
* The user message remains visible.
* The assistant response is associated with the correct conversation.
* The response is not accidentally stored as a USER message.
* The response is not inserted into the user's input box as new user input.
* Streaming chunks are combined or rendered correctly.
* Duplicate callbacks do not create duplicate assistant messages.
* Loading indicators stop when the request completes or fails.
* The interface displays actionable errors instead of remaining stuck.

Reuse existing chat components and message types wherever possible.

---

# PHASE 8 — FIX TEXT-TO-SPEECH AND AUDIBLE RESPONSE

The AI must speak its response aloud when the user initiates a voice conversation.

Inspect the current TTS engine and audio playback implementation.

Determine whether the application uses local TTS, an operating-system voice, or another existing speech engine.

Verify:

1. The TTS engine initializes successfully.
2. The actual assistant response is passed to it.
3. Empty responses are not sent to TTS.
4. The generated audio uses a supported format.
5. The playback component receives the correct audio data.
6. Playback begins successfully.
7. Audio reaches the selected output device.
8. Playback errors are caught and displayed.
9. Old audio is not replayed.
10. Multiple responses do not overlap unintentionally.
11. Audio resources are cleaned up.
12. The assistant's speaking state matches actual playback.

If TTS generates an audio file or byte buffer, verify that the frontend can access and play it correctly.

If the project uses browser-based speech synthesis, verify that the required browser API is supported and that playback is not blocked by its execution context.

If the application uses a desktop shell, inspect its actual audio-output integration.

**Do not treat generating an audio file as proof that the user can hear it.**

The acceptance criterion is actual playback through the configured audio output when the environment permits.

Prefer local/offline TTS to preserve the application's privacy requirements.

If voice output fails, keep the text response visible and provide a clear error rather than losing the conversation.

---

# PHASE 9 — REPAIR THE VOICE CONVERSATION STATE MACHINE

Inspect the existing state management and repair invalid transitions.

Use the existing architecture if possible.

The workflow should support states equivalent to:

* IDLE
* LISTENING
* TRANSCRIBING
* SUBMITTING_USER_MESSAGE
* GENERATING_RESPONSE
* SPEAKING
* ERROR

A valid flow should look like:

IDLE
→ LISTENING
→ TRANSCRIBING
→ SUBMITTING_USER_MESSAGE
→ GENERATING_RESPONSE
→ SPEAKING
→ IDLE

Handle failures with an appropriate recovery path.

Prevent:

* Multiple simultaneous recording sessions.
* Duplicate transcription submissions.
* Duplicate AI requests.
* Stale asynchronous callbacks.
* Infinite retry loops.
* Empty requests.
* Assistant responses being resubmitted as user messages.
* Endless listening when the user is silent.
* Audio playback continuing after cancellation.
* A failed request leaving the interface permanently busy.

Use cancellation and cleanup mechanisms appropriate to the project's framework.

Do not disable the voice feature merely to eliminate the failure.

---

# PHASE 10 — DIAGNOSTIC MODE

Temporarily add a practical diagnostic mode or equivalent structured logs that help identify where voice communication fails.

Expose safe, useful statuses such as:

* Microphone status.
* Recording status.
* Audio duration or sample count.
* Transcription status.
* Recognized-text availability.
* User-message submission status.
* Backend connection status.
* Model-generation status.
* Assistant-response status.
* TTS generation status.
* Audio playback status.

Where appropriate, show an error such as:

"Microphone permission denied."

"No speech was detected. Please try again."

"Speech was recognized, but the message could not be sent."

"The AI model is unavailable. Check that the local model service is running."

"The AI replied, but text-to-speech failed."

Do not expose internal stack traces, credentials, or private data in the normal user interface.

Keep detailed diagnostic information in development logs.

Make diagnostic instrumentation easy to disable or retain behind the project's existing debug setting.

---

# PHASE 11 — TEST THE ACTUAL END-TO-END WORKFLOW

Do not stop after modifying code.

Run the existing application and execute targeted tests.

## Test A: Text chat baseline

1. Type a message manually.
2. Confirm it appears as a user message.
3. Confirm the backend receives it.
4. Confirm the local AI generates a response.
5. Confirm the response appears in chat.

If text chat already works, preserve it.

## Test B: Voice transcription

1. Start the microphone.
2. Speak a clear test sentence.
3. Verify audio is captured.
4. Verify transcription completes.
5. Verify the recognized text appears in chat.

## Test C: Voice-to-AI integration

1. Speak a test sentence.
2. Verify the exact recognized text is submitted.
3. Verify the backend receives the same text.
4. Verify the configured local model generates a real response.
5. Verify the assistant response appears in chat.

## Test D: Spoken assistant response

1. Speak a test sentence.
2. Wait for the AI response.
3. Verify TTS receives the actual response.
4. Verify audio playback starts.
5. Verify playback finishes and the application returns to a usable state.

## Test E: Repeated conversations

1. Speak one sentence.
2. Wait for the assistant to respond.
3. Speak another sentence.
4. Confirm both conversations work.
5. Confirm no old response is replayed.
6. Confirm no duplicate messages appear.

## Test F: Error handling

Test the behavior when:

* The microphone is unavailable.
* Permission is denied.
* No speech is detected.
* Speech recognition fails.
* The backend is unavailable.
* The local model is unavailable.
* TTS fails.
* The user speaks while the assistant is responding, if interruption is supported.

Do not claim to have physically tested the microphone or heard the output if the execution environment does not permit it.

Use automated tests and controlled audio fixtures where appropriate, but clearly distinguish simulated tests from real-device tests.

---

# PHASE 12 — ADD REGRESSION TESTS

Add tests for the actual root cause discovered.

At minimum, test the following where compatible with the architecture:

1. Finalized transcription produces exactly one user message.
2. Empty transcription does not trigger AI generation.
3. The correct transcribed text reaches the backend.
4. A valid backend response appears as an assistant message.
5. The assistant's response is passed to TTS in voice mode.
6. A transcription error does not leave the application stuck.
7. A backend error does not leave the application stuck.
8. A TTS error does not delete the assistant's text response.
9. Duplicate transcription events do not generate duplicate responses.
10. Assistant speech is not submitted as new user input.

Use mocks for isolated unit tests where appropriate. Do not confuse mocked tests with actual microphone or speaker testing.

---

# PHASE 13 — PERFORMANCE AND PRIVACY REQUIREMENTS

Keep the fix focused and efficient.

* Preserve local AI inference.
* Prefer existing local speech recognition and TTS.
* Do not introduce cloud APIs or paid services.
* Avoid unnecessary dependencies.
* Avoid rewriting working components.
* Avoid blocking the UI while waiting for speech recognition or model generation.
* Do not use arbitrary long sleeps to hide race conditions.
* Do not fake transcription or responses.
* Do not remove useful existing functionality.

Measure the main stages separately where possible:

* Audio capture duration.
* Speech-recognition latency.
* Backend request latency.
* Model time to first output.
* Total model-generation time.
* TTS generation time.
* Time to first audible response.

Prioritize correctness first, then optimize measured bottlenecks.

---

# PHASE 14 — FINAL DELIVERABLE

After completing the repairs, create or update this report in the project root:

`AI_Friend_Voice_Bug_Fix_Report.md`

Include:

1. Root cause of the original failure.
2. Exact files and functions involved.
3. Why the spoken text was not appearing in chat.
4. Whether the transcription was reaching the backend.
5. Whether the local model was generating responses.
6. Why voice output did or did not work.
7. Fixes implemented.
8. Tests executed and their actual results.
9. Any tests blocked by microphone, audio-device, model, or environment limitations.
10. Remaining issues.
11. Commands needed to run the repaired application.
12. Any configuration or permission steps still required.

Do not fabricate results.

## FINAL ACCEPTANCE CRITERIA

The task is complete only when the available environment provides sufficient evidence that:

* [ ] The microphone captures valid audio.
* [ ] Spoken words are transcribed.
* [ ] The transcription appears as a user message in chat.
* [ ] The same text reaches the backend.
* [ ] The local AI model generates a genuine response.
* [ ] The response appears as an assistant message.
* [ ] The assistant's response is passed to TTS in voice mode.
* [ ] The generated speech plays through the configured audio output.
* [ ] The application can handle a second spoken message.
* [ ] Errors are visible and recoverable.
* [ ] Empty input does not trigger AI generation.
* [ ] No duplicate messages or infinite loops occur.
* [ ] Existing text chat still works.
* [ ] Regression tests cover the confirmed failure.

If a criterion cannot be verified, state exactly why. Never mark it as passed merely because the code looks correct.

## EXECUTION INSTRUCTIONS

Start by inspecting the current repository and reproducing the voice failure.

Then trace the data through the actual implementation, identify the first broken stage, repair its root cause, and continue testing all downstream stages.

Do not stop after finding a likely cause.

Do not merely provide a report or instructions.

**Modify the existing code, run the tests, verify the complete voice-to-voice workflow as far as the environment allows, and produce the report.**

Work autonomously on routine code changes. Preserve existing data and unrelated modifications.

When finished, give me a concise summary of:

* The actual root cause.
* What you fixed.
* Whether spoken text now appears in chat.
* Whether the AI now responds in text.
* Whether the AI now responds in voice.
* Tests passed and failed.
* Any remaining issue and the exact action required.
* The path to `AI_Friend_Voice_Bug_Fix_Report.md`.
