"""
Unit tests verifying reliable speech detection, silence hangover smoothing,
and prevention of false cooldown gating during user speech.
"""

import time
import numpy as np
import pytest
from PySide6.QtCore import QObject

from app.voice.audio_player import AudioPlayer
from app.voice.echo_suppressor import AcousticEchoSuppressor
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController, ConversationState
from app.voice.voice_service import VoiceService, VoiceMode


def test_audio_player_stop_when_idle_does_not_trigger_cooldown():
    """Stopping an idle AudioPlayer must not arm a false playback cooldown."""
    player = AudioPlayer()
    assert player.is_in_cooldown(0.65) is False

    # Calling stop() when not playing
    player.stop()
    assert player.is_in_cooldown(0.65) is False


def test_echo_suppressor_ended_when_idle_does_not_trigger_decay():
    """Marking playback ended when not playing must not arm a false decay window."""
    suppressor = AcousticEchoSuppressor()
    assert suppressor.is_in_decay_window is False

    suppressor.mark_playback_ended()
    assert suppressor.is_in_decay_window is False


def test_vad_hangover_smoothing_with_ambient_noise_spikes():
    """VADEngine must complete an utterance through sporadic room noise spikes using hangover smoothing."""
    vad = VADEngine(silence_threshold_ms=700)
    sample_rate = 16000
    frame_size = 512

    # 1 second of speech (RMS ~0.15)
    t = np.linspace(0, 1.0, sample_rate, endpoint=False)
    speech = (0.2 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)

    # 1.5 seconds of ambient noise (RMS ~0.02) with sporadic single-frame bumps
    np.random.seed(42)
    noise = np.random.normal(0, 0.02, int(sample_rate * 1.5)).astype(np.float32)
    for bump_t in [0.2, 0.4, 0.6]:
        idx = int(bump_t * sample_rate)
        noise[idx:idx + frame_size] += 0.045

    audio = np.concatenate([speech, noise])
    num_frames = len(audio) // frame_size

    completed_utterance = None
    completed_at_frame = None

    for i in range(num_frames):
        chunk = audio[i * frame_size:(i + 1) * frame_size]
        res = vad.process_frame(chunk)
        if res is not None:
            completed_utterance = res
            completed_at_frame = i
            break

    assert completed_utterance is not None, "Utterance should complete via silence timeout despite noise spikes"
    # Expected completion at ~1.7s to 2.1s (1s speech + ~700-900ms silence)
    completion_time_sec = (completed_at_frame * frame_size) / float(sample_rate)
    assert 1.4 <= completion_time_sec <= 2.2


def test_voice_service_speech_started_does_not_disrupt_vad():
    """When speech onset triggers, VoiceService must not reset VAD or arm cooldown when AI is not speaking."""
    service = VoiceService()
    service.set_mode(VoiceMode.CONTINUOUS)
    vad = service.vad_engine

    assert service.audio_player.is_playing is False
    assert service.audio_player.is_in_cooldown(0.65) is False

    # Simulate onset trigger
    vad.speech_started.emit()

    # Audio player must NOT be in cooldown
    assert service.audio_player.is_in_cooldown(0.65) is False

    service.stop()


def test_vad_silence_detection_with_room_noise_and_dc_offset():
    """Verify that ambient room noise (RMS ~0.033) with DC microphone offset cleanly ends utterance."""
    sample_rate = 16000
    frame_size = 512
    vad = VADEngine(
        sample_rate=sample_rate,
        frame_size=frame_size,
        min_speech_frames=2,
        silence_threshold_ms=500,
        min_utterance_ms=100,
    )

    t = np.linspace(0, 0.032, frame_size, endpoint=False, dtype=np.float32)
    speech_frame = (0.35 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)

    # Ambient room noise matching user diagnostic: RMS ~0.033 with +0.02 DC bias
    np.random.seed(123)
    noise_frame = (np.random.normal(0, 0.033, frame_size) + 0.02).astype(np.float32)

    # 1. User speaks 6 frames (~192ms)
    for _ in range(6):
        vad.process_frame(speech_frame)

    assert vad.state == VADState.SPEAKING

    # 2. User stops speaking; room noise continues (16 frames = 512ms > 500ms)
    completed_utterance = None
    for _ in range(20):
        res = vad.process_frame(noise_frame)
        if res is not None:
            completed_utterance = res
            break

    assert completed_utterance is not None, "VAD must detect end of speech despite ambient room noise and DC bias"
    assert vad.state == VADState.SILENCE
    assert len(completed_utterance) >= frame_size * 6


def test_utterance_timeout_watchdog_forwards_to_transcription(qtbot):
    """Utterance watchdog timeout must force-finalize active speech and forward it to STT."""
    from unittest.mock import MagicMock
    from app.voice.microphone_manager import MicrophoneManager
    from app.voice.whisper_engine import WhisperEngine
    from app.voice.conversation_state import VoiceActivationMode

    mic = MicrophoneManager()
    vad = VADEngine(sample_rate=16000, frame_size=512)
    whisper = WhisperEngine()
    whisper.transcribe_async = MagicMock()
    player = AudioPlayer()

    controller = VoiceConversationController(
        mic_manager=mic,
        vad_engine=vad,
        whisper_engine=whisper,
        audio_player=player,
        activation_mode=VoiceActivationMode.CONTINUOUS,
    )
    controller.enable()

    # Transition to USER_SPEAKING and seed speech frames into VAD
    t = np.linspace(0, 0.032, 512, endpoint=False, dtype=np.float32)
    speech_frame = (0.35 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    for _ in range(4):
        vad.process_frame(speech_frame)

    assert vad.state == VADState.SPEAKING
    controller._transition_to(ConversationState.USER_SPEAKING)

    # Fire watchdog timeout
    controller._on_utterance_timeout()

    # Must transition to TRANSCRIBING and invoke whisper.transcribe_async, not discard!
    assert controller.state == ConversationState.TRANSCRIBING
    assert whisper.transcribe_async.call_count == 1

    controller.cleanup()

