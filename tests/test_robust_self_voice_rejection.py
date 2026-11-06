"""Comprehensive Tests for Robust AI Self-Voice Rejection & Acoustic Echo Cancellation.

Validates:
1. Reference signal tracking and ring buffering in AcousticEchoCanceller.
2. Normalized Cross-Correlation (NCC) discrimination between AI playback and user speech.
3. Pre-STT waveform-level utterance correlation preventing Whisper dispatch of echoed speech.
4. Gating strategy during playback and acoustic decay cooldown in speaker mode.
5. Headset vs. Speaker auto-detection and profile switching.
6. Configurable VAD silence threshold and end-of-speech detection.
7. End-to-end prevention of infinite AI self-conversation loops.
8. Stop and Mute controls halting audio capture and playback.
"""

from __future__ import annotations

import time
from typing import List
from unittest.mock import MagicMock

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
import pytest

from app.voice.acoustic_echo_canceller import AcousticEchoCanceller, EchoFrameAnalysis
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.echo_suppressor import AcousticEchoSuppressor
from app.voice.interruption_manager import InterruptionManager
from app.voice.microphone_manager import MicrophoneManager
from app.voice.streaming_audio_queue import StreamingAudioQueue
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


# ─────────────────────────────────────────────────────────────────────────────
# Test Fixtures & Dummy Components
# ─────────────────────────────────────────────────────────────────────────────

class DummyTTSEngine(BaseTTSEngine):
    """Fast dummy TTS synthesizer returning dummy audio sine wave."""

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent=parent)
        self.synthesize_calls: List[str] = []

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str) -> SynthesizedAudio:
        self.synthesize_calls.append(text)
        sample_rate = 16000
        duration = 0.5
        samples = (np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration))) * 0.5).astype(np.float32)
        return SynthesizedAudio(
            samples=samples,
            sample_rate=sample_rate,
            duration_seconds=duration,
            text=text,
            voice_name="dummy",
        )

    def load_model(self, voice_name: str) -> bool:
        return True

    def get_available_voices(self) -> List[str]:
        return ["dummy"]


from app.core.signals import signals


class DummyWhisperEngine(QObject):
    """Mock WhisperEngine that returns fast transcription result."""

    error_occurred = Signal(str)

    def __init__(self, text: str = "Hello Buddy", parent: QObject = None) -> None:
        super().__init__(parent)
        self.text = text

    def transcribe_async(self, audio_data: np.ndarray, language=None, prompt=None, callback=None) -> None:
        res = TranscriptionResult(
            text=self.text,
            language="en",
            language_probability=0.99,
            duration_seconds=len(audio_data) / 16000.0,
        )
        if callback:
            callback(res)


class DummyAIService(QObject):
    """Mock AIService for testing voice vs text segregation and turn dispatch."""

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent=parent)
        self.asked_prompts: List[str] = []
        self._is_current_voice = False
        self.cancel_generation_called = False

    @property
    def is_current_generation_voice(self) -> bool:
        return self._is_current_voice

    def ask(self, user_prompt: str, is_voice: bool = False, **kwargs) -> None:
        self._is_current_voice = is_voice
        self.asked_prompts.append(user_prompt)
        if is_voice:
            signals.ai_response_chunk.emit("I hear you loud and clear. ")
            signals.ai_response_complete.emit("I hear you loud and clear.")

    def cancel_generation(self) -> None:
        self.cancel_generation_called = True


# ─────────────────────────────────────────────────────────────────────────────
# 1. Reference Signal Ingestion & Ring Buffer
# ─────────────────────────────────────────────────────────────────────────────

def test_aec_reference_signal_ingestion():
    """AcousticEchoCanceller must resample and buffer playback samples."""
    aec = AcousticEchoCanceller(sample_rate=16000, cooldown_decay_sec=0.65)
    assert aec.is_playing is False
    assert aec.is_in_cooldown() is False

    # Feed 24kHz audio (e.g. Kokoro TTS output)
    sr_24k = 24000
    samples_24k = np.random.randn(24000).astype(np.float32) * 0.2
    aec.feed_reference_audio(samples_24k, sr_24k)

    assert aec.is_playing is True
    assert aec.is_in_cooldown() is True
    assert aec._total_ref_samples == 16000  # Resampled from 24kHz (1.0s) to 16kHz (1.0s)

    # Stop playback and verify decay window
    aec.mark_playback_stopped()
    assert aec.is_playing is False
    assert aec.is_in_cooldown() is True  # In 0.65s cooldown


