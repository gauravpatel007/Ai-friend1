"""Tests for Phase 9 — Repair the Voice Conversation State Machine.

Validates:
1. Complete valid lifecycle: IDLE -> LISTENING -> TRANSCRIBING -> SUBMITTING_USER_MESSAGE -> GENERATING_RESPONSE -> SPEAKING -> IDLE.
2. Rejection of invalid state transitions.
3. Prevention of multiple simultaneous recording sessions.
4. Prevention of duplicate transcription submissions and stale async callbacks.
5. Prevention of empty requests.
6. Prevention of assistant responses being resubmitted as user messages (echo suppression).
7. Utterance duration watchdog preventing endless listening on continuous silence/noise.
8. Immediate audio playback & queue clearance on turn cancellation and emergency stop.
9. Generation watchdog and error recovery preventing the interface from remaining permanently busy.
10. Bounded error recovery preventing infinite retry loops.
"""

import time
from typing import Any, List
import numpy as np
import pytest
from PySide6.QtCore import QObject, QTimer

from app.character.states import CharacterState
from app.core.signals import signals
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import (
    ConversationLatencyMetrics,
    ConversationState,
    VoiceActivationMode,
)
from app.voice.microphone_manager import MicrophoneManager
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine
from app.voice.voice_conversation_controller import (
    VALID_TRANSITIONS,
    VoiceConversationController,
)
from app.voice.voice_service import VoiceMode, VoiceService
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


class MockTTS(BaseTTSEngine):
    def __init__(self, duration: float = 0.05) -> None:
        super().__init__()
        self.duration = duration
        self.synthesized_texts: List[str] = []

    def synthesize(self, text: str, **kwargs: Any) -> SynthesizedAudio:
        self.synthesized_texts.append(text)
        samples = np.ones(int(16000 * self.duration), dtype=np.float32) * 0.1
        return SynthesizedAudio(
            samples=samples,
            sample_rate=16000,
            duration_seconds=self.duration,
            text=text,
            voice_name="mock_voice",
        )

    def is_available(self) -> bool:
        return True


class MockWhisper(WhisperEngine):
    def __init__(self, text: str = "Hello Buddy!", lang: str = "en") -> None:
        super().__init__()
        self.text = text
        self.lang = lang
        self.call_count = 0

    def transcribe_async(self, audio_data: np.ndarray, callback=None, language=None, prompt=None) -> None:
        self.call_count += 1
        res = TranscriptionResult(
            text=self.text,
            language=language or self.lang,
            language_probability=0.99,
            duration_seconds=len(audio_data) / 16000.0,
        )
        if callback:
            callback(res)


class MockAIService:
    def __init__(self) -> None:
        self.asked_prompts: List[str] = []
        self._is_generating: bool = False
        self.cancelled: bool = False

    def ask(self, user_prompt: str, is_voice: bool = True) -> int:
        self.asked_prompts.append(user_prompt)
        self._is_generating = True
        # Immediately stream tokens and complete
        signals.ai_response_chunk.emit("I hear you loud and clear. ")
        signals.ai_response_complete.emit("I hear you loud and clear.")
        self._is_generating = False
        return 1

    def cancel_generation(self) -> None:
        self.cancelled = True
        self._is_generating = False


@pytest.fixture
def voice_pipeline(qapp_instance, monkeypatch):
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = MockWhisper(text="What is the weather?", lang="en")
    player = AudioPlayer()
    tts = MockTTS(duration=0.03)
    ai_service = MockAIService()

    monkeypatch.setattr(mic, "start_recording", lambda: True)
    monkeypatch.setattr(mic, "stop_recording", lambda: None)

    def mock_play(samples, sample_rate):
        player._is_playing = True
        player.playback_started.emit()
        QTimer.singleShot(25, lambda: (setattr(player, "_is_playing", False), player.playback_finished.emit()))
        return True

    monkeypatch.setattr(player, "play", mock_play)

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=ai_service,
        parent=None,
    )
    return controller, mic, vad, whisper, player, tts, ai_service


