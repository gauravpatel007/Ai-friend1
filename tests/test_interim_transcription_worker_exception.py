"""Tests for Bug #15: _InterimTranscribeWorker.run() Exception Skips Callback, Freezing Word-by-Word Interim Speech Streaming.

Verifies:
1. _InterimTranscribeWorker calls callback in finally: block even when transcribe_interim() raises an exception.
2. Callback receives empty string when an exception occurs, allowing the caller to release locks.
3. VoiceConversationController._on_interim_transcription_ready clears _is_interim_transcribing lock even on empty/error result.
4. Subsequent interim transcription passes succeed after an exception without freezing.
5. VoiceConversationController auto-recovers if interim transcription pass exceeds 1.5s timeout.
6. cancel_current_turn() resets _is_interim_transcribing and invalidates in-flight generation id.
"""

import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from app.voice.whisper_engine import _InterimTranscribeWorker, WhisperEngine
from app.voice.conversation_state import ConversationState, VoiceActivationMode


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_interim_transcribe_worker_success():
    """Verify standard happy-path execution of _InterimTranscribeWorker."""
    mock_engine = MagicMock()
    mock_engine.transcribe_interim.return_value = "hello world"
    mock_callback = MagicMock()

    worker = _InterimTranscribeWorker(
        engine=mock_engine,
        audio_data=np.zeros(2048, dtype=np.float32),
        generation_id=42,
        language="en",
        prompt=None,
        callback=mock_callback,
    )

    worker.run()

    mock_engine.transcribe_interim.assert_called_once()
    mock_callback.assert_called_once_with(42, "hello world")


def test_interim_transcribe_worker_exception_invokes_callback_with_empty_text():
    """Verify that when transcribe_interim raises an Exception, callback is still called via finally:."""
    mock_engine = MagicMock()
    mock_engine.transcribe_interim.side_effect = RuntimeError("CUDA memory allocation failed")
    mock_callback = MagicMock()

    worker = _InterimTranscribeWorker(
        engine=mock_engine,
        audio_data=np.zeros(2048, dtype=np.float32),
        generation_id=99,
        language="en",
        prompt=None,
        callback=mock_callback,
    )

    # Must NOT raise exception to outer thread
    worker.run()

    # Callback MUST be called with empty text so receiver releases locks
    mock_callback.assert_called_once_with(99, "")


def test_interim_transcribe_worker_handles_callback_exception_gracefully():
    """Verify that if the callback itself raises an exception, worker handles it safely."""
    mock_engine = MagicMock()
    mock_engine.transcribe_interim.return_value = "test"
    mock_callback = MagicMock(side_effect=ValueError("Callback error"))

    worker = _InterimTranscribeWorker(
        engine=mock_engine,
        audio_data=np.zeros(2048, dtype=np.float32),
        generation_id=1,
        language="en",
        prompt=None,
        callback=mock_callback,
    )

    # Must not raise
    worker.run()
    mock_callback.assert_called_once_with(1, "test")


def test_controller_interim_transcription_clears_lock_on_exception(qapp):
    """Verify VoiceConversationController clears _is_interim_transcribing when worker raises an exception."""
    from app.voice.voice_conversation_controller import VoiceConversationController

    controller = VoiceConversationController()
    controller._state = ConversationState.USER_SPEAKING
    controller._activation_mode = VoiceActivationMode.CONTINUOUS

    # Simulate in-flight interim transcription
    controller._is_interim_transcribing = True
    controller._last_interim_text = "Good morning"
    current_gen_id = controller._interim_generation_id

    # Background worker fails and invokes callback with empty string
    controller._on_interim_transcription_ready(current_gen_id, "")

    # Lock must be released
    assert controller._is_interim_transcribing is False
    # Existing valid interim text must NOT be cleared or overwritten with empty
    assert controller._last_interim_text == "Good morning"

    controller.cleanup()


def test_controller_subsequent_interim_passes_succeed_after_error(qapp):
    """Verify that subsequent mic frames can dispatch new interim passes after an error."""
    from app.voice.voice_conversation_controller import VoiceConversationController

    controller = VoiceConversationController()
    controller._state = ConversationState.USER_SPEAKING
    controller._activation_mode = VoiceActivationMode.CONTINUOUS

    # Setup mock VAD engine to return speech buffer
    mock_vad = MagicMock()
    mock_vad.get_current_speech_buffer.return_value = np.zeros(4096, dtype=np.float32)
    controller.vad_engine = mock_vad

    # Mock whisper engine transcribe_interim_async
    dispatched_passes = []

    def mock_transcribe_interim_async(audio_data, generation_id, callback, language=None, prompt=None):
        dispatched_passes.append(generation_id)
        # Simulate worker executing with failure on first pass
        if len(dispatched_passes) == 1:
            # First pass fails -> callback called with ""
            callback(generation_id, "")
        else:
            # Second pass succeeds
            callback(generation_id, "hello world")

    controller.whisper_engine.transcribe_interim_async = mock_transcribe_interim_async

    # Frame 1: triggers first interim pass
    controller._frames_since_last_interim = 3
    controller.process_mic_frame(np.zeros(512, dtype=np.float32))

    assert len(dispatched_passes) == 1
    # Because callback was invoked in finally:, lock was released!
    assert controller._is_interim_transcribing is False

    # Frame 2: triggers second interim pass (must NOT be blocked)
    controller._frames_since_last_interim = 3
    controller.process_mic_frame(np.zeros(512, dtype=np.float32))

    assert len(dispatched_passes) == 2
    assert controller._is_interim_transcribing is False
    assert controller._last_interim_text == "hello world"

    controller.cleanup()


def test_controller_interim_timeout_watchdog_auto_releases_lock(qapp):
    """Verify that if an interim pass somehow hangs, the 1.5s timeout watchdog auto-releases the lock."""
    from app.voice.voice_conversation_controller import VoiceConversationController

    controller = VoiceConversationController()
    controller._state = ConversationState.USER_SPEAKING
    controller._activation_mode = VoiceActivationMode.CONTINUOUS

    # Simulate stuck lock dispatched 2.0 seconds ago
    controller._is_interim_transcribing = True
    controller._last_interim_dispatch_time = time.monotonic() - 2.0

    mock_vad = MagicMock()
    mock_vad.get_current_speech_buffer.return_value = None
    controller.vad_engine = mock_vad

    # Feed a frame
    controller.process_mic_frame(np.zeros(512, dtype=np.float32))

    # Lock must be auto-released by the watchdog
    assert controller._is_interim_transcribing is False

    controller.cleanup()


def test_cancel_current_turn_resets_interim_transcribing_lock(qapp):
    """Verify cancel_current_turn() resets _is_interim_transcribing and increments generation id."""
    from app.voice.voice_conversation_controller import VoiceConversationController

    controller = VoiceConversationController()
    controller._state = ConversationState.USER_SPEAKING
    controller._activation_mode = VoiceActivationMode.CONTINUOUS

    controller._is_interim_transcribing = True
    old_gen_id = controller._interim_generation_id

    controller.cancel_current_turn()

    assert controller._is_interim_transcribing is False
    assert controller._interim_generation_id > old_gen_id

    controller.cleanup()
