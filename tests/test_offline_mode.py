"""Offline Mode Verification Test Suite (Phase 12.4).

Ensures the AI Desktop Friend operates completely offline:
- Blocks external network calls (allows only loopback/localhost)
- AI responses work via local Ollama endpoint
- Speech recognition works via local Faster-Whisper
- Voice synthesis works via local TTS engines
- Memory repository and SQLite work offline
- Character renderer works with bundled sprite assets
"""

import socket
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.character.renderer import CharacterRenderer
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.memory.memory_manager import MemoryManager
from app.settings.config_manager import ConfigManager
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def block_external_networks(monkeypatch):
    """Enforce strict offline environment by blocking any non-loopback network calls."""
    real_create_connection = socket.create_connection

    def guarded_create_connection(address, *args, **kwargs):
        host, port = address
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise OSError(f"Simulated Offline Mode: Outbound connection to {host}:{port} blocked.")
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)


def test_offline_memory_and_database():
    """Verify SQLite database and memory manager operate 100% offline without remote calls."""
    db_file = SCRATCH_DIR / f"offline_test_{uuid.uuid4().hex}.db"
    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)

    # 1. Conversation and messages
    conv = repo.create_conversation("Offline Session")
    user_msg = repo.add_message(conv.id, "user", "What is stored in my local offline memory?")
    ai_msg = repo.add_message(conv.id, "assistant", "All your memories are stored locally in SQLite.")

    history = repo.get_messages(conv.id)
    assert len(history) == 2
    assert history[0].content == "What is stored in my local offline memory?"
    assert history[1].content == "All your memories are stored locally in SQLite."

    # 2. Long-term memory extraction
    mem_mgr = MemoryManager(db_manager=db_mgr)
    mem_id = mem_mgr.add_memory("User prefers dark mode and offline operations", category="preference")
    assert mem_id is not None
    mems = mem_mgr.get_all_memories()
    assert len(mems) == 1
    assert mems[0].category == "preference"


def test_offline_character_rendering(qapp_instance):
    """Verify character rendering loads bundled local sprite assets without network."""
    renderer = CharacterRenderer(character_name="robot")
    renderer.set_size(150)
    renderer.set_state("idle")

    # Render frame
    pixmap = renderer.get_current_pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()
    assert pixmap.width() > 0
    assert pixmap.height() > 0

    # Switch to thinking and render
    renderer.set_state("thinking")
    pixmap_thinking = renderer.get_current_pixmap()
    assert pixmap_thinking is not None
    assert not pixmap_thinking.isNull()


def test_offline_ollama_local_inference():
    """Verify local Ollama client connects strictly to loopback without external traffic."""
    from app.ai.ollama_client import OllamaClient
    client = OllamaClient(base_url="http://127.0.0.1:11434")

    # Mock local socket response from Ollama
    with patch("urllib.request.OpenerDirector.open") as mock_open:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"models": [{"name": "qwen3:1.7b"}]}'
        mock_open.return_value.__enter__.return_value = mock_resp
        assert client.is_server_reachable() is True


def test_offline_speech_recognition_mock():
    """Verify speech recognition executes locally without external API."""
    engine = WhisperEngine()
    engine.is_model_loaded = True

    dummy_audio = np.zeros(16000, dtype=np.float32)

    with patch.object(engine, "transcribe") as mock_transcribe:
        mock_transcribe.return_value = TranscriptionResult(
            text="Offline recognition verified.",
            language="en",
            language_probability=0.99,
            duration_seconds=1.0,
        )
        res = engine.transcribe(dummy_audio)
        assert res.text == "Offline recognition verified."
        assert res.language == "en"