# ─────────────────────────────────────────────────────────────────────────────
# 1. Full Valid Lifecycle: IDLE -> LISTENING -> TRANSCRIBING ->
#    SUBMITTING_USER_MESSAGE -> GENERATING_RESPONSE -> SPEAKING -> IDLE
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_valid_state_machine_flow(voice_pipeline, qtbot) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    state_history: List[ConversationState] = []
    controller.state_changed.connect(state_history.append)

    # Initially IDLE
    assert controller.state in (ConversationState.IDLE, ConversationState.DISABLED)

    # IDLE -> LISTENING
    assert controller.enable() is True
    assert controller.state == ConversationState.LISTENING

    # LISTENING -> USER_SPEAKING
    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # USER_SPEAKING -> TRANSCRIBING -> SUBMITTING_USER_MESSAGE -> GENERATING_RESPONSE -> SPEAKING
    dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
    controller._on_vad_speech_ended(dummy_audio)

    # Wait for TTS audio output and hands-free return
    qtbot.waitUntil(lambda: controller.state == ConversationState.LISTENING, timeout=4000)

    # Verify all explicit states in Phase 9 were traversed
    assert ConversationState.LISTENING in state_history
    assert ConversationState.USER_SPEAKING in state_history
    assert ConversationState.TRANSCRIBING in state_history
    assert ConversationState.SUBMITTING_USER_MESSAGE in state_history
    assert ConversationState.GENERATING_RESPONSE in state_history
    assert ConversationState.SPEAKING in state_history

    # In continuous mode, loop returns cleanly to LISTENING
    assert controller.state == ConversationState.LISTENING


# ─────────────────────────────────────────────────────────────────────────────
# 2. Prevention of Invalid State Transitions
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_invalid_transitions_rejected(voice_pipeline) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()
    assert controller.state == ConversationState.LISTENING

    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # Illegal transition: USER_SPEAKING directly to SUBMITTING_USER_MESSAGE (must transcribe first!)
    controller._transition_to(ConversationState.SUBMITTING_USER_MESSAGE)
    assert controller.state == ConversationState.USER_SPEAKING  # Rejected!

    # Illegal transition: USER_SPEAKING directly to SPEAKING
    controller._transition_to(ConversationState.SPEAKING)
    assert controller.state == ConversationState.USER_SPEAKING  # Rejected!


# ─────────────────────────────────────────────────────────────────────────────
# 3. Prevention of Multiple Simultaneous Recording Sessions
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_prevent_simultaneous_recording(voice_pipeline) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()

    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # A secondary speech onset while already recording must be rejected
    speech_onsets: List[bool] = []
    controller.speech_started.connect(lambda: speech_onsets.append(True))
    controller._on_vad_speech_started()
    assert len(speech_onsets) == 0  # No duplicate onset fired!


# ─────────────────────────────────────────────────────────────────────────────
# 4. Prevention of Duplicate Transcription Submissions & Stale Callbacks
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_prevent_duplicate_transcriptions_and_stale_callbacks(voice_pipeline) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()

    # Trigger turn 1
    controller._on_vad_speech_started()
    controller._on_vad_speech_ended(np.ones(16000, dtype=np.float32) * 0.1)

    turn_1_id = controller.current_turn_id
    assert turn_1_id == 1

    # Simulate delayed stale callback for turn 0 (previous or superseded turn)
    stale_result = TranscriptionResult(text="Old stale query", language="en", language_probability=0.99, duration_seconds=1.0)
    controller._on_transcription_completed(stale_result, turn_id=999)

    # Must NOT have dispatched stale query to AI
    assert "Old stale query" not in ai.asked_prompts

    # Duplicate callback for the same turn 1 must also be rejected
    controller._on_transcription_completed(stale_result, turn_id=turn_1_id)
    assert "Old stale query" not in ai.asked_prompts


# ─────────────────────────────────────────────────────────────────────────────
# 5. Prevention of Empty Requests
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_prevent_empty_requests(voice_pipeline) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()

    # Configure whisper to return whitespace-only text
    whisper.text = "   \n  "
    controller._on_vad_speech_started()
    controller._on_vad_speech_ended(np.ones(16000, dtype=np.float32) * 0.1)

    # Empty text must NOT reach AI and state should recover to LISTENING
    assert len(ai.asked_prompts) == 0
    assert controller.state == ConversationState.LISTENING