# ─────────────────────────────────────────────────────────────────────────────
# 2. Normalized Cross-Correlation (NCC) AI Voice Discrimination
# ─────────────────────────────────────────────────────────────────────────────

def test_aec_frame_ncc_discrimination():
    """AEC must flag mic frames containing reference playback audio and pass independent voice."""
    aec = AcousticEchoCanceller(sample_rate=16000, echo_mode="headset")
    # Feed 1.0s of reference audio
    reference_audio = np.random.randn(16000).astype(np.float32) * 0.3
    aec.feed_reference_audio(reference_audio, 16000)

    # Case A: Mic captures a 512-sample chunk from the playback audio (acoustic leak)
    echo_chunk = reference_audio[12000:12512] + 0.02 * np.random.randn(512).astype(np.float32)
    analysis_echo = aec.analyze_mic_frame(echo_chunk)
    assert analysis_echo.is_echo is True
    assert analysis_echo.correlation >= aec.correlation_threshold
    assert analysis_echo.reason == "ncc_correlation_match"

    # Case B: Mic captures independent human speech (uncorrelated with reference)
    user_voice_chunk = np.random.randn(512).astype(np.float32) * 0.3
    analysis_user = aec.analyze_mic_frame(user_voice_chunk)
    assert analysis_user.is_echo is False
    assert analysis_user.correlation < aec.correlation_threshold
    assert analysis_user.reason == "clean"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pre-STT Utterance Waveform Correlation Rejection
# ─────────────────────────────────────────────────────────────────────────────

def test_aec_utterance_waveform_correlation_rejection():
    """Utterance matching the assistant's playback waveform must be rejected before Whisper."""
    aec = AcousticEchoCanceller(sample_rate=16000)
    # Assistant spoke a 2-second sentence
    ref_samples = np.random.randn(32000).astype(np.float32) * 0.25
    aec.feed_reference_audio(ref_samples, 16000)
    aec.mark_playback_stopped()

    # Leaked audio segment captured by microphone
    leaked_utterance = ref_samples[8000:24000] + 0.01 * np.random.randn(16000).astype(np.float32)

    is_echo, corr, reason = aec.correlate_utterance_with_playback(leaked_utterance)
    assert is_echo is True
    assert corr >= aec.correlation_threshold
    assert reason == "waveform_reference_match"

    # Genuine user utterance (different waveform)
    user_utterance = np.random.randn(16000).astype(np.float32) * 0.25
    is_echo_user, corr_user, _ = aec.correlate_utterance_with_playback(user_utterance)
    assert is_echo_user is False
    assert corr_user < aec.correlation_threshold


# ─────────────────────────────────────────────────────────────────────────────
# 4. Microphone Gating Strategy in Speaker Mode
# ─────────────────────────────────────────────────────────────────────────────

def test_microphone_gating_speaker_mode(qtbot):
    """In speaker mode, mic frames are dropped during playback and decay cooldown, keeping VAD clean."""
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = DummyWhisperEngine(text="Hello Buddy")
    player = AudioPlayer()
    tts = DummyTTSEngine()
    ai = DummyAIService()

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=ai,
    )
    controller.echo_canceller.set_echo_mode("speaker")
    assert controller.echo_canceller.echo_mode == "speaker"

    controller.enable()
    assert controller.state == ConversationState.LISTENING

    # Simulate speaker audio playback
    ref_audio = np.random.randn(8000).astype(np.float32) * 0.3
    controller.echo_canceller.feed_reference_audio(ref_audio, 16000)
    controller.echo_canceller.mark_playback_started()
    assert controller.echo_canceller.is_playing is True

    # High-amplitude speech frames arrive at mic during playback
    loud_speech_frame = np.ones(512, dtype=np.float32) * 0.2
    for _ in range(10):
        controller.process_mic_frame(loud_speech_frame)

    # VAD must NOT have triggered, state remains LISTENING, VAD remains in SILENCE
    assert controller.state == ConversationState.LISTENING
    assert vad.state == VADState.SILENCE
    assert len(vad._active_utterance_frames) == 0

    # Stop playback -> enters cooldown
    controller.echo_canceller.mark_playback_stopped()
    assert controller.echo_canceller.is_in_cooldown() is True

    # Frames arriving during cooldown are also dropped
    for _ in range(5):
        controller.process_mic_frame(loud_speech_frame)

    assert controller.state == ConversationState.LISTENING
    assert vad.state == VADState.SILENCE

    controller.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Device Profile Auto-Detection (Headset vs. Speaker)
# ─────────────────────────────────────────────────────────────────────────────

