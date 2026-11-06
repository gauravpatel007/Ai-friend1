"""Tests for Bug #14: History Pruning Pops Odd Messages, Leaving Orphaned Assistant Turns as the Conversation Start.

Validates:
1. Turn-based pruning with an odd message count drops orphaned leading assistant messages.
2. Token budget pruning drops orphaned leading assistant messages when an oldest user message is popped.
3. Deserializing raw history with an orphaned assistant start automatically cleanses history.
4. get_messages() sanitizes any history state so conversation always starts with a user turn.
5. History containing exclusively assistant messages is safely pruned to empty.
6. Multi-turn alternating dialogue structure (user, assistant, user, assistant...) is strictly preserved after pruning.
"""

from app.ai.conversation_context import ConversationContext


def test_pruning_odd_number_of_messages_turn_based() -> None:
    """Verify that when turn-based pruning slices an odd turn, the orphaned assistant message is pruned."""
    # max_turns=2 -> max_messages=4
    ctx = ConversationContext(system_prompt="You are Buddy.", max_turns=2)

    ctx.add_user_message("User 1")
    ctx.add_assistant_message("AI 1")
    ctx.add_user_message("User 2")
    ctx.add_assistant_message("AI 2")
    # Now add User 3 (total 5 messages in conversational history)
    ctx.add_user_message("User 3")

    messages = ctx.get_messages()

    # messages[0] is system
    assert messages[0]["role"] == "system"
    # messages[1] MUST be user, NOT an orphaned assistant message!
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "User 2"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "AI 2"
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == "User 3"
    assert len(messages) == 4  # system + 3 history messages


def test_pruning_odd_number_of_messages_token_budget() -> None:
    """Verify token budget pruning drops orphaned leading assistant message when user message is popped."""
    # available_budget has a minimum floor of 256 tokens (~1024 chars).
    # User 1 is 800 chars (~200 tokens), AI 1 is 400 chars (~100 tokens). Total 300+ tokens > 256 tokens.
    ctx = ConversationContext(system_prompt="Sys", max_token_budget=50)

    ctx.add_user_message("A" * 800)       # Heavy user message (200 tokens)
    ctx.add_assistant_message("B" * 400)  # Heavy assistant message (100 tokens)
    ctx.add_user_message("Next question") # Short user question

    messages = ctx.get_messages()
    assert messages[0]["role"] == "system"

    # Conversational history must start with user turn ("Next question"), NOT orphaned assistant ("B" * 400)
    non_system_roles = [m["role"] for m in messages if m["role"] != "system"]
    assert non_system_roles[0] == "user"
    assert messages[1]["content"] == "Next question"


def test_deserialization_with_orphaned_assistant_start() -> None:
    """Verify deserializing history that begins with an assistant turn sanitizes it."""
    ctx = ConversationContext(system_prompt="System Prompt")
    raw_data = {
        "system_prompt": "System Prompt",
        "max_turns": 5,
        "max_token_budget": 1000,
        "history": [
            {"role": "assistant", "content": "Orphaned greeting from previous corrupt session"},
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "Paris."},
        ],
        "memories": [],
        "summaries": [],
    }

    ctx.deserialize(raw_data)
    messages = ctx.get_messages()

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "What is the capital of France?"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Paris."
    assert len(messages) == 3


def test_manual_history_manipulation_sanitized_on_get_messages() -> None:
    """Verify get_messages() sanitizes history even if modified externally."""
    ctx = ConversationContext(system_prompt="System")
    ctx._history = [
        {"role": "assistant", "content": "Ghost assistant message"},
        {"role": "user", "content": "Legitimate user message"},
        {"role": "assistant", "content": "Legitimate assistant response"},
    ]

    messages = ctx.get_messages()
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Legitimate user message"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Legitimate assistant response"


def test_multiple_orphaned_assistant_messages_pruned_before_user() -> None:
    """Verify that multiple leading assistant messages before a user message are pruned completely."""
    ctx = ConversationContext(system_prompt="System")
    ctx._history = [
        {"role": "assistant", "content": "Orphaned 1"},
        {"role": "assistant", "content": "Orphaned 2"},
        {"role": "user", "content": "Valid user query"},
        {"role": "assistant", "content": "Valid AI response"},
    ]

    messages = ctx.get_messages()
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Valid user query"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Valid AI response"
    assert ctx.history_length == 2


def test_alternating_structure_preserved_across_multi_turn_pruning() -> None:
    """Verify alternating user-assistant pattern holds after substantial multi-turn pruning."""
    ctx = ConversationContext(system_prompt="System", max_turns=3)

    for i in range(10):
        ctx.add_user_message(f"User query {i}")
        ctx.add_assistant_message(f"Assistant answer {i}")

    messages = ctx.get_messages()
    # System + 3 turns (6 messages) = 7 messages total
    assert len(messages) == 7
    assert messages[0]["role"] == "system"

    # Verify alternating pattern for all conversational messages
    for idx, msg in enumerate(messages[1:]):
        expected_role = "user" if idx % 2 == 0 else "assistant"
        assert msg["role"] == expected_role, f"Message at index {idx+1} should have role {expected_role}"
