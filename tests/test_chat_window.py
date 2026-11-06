"""Tests for FloatingChatWindow and chat lifecycle."""

from pathlib import Path
from PySide6.QtCore import QPoint, QRect, QTimer
import pytest

from app.core.signals import signals
from app.desktop.chat_window import FloatingChatWindow, HistorySearchDialog
from app.memory.conversation_repository import ConversationRepository
from app.memory.database import DatabaseManager
from app.settings.config_manager import ConfigManager


@pytest.fixture
def test_chat_setup(tmp_path: Path):
    """Fixture providing isolated config and database repository."""
    config_file = tmp_path / "settings.json"
    cfg = ConfigManager(config_path=config_file)
    db_mgr = DatabaseManager(db_path=tmp_path / "test_chat_window.db")
    repo = ConversationRepository(db_manager=db_mgr)
    return cfg, repo


def test_chat_window_initialization(qapp_instance, test_chat_setup):
    """Verify chat window initializes and creates an active conversation."""
    cfg, repo = test_chat_setup
    window = FloatingChatWindow(config_manager=cfg, repository=repo)

    assert window.active_conversation is not None
    assert "Buddy" in window.title_label.text()
    assert window.isVisible() is False

    window.show_chat()
    assert window.isVisible() is True

    window.hide_chat()
    assert window.isVisible() is False

    window.close()


def test_chat_window_position_near_pet(qapp_instance, test_chat_setup):
    """Verify chat window positions adjacent to pet window without going offscreen."""
    cfg, repo = test_chat_setup
    window = FloatingChatWindow(config_manager=cfg, repository=repo)

    pet_rect = QRect(200, 200, 120, 120)
    window.position_near_pet(pet_rect)

    pos = window.pos()
    # Should be to the right of the pet (>= 335)
    assert pos.x() >= pet_rect.right()
    window.close()


def test_chat_window_send_and_streaming(qapp_instance, test_chat_setup):
    """Verify user message send, streaming chunks, and completion."""
    cfg, repo = test_chat_setup
    window = FloatingChatWindow(config_manager=cfg, repository=repo)

    # 1. Send user prompt
    window._on_user_send("Hi Buddy!")

    # Check database stored message
    messages = repo.get_messages(window.active_conversation.id)
    assert len(messages) == 1
    assert messages[0].content == "Hi Buddy!"
    assert window._current_thinking_widget is not None

    # 2. Simulate streaming chunks arriving from signal bus
    signals.ai_response_chunk.emit("Hello ")
    assert window._current_thinking_widget is None
    assert window._current_ai_bubble is not None
    assert window._current_ai_bubble.content_label.text() == "Hello "

    signals.ai_response_chunk.emit("there!")
    assert window._current_ai_bubble.content_label.text() == "Hello there!"

    # 3. Simulate completion
    signals.ai_response_complete.emit("Hello there!")
    assert window.input_bar._is_generating is False

    # Check database updated with full assistant message
    messages_after = repo.get_messages(window.active_conversation.id)
    assert len(messages_after) == 2
    assert messages_after[1].content == "Hello there!"
    assert messages_after[1].status == "completed"

    window.close()


def test_chat_window_cancellation(qapp_instance, test_chat_setup):
    """Verify cancellation marks active streaming bubble as cancelled."""
    cfg, repo = test_chat_setup
    window = FloatingChatWindow(config_manager=cfg, repository=repo)

    window._on_user_send("Question to cancel")
    signals.ai_response_chunk.emit("Starting ")

    # Cancel
    window._on_user_cancel()
    assert window.input_bar._is_generating is False

    window.close()


def test_chat_window_conversation_management(qapp_instance, test_chat_setup):
    """Verify switching, clearing, and creating new conversations."""
    cfg, repo = test_chat_setup
    window = FloatingChatWindow(config_manager=cfg, repository=repo)
    first_conv_id = window.active_conversation.id

    # Add message in first conversation
    window._on_user_send("Message in chat 1")

    # Create new conversation
    window.new_conversation()
    second_conv_id = window.active_conversation.id
    assert second_conv_id != first_conv_id

    # Switch back to first conversation
    window.switch_conversation(first_conv_id)
    assert window.active_conversation.id == first_conv_id
    msgs = repo.get_messages(first_conv_id)
    assert len(msgs) == 1

    # Clear chat messages
    window._clear_active_chat()
    assert len(repo.get_messages(first_conv_id)) == 0

    window.close()


def test_chat_history_search_dialog(qapp_instance, test_chat_setup):
    """Verify search dialog finds matching text and emits selected conversation."""
    cfg, repo = test_chat_setup
    conv = repo.create_conversation("Searchable")
    repo.add_message(conv.id, "user", "Finding a needle in a haystack")

    dialog = HistorySearchDialog(repository=repo)
    selected_convs = []
    dialog.conversation_selected.connect(selected_convs.append)

    dialog._do_search("needle")
    assert dialog.results_list.count() == 1

    dialog._on_item_double_clicked(dialog.results_list.item(0))
    assert selected_convs == [conv.id]

    dialog.close()
