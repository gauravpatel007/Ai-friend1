"""Integration tests for complete interaction pipelines (Phase 12.2).

Tests:
1. AI Chat Pipeline: Text Input -> Ollama -> AI Response -> Chat Display / Signal -> SQLite Storage
2. Voice Conversation Pipeline: Mic -> Speech Detection -> Whisper -> Ollama -> TTS -> Audio Playback
3. Interruption Pipeline: AI Speaking -> User Interrupts -> Cancel Generation -> Stop Audio -> Start Listening
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ai.ai_service import AIService
from app.character.states import CharacterState
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.settings.config_manager import ConfigManager
from app.voice.audio_player import AudioPlayer
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.interruption_manager import InterruptionConfig, InterruptionManager
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.vad_engine import VADEngine, VADState
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceMode, VoiceService
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


class MockTTSForIntegration(BaseTTSEngine):
    """Mock TTS producing valid synthetic audio buffers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.synthesize_calls = []

    def is_available(self) -> bool:
        return True

    def load_model(self, voice_name: str | None = None) -> bool:
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        self.synthesize_calls.append(text)
        samples = np.ones(1600, dtype=np.float32) * 0.05
        return SynthesizedAudio(
            samples=samples,
            sample_rate=16000,
            duration_seconds=0.1,
            text=text,
            voice_name="mock_voice",
        )


def test_ai_chat_pipeline_end_to_end(qapp_instance):
    """Test Pipeline 1: Text Input -> Ollama -> AI Response -> Chat -> SQLite."""
    db_file = SCRATCH_DIR / "test_chat_pipeline.db"
    if db_file.exists():
        db_file.unlink()

    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)
    config = ConfigManager(config_path=SCRATCH_DIR / "test_chat_cfg.json")

    conv = repo.create_conversation("Pipeline Test Chat")
    user_prompt = "Hello Buddy, explain quantum tunneling."

    # 1. User sends message -> Saved in SQLite
    user_msg = repo.add_message(conv.id, "user", user_prompt)
    assert user_msg.id is not None

    # 2. Mock Ollama streaming response through AIService
    ai_service = AIService(config_manager=config)
    ai_service.model_manager.is_available = MagicMock(return_value=True)
    ai_service.model_manager.select_active_model = MagicMock(return_value="qwen3:1.7b")
    ai_service.client.chat_stream = MagicMock(return_value=[
        "Quantum ", "tunneling ", "is ", "a ", "fascinating ", "phenomenon."
    ])

    chunks_received = []
    complete_received = []

    signals.ai_response_chunk.connect(lambda c: chunks_received.append(c))
    signals.ai_response_complete.connect(lambda full: complete_received.append(full))

    # Trigger generation via ask()
    ai_service.ask(user_prompt)

    # Wait for background worker to complete
    for _ in range(50):
        qapp_instance.processEvents()
        if len(complete_received) > 0:
            break
        import time; time.sleep(0.02)

    assert len(complete_received) == 1
    full_text = complete_received[0]
    assert "Quantum tunneling is a fascinating phenomenon." in full_text

    # 3. Save AI response into SQLite storage
    ai_msg = repo.add_message(conv.id, "assistant", full_text)
    assert ai_msg.id is not None

    # Verify database persistence
    history = repo.get_messages(conv.id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"
    assert history[1].content == full_text
    ai_service.stop()


def test_voice_conversation_pipeline(qapp_instance):
    """Test Pipeline 2: Mic Audio -> Whisper STT -> Ollama -> TTS -> Audio Playback."""
    mock_tts = MockTTSForIntegration()
    mock_player = MagicMock(spec=AudioPlayer)
    mock_player.is_playing.return_value = False

    mock_ai = MagicMock(spec=AIService)

    voice_service = VoiceService()
    voice_service.audio_player = mock_player
    voice_service.active_tts_engine = mock_tts
    voice_service.attach_ai_service(mock_ai)

    # 1. Simulate speech transcription completion in controller
    result = TranscriptionResult(
        text="What time is it?",
        language="en",
        language_probability=0.99,
        duration_seconds=1.0,
    )
    voice_service.conversation_controller._state = ConversationState.TRANSCRIBING
    voice_service.conversation_controller._turn_id = 1

    voice_service.conversation_controller._on_transcription_completed(result, turn_id=1)
    mock_ai.ask.assert_called_with(user_prompt="What time is it?", is_voice=True)

    # 2. Simulate AI response completion triggering TTS and playback
    voice_service.speak("It is twelve o'clock.")
    # Allow background TTS worker to run
    for _ in range(25):
        qapp_instance.processEvents()
        if len(mock_tts.synthesize_calls) > 0:
            break
        import time; time.sleep(0.02)

    assert len(mock_tts.synthesize_calls) == 1
    assert mock_tts.synthesize_calls[0] == "It is twelve o'clock."
    mock_player.play.assert_called()


def test_interruption_pipeline(qapp_instance):
    """Test Pipeline 3: AI Speaking -> User Interrupts -> Cancel Generation -> Stop Audio -> Start Listening."""
    mock_player = MagicMock(spec=AudioPlayer)
    mock_player.is_playing.return_value = True

    mock_ai = MagicMock(spec=AIService)
    mock_ai._is_generating = True

    cancelled_events = []
    character_states = []
    signals.ai_cancel_requested.connect(lambda: cancelled_events.append(True))
    signals.character_state_changed.connect(lambda s: character_states.append(s))

    voice_service = VoiceService()
    voice_service.audio_player = mock_player
    voice_service.attach_ai_service(mock_ai)
    voice_service.conversation_controller.audio_player = mock_player

    # Set controller to AI_SPEAKING state
    voice_service.conversation_controller._state = ConversationState.AI_SPEAKING

    # User speaks while AI is speaking -> interruption triggered
    speech_samples = np.ones(3200, dtype=np.float32) * 0.1
    voice_service.conversation_controller._on_interruption_detected(1, speech_samples)

    # Verify:
    # 1. Audio player stopped immediately
    mock_player.stop.assert_called()
    # 2. Ongoing AI generation cancelled
    mock_ai.cancel_generation.assert_called()
    assert len(cancelled_events) == 1
    # 3. Character animation switched to LISTENING
    assert "listening" in character_states
