"""Tests for ChatMessageWidget, ThinkingIndicatorWidget, and ChatInputBar."""

from PySide6.QtCore import Qt

from app.desktop.chat_components import (
    ChatInputBar,
    ChatMessageWidget,
    ThinkingIndicatorWidget,
)


def test_chat_message_widget_user(qapp_instance):
    """Verify user message bubble formatting."""
    widget = ChatMessageWidget(role="user", content="Hello world!")
    assert widget.role == "user"
    assert widget.content_label.text() == "Hello world!"
    assert widget.time_label.alignment() & Qt.AlignRight


def test_chat_message_widget_assistant_and_streaming(qapp_instance):
    """Verify assistant message bubble streaming and chunk appending."""
    widget = ChatMessageWidget(role="assistant", content="Initial ", status="streaming")
    assert widget.role == "assistant"
    assert widget.content_label.text() == "Initial "

    # Append stream chunk
    widget.append_chunk("token")
    assert widget.content_label.text() == "Initial token"

    widget.set_status("completed")
    assert widget.status == "completed"


def test_chat_message_widget_error_state(qapp_instance):
    """Verify error message bubble rendering."""
    widget = ChatMessageWidget(role="assistant", content="⚠️ Failed to connect", status="error")
    assert widget.status == "error"


def test_thinking_indicator_widget(qapp_instance):
    """Verify thinking indicator initializes and contains companion name."""
    widget = ThinkingIndicatorWidget(companion_name="Sparky")
    assert "Thinking" in widget.text_label.text() or "Sparky" in widget.text_label.text()


def test_chat_input_bar_mode_switching(qapp_instance):
    """Verify mode switching between text, PTT, and continuous."""
    bar = ChatInputBar()
    recorded_modes = []
    bar.mode_changed.connect(recorded_modes.append)

    assert bar.current_mode == "text"

    bar.set_mode("push_to_talk")
    assert bar.current_mode == "push_to_talk"

    bar.set_mode("continuous")
    assert bar.current_mode == "continuous"

    assert recorded_modes == ["push_to_talk", "continuous"]


def test_chat_input_bar_send_and_cancel(qapp_instance):
    """Verify send button and cancel/stop button toggle during generation."""
    bar = ChatInputBar()
    sent_text = []
    cancel_fired = []

    bar.send_requested.connect(sent_text.append)
    bar.cancel_requested.connect(lambda: cancel_fired.append(True))

    bar.text_input.setPlainText("Test question")
    bar._on_send_clicked()

    assert sent_text == ["Test question"]
    assert bar.text_input.toPlainText() == ""

    # Switch to generating state -> button turns to Stop (■)
    bar.set_generating(True)
    assert bar.btn_action.text() == "■"

    # Clicking action button now fires cancel_requested
    bar._on_action_clicked()
    assert len(cancel_fired) == 1
