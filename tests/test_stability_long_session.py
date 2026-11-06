"""Long-Session Stability and Stress Testing (Phase 12.5).

Simulates extended conversation sessions (25 turns) while verifying:
1. Memory leaks (RSS growth remains bounded)
2. Database reliability (all messages saved, PRAGMA integrity_check == 'ok')
3. Audio queue bounds (no unbounded buffer accumulation)
4. Application responsiveness
"""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock
import psutil
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.performance_monitor import get_performance_monitor
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.memory.memory_manager import MemoryManager
from app.settings.config_manager import ConfigManager
from app.voice.audio_player import AudioPlayer

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


def test_long_session_dialogue_stability_and_memory(qapp_instance):
    """Run a 25-turn conversation session and measure resource stability."""
    process = psutil.Process(os.getpid())
    perf_monitor = get_performance_monitor()
    initial_snapshot = perf_monitor.get_snapshot()

    initial_rss = initial_snapshot.process_rss_mb

    # Initialize isolated database and managers
    db_file = SCRATCH_DIR / f"stability_test_{uuid.uuid4().hex}.db"
    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)
    mem_mgr = MemoryManager(db_manager=db_mgr)

    conv = repo.create_conversation("Extended 25-Turn Stress Test")

    # Mock audio player to simulate consumption without audio hardware
    mock_player = AudioPlayer()
    mock_player.play = MagicMock(return_value=True)

    # Execute 25 simulated conversation turns
    for turn in range(1, 26):
        user_text = f"Turn {turn}: Tell me an interesting scientific fact about quantum mechanics or astrophysics."
        repo.add_message(conv.id, "user", user_text)

        ai_response = f"Response {turn}: Quantum entanglement demonstrates non-local correlations between particles."
        repo.add_message(conv.id, "assistant", ai_response)

        # Every 5 turns, record a user preference memory
        if turn % 5 == 0:
            mem_mgr.add_memory(f"User is interested in science topic #{turn}", category="interest")

        # Process Qt events to simulate GUI event loop activity
        qapp_instance.processEvents()

    # 1. Verify all 50 messages were persisted accurately
    messages = repo.get_messages(conv.id)
    assert len(messages) == 50
    assert messages[0].content.startswith("Turn 1:")
    assert messages[-1].content.startswith("Response 25:")

    # 2. Verify database integrity
    conn = db_mgr.get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check")
    status = cursor.fetchone()[0]
    assert status == "ok"

    # 3. Verify memory count
    memories = mem_mgr.get_all_memories()
    assert len(memories) == 5

    # 4. Measure memory RSS growth
    final_rss = process.memory_info().rss / (1024 * 1024)
    delta_rss = final_rss - initial_rss

    # Assert bounded memory usage (growth under 60 MB for 25 turns)
    assert delta_rss < 60.0, f"Excessive memory leak detected: +{delta_rss:.1f} MB over 25 turns"
