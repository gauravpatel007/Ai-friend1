# 🐛 AI Friend — Full Project Bug Report

> **Generated**: 2026-10-30  
> **Project**: AI Desktop Friend A1  
> **Scope**: Complete codebase analysis — Python backend, React frontend, lifecycle, voice, AI, movies, settings, API  
> **Method**: Bugs are audited and appended one-by-one during live code analysis.

---



### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #1: `UnboundLocalError` on Faster-Whisper Fallback Loading
- **File**: [`app/voice/whisper_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/whisper_engine.py#L166-L195)
- **Severity**: **High / Runtime Crash**
- **Component**: Voice Engine / Speech Recognition
- **Description**:
  In `load_model()`, the import `from faster_whisper import WhisperModel` is placed inside the initial `try` block. If `faster_whisper` fails to import (e.g. module missing, DLL load failure, or CUDA incompatibility), `WhisperModel` is never assigned.
  However, in the fallback `except Exception:` block, line 190 attempts:
  ```python
  self._model = WhisperModel(
      model_size_or_path="tiny",
      ...
  )
  ```
  Because `WhisperModel` was defined locally via import in the `try` block, Python treats it as a local variable. Referencing it after import failure triggers:
  `UnboundLocalError: cannot access local variable 'WhisperModel' where it is not associated with a value`
- **Impact**:
  When Whisper fails to load (such as on machines without pre-installed `faster_whisper` or missing CTranslate2 runtime), the fallback recovery branch immediately crashes with an `UnboundLocalError`, preventing graceful fallback or proper error reporting.
- **Fix Required**:
  Import `WhisperModel` safely or guard fallback instantiation with `try: from faster_whisper import WhisperModel except ImportError:` before attempting to use it in the fallback block.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #2: SAPI5 TTS Broken Due to Missing `pythonnet` Dependency Instead of Native `win32com`
- **File**: [`app/voice/sapi5_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/sapi5_engine.py#L116-L127)
- **Severity**: **High / Feature Broken**
- **Component**: Voice Engine / Offline Windows TTS
- **Description**:
  The SAPI5 engine implementation requires `import clr` (PythonNet CLR bridge) in both `is_available()` (line 116) and `synthesize()` (line 199) to instantiate COM objects `SAPI.SpVoice` and `SAPI.SpMemoryStream`.
  However, `pythonnet` / `clr` is not installed in the application virtual environment. Meanwhile, `pywin32` (`win32com.client`) is already installed and fully capable of driving native SAPI5 without any third-party .NET CLR bridge.
- **Impact**:
  `Sapi5TTSEngine.is_available()` always evaluates to `False`. When Kokoro and Piper are not yet downloaded or fail, the application cannot use Windows' built-in speech synthesizer ("Microsoft David Desktop" / "Microsoft Zira Desktop") and falls back to an artificial sine-wave beep tone instead of real offline speech.
- **Fix Required**:
  Add a primary `win32com.client` COM dispatch implementation in `sapi5_engine.py` (with `pythoncom.CoInitialize()`) with fallback to `clr`, so that native Windows speech works out-of-the-box without requiring .NET dependencies.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #3: Pet Position Multi-Monitor Clamp Bug in `pet_window.py`
- **File**: [`app/desktop/pet_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py#L254-L264)
- **Severity**: **Medium / UI Regression**
- **Component**: Desktop Pet Overlay / Window Positioning
- **Description**:
  In `DesktopPetWindow._restore_position()`, the method correctly checks whether the saved `(pos_x, pos_y)` coordinates lie on any connected monitor using `_is_position_on_active_screen(target)`.
  However, in line 254:
  ```python
  screen = QApplication.primaryScreen()
  screen_geo = screen.availableGeometry() if screen else None
  ```
  It unconditionally obtains the geometry of the **primary** screen. If the user placed Buddy on a secondary monitor (for instance, an external display at negative X coordinates or extended desktop X > 1920), line 261 clamps the coordinates against `screen_geo` of the primary screen:
  ```python
  clamped_x = max(screen_geo.left() + 20, min(int(pos_x), screen_geo.right() - self.width() - 30))
  ```
- **Impact**:
  Users with dual or triple monitor setups who place their companion on a secondary monitor find that every time the app launches or restarts, Buddy is dragged back onto their primary screen.
- **Fix Required**:
  Determine the active screen using `QApplication.screenAt(target) or QApplication.primaryScreen()` so the boundary clamping respects the actual monitor containing the pet.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #4: Global Bare `Escape` Key Hook Permanently Disables Voice During Normal PC Usage
- **File**: [`app/core/global_hotkeys.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/global_hotkeys.py#L113-L119) & [`app/voice/voice_conversation_controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py#L494-L520)
- **Severity**: **High / Severe UX Bug**
- **Component**: Core Input Interception / Voice Controller
- **Description**:
  `GlobalHotkeyManager` installs an operating-system-wide low-level keyboard hook (`WH_KEYBOARD_LL`) that intercepts the bare `VK_ESCAPE` keypress with zero keyboard modifiers, even when third-party applications (VS Code, games, browsers, Excel) are in the foreground.
  When triggered, `emergency_stop()` is dispatched, which:
  1. Stops and purges the microphone recording stream (`self.mic_manager.emergency_stop()`).
  2. Disables the wake word engine (`self.wake_word_engine.disable()`).
  3. Transitions voice state to `"off"` (`signals.voice_state_changed.emit("off")`).
- **Impact**:
  During routine PC work (such as exiting a menu, cancelling a search, or closing a dialog in any other application), pressing `Escape` silently terminates Buddy's microphone capture and shuts down voice listening. The user has no indication why their companion suddenly went deaf and stopped responding to their voice.
- **Fix Required**:
  Either:
  1. Require a dedicated modifier combo (e.g., `Ctrl+Escape` or `Ctrl+Alt+Escape`) for system-wide emergency stop.
  2. Or restrict bare `Escape` handling to when AI Friend's own windows (Chat, Pet, Settings) have active focus.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #5: Stream Abort on Cancellation Leaks Unhandled `ValueError` / `AttributeError` in `ollama_client.py`
- **File**: [`app/ai/ollama_client.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ollama_client.py#L254-L260) & [`#L306-L310`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ollama_client.py#L306-L310)
- **Severity**: **Medium / False Error Notification**
- **Component**: AI Service / Ollama Streaming Client
- **Description**:
  In `OllamaClient.chat_stream()`, when cancellation is triggered from another thread (such as user clicking Cancel, editing prompt, or speaking an interruption), `cancellation_token.register(lambda: resp.close())` closes the HTTP response handle.
  In Python's `http.client.HTTPResponse`, calling `.close()` from a background thread while `for line in resp:` is iterating on another thread sets the internal file pointer `resp.fp` to `None`. The next line iteration throws `ValueError: I/O operation on closed file` or `AttributeError: 'NoneType' object has no attribute 'readline'`.
  However, the `except` clause on line 306 only catches:
  ```python
  except (urllib.error.URLError, socket.error) as e:
      if cancellation_token and cancellation_token.is_cancelled:
          raise OllamaCancelledError("Stream aborted per cancellation request.") from e
  ```
  Neither `ValueError` nor `AttributeError` is caught in this block.
- **Impact**:
  The unhandled `ValueError` escapes from `chat_stream()`. Even though the user intentionally cancelled the request, the UI displays a red error notification (*"Generation error: I/O operation on closed file"*) instead of gracefully completing the cancellation.
- **Fix Required**:
  Add `(urllib.error.URLError, socket.error, ValueError, AttributeError)` to the caught exceptions and check `cancellation_token.is_cancelled` before re-raising.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #6: Recommendation Intent Parser Over-Matches 'like' Substrings
- **File**: [`app/ai/movie_recommendation_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_recommendation_engine.py#L292-L308)
- **Severity**: **Medium / Query Misinterpretation**
- **Component**: Movie Hub / Intent Recognition
- **Description**:
  In `MovieRecommendationEngine.parse_intent()`, the regex pattern for finding reference titles is:
  ```python
  m_like = re.search(r"\b(?:like|similar\s+to)\s+([A-Za-z0-9\s:,\'-]+?)(?:\s+(?:movies?|films?|series|shows?|in\b|from\b|$))", query, re.IGNORECASE)
  ```
  The word `"like"` in English is frequently used as a desire verb rather than a comparison preposition (e.g., *"I would like a good thriller"*, *"Can you give me something like exciting"*).
- **Impact**:
  When a user types *"I would like a good thriller"*, the parser extracts `similar_to = "a good thriller"`. It then queries TMDB's search API for a movie literally titled *"a good thriller"*. When that lookup fails or returns irrelevant results, the entire recommendation pipeline is corrupted.
- **Fix Required**:
  Require explicit comparison phrasing such as `r"(?:movies?\s+like|films?\s+like|similar\s+to)\s+([A-Za-z0-9\s:,\'-]+)"` or explicitly ignore `"would like"`, `"i'd like"`, `"i like"`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #7: Control Bar Capsule & Speech Bubble Clamp Against Primary Screen Instead of Active Screen
- **File**: [`app/desktop/control_bar.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/control_bar.py#L196-L213) & [`app/desktop/speech_bubble.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/speech_bubble.py#L265-L272)
- **Severity**: **Medium / Multi-Monitor Visual Disconnect**
- **Component**: Desktop UI / Overlay Anchoring
- **Description**:
  When calculating anchor positions relative to Buddy, both `control_bar.py` and `speech_bubble.py` query:
  ```python
  screen = QApplication.primaryScreen()
  screen_rect = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
  ```
  They clamp the popup coordinates to `screen_rect` of the primary monitor.
- **Impact**:
  If the pet window is located on a secondary monitor (e.g. monitor with bounds X: [1920, 3840]), the control capsule dock and speech bubble clamp their X positions to `screen_rect.right()` of the primary monitor (X <= 1920). The speech bubble and dock appear stranded on the edge of the first monitor while Buddy is sitting on the second monitor.
- **Fix Required**:
  Query `screen = QApplication.screenAt(pet_rect.center()) or QApplication.primaryScreen()` so geometry clamping aligns with the pet's active display.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #8: Concurrent Search History Double-Save Causes UUID Mismatch and Ghost Entries
- **File**: [`app/api/movie_routes.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/movie_routes.py#L958-L961) & [`src/components/MovieHub/AIRecommendationSection.tsx`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/src/components/MovieHub/AIRecommendationSection.tsx#L198-L209)
- **Severity**: **Medium / State Desync & UI Glitch**
- **Component**: Movie Hub / Search History Sync
- **Description**:
  When a user executes an AI recommendation query:
  1. The backend route `POST /api/movies/recommendations` automatically calls `storage.add_search_history_query(req.query)`. Inside SQLite, this generates a new record with a server-generated UUID `server_uuid`.
  2. Concurrently, the frontend `AIRecommendationSection.tsx` generates its own client-side UUID `client_uuid` and sends a `POST /api/movies/history` request with `{ id: client_uuid, query: text }`.
  3. `add_search_history_query` has a deduplication clause: if an identical query exists within 20 seconds, it deletes the existing record and replaces it.
- **Impact**:
  The record created by the frontend is deleted and replaced with a different UUID. When the user later attempts to click "Delete" on that history entry in the frontend, the frontend sends a `DELETE /api/movies/history/{client_uuid}` request. The backend finds 0 rows matching `client_uuid`, and the deleted item ghosts back into the list upon next refresh.
- **Fix Required**:
  Remove the duplicate client-side `POST /api/movies/history` invocation when `getRecommendations()` already performs persistence on the backend, and return the canonical `history_id` in `RecommendationResponse`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #9: `POST /api/config/reset` Resets JSON File but Fails to Synchronize Runtime Systems
- **File**: [`app/api/server.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py#L333-L342) & [`app/settings/config_manager.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/settings/config_manager.py#L215-L222)
- **Severity**: **Medium / Settings Desynchronization**
- **Component**: Application Settings / Reset Lifecycle
- **Description**:
  When `POST /api/config/reset` is invoked, `config_manager.reset_to_defaults()` writes the factory default JSON to disk and emits `config_reloaded`.
  However, runtime subsystems that register external OS resources (specifically: Windows Startup registry via `startup_manager`, active TMDB API client keys in memory, personality prompt parameters, and voice service speeds) do not listen to `config_reloaded`.
- **Impact**:
  If the user disabled Windows startup and reset settings to defaults (where startup is enabled), the registry key is not re-registered. If the user had a custom TMDB key and resets settings, the in-memory TMDB client continues using the old key until a cold restart.
- **Fix Required**:
  In `_on_config_reset`, explicitly invoke `set_startup_enabled(default_startup)`, re-initialize `TMDBCredentialManager.refresh()`, and notify `VoiceService`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #10: Post-`app.exec()` `processEvents()` Call Deadlocks on Chromium DirectX Thread
- **File**: [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L164-L171) & [`app/core/lifecycle.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/lifecycle.py#L493-L502)
- **Severity**: **High / Process Hang on Exit**
- **Component**: Application Lifecycle / Shutdown Coordinator
- **Description**:
  After `app.exec()` exits with code 0 on line 175 of `main.py`, the teardown sequence previously attempted to run `app.processEvents()` to clear lingering Qt events.
  However, `QWebEngineView` (Chromium) initializes DirectX hardware acceleration threads (`QDxgiVSyncService`). Calling `processEvents()` on a terminating event loop blocks waiting on the DXGI sync service thread:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x...
  ```
- **Impact**:
  The application process never exits cleanly. The terminal hangs indefinitely, blocking the user from running new commands. Background threads (FastAPI port 8765) remain active in the Windows process table as an orphaned process.
- **Fix Required**:
  Never invoke `app.processEvents()` after `app.exec()` has returned. Allow the main process to exit cleanly and invoke `os._exit(exit_code)` if unmanaged native C-threads (WASAPI/DirectX) fail to join within a 1.5-second bounded grace timeout.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #11: Math Expression Evaluator Misinterprets Slashed/Hyphenated Dates as Arithmetic Operations
- **File**: [`app/ai/math_evaluator.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/math_evaluator.py#L43-L45) & [`app/ai/ai_service.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ai_service.py#L610-L622)
- **Severity**: **Medium / Prompt Hijacking Bug**
- **Component**: AI Service / Deterministic Fast-Path Evaluators
- **Description**:
  In `MathExpressionEvaluator.extract_and_evaluate()`:
  ```python
  pattern = re.compile(
      r"(?:(?:what\s+is|calculate|evaluate|solve)\s+)?"
      r"([0-9]+(?:\.[0-9]+)?(?:\s*[\+\-\*\/\^]\s*[0-9]+(?:\.[0-9]+)?)+)",
      re.IGNORECASE,
  )
  ```
  The regex matches digit strings separated by `/` or `-` without requiring math intent verbs or operator spacing.
- **Impact**:
  Whenever the user references a date in natural conversation (e.g., *"What events happened on 2026/10/30?"*, *"Remind me on 12/25/2024"*, or *"My appointment is on 2024-11-15"*), the companion is commanded that the user asked a math problem. It forcibly responds: *"The answer to 2026/10/30 is 6.7533"* or *"The result of 2024-11-15 is 1998"*, completely ignoring the user's actual question.
- **Fix Required**:
  Add date rejection filters in `MathExpressionEvaluator` that ignore strings matching date formats (`\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b` and `\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b`), and require spaces around `/` or `-` operators unless explicitly preceded by calculation intent verbs (*"calculate"*, *"what is"*, *"solve"*).

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #12: Companion Repeatedly Flashes Introductory Greeting ("Hey! I'm Buddy!") on Every Conversation Turn
- **File**: [`app/desktop/pet_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py#L356-L379)
- **Severity**: **Medium / Annoying UX Bug**
- **Component**: Desktop Companion / Speech Bubble & Visual State Sync
- **Description**:
  In `DesktopPetWindow._apply_visual_state()`, the state-to-speech mapping includes:
  ```python
  state_speeches = {
      "idle": f"Hey! 👋 I'm {companion_name}!",
      "listening": "I'm listening...",
      "thinking": "Thinking...",
      "speaking": "Let me tell you...",
      "happy": "That's awesome!",
      "sleeping": "Z z z ...",
  }
  ```
  Whenever any state transitions back to `"idle"`:
  - After TTS playback completes a conversation turn
  - When speech is stopped or cancelled
  - After dragging the pet window
  - When waking up from sleep mode
  
  line 376 executes:
  ```python
  self.speech_bubble.show_message(state_speeches[state_str], self.frameGeometry(), duration_ms=3200)
  ```
- **Impact**:
  Buddy re-introduces himself with *"Hey! 👋 I'm Buddy!"* for 3.2 seconds at the end of **every single voice interaction or response**, cluttering the screen and breaking immersion.
- **Fix Required**:
  Add an `_initial_greeting_shown: bool = False` flag to `DesktopPetWindow`. Show the greeting bubble only once on initial pet display, and do not show introductory speech on subsequent returns to `CharacterState.IDLE`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #13: Voice Window "Stop" Control Permanently Kills Microphone Capture and Sets Voice Mode to "OFF"
- **File**: [`app/desktop/voice_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/voice_window.py#L643-L646), [`app/voice/voice_service.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_service.py#L385), & [`app/voice/voice_conversation_controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py#L508)
- **Severity**: **High / Severe UX Bug**
- **Component**: Voice UI / Voice Conversation State Machine
- **Description**:
  In `VoiceWindow`, the primary circular red action button `btn_stop` has the tooltip *"Stop Voice Interaction"*. When clicked, `_on_stop_clicked()` emits:
  ```python
  def _on_stop_clicked(self) -> None:
      signals.emergency_stop_requested.emit()
      signals.ai_cancel_requested.emit()
      self.set_state("idle")
  ```
  Both `VoiceService.emergency_stop()` and `VoiceConversationController.emergency_stop()` contain:
  ```python
  self.set_mode(VoiceMode.OFF)
  signals.voice_state_changed.emit("off")
  ```
- **Impact**:
  When a user clicks the Stop button simply to interrupt Buddy speaking or halt an ongoing monologue, Buddy does not just pause or stop talking—his microphone capture is completely closed, the wake word engine is disabled, and the global voice mode switches permanently to `"off"`. Buddy goes completely deaf and will no longer respond to wake words or voice input until the user manually digs into the Settings dialog to re-enable voice mode.
- **Fix Required**:
  Update `_on_stop_clicked()` to halt active playback and cancel the current inference turn (`audio_player.stop()` and `ai_cancel_requested`) without transitioning global voice listening mode to `"off"`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #14: History Pruning Pops Odd Messages, Leaving Orphaned Assistant Turns as the Conversation Start
- **File**: [`app/ai/conversation_context.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/conversation_context.py#L120-L136)
- **Severity**: **Medium / Prompt Integrity Bug**
- **Component**: AI Service / Conversation Context & Memory Management
- **Description**:
  In `ConversationContext._prune_history()`, when token budget is exceeded, the loop drops individual messages one at a time:
  ```python
  total_tokens = sum(estimate_token_count(m["content"]) for m in self._history)
  while self._history and total_tokens > available_budget:
      # Drop the oldest message
      dropped = self._history.pop(0)
      total_tokens -= estimate_token_count(dropped["content"])
  ```
  Likewise, in turn-based pruning:
  ```python
  max_messages = self.max_turns * 2
  if len(self._history) > max_messages:
      self._history = self._history[-max_messages:]
  ```
- **Impact**:
  Normal conversational history consists of alternating `(user, assistant)` message pairs. When an odd number of messages is pruned, the remaining history begins with an `assistant` turn immediately following the `system` prompt:
  ```json
  [
    {"role": "system", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."}
  ]
  ```
  Major LLM backends (such as Ollama's Llama 3/Mistral chat templates and Anthropic/OpenAI completion parsers) strictly expect the chat history after `system` to begin with a `user` turn. When history starts with an orphaned `assistant` message, the model hallucinates that it is conversing with itself, continues an uninterrupted monologue, or produces invalid prompt token sequences.
- **Fix Required**:
  Update `_prune_history()` to prune in complete turn pairs (pop both `user` and `assistant`), or guarantee via `while self._history and self._history[0]["role"] != "user": self._history.pop(0)` that the pruned history always begins with a user turn.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #15: `_InterimTranscribeWorker.run()` Exception Skips Callback, Freezing Word-by-Word Interim Speech Streaming
- **File**: [`app/voice/whisper_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/whisper_engine.py#L102-L113) & [`app/voice/voice_conversation_controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py#L625-L628)
- **Severity**: **Medium / Live STT Freezing**
- **Component**: Voice Engine / Real-Time Interim Speech Recognition
- **Description**:
  In `_InterimTranscribeWorker.run()`:
  ```python
  def run(self) -> None:
      try:
          text = self.engine.transcribe_interim(
              audio_data=self.audio_data,
              language=self.language,
              prompt=self.prompt,
          )
          if self.callback:
              self.callback(self.generation_id, text)
      except Exception as e:
          logger.debug("Interim transcription pass skipped: %s", e)
  ```
  In `voice_conversation_controller.py`:
  ```python
  if ... and not self._is_interim_transcribing:
      self._is_interim_transcribing = True
      self.whisper_engine.transcribe_interim_async(...)
  ```
  The lock `self._is_interim_transcribing = False` is cleared inside the callback:
  ```python
  def _on_interim_transcription_ready(self, gen_id: int, text: str) -> None:
      self._is_interim_transcribing = False
  ```
- **Impact**:
  If an exception occurs during `transcribe_interim()` (e.g. CUDA transient memory error, lock acquisition timeout, or numpy array reshaping error), `self.callback` is never called.
  As a result, `_is_interim_transcribing` remains `True` permanently for the rest of that user utterance. The controller never dispatches any further interim transcription requests, and the live word-by-word speech subtitle UI completely freezes for the remainder of the user's speech.
- **Fix Required**:
  Place the callback invocation or error notification in a `finally:` block in `_InterimTranscribeWorker.run()`:
  ```python
  def run(self) -> None:
      text = ""
      try:
          text = self.engine.transcribe_interim(...)
      except Exception as e:
          logger.debug("Interim transcription pass skipped: %s", e)
      finally:
          if self.callback:
              self.callback(self.generation_id, text)
  ```

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #16: `WebSocketManager.broadcast()` Lacks `default=str`, Crashing Broadcast Loops on Non-Primitive Types
- **File**: [`app/api/websocket.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/websocket.py#L51-L57)
- **Severity**: **High / Broadcast Task Crash**
- **Component**: Backend WebSocket Manager
- **Description**:
  In `WebSocketManager.broadcast(event_type, data)`:
  ```python
  payload = json.dumps({"type": event_type, "data": data if data is not None else {}})
  ```
  `json.dumps()` is called without `default=str` or custom serializer, outside of any `try/except` block.
- **Impact**:
  Whenever event `data` contains standard Python types commonly used in our backend models—such as `datetime`, `date`, `uuid.UUID`, `pathlib.Path`, `set`, numpy scalar numbers (`np.float32`, `np.int64`), or Pydantic instances—`json.dumps()` immediately raises `TypeError: Object of type ... is not JSON serializable`.
  Because this exception occurs before the connection loop `for conn in list(self.active_connections):`, the broadcast task immediately aborts. None of the connected clients (React MovieHub, Desktop Chat, or Voice Window) receive the update.
- **Fix Required**:
  Update line 56 to use `json.dumps({"type": event_type, "data": data if data is not None else {}}, default=str)`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #17: Windows Startup Registry Auto-Launch Executes in `System32`, Causing `load_dotenv()` to Miss `.env` File
- **File**: [`app/core/startup_manager.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/startup_manager.py#L40-L42) & [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L13-L16)
- **Severity**: **High / Environment Configuration Failure**
- **Component**: Core Startup Integration / Process Working Directory
- **Description**:
  `startup_manager._get_executable_path()` registers `pythonw.exe "g:\...\main.py"` under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
  When Windows logs the user in and launches this command, the operating system assigns `C:\Windows\System32` (or `%USERPROFILE%`) as the Current Working Directory (`os.getcwd()`).
  In `main.py`:
  ```python
  from dotenv import load_dotenv
  load_dotenv()
  ```
  Without an explicit directory argument, `load_dotenv()` searches for `.env` in `os.getcwd()` (`C:\Windows\System32\.env`), which does not exist.
- **Impact**:
  When the application starts automatically on PC boot, `.env` is never loaded. Critical credentials (such as `TMDB_API_KEY` or custom LLM server addresses defined in `.env`) are missing, breaking movie search and external API integrations until the user manually restarts the app from its workspace folder.
- **Fix Required**:
  In `main.py`, explicitly resolve the project directory:
  ```python
  project_root = Path(__file__).resolve().parent
  load_dotenv(project_root / ".env")
  os.chdir(project_root)
  ```

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #18: `KokoroTTSEngine.synthesize()` Hardcodes `lang="en-us"`, Causing Phonemization Failures on British Voices
- **File**: [`app/voice/kokoro_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/kokoro_engine.py#L288-L293)
- **Severity**: **Medium / Audio Distortion Bug**
- **Component**: Voice Engine / Neural Kokoro TTS
- **Description**:
  In `KokoroTTSEngine.synthesize()`:
  ```python
  samples, sample_rate = self._kokoro.create(
      text=cleaned_text,
      voice=voice,
      speed=self._speed,
      lang="en-us",
  )
  ```
  The synthesis language parameter `lang="en-us"` is unconditionally hardcoded.
- **Impact**:
  Kokoro-82M explicitly supports British English voices (`bf_emma`, `bm_george`) and international languages. When a British voice is selected, `kokoro-onnx` requires `lang="en-gb"`. Forcing `lang="en-us"` on British voice models causes the phonemizer to misparse phoneme representations, producing unnatural glitches, wrong vowel pitches, or runtime phonemizer warnings.
- **Fix Required**:
  Derive the appropriate language tag dynamically from the voice name or `kwargs`:
  ```python
  lang_code = "en-gb" if voice.startswith(("bf_", "bm_")) else "en-us"
  ```

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #19: `KokoroTTSEngine` Emits Duplicate `synthesis_completed` Signal When Delegating to Fallback Engine
- **File**: [`app/voice/kokoro_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/kokoro_engine.py#L254-L257) & [`#L319-L321`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/kokoro_engine.py#L319-L321)
- **Severity**: **Medium / State Desync & Double Audio Trigger**
- **Component**: Voice Engine / Fallback Chain Architecture
- **Description**:
  When `KokoroTTSEngine` encounters missing model weights or a synthesis exception, it delegates to `self.fallback_engine` (e.g. `PiperTTSEngine` or `Sapi5TTSEngine`):
  ```python
  audio = self.fallback_engine.synthesize(cleaned_text, **kwargs)
  self.synthesis_completed.emit(audio)
  return audio
  ```
  However, `self.fallback_engine.synthesize()` *already* internally emits `self.synthesis_completed.emit(result)`.
- **Impact**:
  Both the fallback engine and Kokoro emit the `synthesis_completed` Qt signal for the exact same synthesized audio chunk. Downstream listeners that subscribe to both engines or to the signal bus receive duplicate audio completion events, resulting in double metric recordings, duplicate subtitles, and potential playback stutter.
- **Fix Required**:
  Do not emit `self.synthesis_completed.emit(audio)` when delegating to `self.fallback_engine.synthesize()`, as the fallback engine already handles its own signal emission.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #20: `ConversationRepository.add_message()` Over-Aggressive 4-Second De-Duplication Drops Legitimate Repeated User Prompts and Corrupts SQLite History
- **File**: [`app/memory/conversation_repository.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/memory/conversation_repository.py#L148-L179) & [`app/api/server.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py#L552-L567)
- **Severity**: **High / Data Loss & History Corruption**
- **Component**: Memory System / Conversation Repository
- **Description**:
  In `ConversationRepository.add_message()`:
  ```python
  if role_clean == "user":
      last_row = conn.execute("...").fetchone()
      if last_row and last_row["role"] == "user" and last_row["content"] == content:
          if (now_ts - last_ts) < 4.0:
              return Message(...)  # Returns existing message without inserting
  ```
  Meanwhile, in `POST /api/chat/messages` in `server.py`:
  ```python
  user_msg = repo.add_message(conv_id, "user", cleaned, status="completed")
  assistant_msg = repo.add_message(conv_id, "assistant", "", status="streaming")
  ```
- **Impact**:
  If the user quickly repeats a short word in two consecutive turns (e.g. AI asks: *"Should I proceed?"*, user replies *"yes"*; then AI asks: *"Confirm?"*, user replies *"yes"* within 4 seconds), `add_message()` silently rejects inserting the second user message.
  However, `server.py` immediately proceeds to insert a new empty `assistant` placeholder and triggers AI generation. SQLite now contains two consecutive assistant messages with no intervening user turn! When reloading chat history, the database is permanently corrupted with orphaned assistant messages.
- **Fix Required**:
  Only reject duplicate user messages if the *very last* message in the entire conversation is already that exact user message AND no assistant response was ever recorded for it. If the last message was from the assistant, always allow the user's new message.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #21: `BuddyStateManager.enter_sleep()` Emits `emergency_stop_requested`, Killing Microphone Capture and Disabling the Wake Word Engine Needed to Wake Him Up
- **File**: [`app/core/buddy_state_manager.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/buddy_state_manager.py#L125-L131)
- **Severity**: **High / Severe UX & Logic Contradiction**
- **Component**: Core Companion State Machine / Sleep-Wake Cycle
- **Description**:
  When Buddy is commanded to go to sleep (*"Go to sleep"*, *"Sleep Buddy"*), `BuddyStateManager.enter_sleep()` executes:
  ```python
  signals.ai_cancel_requested.emit()
  signals.emergency_stop_requested.emit()
  ```
  However, `emergency_stop_requested` triggers `voice_service.emergency_stop()`, which:
  1. Shuts down PortAudio microphone capture (`mic_manager.emergency_stop()`).
  2. Disables the wake word detector (`wake_word_engine.disable()`).
  3. Transitions voice state to `"off"`.
- **Impact**:
  Even though the architecture doc specifically states that during sleep *"the wake-word detection mechanism remains operational to listen for explicit wake commands"*, line 128 completely terminates microphone capture and kills the wake word engine!
  Buddy goes completely deaf and can **NEVER** be woken up by voice commands (*"Hey Buddy, wake up"*). The user is forced to open Settings or click menus manually because voice capture was destroyed.
- **Fix Required**:
  Replace `signals.emergency_stop_requested.emit()` with `signals.ai_cancel_requested.emit()` and `audio_player.stop()`. Halting speech and cancelling AI inference must not shut down the microphone stream or disable the wake word detector.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #22: `HDHub4uManager.build_search_url()` Performs Unbounded Global Regex Replacement of `pixels`, Corrupting Domain Names and Hostnames
- **File**: [`app/api/hdhub4u_manager.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/hdhub4u_manager.py#L188-L190)
- **Severity**: **Medium / URL Generation Bug**
- **Component**: Movie Hub / HDHub4u Link Provider
- **Description**:
  In `HDHub4uManager.build_search_url()`:
  ```python
  if re.search(r"pixels", tmpl, re.IGNORECASE):
      return re.sub(r"pixels", encoded_title, tmpl, flags=re.IGNORECASE)
  ```
  The placeholder replacement uses an unanchored global search across the entire URL string.
- **Impact**:
  If a user uses a mirror domain containing "pixels" (e.g. `https://pixels-movie.hdhub4u.com/search?q=pixels`) or if a query parameter contains `pixels` in a non-search field, `re.sub()` modifies the domain name itself:
  `https://avengers+endgame-movie.hdhub4u.com/search?q=avengers+endgame`!
  The domain becomes invalid, causing DNS resolution failures and broken links.
- **Fix Required**:
  Parse the URL with `urllib.parse.urlparse`, isolate the query parameters, and replace `pixels` only within query values or after `q=` / `s=`, preserving the scheme and netloc hostname intact.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #23: Desktop Pet Window `closeEvent()` Fails to Initiate Central Lifecycle Shutdown on Window Close
- **File**: [`app/desktop/pet_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py#L825-L838)
- **Severity**: **High / Incomplete Exit Path**
- **Component**: Desktop UI / Window Event Handling
- **Description**:
  In `DesktopPetWindow.closeEvent()`:
  ```python
  def closeEvent(self, event) -> None:
      if hasattr(self, "anim_controller") and self.anim_controller:
          self.anim_controller.stop()
      ...
      super().closeEvent(event)
  ```
  The method cleans up child widgets and saves position, but calls `super().closeEvent(event)` without notifying `LifecycleManager`.
- **Impact**:
  When a user closes the pet window using native Windows controls (e.g. `Alt+F4`, Taskbar close, or right-clicking the window preview), the pet disappears, but the application does not shut down. The FastAPI server on port 8765, background audio workers, and tray icon remain alive in the background indefinitely.
- **Fix Required**:
  In `DesktopPetWindow.closeEvent()`, check `if not lifecycle.is_shutting_down: lifecycle.request_shutdown(source="pet_window_close")` so that closing the primary pet window triggers the centralized, orderly shutdown coordinator.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #24: Single-Frame Character Animations in `AnimationController._advance_frame()` Vanish Instantly After 100ms Due to Immediate End-Of-Animation Reversion
- **File**: [`app/character/animation_controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/character/animation_controller.py#L256-L269) & [`app/character/states.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/character/states.py#L62-L65)
- **Severity**: **Medium / Visual Animation Glitch**
- **Component**: Character Animation Engine
- **Description**:
  In `states.py`, `CharacterState.HAPPY` is configured as non-looping (`looping=False`, `fps=10.0`, `next_state=CharacterState.IDLE`).
  In `_advance_frame()`:
  ```python
  if not self._config.looping:
      frames = self._renderer._frame_cache.get(self._current_state.name.lower(), [])
      if frames:
          current_idx = self._renderer._current_frame_index
          if current_idx >= len(frames) - 1:
              next_st = self._config.next_state or CharacterState.IDLE
              self.request_state(next_st, force=True)
  ```
  When sprite assets contain only a single frame (`happy.png`), `len(frames) == 1`. On the very first tick (after just 100ms at 10 fps), `current_idx` (0) is already `>= len(frames) - 1` (0 >= 0).
- **Impact**:
  Whenever the companion transitions to `HAPPY` (e.g., after an enthusiastic response or praise), the happy emotion displays for only 100 milliseconds (one tenth of a second) and then instantly reverts back to `IDLE`. The user never gets to see the character's happy expression.
- **Fix Required**:
  For non-looping animations, require a minimum hold duration (e.g., at least 2.0 to 2.5 seconds) before automatically reverting to `next_state`, especially when sprite frame sequences are short or single-frame.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #25: `SentenceChunker._extract_next_sentence()` Slices `self._buffer` Using Index Measured on Stripped `candidate`, Mangling Remaining Audio Text
- **File**: [`app/voice/sentence_chunker.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/sentence_chunker.py#L124-L133)
- **Severity**: **High / Audio Text Truncation & Corruption**
- **Component**: Voice Engine / Real-Time Sentence Chunker
- **Description**:
  In `SentenceChunker._extract_next_sentence()`:
  ```python
  candidate = self._buffer[:punct_end].strip()
  ...
  if len(candidate) > self.max_chars:
      clause_match = None
      for cm in re.finditer(r'([,;:—])\s+', candidate[:self.max_chars]):
          if cm.end() >= self.min_chars:
              clause_match = cm
      if clause_match:
          split_idx = clause_match.end()
          sentence = candidate[:split_idx].strip()
          self._buffer = self._buffer[split_idx:]
          self._is_first_chunk = False
          return sentence
  ```
- **Impact**:
  `candidate` was computed with `.strip()`. If `self._buffer` begins with spaces or newlines (common in streaming LLM responses like `" \n\nSure, here is your summary..."`), `split_idx` corresponds to the character position within `candidate`, NOT within `self._buffer`.
  When line 131 executes `self._buffer = self._buffer[split_idx:]`, it advances `self._buffer` by fewer characters than intended (omitting the stripped leading whitespace).
  The next speech chunk generated by the chunker begins with truncated, garbled words (e.g. `"e, here is your summary"` instead of `"here is your summary"`), which are then spoken aloud by the TTS engine as incomprehensible gibberish.
- **Fix Required**:
  Calculate `split_idx` directly against `self._buffer`, or compute `offset = len(self._buffer[:punct_end]) - len(self._buffer[:punct_end].lstrip())` and slice `self._buffer[offset + split_idx:]`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #26: `SetupWizard._save_and_finish()` Collects `user_name` From Input Field But Omits Saving It to Configuration
- **File**: [`app/desktop/setup_wizard.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/setup_wizard.py#L719-L751)
- **Severity**: **Medium / State Persistence Bug**
- **Component**: Desktop UI / Setup Wizard
- **Description**:
  In `SetupWizard._save_and_finish()`:
  Line 719 reads the user's name from the input field:
  ```python
  user_name = self.user_name_input.text().strip() or "User"
  ```
  However, in the configuration write section (lines 739–750):
  ```python
  self.config_manager.set("ai.companion_name", companion_name)
  self.config_manager.set("ai.personality", chosen_personality)
  self.config_manager.set("ai.model", raw_model)
  self.config_manager.set("voice.enabled", voice_enabled)
  self.config_manager.set("voice.microphone", mic_name)
  self.config_manager.set("voice.tts_voice", raw_voice)
  self.config_manager.set("voice.voice_speed", voice_speed)
  self.config_manager.set("performance.profile", chosen_profile)
  self.config_manager.set("general.start_at_login", start_at_login)
  self.config_manager.set("general.show_hud", show_hud)
  self.config_manager.set("general.setup_completed", True)
  self.config_manager.save()
  ```
  `user_name` is never assigned to `self.config_manager.set("ai.user_name", user_name)`.
- **Impact**:
  The user enters their personal name during the first-run wizard setup, but the companion completely discards it. The AI prompt generator continues to fall back to `"User"` or anonymous greeting, failing to address the user by their entered name.
- **Fix Required**:
  Add `self.config_manager.set("ai.user_name", user_name)` to `_save_and_finish()`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #27: `VoiceConversationController.process_mic_frame()` Gates Barge-in Behind Undefined `enable_barge_in` Attribute, Permanently Disabling User Voice Interruption
- **File**: [`app/voice/voice_conversation_controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/voice_conversation_controller.py#L594-L603)
- **Severity**: **High / Feature Inoperative**
- **Component**: Voice Conversation Engine / Interruption Subsystem
- **Description**:
  In `VoiceConversationController.process_mic_frame()`:
  ```python
  if is_speaking_state and getattr(self, "enable_barge_in", False) and effective_echo_mode == "headset":
      if hasattr(self, "echo_canceller"):
          analysis = self.echo_canceller.analyze_mic_frame(chunk)
          if not analysis.is_echo:
              self.interruption_manager.process_mic_frame(chunk, self._turn_id)
      else:
          self.interruption_manager.process_mic_frame(chunk, self._turn_id)
  return
  ```
  The attribute `self.enable_barge_in` is never initialized in `__init__`, never read from `default_config.json`, and never exposed in `SettingsDialog`. It unconditionally resolves to `False`.
- **Impact**:
  The entire Phase 9 Interruption subsystem (`InterruptionManager`) is dead code during normal execution. When Buddy is speaking, microphone frames are unconditionally discarded without ever being inspected for user speech or interruptions. A user can never interrupt Buddy by speaking, forcing them to wait until Buddy finishes talking or manually click a button.
- **Fix Required**:
  Initialize `self.enable_barge_in = bool(config_manager.get("voice.enable_barge_in", True))` during controller initialization, and allow barge-in in speaker mode when microphone RMS significantly exceeds output speaker amplitude using `InterruptionManager`'s speaker attenuation ratio.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #28: `WakeWordEngine.process_frame()` High-Energy Mock Hack Triggers Wake Detection on Any Loud Ambient Noise
- **File**: [`app/voice/wake_word_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/wake_word_engine.py#L334-L342)
- **Severity**: **High / False Positive Wake Trigger**
- **Component**: Voice Engine / Wake Word Keyword Spotting
- **Description**:
  In `WakeWordEngine.process_frame()`:
  ```python
  # 2. High-energy burst trigger (backward compatibility with acoustic mocks/tests)
  if rms >= 0.25:
      score = 0.85
      self.score_updated.emit(self.config.activation_phrase, score)
      self._last_detection_time = now
      logger.info("🎯 WAKE WORD TRIGGERED (acoustic energy): score=%.2f", score)
      self.wake_word_detected.emit(self.config.activation_phrase, score)
      self.exit_standby()
      return True
  ```
- **Impact**:
  A test mock bypass was left active in the live production audio processing pipeline. Any sharp transient acoustic sound in the room with RMS >= 0.25 (such as coughing, laughing, clapping, dropping a notebook, typing vigorously on a mechanical keyboard, or background television noise) triggers an immediate wake-word activation as if the user spoke *"Hey Buddy"*.
  Buddy unexpectedly wakes up and starts recording the user during ordinary room noise.
- **Fix Required**:
  Remove the raw energy check `if rms >= 0.25:` from production code, or strictly restrict it to test environments via `if getattr(self, "_is_unit_test", False):`.

---


### Bug #29: Universal Desktop Screen Flicker Across Windows (DWM Composition Thrashing, Chromium Swapchain Conflicts, Missing `WA_NoSystemBackground`, and Simulated Alt Key Menu Flashing)
- **Files**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L25-L35)
  - [`app/desktop/pet_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py#L121-L195)
  - [`app/utils/window_elevation.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/utils/window_elevation.py#L13-L80)
  - [`app/desktop/control_bar.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/control_bar.py#L120-L130)
  - [`app/desktop/speech_bubble.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/speech_bubble.py#L80-L90)
  - [`app/desktop/status_hud.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/status_hud.py#L70-L75)
  - [`app/desktop/notification_toast.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/notification_toast.py#L85-L95)
  - [`app/desktop/chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/chat_window.py#L660-L665)
  - [`app/desktop/voice_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/voice_window.py#L295-L300)
  - [`src/components/MovieHub/FullScreenTrailerModal.css`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/src/components/MovieHub/FullScreenTrailerModal.css#L5-L45)
- **Severity**: **Critical / Display & Rendering Stability Flaw**
- **Component**: Desktop Window Management (DWM) / Win32 / PySide6 / QtWebEngine
- **Description & Root Causes**:
  1. **Win32 `SetWindowPos(SWP_SHOWWINDOW)` Periodic Thrashing**:
     In `pet_window.py`, `_topmost_timer` fired every 1200ms calling `enforce_topmost()`. Inside `enforce_topmost()`, `user32.SetWindowPos(hwnd, HWND_TOPMOST, ..., SWP_SHOWWINDOW)` was unconditionally called on the visible pet window every 1.2 seconds. Passing `SWP_SHOWWINDOW` (0x0040) instructs Windows DWM to reconstruct the desktop composition z-order and redraw the window and underlying surfaces. When watching full-screen video (such as movie trailers) or interacting with desktop apps, this forced the OS display to stutter and flash every 1.2 seconds.
  2. **Missing `Qt.WA_NoSystemBackground` on Layered Translucent Windows**:
     All transparent desktop overlay windows (`DesktopPetWindow`, `FloatingControlBar`, `SpeechBubbleWidget`, `StatusHUD`, `NotificationToast`, etc.) had `Qt.WA_TranslucentBackground` enabled but were missing `Qt.WA_NoSystemBackground`. In Qt on Windows, without this attribute, Windows DWM sends `WM_ERASEBKGND` before every `paintEvent()`, clearing the window surface with an opaque background brush before drawing transparent alpha frames. Repainting at 30 FPS caused rapid micro-flickering and strobe flashes around the character and widgets.
  3. **DirectX DirectComposition Swapchain Fighting in Chromium WebEngine**:
     `QWebEngineView` in `main.py` initialized Chromium without GPU isolation flags. Chromium created DirectX 11 / DXGI swapchains (`QDxgiVSyncService`) and DirectComposition video overlays. On Windows 10/11, DirectComposition hardware overlays fight with GDI/DWM layered alpha windows, causing entire monitor screens to flash black/white when video is played.
  4. **Simulated Alt-Key Menu Flashing in Window Elevation**:
     `elevate_window_to_front()` in `window_elevation.py` simulated `keybd_event(0x12, ...)` (VK_MENU / Alt key down/up) to break foreground timeouts, followed by immediate `SWP_SHOWWINDOW` calls flipping `HWND_TOPMOST` and `HWND_NOTOPMOST`. Simulating Alt toggled system menus in active Windows applications, and rapid double `SetWindowPos` calls caused the active window to flicker.
  5. **Heavy CSS `backdrop-filter: blur(16px)` on Fullscreen Video Overlays**:
     In `FullScreenTrailerModal.css`, the topbar over the YouTube video iframe applied expensive `backdrop-filter: blur(16px)` during 60 FPS video playback, stalling Chromium GPU compositor passes.
- **Impact**:
  Constant screen flickering, black/white frame strobing, and display stutter across the entire application and OS desktop during normal usage and video playback.
- **Remediation Implemented**:
  1. Set Chromium environment flags in `main.py` (`--disable-gpu-compositing`, `--disable-direct-composition-video-overlays`, `--enable-begin-frame-scheduling`) and enabled `Qt.AA_ShareOpenGLContexts`.
  2. Added `self.setAttribute(Qt.WA_NoSystemBackground, True)` across all frameless translucent Qt windows.
  3. Optimized `enforce_topmost()`: verified `WS_EX_TOPMOST` via `GetWindowLongW()` before invoking Win32 calls, removed `SWP_SHOWWINDOW` in favor of non-destructive flags (`SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOREDRAW | SWP_NOSENDCHANGING | SWP_NOOWNERZORDER`), and relaxed timer interval to 5000ms.
  4. Cleaned `elevate_window_to_front()`: removed simulated Alt key events, removed `SWP_SHOWWINDOW`, eliminated `SetFocus` on focus-less windows, and verified foreground status first.
  5. Optimized `FullScreenTrailerModal.css` with `transform: translateZ(0)` and clean translucent solid styling without heavy live `backdrop-filter` recalculations on video frames; re-compiled frontend dist with `npm run build`.

---

### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

### Bug #30: 10 to 15 Flashing Terminal Windows on Startup (Ollama Runner Capability Probing Under Mutually Exclusive `DETACHED_PROCESS` Flag, Missing `CREATE_NO_WINDOW`, and Launcher Re-Exec Recursion)
- **Files**:
  - [`app/ai/ollama_supervisor.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ollama_supervisor.py#L198-L215)
  - [`app/core/ollama_installer.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/ollama_installer.py#L88-L105)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L25-L75)
  - [`AI_Desktop_Friend_Silent.vbs`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/AI_Desktop_Friend_Silent.vbs)
- **Severity**: **Critical / User Experience & Startup Stability Flaw**
- **Component**: Process Management / Subprocess Execution / Ollama Background Daemon / Launcher Lifecycle
- **Description & Root Causes**:
  1. **Mutually Exclusive Win32 Process Creation Flags in `OllamaSupervisor`**:
     In `app/ai/ollama_supervisor.py`:
     ```python
     kwargs["creationflags"] = 0x00000008 | 0x08000000 # DETACHED_PROCESS | CREATE_NO_WINDOW
     ```
     In the Microsoft Win32 API (`CreateProcessW`), `DETACHED_PROCESS` and `CREATE_NO_WINDOW` are strictly mutually exclusive flags. When combined, Windows produces undefined behavior, discarding `CREATE_NO_WINDOW` and allocating a detached process context with no attached console.
     When `ollama.exe serve` starts, Ollama's Go runtime (`runner.go`) probes available CPU instruction sets and GPU acceleration runners located in `%LOCALAPPDATA%\Programs\Ollama\lib\ollama` (probing 14 CPU DLL architectures: `ggml-cpu-alderlake`, `ggml-cpu-cannonlake`, `ggml-cpu-cascadelake`, `ggml-cpu-cooperlake`, `ggml-cpu-haswell`, `ggml-cpu-icelake`, `ggml-cpu-ivybridge`, `ggml-cpu-piledriver`, `ggml-cpu-sandybridge`, `ggml-cpu-sapphirerapids`, `ggml-cpu-skylakex`, `ggml-cpu-sse42`, `ggml-cpu-x64`, `ggml-cpu-zen4`, plus `cuda_v12`, `cuda_v13`, `rocm`, and `vulkan`).
     Because the parent process was detached without a suppressed console context, Windows `conhost.exe` allocated and popped open a visible console window for every single capability probe (exactly 10 to 15 times in rapid succession) before immediately closing each one as the probe completed.
  2. **Completely Missing `CREATE_NO_WINDOW` in `ollama_installer.py`**:
     In `app/core/ollama_installer.py`:
     ```python
     creation_flags = 0x00000008 | 0x00000200 # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
     ```
     `CREATE_NO_WINDOW` (`0x08000000`) and `STARTUPINFO` `SW_HIDE` were completely missing. Any invocation of `ollama_installer.py` explicitly launched Ollama in a mode where child processes allocate visible consoles.
  3. **Launcher Recursive Re-Execution and `--force` Bypass in `run_desktop.py`**:
     In `run_desktop.py`:
     - The venv auto-detect check `if os.path.normcase(sys.executable) != os.path.normcase(venv_python) and "--no-reexec" not in sys.argv:` ran `cmd = [venv_python, os.path.abspath(__file__)] + sys.argv[1:]` without appending `"--no-reexec"`. If path normalization differed or symlinks/short paths were encountered, it risked recursive sub-process re-execution.
     - `run_desktop.py` unconditionally appended `"--force"` to `sys.argv`, completely bypassing `SingleInstanceGuard`. If the user launched the batch file or shortcut more than once, multiple instances ran simultaneously, clashing on port 8765, terminating each other's processes, and spawning new terminals.
- **Impact**:
  When starting the project, 10 to 15 black command prompt / terminal windows flashed open and closed across the desktop in rapid succession, alarming the user and polluting the desktop environment.
- **Remediation Implemented**:
  1. Updated `app/ai/ollama_supervisor.py` to use `subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP` alongside `startupinfo = subprocess.STARTUPINFO()` with `STARTF_USESHOWWINDOW` and `wShowWindow = SW_HIDE`. Removed `DETACHED_PROCESS` so that child processes (runner capability probes) inherit the headless/hidden execution context and never allocate visible `conhost.exe` console windows.
  2. Updated `app/core/ollama_installer.py` with identical `CREATE_NO_WINDOW`, `CREATE_NEW_PROCESS_GROUP`, and `SW_HIDE` startup info.
  3. Fixed `run_desktop.py`:
     - Appended `"--no-reexec"` to `cmd` to prevent any re-exec looping.
     - Handled `sys.stdout is None` and `sys.stderr is None` safely for windowless execution (e.g., `pythonw.exe`).
     - Removed unconditional `sys.argv.append("--force")` so `SingleInstanceGuard` functions properly and brings existing instances to the foreground instead of fighting and killing each other.
  4. Created `AI_Desktop_Friend_Silent.vbs` as a 100% windowless launcher option using `pythonw.exe`.

---


### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.

---

### Bug #31: Python Process Hangs on Terminal Exit with `QDxgiVSyncService not destroyed in time` & `QThreadStorage` Deadlock
- **File**:
  - [`main.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/main.py#L180-L221)
  - [`run_desktop.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/run_desktop.py#L70-L80)
  - [`app/desktop/modern_chat_window.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py#L489-L506)
  - [`app/core/controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L1285-L1295)
- **Severity**: **Critical / Application Teardown & Process Deadlock**
- **Component**: Application Lifecycle / Shutdown Coordinator / PySide6 & Chromium DirectX Teardown
- **Description & Root Causes**:
  When shutting down the application via any exit path (Ctrl+C in terminal, tray Exit, pet context menu Exit, or window close), the application completed all subsystem shutdowns cleanly, yet the terminal remained permanently frozen on:
  ```text
  Qt event loop exited with code 0.
  QDxgiVSyncService not destroyed in time
  QThreadStorage: entry 2 destroyed before end of thread 0x1936de94580
  QThreadStorage: entry 1 destroyed before end of thread 0x1936de94580
  ```
  The prompt never returned and the process remained hung in the Windows process table.
  
  **Root Causes**:
  1. **Asynchronous Browser Navigation During Widget Teardown**:
     In `ModernChatWindow.cleanup()`, line 500 called `self.browser.load(QUrl("about:blank"))` immediately before `self.browser.deleteLater()`. Navigating to `about:blank` instructed Chromium to initiate a new asynchronous render task and swapchain buffer right as the window was being closed.
  2. **Event Loop Pumping During Teardown**:
     In `ApplicationController.shutdown()`, line 1289 called `self.app.processEvents()` to clear deferred deletions. Spinning the event loop while DirectX and WebEngine views were being torn down triggered DirectX frame callbacks on half-destroyed objects.
  3. **CPython `Py_FinalizeEx` Teardown vs. Daemon Thread Watchdogs**:
     In `main.py` and `run_desktop.py`, `main()` was returning `exit_code` to `sys.exit(exit_code)`. During `sys.exit()`, Python enters `Py_FinalizeEx`, which immediately terminates all daemon threads (including `ExitGraceWatchdog` and `ShutdownWatchdog`). Python then unloaded C++ extensions and destroyed `QApplication`. Qt's platform plugin (`qwindows.dll`) timed out waiting on the unjoined DXGI VSync thread (`QDxgiVSyncService not destroyed in time`), and then deadlocked inside the Windows Loader Lock (`LdrpLoaderLock`). Because the Python watchdog was a daemon thread killed by `Py_FinalizeEx`, it could never wake up to call `os._exit()`, leaving the console frozen indefinitely.
- **Impact**:
  The application failed to return control to the terminal or batch script upon exit, requiring manual Task Manager intervention.
- **Remediation Implemented**:
  1. Updated `ModernChatWindow.cleanup()`: Removed `self.browser.load(QUrl("about:blank"))` so no new asynchronous navigations or swapchains are initiated during destruction.
  2. Updated `ApplicationController.shutdown()`: Removed `self.app.processEvents()` and flushed deferred deletes safely using `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` without spinning the event loop.
  3. Updated `main.py` and `run_desktop.py`: Flushed output streams (`sys.stdout.flush()`, `sys.stderr.flush()`), and invoked `os._exit(exit_code)` directly for standalone application runs (while preserving `return exit_code` under `PYTEST_CURRENT_TEST` for automated testing). `os._exit()` invokes the Win32 `ExitProcess()` API, ensuring instantaneous, clean termination without hanging in C++ static destructors.
  4. Verified with full automated test suite: 38/38 tests passed.
