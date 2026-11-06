"""Tests for StreamingThinkingFilter and strip_thinking_tags."""

from app.ai.thinking_filter import StreamingThinkingFilter, strip_thinking_tags


def test_strip_thinking_tags_basic():
    """Verify stripping <think> tags from completed responses."""
    raw = "<think>Let me think about this question.</think>Hello! How can I help you today?"
    assert strip_thinking_tags(raw) == "Hello! How can I help you today?"


def test_strip_thinking_tags_multiline():
    """Verify multiline reasoning blocks are removed cleanly."""
    raw = "<think>\nStep 1: Check time\nStep 2: Greet\n</think>\nGood morning!"
    assert strip_thinking_tags(raw) == "Good morning!"


def test_strip_thinking_tags_no_tags():
    """Verify text without thinking tags is unchanged."""
    raw = "Just a friendly message!"
    assert strip_thinking_tags(raw) == "Just a friendly message!"


def test_streaming_thinking_filter_normal_text():
    """Verify normal text passes through streaming filter unmodified."""
    flt = StreamingThinkingFilter()
    chunks = ["Hello", " world", "!"]
    output = [flt.process_chunk(c) for c in chunks]
    output.append(flt.flush())
    assert "".join(output) == "Hello world!"


def test_streaming_thinking_filter_with_split_tags():
    """Verify tags split across arbitrary chunk boundaries are filtered out."""
    flt = StreamingThinkingFilter()
    # Simulates streaming where '<think>' arrives in pieces
    chunks = [
        "<th",
        "ink>Internal",
        " thought process",
        " continuing...",
        "</th",
        "ink>",
        "Hi there",
        " buddy!",
    ]
    output = []
    for c in chunks:
        out = flt.process_chunk(c)
        if out:
            output.append(out)
    tail = flt.flush()
    if tail:
        output.append(tail)

    full_output = "".join(output)
    assert full_output == "Hi there buddy!"
    assert "Internal" not in full_output
    assert "thought" not in full_output


def test_streaming_thinking_filter_tag_at_end():
    """Verify filter handles trailing tag prefix buffer correctly."""
    flt = StreamingThinkingFilter()
    chunks = ["Greeting: <th"]
    output = [flt.process_chunk(c) for c in chunks]
    # Buffer held '<th' in case it's '<think>'
    assert "".join(output) == "Greeting: "
    # Flush should emit the held non-tag text if it turns out not to be a tag
    tail = flt.flush()
    assert tail == "<th"


def test_thinking_filter_synchronous_instance_method():
    """Verify ThinkingFilter().filter(text) cleanly strips thinking tags (Bug 8)."""
    from app.ai.thinking_filter import ThinkingFilter

    flt = ThinkingFilter()
    raw = "<think>Calculating optimal greeting...</think>Hello, friend!"
    result = flt.filter(raw)
    assert result == "Hello, friend!"


def test_thinking_filter_synchronous_classmethod():
    """Verify ThinkingFilter.filter(text) can be called directly without instantiating."""
    from app.ai.thinking_filter import ThinkingFilter

    raw = "<think>Silent thought</think>Direct class call"
    result = ThinkingFilter.filter(raw)
    assert result == "Direct class call"


def test_streaming_thinking_filter_synchronous_method():
    """Verify StreamingThinkingFilter also exposes .filter() synchronously."""
    flt = StreamingThinkingFilter()
    raw = "<think>Inner thought</think>Streaming filter response"
    assert flt.filter(raw) == "Streaming filter response"
    assert StreamingThinkingFilter.filter(raw) == "Streaming filter response"


def test_thinking_filter_callable():
    """Verify ThinkingFilter instances can be invoked directly as callables."""
    from app.ai.thinking_filter import ThinkingFilter

    flt = ThinkingFilter()
    raw = "<think>Processing</think>Callable works!"
    assert flt(raw) == "Callable works!"
    assert flt.filter_text(raw) == "Callable works!"


def test_thinking_filter_case_insensitive_and_attributes():
    """Verify thinking filter removes uppercase tags and tags with attributes."""
    from app.ai.thinking_filter import ThinkingFilter

    flt = ThinkingFilter()
    assert flt.filter("<THINK>Shouting thought</THINK>Calm response") == "Calm response"
    assert flt.filter("<Think>Mixed case</Think>Clean") == "Clean"
    assert flt.filter('<think class="reasoning">Attributes</think>Result') == "Result"


def test_thinking_filter_unclosed_tag():
    """Verify thinking filter cleans trailing unclosed <think> blocks."""
    from app.ai.thinking_filter import ThinkingFilter

    flt = ThinkingFilter()
    assert flt.filter("<think>Unclosed reasoning at end") == ""
    assert flt.filter("Initial greeting. <think>Unfinished thought") == "Initial greeting."


def test_thinking_filter_stateless_safety():
    """Verify calling .filter() does not pollute active streaming buffer."""
    from app.ai.thinking_filter import ThinkingFilter

    flt = ThinkingFilter()
    # Partially stream something
    out1 = flt.process_chunk("Hello <th")
    assert out1 == "Hello "

    # Call synchronous filter in the middle
    sync_result = flt.filter("<think>Other thought</think>Other response")
    assert sync_result == "Other response"

    # Complete the original stream
    out2 = flt.process_chunk("ink>Reasoning</think>world!")
    out3 = flt.flush()
    assert (out1 + out2 + out3) == "Hello world!"


def test_app_ai_package_exports_thinking_filter():
    """Verify ThinkingFilter is properly exported in app.ai package."""
    from app.ai import ThinkingFilter

    flt = ThinkingFilter()
    assert flt.filter("<think>Exported</think>Success") == "Success"