# ─────────────────────────────────────────────────────────────────────────────
# 6. Prevention of Assistant Response Echo Feedback
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_prevent_assistant_speech_echo(voice_pipeline) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()

    # Record assistant speech
    controller._last_assistant_response = "I am your AI assistant"
    controller.echo_suppressor.record_assistant_speech("I am your AI assistant")

    # Configure whisper to transcribe the exact assistant echo
    whisper.text = "I am your AI assistant"
    controller._on_vad_speech_started()
    controller._on_vad_speech_ended(np.ones(16000, dtype=np.float32) * 0.1)

    # Echo must be discarded and controller resumes LISTENING
    assert "I am your AI assistant" not in ai.asked_prompts
    assert controller.state == ConversationState.LISTENING


# ─────────────────────────────────────────────────────────────────────────────
# 7. Utterance Duration Watchdog (Endless Listening Prevention)
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_utterance_duration_watchdog(voice_pipeline, qtbot) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()

    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # Override utterance watchdog with 50ms for fast test
    controller._start_utterance_watchdog(timeout_sec=0.05)

    # Wait for watchdog to trigger force-finalization back to LISTENING
    qtbot.waitUntil(lambda: controller.state == ConversationState.LISTENING, timeout=1000)
    assert controller.state == ConversationState.LISTENING


# ─────────────────────────────────────────────────────────────────────────────
# 8. Cancellation & Immediate Audio Playback Cleanup
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_cancellation_and_emergency_stop_cleanup(voice_pipeline) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()

    # Transition to SPEAKING state
    controller._transition_to(ConversationState.SPEAKING)
    player._is_playing = True

    # 1. Cancel ongoing turn
    controller.cancel_current_turn()
    assert player.is_playing is False
    assert controller.audio_queue.is_empty is True
    assert ai.cancelled is True

    # 2. Emergency stop
    controller.emergency_stop()
    assert controller.state in (ConversationState.IDLE, ConversationState.DISABLED)
    assert player.is_playing is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. Generation Watchdog & Error Recovery (No Permanently Busy Interface)
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_generation_watchdog_recovers_error(voice_pipeline, qtbot) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()

    controller._transition_to(ConversationState.GENERATING_RESPONSE)
    assert controller.state == ConversationState.GENERATING_RESPONSE

    # Start 50ms generation watchdog
    controller._start_generation_watchdog(turn_id=controller.current_turn_id, timeout_sec=0.05)

    # Wait for timeout to trigger ERROR state
    qtbot.waitUntil(lambda: controller.state == ConversationState.ERROR, timeout=1000)
    assert controller.state == ConversationState.ERROR

    # Call auto-recovery
    controller._recover_from_error()
    assert controller.state == ConversationState.LISTENING


# ─────────────────────────────────────────────────────────────────────────────
# 10. Bounded Error Retries (Infinite Retry Loop Prevention)
# ─────────────────────────────────────────────────────────────────────────────

def test_phase9_bounded_error_retries(voice_pipeline) -> None:
    controller, mic, vad, whisper, player, tts, ai = voice_pipeline
    controller.enable()

    # Trigger 4 consecutive errors
    controller._on_pipeline_error("Simulated failure 1", stage="llm")
    assert controller._consecutive_error_count == 1
    assert controller.state == ConversationState.ERROR

    controller._on_pipeline_error("Simulated failure 2", stage="llm")
    assert controller._consecutive_error_count == 2

    controller._on_pipeline_error("Simulated failure 3", stage="llm")
    assert controller._consecutive_error_count == 3

    # 4th error exceeds limit (max 3) -> Must halt to IDLE, preventing infinite loop!
    controller._on_pipeline_error("Simulated failure 4", stage="llm")
    assert controller.state in (ConversationState.IDLE, ConversationState.DISABLED)
    assert controller._consecutive_error_count == 0
