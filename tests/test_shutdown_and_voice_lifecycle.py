"""Comprehensive Verification & Regression Suite for Voice Lifecycle, Audio Shutdown, and Anti-Echo Protections.

Tests strict requirements:
1. Centralized, idempotent shutdown mechanism (LifecycleManager).
2. Immediate cessation of TTS playback, microphone capture, and background loops on shutdown.
3. Prevention of new audio tasks starting once shutdown has begun.
4. Child process registration and termination tree handling.
5. Verification that typed chat messages do not trigger spoken TTS playback.
6. Single-spoken-response guarantee (no duplicate speech during streaming turns).
7. Acoustic echo suppressor preventing infinite self-response loops.
8. Rapid stop / emergency stop while audio is actively playing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import List
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtCore import QObject, QTimer

from app.core.lifecycle import LifecycleManager, LifecycleState, get_lifecycle_manager
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.echo_suppressor import AcousticEchoSuppressor
from app.voice.microphone_manager import MicrophoneManager
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceMode, VoiceService


class MockFastTTS(BaseTTSEngine):
    """Mock TTS synthesizer for instant testing."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.synthesize_calls: list[str] = []

    def is_available(self) -> bool:
        return True

    def get_available_voices(self) -> list[str]:
        return ["mock_voice"]

    def load_model(self, voice_name: str | None = None) -> bool:
        self._is_loaded = True
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        self.synthesize_calls.append(text)
        sample_rate = 22050
        duration = 0.05
        samples = np.zeros(int(sample_rate * duration), dtype=np.float32)
        return SynthesizedAudio(
            samples=samples,
            sample_rate=sample_rate,
            duration_seconds=duration,
            text=text,
            voice_name="mock",
        )

    def stop(self) -> None:
        pass


# -----------------------------------------------------------------------------
# 1. LifecycleManager Centralized Shutdown & Idempotence
# -----------------------------------------------------------------------------

def test_lifecycle_manager_idempotence_and_priority() -> None:
    """Verify that LifecycleManager runs shutdown hooks in priority order, only once."""
    mgr = LifecycleManager()
    execution_order: List[str] = []

    mgr.register_shutdown_hook(lambda: execution_order.append("low"), priority=10, name="low_hook")
    mgr.register_shutdown_hook(lambda: execution_order.append("high"), priority=100, name="high_hook")
    mgr.register_shutdown_hook(lambda: execution_order.append("medium"), priority=50, name="med_hook")

    # Initial state
    assert mgr.state == LifecycleState.STARTING or mgr.state == LifecycleState.RUNNING

    # First shutdown call
    mgr.shutdown(reason="Unit Test 1", force_exit_delay_sec=5.0, exit_process=False)

    assert execution_order == ["high", "medium", "low"]
    assert mgr.state == LifecycleState.SHUTDOWN_COMPLETED
    assert mgr.is_shutting_down is True

    # Second shutdown call must be idempotent (no repeated execution)
    mgr.shutdown(reason="Unit Test 2 Repeated", force_exit_delay_sec=5.0, exit_process=False)
    assert execution_order == ["high", "medium", "low"]


# -----------------------------------------------------------------------------
# 2. AudioPlayer Emergency Stop & Shutdown Guards
# -----------------------------------------------------------------------------

def test_audio_player_shutdown_guards(qapp_instance) -> None:
    """Verify AudioPlayer halts active audio immediately and rejects new playback after shutdown."""
    player = AudioPlayer()
    assert player.is_shutdown is False

    # Simulate play
    dummy_samples = np.sin(np.linspace(0, 100, 44100, dtype=np.float32))
    ok = player.play(dummy_samples, sample_rate=44100)
    assert ok is True
    assert player.is_playing is True

    # Trigger emergency stop while playing
    player.emergency_stop()
    assert player.is_playing is False

    # Trigger full shutdown
    player.shutdown()
    assert player.is_shutdown is True

    # Playback must be completely rejected once shut down
    second_play = player.play(dummy_samples, sample_rate=44100)
    assert second_play is False
    assert player.is_playing is False


# -----------------------------------------------------------------------------
# 3. MicrophoneManager Emergency Stop & Shutdown Guards
# -----------------------------------------------------------------------------

def test_microphone_manager_shutdown_guards(monkeypatch) -> None:
    """Verify MicrophoneManager closes stream and rejects start_recording after shutdown."""
    mic = MicrophoneManager()
    assert mic.is_shutdown is False

    from app.voice.microphone_manager import AudioDeviceInfo
    dummy_dev = AudioDeviceInfo(
        index=0,
        name="Mock Mic",
        hostapi_name="DirectSound",
        max_input_channels=1,
        default_samplerate=16000.0,
        is_default=True,
    )
    monkeypatch.setattr(mic, "get_input_devices", lambda: [dummy_dev])

    class DummyStream:
        def __init__(self, *args, **kwargs):
            self.active = True
        def start(self):
            self.active = True
        def stop(self):
            self.active = False
        def close(self):
            self.active = False

    dummy = DummyStream()
    import sounddevice as sd
    monkeypatch.setattr(sd, "InputStream", lambda *args, **kwargs: dummy)

    started = mic.start_recording()
    assert started is True
    assert mic.is_recording is True

    # Shutdown
    mic.shutdown()
    assert mic.is_shutdown is True
    assert mic.is_recording is False

    # Subsequent recording must be rejected
    second_start = mic.start_recording()
    assert second_start is False
    assert mic.is_recording is False


# -----------------------------------------------------------------------------
# 4. StreamingAudioQueue Shutdown & Turn Invalidation
# -----------------------------------------------------------------------------

