"""Comprehensive test suite verifying fixes for continuous voice conversation bugs:
1. Continuous Voice Mode reliably listens and resumes listening.
2. Text-chat responses are strictly separated from voice-mode responses (zero TTS on typed text).
3. AI voice responses are spoken exactly once (no duplicate TTS calls, no 3x word repetition).
4. Microphone gating and acoustic echo suppressor prevent self-conversation feedback loops.
5. Stop and Mute operations immediately halt audio and generation.
"""

from __future__ import annotations

import time
from typing import Any, List
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QObject, QTimer

from app.character.states import CharacterState
from app.core.signals import signals
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.echo_suppressor import AcousticEchoSuppressor
from app.voice.microphone_manager import MicrophoneManager
from app.voice.sentence_chunker import SentenceChunker
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceMode, VoiceService
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


@pytest.fixture(scope="session")
def qapp():
    """Ensure QCoreApplication exists for Qt signals and timers."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


class MockTTS(BaseTTSEngine):
    """Deterministic in-memory TTS engine for tests."""

    def __init__(self, sample_rate: int = 16000, duration: float = 0.05) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.duration = duration
        self.synthesized_calls: List[str] = []

    def synthesize(self, text: str, **kwargs: Any) -> SynthesizedAudio:
        self.synthesized_calls.append(text)
        samples = np.ones(int(self.sample_rate * self.duration), dtype=np.float32) * 0.05
        return SynthesizedAudio(
            samples=samples,
            sample_rate=self.sample_rate,
            duration_seconds=self.duration,
            text=text,
            voice_name="mock_voice",
        )

    def is_available(self) -> bool:
        return True


class MockAIService(QObject):
    """Mock AI Service tracking prompt submissions and voice mode flag."""

    def __init__(self) -> None:
        super().__init__()
        self.prompts: List[str] = []
        self._is_generating = False
        self._is_current_voice = False
        self.cancellation_count = 0

    @property
    def is_current_generation_voice(self) -> bool:
        return self._is_current_voice

    def ask(self, user_prompt: str, is_voice: bool = False, **kwargs: Any) -> int:
        self.prompts.append(user_prompt)
        self._is_current_voice = bool(is_voice)
        self._is_generating = True
        return 1

    def cancel_generation(self) -> None:
        self._is_generating = False
        self.cancellation_count += 1


# =============================================================================
# 1. Verification of Bug 2: Typed text messages produce ZERO TTS audio
# =============================================================================

def test_typed_text_produces_zero_tts(qapp):
    """When a user types a message in text chat (is_voice=False), TTS must not speak."""
    from app.core.controller import ApplicationController

    # Create mock controller environment
    ctrl = MagicMock()
    mock_ai = MockAIService()
    mock_voice = MagicMock()
    mock_voice.tts_enabled = True

    ctrl.ai_service = mock_ai
    ctrl.voice_service = mock_voice

    # Simulate typed text query
    mock_ai.ask("What is the capital of France?", is_voice=False)
    assert not mock_ai.is_current_generation_voice

    # Invoke _on_ai_response_tts with full response text
    ApplicationController._on_ai_response_tts(ctrl, "The capital of France is Paris.")

    # mock_voice.speak must NOT have been called!
    mock_voice.speak.assert_not_called()


def test_voice_conversation_controller_ignores_text_stream_chunks(qapp):
    """VoiceConversationController must ignore streaming tokens if is_current_generation_voice is False."""
    mock_ai = MockAIService()
    mock_tts = MockTTS()
    mock_player = MagicMock(spec=AudioPlayer)
    mock_player.is_playing = False
    mock_player.is_in_cooldown.return_value = False

    ctrl = VoiceConversationController(
        ai_service=mock_ai,
        tts_engine=mock_tts,
        audio_player=mock_player,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )

    # Set controller in generating state
    ctrl._state = ConversationState.GENERATING_RESPONSE

    # AI is generating a typed text response (is_voice=False)
    mock_ai.ask("Explain quantum computing", is_voice=False)
    assert not mock_ai.is_current_generation_voice

    # Stream chunks arrive
    ctrl._on_ai_stream_chunk("Quantum ")
    ctrl._on_ai_stream_chunk("computing ")
    ctrl._on_ai_stream_chunk("is fascinating. ")
    ctrl._on_ai_stream_complete("Quantum computing is fascinating.")

    # Audio queue must have received zero sentences for synthesis
    assert len(mock_tts.synthesized_calls) == 0
    assert len(ctrl._accumulated_ai_response) == 0
    ctrl.cleanup()


# =============================================================================
# 2. Verification of Bug 3: Voice response is spoken exactly once
# =============================================================================

def test_voice_response_spoken_once_streaming_queue_suppresses_duplicate_tts(qapp):
    """When continuous voice mode is enabled, streaming queue handles chunks and controller suppresses full-text TTS."""
    from app.core.controller import ApplicationController

    ctrl = MagicMock()
    mock_ai = MockAIService()
    mock_voice = MagicMock()
    mock_voice.tts_enabled = True

    # Continuous conversation controller is enabled
    mock_conv_ctrl = MagicMock()
    mock_conv_ctrl.is_enabled = True
    mock_voice.conversation_controller = mock_conv_ctrl

    ctrl.ai_service = mock_ai
    ctrl.voice_service = mock_voice

    # AI is responding to voice input
    mock_ai.ask("Hello friend", is_voice=True)
    assert mock_ai.is_current_generation_voice

    # Completion event arrives
    ApplicationController._on_ai_response_tts(ctrl, "Hello! How can I assist you today?")

    # Because mock_conv_ctrl.is_enabled is True, speak() must NOT be called (preventing duplicate full playback!)
    mock_voice.speak.assert_not_called()


def test_voice_response_spoken_once_when_continuous_controller_disabled(qapp):
    """When continuous controller is disabled (e.g. PTT or one-shot voice), full-text TTS is spoken once."""
    from app.core.controller import ApplicationController

    ctrl = MagicMock()
    mock_ai = MockAIService()
    mock_voice = MagicMock()
    mock_voice.tts_enabled = True

    # Continuous controller disabled
    mock_conv_ctrl = MagicMock()
    mock_conv_ctrl.is_enabled = False
    mock_voice.conversation_controller = mock_conv_ctrl

    ctrl.ai_service = mock_ai
    ctrl.voice_service = mock_voice

    # AI is responding to voice input
    mock_ai.ask("Hello friend", is_voice=True)

    ApplicationController._on_ai_response_tts(ctrl, "Hello! How can I assist you today?")

    # Spoken exactly once
    mock_voice.speak.assert_called_once_with("Hello! How can I assist you today?")


# =============================================================================
# 3. Verification of Bug 4: Microphone Gating during TTS & Echo Loop Prevention
# =============================================================================

def test_microphone_gating_drops_frames_during_audio_playback(qapp):
    """While AudioPlayer is playing or in cooldown, mic frames must be gated and VAD reset."""
    mock_player = MagicMock(spec=AudioPlayer)
    mock_player.is_playing = True
    mock_player.is_in_cooldown.return_value = True

    mock_vad = MagicMock(spec=VADEngine)

    ctrl = VoiceConversationController(
        audio_player=mock_player,
        vad_engine=mock_vad,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )
    ctrl._state = ConversationState.SPEAKING

    # Microphone frame arrives containing loud audio (simulating speaker output)
    loud_frame = np.ones(512, dtype=np.float32) * 0.8
    ctrl.process_mic_frame(loud_frame)

    # VAD must have been reset and process_frame must NOT have been called
    mock_vad.reset_states.assert_called()
    mock_vad.process_frame.assert_not_called()
    ctrl.cleanup()


def test_microphone_gating_drops_frames_during_decay_cooldown(qapp):
    """Even if audio player stopped, decay window must continue gating microphone frames."""
    mock_player = MagicMock(spec=AudioPlayer)
    mock_player.is_playing = False
    mock_player.is_in_cooldown.return_value = True

    mock_vad = MagicMock(spec=VADEngine)

    ctrl = VoiceConversationController(
        audio_player=mock_player,
        vad_engine=mock_vad,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )
    ctrl._state = ConversationState.SPEAKING

    frame = np.ones(512, dtype=np.float32) * 0.5
    ctrl.process_mic_frame(frame)

    mock_vad.reset_states.assert_called()
    mock_vad.process_frame.assert_not_called()
    ctrl.cleanup()


def test_echo_suppressor_detects_immediate_post_playback_fragment():
    """EchoSuppressor must detect single words or fragments uttered within 3s of playback as echo."""
    suppressor = AcousticEchoSuppressor(cooldown_decay_sec=0.65)
    suppressor.record_assistant_speech("Hello! I am your AI desktop companion.")
    suppressor.mark_playback_ended()

    # Immediate leak of a single word from assistant's sentence
    is_echo, reason, conf = suppressor.is_echo("companion")
    assert is_echo is True
    assert reason in ("post_playback_fragment", "substring_match")

    # Immediate leak of a short fragment
    is_echo2, reason2, _ = suppressor.is_echo("desktop companion")
    assert is_echo2 is True

    # Exact match must always be an echo
    is_echo3, reason3, _ = suppressor.is_echo("Hello! I am your AI desktop companion.")
    assert is_echo3 is True
    assert reason3 == "exact_match"


# =============================================================================
# 4. Verification of Bug 1: Continuous Listening Resumption
# =============================================================================

def test_continuous_mode_resumes_listening_after_all_speech_played(qapp):
    """After all speech chunks have played, controller cleanly returns to LISTENING."""
    mock_vad = MagicMock(spec=VADEngine)
    mock_player = MagicMock(spec=AudioPlayer)
    mock_player.is_playing = False
    mock_player.is_in_cooldown.return_value = False

    ctrl = VoiceConversationController(
        vad_engine=mock_vad,
        audio_player=mock_player,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )
    ctrl._state = ConversationState.SPEAKING
    turn_id = ctrl.current_turn_id

    # Finish speech callback
    ctrl._on_all_speech_played(turn_id)

    # Process pending singleShot Qt timer (600ms decay)
    start_time = time.time()
    while ctrl.state != ConversationState.LISTENING and (time.time() - start_time) < 1.5:
        qapp.processEvents()
        time.sleep(0.05)

    assert ctrl.state == ConversationState.LISTENING
    ctrl.cleanup()


# =============================================================================
# 5. Verification of Stop & Mute operations
# =============================================================================

def test_api_voice_stop_cancels_generation_and_playback():
    """The /api/voice/stop endpoint must cancel AI generation, stop audio queue and mic capture."""
    from starlette.testclient import TestClient
    from app.api.server import create_app

    app = create_app()
    mock_ai = MockAIService()
    mock_voice = MagicMock(spec=VoiceService)

    app.state.ai_service = mock_ai
    app.state.voice_service = mock_voice

    # Start generation
    mock_ai.ask("Long story...", is_voice=True)
    assert mock_ai._is_generating is True

    client = TestClient(app)
    res = client.post("/api/voice/stop", headers={"origin": "http://127.0.0.1:8765"})
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    # Generation cancelled
    assert mock_ai._is_generating is False
    assert mock_ai.cancellation_count >= 1

    # Audio stopped
    mock_voice.stop_speaking.assert_called()
    mock_voice.emergency_stop.assert_called()


def test_api_voice_mute_mutes_audio_player():
    """The /api/voice/mute endpoint mutes the underlying audio player."""
    from starlette.testclient import TestClient
    from app.api.server import create_app

    app = create_app()
    mock_voice = MagicMock(spec=VoiceService)
    app.state.voice_service = mock_voice

    client = TestClient(app)
    res = client.post(
        "/api/voice/mute",
        json={"muted": True},
        headers={"origin": "http://127.0.0.1:8765"},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "muted": True}
    mock_voice.set_muted.assert_called_once_with(True)
