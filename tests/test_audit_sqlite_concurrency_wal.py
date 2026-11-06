"""Comprehensive SQLite WAL Mode and Concurrency Audit Test Suite.

Explicitly satisfies Test1.md Section 7.E and Section 7.A-D:
- WAL mode active verification
- Foreign key constraint enforcement
- Read-while-write concurrency
- Multi-threaded concurrent message insertions
- Simultaneous conversation creation and updates
- Transaction rollback safety
- Database reopening and persistence verification
- Clean resource closure
"""

import concurrent.futures
from pathlib import Path
import sqlite3
import threading
import time

import pytest

from app.memory.database import DatabaseManager
from app.memory.conversation_repository import ConversationRepository


def test_sqlite_wal_mode_and_foreign_keys_active(tmp_path: Path):
    """Verify WAL mode and foreign key constraints are enabled on connections."""
    db_file = tmp_path / "wal_verify.db"
    db_mgr = DatabaseManager(db_path=db_file)
    conn = db_mgr.get_connection()

    # Check journal_mode is WAL
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert mode.lower() == "wal"

    # Check foreign_keys is ON
    fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert fk == 1

    db_mgr.close()


def test_sqlite_foreign_key_enforcement_raises_on_invalid_parent(tmp_path: Path):
    """Verify inserting a message referencing a nonexistent conversation raises IntegrityError."""
    db_file = tmp_path / "fk_enforce.db"
    db_mgr = DatabaseManager(db_path=db_file)
    conn = db_mgr.get_connection()

    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at, status) "
                "VALUES ('nonexistent-conv-id', 'user', 'Hello?', '2026-01-01T00:00:00Z', 'completed');"
            )

    db_mgr.close()


def test_sqlite_wal_read_while_writing(tmp_path: Path):
    """Verify in WAL mode a reader thread can read while another connection is writing."""
    db_file = tmp_path / "wal_read_write.db"
    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)

    conv = repo.create_conversation("Read While Write")
    repo.add_message(conv.id, "user", "Initial seed message")

    read_results = []
    read_barrier = threading.Barrier(2)

    def reader_worker():
        read_barrier.wait()
        # Reader runs on separate thread using thread-local connection
        reader_conn = db_mgr.get_connection()
        rows = reader_conn.execute("SELECT content FROM messages WHERE conversation_id=?", (conv.id,)).fetchall()
        read_results.extend([r["content"] for r in rows])

    reader_thread = threading.Thread(target=reader_worker)
    reader_thread.start()

    # Writer performs writes
    read_barrier.wait()
    repo.add_message(conv.id, "assistant", "Parallel generated response")
    reader_thread.join(timeout=5.0)

    assert not reader_thread.is_alive()
    assert len(read_results) >= 1
    assert "Initial seed message" in read_results

    db_mgr.close()


def test_sqlite_concurrent_message_insertions(tmp_path: Path):
    """Verify concurrent worker threads inserting messages concurrently don't corrupt database."""
    db_file = tmp_path / "concurrent_messages.db"
    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)

    conv = repo.create_conversation("Concurrency Test")
    num_threads = 6
    messages_per_thread = 10

    def insert_worker(thread_idx: int):
        for i in range(messages_per_thread):
            repo.add_message(
                conversation_id=conv.id,
                role="user" if (i % 2 == 0) else "assistant",
                content=f"Message {i} from thread {thread_idx}",
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(insert_worker, t) for t in range(num_threads)]
        for f in concurrent.futures.as_completed(futures, timeout=10.0):
            f.result()

    # Check total message count
    all_msgs = repo.get_messages(conv.id)
    expected_count = num_threads * messages_per_thread
    assert len(all_msgs) == expected_count

    # Check message ordering integrity
    ids = [m.id for m in all_msgs]
    assert ids == sorted(ids)

    db_mgr.close()


def test_sqlite_concurrent_conversation_creation(tmp_path: Path):
    """Verify simultaneous conversation creations across multiple threads."""
    db_file = tmp_path / "concurrent_convs.db"
    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)

    created_ids = []
    lock = threading.Lock()

    def create_worker(idx: int):
        c = repo.create_conversation(f"Thread Conv {idx}")
        with lock:
            created_ids.append(c.id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(create_worker, i) for i in range(16)]
        for f in concurrent.futures.as_completed(futures, timeout=10.0):
            f.result()

    assert len(created_ids) == 16
    all_convs = repo.list_conversations()
    assert len(all_convs) == 16

    db_mgr.close()


def test_sqlite_transaction_rollback_on_failure(tmp_path: Path):
    """Verify failed operations roll back without leaving partial corrupt writes."""
    db_file = tmp_path / "rollback.db"
    db_mgr = DatabaseManager(db_path=db_file)
    repo = ConversationRepository(db_manager=db_mgr)

    conv = repo.create_conversation("Rollback Conv")
    conn = db_mgr.get_connection()

    initial_count = conn.execute("SELECT COUNT(*) FROM messages;").fetchone()[0]
    assert initial_count == 0

    # Execute a transaction that intentionally fails halfway through
    try:
        with conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at, status) "
                "VALUES (?, 'user', 'Will be rolled back', '2026-01-01', 'completed');",
                (conv.id,),
            )
            # Intentionally fail with a foreign key violation or bad column
            conn.execute("INSERT INTO messages (conversation_id, non_existent_col) VALUES (?, ?);", (conv.id, "bad"))
    except sqlite3.OperationalError:
        pass

    # Verify rollback: 0 messages
    final_count = conn.execute("SELECT COUNT(*) FROM messages;").fetchone()[0]
    assert final_count == 0

    db_mgr.close()


def test_sqlite_reopening_and_persistence(tmp_path: Path):
    """Verify closing DatabaseManager and opening a new one preserves all data."""
    db_file = tmp_path / "reopen.db"

    # Step 1: Open, write, close
    db_mgr1 = DatabaseManager(db_path=db_file)
    repo1 = ConversationRepository(db_manager=db_mgr1)
    c1 = repo1.create_conversation("Persistent Conv")
    repo1.add_message(c1.id, "user", "Message for future session")
    db_mgr1.close()

    # Step 2: Open with new DatabaseManager
    db_mgr2 = DatabaseManager(db_path=db_file)
    repo2 = ConversationRepository(db_manager=db_mgr2)
    convs = repo2.list_conversations()
    assert len(convs) == 1
    assert convs[0].id == c1.id
    assert convs[0].title == "Persistent Conv"

    msgs = repo2.get_messages(c1.id)
    assert len(msgs) == 1
    assert msgs[0].content == "Message for future session"

    db_mgr2.close()