def test_headset_vs_speaker_profile_detection():
    """AcousticEchoCanceller detects headsets and laptop speakers based on device name."""
    aec = AcousticEchoCanceller(echo_mode="auto")

    assert aec.detect_device_mode("Speakers (Realtek(R) Audio)") == "speaker"
    assert aec.detect_device_mode("Headphones (AirPods Pro)") == "headset"
    assert aec.detect_device_mode("Wireless Stereo Headset WH-1000XM4") == "headset"
    assert aec.detect_device_mode("Earphones (Galaxy Buds2 Pro)") == "headset"
    assert aec.detect_device_mode("High Definition Audio Device (Speakers)") == "speaker"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Configurable VAD Silence Threshold
# ─────────────────────────────────────────────────────────────────────────────

def test_configurable_vad_silence_threshold():
    """VADEngine silence threshold can be dynamically configured."""
    vad = VADEngine(silence_threshold_ms=750)
    assert vad.silence_threshold_ms == 750

    vad.set_silence_threshold(1200)
    assert vad.silence_threshold_ms == 1200

    # Bounded limits (min 250ms, max 5000ms)
    vad.set_silence_threshold(100)
    assert vad.silence_threshold_ms == 250
    vad.set_silence_threshold(10000)
    assert vad.silence_threshold_ms == 5000


# ─────────────────────────────────────────────────────────────────────────────
# 7. End-to-End Prevention of Infinite Self-Conversation Loop
# ─────────────────────────────────────────────────────────────────────────────

def test_infinite_conversation_loop_prevented(qtbot):
    """Assistant speech played into the microphone does not trigger a new turn or infinite loop."""
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = DummyWhisperEngine(text="Hello Buddy")
    player = AudioPlayer()
    tts = DummyTTSEngine()
    ai = DummyAIService()

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=ai,
    )
    controller.enable()

    # Step 1: User speaks legitimate prompt
    controller._on_vad_speech_started()
    assert controller.state == ConversationState.USER_SPEAKING

    # Synthesize user utterance
    user_audio = np.ones(16000, dtype=np.float32) * 0.15
    controller._on_vad_speech_ended(user_audio)

    # Wait for completion of turn
    qtbot.waitUntil(lambda: controller.state == ConversationState.LISTENING, timeout=4000)

    assert len(ai.asked_prompts) == 1
    first_turn_prompt = ai.asked_prompts[0]

    # Step 2: Now simulate assistant playback leaking into microphone
    assistant_speech = "Hello, I am Buddy, your AI companion!"
    controller.echo_canceller.mark_playback_started()
    controller.echo_suppressor.record_assistant_speech(assistant_speech)

    # Synthesize assistant audio and feed as reference
    assistant_audio = (np.sin(2 * np.pi * 300 * np.linspace(0, 1.0, 16000)) * 0.4).astype(np.float32)
    controller.echo_canceller.feed_reference_audio(assistant_audio, 16000)

    # Try feeding leaked assistant audio into microphone
    for i in range(0, 16000, 512):
        chunk = assistant_audio[i : i + 512]
        controller.process_mic_frame(chunk)

    # In speaker mode, mic frames were completely gated
    assert controller.state == ConversationState.LISTENING
    assert vad.state == VADState.SILENCE
    # AI ask() was NOT called a second time!
    assert len(ai.asked_prompts) == 1

    # Step 3: Even if a leak bypassed frame gating and produced an utterance matching playback
    is_echo, corr, _ = controller.echo_canceller.correlate_utterance_with_playback(assistant_audio)
    assert is_echo is True
    # And if text is transcribed, EchoSuppressor flags it
    is_echo_text, reason, _ = controller.echo_suppressor.is_echo(assistant_speech)
    assert is_echo_text is True

    # No second ask() call occurred!
    assert len(ai.asked_prompts) == 1

    controller.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# 8. Stop and Mute Controls Safely Halt Operations
# ─────────────────────────────────────────────────────────────────────────────

def test_stop_and_mute_controls_safe_execution(qtbot):
    """Emergency stop and mute prevent audio operations and self-reaction."""
    mic = MicrophoneManager()
    vad = VADEngine()
    whisper = DummyWhisperEngine(text="Hello Buddy")
    player = AudioPlayer()
    tts = DummyTTSEngine()
    ai = DummyAIService()

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        tts_engine=tts,
        ai_service=ai,
    )
    controller.enable()

    # Mute player
    player.set_muted(True)
    assert player.is_muted is True

    # Emergency stop
    controller.emergency_stop()
    assert controller.state == ConversationState.IDLE
    assert player.is_playing is False
    assert mic.is_recording is False
    assert ai.cancel_generation_called is True

    controller.cleanup()
