"""Tests for ConversationContext."""

from app.ai.conversation_context import ConversationContext


def test_conversation_context_add_and_retrieve():
    """Verify appending messages and building payload."""
    ctx = ConversationContext(system_prompt="You are a helper.")
    ctx.add_user_message("Hello!")
    ctx.add_assistant_message("Hi! How are you?")

    messages = ctx.get_messages()
    assert len(messages) == 3
    assert messages[0] == {"role": "system", "content": "You are a helper."}
    assert messages[1] == {"role": "user", "content": "Hello!"}
    assert messages[2] == {"role": "assistant", "content": "Hi! How are you?"}


def test_conversation_context_turn_pruning():
    """Verify turn limit pruning preserves system message and recent dialogue."""
    ctx = ConversationContext(system_prompt="System", max_turns=2)
    # Add 3 turns (6 messages)
    for i in range(3):
        ctx.add_user_message(f"User {i}")
        ctx.add_assistant_message(f"AI {i}")

    messages = ctx.get_messages()
    # With max_turns=2, should have 1 system message + 4 messages (turns 1 and 2)
    assert len(messages) == 5
    assert messages[0]["content"] == "System"
    assert messages[1]["content"] == "User 1"
    assert messages[4]["content"] == "AI 2"


def test_conversation_context_token_budget_pruning():
    """Verify token budget pruning drops oldest messages to stay under budget."""
    ctx = ConversationContext(system_prompt="Sys", max_token_budget=50)
    # Add large messages
    ctx.add_user_message("A" * 80)
    ctx.add_assistant_message("B" * 80)
    ctx.add_user_message("C" * 20)

    messages = ctx.get_messages()
    assert messages[0]["role"] == "system"
    # Older heavy messages should be trimmed
    contents = [m["content"] for m in messages]
    assert "C" * 20 in contents


def test_conversation_context_memory_injection():
    """Verify injecting stored memories attaches them to system section."""
    ctx = ConversationContext(system_prompt="Base prompt")
    ctx.inject_memories(["User loves astronomy", "User lives in Seattle"])
    ctx.add_user_message("What should I look at tonight?")

    messages = ctx.get_messages()
    system_content = messages[0]["content"]
    assert "Base prompt" in system_content
    assert "astronomy" in system_content
    assert "Seattle" in system_content


def test_conversation_context_clear():
    """Verify clearing removes history but preserves system prompt."""
    ctx = ConversationContext(system_prompt="Preserved system")
    ctx.add_user_message("Test")
    ctx.add_assistant_message("Response")
    assert ctx.history_length == 2

    ctx.clear()
    assert ctx.history_length == 0
    msgs = ctx.get_messages()
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Preserved system"


def test_conversation_context_serialization():
    """Verify serialization round-trip."""
    ctx = ConversationContext(system_prompt="Sys", max_turns=5)
    ctx.add_user_message("One")
    ctx.add_assistant_message("Two")
    ctx.inject_memories(["Mem1"])

    data = ctx.serialize()
    restored = ConversationContext()
    restored.deserialize(data)

    assert restored.system_prompt == "Sys"
    assert restored.history_length == 2
    assert restored._injected_memories == ["Mem1"]