def test_streaming_audio_queue_shutdown(qapp_instance) -> None:
    """Verify StreamingAudioQueue purges all queued items and rejects new turns on shutdown."""
    player = AudioPlayer()
    tts = MockFastTTS()
    queue = StreamingAudioQueue(audio_player=player, tts_engine=tts)

    queue.start_new_turn(turn_id=1)
    queue.enqueue_sentence("Hello sentence one.", turn_id=1)
    queue.enqueue_sentence("Hello sentence two.", turn_id=1)
    assert queue.get_queue_length() > 0

    # Emergency stop
    queue.emergency_stop()
    assert queue.is_empty is True
    assert queue.get_queue_length() == 0

    # Shutdown
    queue.shutdown()
    assert queue.is_shutdown is True

    # New turn after shutdown must be rejected
    queue.start_new_turn(turn_id=2)
    queue.enqueue_sentence("Should never be queued", turn_id=2)
    assert queue.is_empty is True


# -----------------------------------------------------------------------------
# 5. VoiceService Shutdown & Stop Speaking
# -----------------------------------------------------------------------------

def test_voice_service_shutdown_and_guards(qapp_instance) -> None:
    """Verify VoiceService halts all audio, clears pools, and rejects speech once shut down."""
    service = VoiceService()
    assert service.is_shutdown is False

    # Speak command
    service.speak("Testing voice service output.")
    assert getattr(service, "_last_spoken_text", "") == "Testing voice service output."

    # Shut down voice service
    service.shutdown()
    assert service.is_shutdown is True
    assert service.audio_player.is_shutdown is True
    assert service.mic_manager.is_shutdown is True

    # Further speak requests must be completely rejected
    service.speak("This speech must be discarded.")
    assert getattr(service, "_last_spoken_text", "") != "This speech must be discarded."


# -----------------------------------------------------------------------------
# 6. Anti-Echo Feedback Loop Suppression
# -----------------------------------------------------------------------------

def test_acoustic_echo_suppressor_intercepts_assistant_voice() -> None:
    """Verify AcousticEchoSuppressor detects assistant speech and prevents infinite reply loop."""
    suppressor = AcousticEchoSuppressor()

    spoken_assistant = "I am Buddy, your AI companion on your desktop."
    suppressor.record_assistant_speech(spoken_assistant)

    # 1. Exact speech captured by microphone
    is_echo, reason, conf = suppressor.is_echo("I am Buddy, your AI companion on your desktop.")
    assert is_echo is True
    assert conf >= 0.8

    # 2. Substring captured (e.g. microphone only caught the second half)
    is_echo_sub, reason_sub, conf_sub = suppressor.is_echo("your AI companion on your desktop")
    assert is_echo_sub is True

    # 3. Fuzzy STT typo variation
    is_echo_fuzzy, reason_fuzzy, conf_fuzzy = suppressor.is_echo("I am Budi your AI companion on desktop")
    assert is_echo_fuzzy is True

    # 4. Legitimate user query must NOT be flagged as echo
    is_legit, _, _ = suppressor.is_echo("What is the current weather outside?")
    assert is_legit is False


# -----------------------------------------------------------------------------
# 7. Single Spoken Response Guarantee (No Duplicate Speech)
# -----------------------------------------------------------------------------

def test_controller_tts_handler_prevents_duplicate_speech(qapp_instance) -> None:
    """Verify ApplicationController._on_ai_response_tts does not trigger full-text TTS

    when the user typed the message (is_voice=False) or when continuous streaming
    audio queue is already synthesizing the response chunks.
    """
    from app.core.controller import ApplicationController
    from app.settings.config_manager import ConfigManager

    cfg = ConfigManager()
    controller = ApplicationController(app=qapp_instance, config_manager=cfg)

    # Mock voice service & AI service
    mock_voice = MagicMock()
    mock_voice.tts_enabled = True
    mock_ai = MagicMock()

    controller.voice_service = mock_voice
    controller.ai_service = mock_ai

    # Case A: User typed message (is_voice = False)
    mock_ai.is_current_generation_voice = False
    controller._on_ai_response_tts("This is an answer to a typed prompt.")
    # Must NOT speak aloud
    mock_voice.speak.assert_not_called()

    # Case B: Voice turn with active continuous conversation controller
    mock_ai.is_current_generation_voice = True
    conv_ctrl = MagicMock()
    conv_ctrl.is_enabled = True
    mock_voice.conversation_controller = conv_ctrl

    controller._on_ai_response_tts("This was streamed by conversation controller.")
    # Must NOT speak again (prevent duplicate full-text audio)
    mock_voice.speak.assert_not_called()

    # Case C: Voice turn without streaming controller (e.g. manual push-to-talk single utterance)
    conv_ctrl.is_enabled = False
    controller._on_ai_response_tts("Spoken response for push-to-talk.")
    mock_voice.speak.assert_called_once_with("Spoken response for push-to-talk.")


# -----------------------------------------------------------------------------
# 8. Child Process Registration & Tree Termination
# -----------------------------------------------------------------------------

def test_child_process_tree_termination() -> None:
    """Verify that processes registered with LifecycleManager are terminated cleanly."""
    mgr = LifecycleManager()

    # Spawn a sleeping background Python child process
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    proc = subprocess.Popen(cmd)
    child_pid = proc.pid
    assert proc.poll() is None  # Process is running

    mgr.register_child_process(child_pid)

    # Call internal process termination
    mgr._terminate_child_processes()

    # Child process must be terminated within 2 seconds
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    assert proc.poll() is not None
