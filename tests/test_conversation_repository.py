"""Tests for ConversationRepository data access layer."""

from pathlib import Path

from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager


def test_repository_conversation_lifecycle(tmp_path: Path):
    """Verify creating, listing, renaming, and deleting conversations."""
    db_mgr = DatabaseManager(db_path=tmp_path / "test_repo.db")
    repo = ConversationRepository(db_manager=db_mgr)

    # 1. Create conversation
    conv = repo.create_conversation("My First Chat")
    assert conv.id is not None
    assert conv.title == "My First Chat"

    # 2. Get conversation
    fetched = repo.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.id == conv.id
    assert fetched.title == "My First Chat"

    # 3. Rename conversation
    assert repo.rename_conversation(conv.id, "Renamed Chat") is True
    assert repo.get_conversation(conv.id).title == "Renamed Chat"

    # 4. List conversations
    conv2 = repo.create_conversation("Second Chat")
    all_convs = repo.list_conversations()
    assert len(all_convs) == 2
    # Ordered by updated_at DESC (conv2 newest)
    assert all_convs[0].id == conv2.id

    # 5. Delete conversation
    assert repo.delete_conversation(conv.id) is True
    assert repo.get_conversation(conv.id) is None
    assert len(repo.list_conversations()) == 1


def test_repository_message_operations_and_auto_titling(tmp_path: Path):
    """Verify adding messages, updating content, and auto-titling from user prompt."""
    db_mgr = DatabaseManager(db_path=tmp_path / "test_messages.db")
    repo = ConversationRepository(db_manager=db_mgr)

    conv = repo.create_conversation()  # Defaults to "New Chat"
    assert conv.title == "New Chat"

    # Add first user message -> should trigger auto-titling
    user_msg = repo.add_message(
        conversation_id=conv.id,
        role="user",
        content="What is the distance to the Moon?",
    )
    assert user_msg.id is not None
    assert user_msg.role == "user"

    # Verify conversation title auto-updated
    updated_conv = repo.get_conversation(conv.id)
    assert "distance to the Moon" in updated_conv.title

    # Add streaming assistant message
    ai_msg = repo.add_message(
        conversation_id=conv.id,
        role="assistant",
        content="The distance is ",
        status="streaming",
    )
    assert ai_msg.status == "streaming"

    # Update assistant message when stream finishes
    assert repo.update_message_content(
        ai_msg.id,
        content="The distance is approximately 384,400 km.",
        status="completed",
    ) is True

    # Retrieve all messages
    messages = repo.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].content == "What is the distance to the Moon?"
    assert messages[1].content == "The distance is approximately 384,400 km."
    assert messages[1].status == "completed"


def test_repository_clear_messages(tmp_path: Path):
    """Verify clearing all messages in a conversation."""
    db_mgr = DatabaseManager(db_path=tmp_path / "test_clear.db")
    repo = ConversationRepository(db_manager=db_mgr)

    conv = repo.create_conversation("Clear Test")
    repo.add_message(conv.id, "user", "Message 1")
    repo.add_message(conv.id, "assistant", "Message 2")
    assert len(repo.get_messages(conv.id)) == 2

    repo.clear_conversation_messages(conv.id)
    assert len(repo.get_messages(conv.id)) == 0
    # Conversation itself is preserved
    assert repo.get_conversation(conv.id) is not None


def test_repository_search_messages(tmp_path: Path):
    """Verify searching message text across conversations."""
    db_mgr = DatabaseManager(db_path=tmp_path / "test_search.db")
    repo = ConversationRepository(db_manager=db_mgr)

    c1 = repo.create_conversation("Science")
    repo.add_message(c1.id, "user", "Tell me about quantum computing")
    repo.add_message(c1.id, "assistant", "Quantum computers use qubits")

    c2 = repo.create_conversation("Cooking")
    repo.add_message(c2.id, "user", "How to make sourdough bread?")

    results = repo.search_messages("quantum")
    assert len(results) == 2
    assert results[0]["conversation_title"] == "Science"

    results_bread = repo.search_messages("sourdough")
    assert len(results_bread) == 1
    assert results_bread[0]["conversation_title"] == "Cooking"
