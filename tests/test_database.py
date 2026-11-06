"""Tests for DatabaseManager SQLite layer."""

from pathlib import Path
import sqlite3

from app.memory.database import DatabaseManager


def test_database_initialization_and_schema(tmp_path: Path):
    """Verify tables and indexes are created properly."""
    db_file = tmp_path / "test_conversations.db"
    db_mgr = DatabaseManager(db_path=db_file)

    conn = db_mgr.get_connection()

    # Check tables
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
    ]
    assert "conversations" in tables
    assert "messages" in tables

    # Check indexes
    indexes = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index';"
        ).fetchall()
    ]
    assert "idx_messages_conversation_id" in indexes
    assert "idx_conversations_updated_at" in indexes

    db_mgr.close()


def test_database_foreign_key_cascade(tmp_path: Path):
    """Verify deleting a conversation cascades deletion to its messages."""
    db_file = tmp_path / "test_cascade.db"
    db_mgr = DatabaseManager(db_path=db_file)
    conn = db_mgr.get_connection()

    with conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES ('c1', 'Title', 'now', 'now');"
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at, status) VALUES ('c1', 'user', 'Hi', 'now', 'completed');"
        )

    # Message exists
    count = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id='c1';").fetchone()[0]
    assert count == 1

    # Delete conversation
    with conn:
        conn.execute("DELETE FROM conversations WHERE id='c1';")

    # Messages must be cascaded away
    count_after = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id='c1';").fetchone()[0]
    assert count_after == 0

    db_mgr.close()
