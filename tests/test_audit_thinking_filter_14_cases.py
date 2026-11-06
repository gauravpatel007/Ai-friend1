"""Comprehensive 14-case audit test suite for thinking tag filtering.

Explicitly validates all 14 mandatory test cases from Test1.md Section 6.C:
1. Ordinary text without reasoning tags
2. Complete <think>...</think> block
3. Reasoning followed by a final answer
4. Multiple reasoning blocks
5. Opening tag split across chunks (<th + ink>)
6. Closing tag split across chunks (</th + ink>)
7. Tags with surrounding whitespace
8. Empty reasoning blocks (<think></think>)
9. Unfinished reasoning block at stream termination
10. Malformed or nested tags (<think><think>nested</think></think>)
11. Uppercase or unexpected tag variants (<THINK>...</THINK>)
12. Literal tag-like text appearing in an answer (e.g. 5 < 10 and 10 > 2, <thing>)
13. Cancellation while filter is inside a reasoning block
14. Streaming where the final answer begins in the same chunk closing the reasoning block
"""

import pytest
from app.ai.thinking_filter import StreamingThinkingFilter, strip_thinking_tags, ThinkingFilter


def run_stream(flt: StreamingThinkingFilter, chunks: list[str]) -> str:
    """Helper to feed chunks through a StreamingThinkingFilter and return total output."""
    output = []
    for c in chunks:
        out = flt.process_chunk(c)
        if out:
            output.append(out)
    tail = flt.flush()
    if tail:
        output.append(tail)
    return "".join(output)


# Case 1: Ordinary text without reasoning tags
def test_case_01_ordinary_text_without_tags():
    flt = StreamingThinkingFilter()
    chunks = ["The quick ", "brown fox ", "jumps over the lazy dog."]
    result = run_stream(flt, chunks)
    assert result == "The quick brown fox jumps over the lazy dog."
    assert strip_thinking_tags("The quick brown fox jumps over the lazy dog.") == "The quick brown fox jumps over the lazy dog."


# Case 2: Complete <think>...</think> block
def test_case_02_complete_thinking_block():
    flt = StreamingThinkingFilter()
    chunks = ["<think>pondering the secrets of the universe</think>"]
    result = run_stream(flt, chunks)
    assert result == ""
    assert strip_thinking_tags("<think>pondering the secrets of the universe</think>") == ""


# Case 3: Reasoning followed by a final answer
def test_case_03_reasoning_followed_by_final_answer():
    flt = StreamingThinkingFilter()
    chunks = ["<think>analyzing query</think>", "Hello! How can I assist you?"]
    result = run_stream(flt, chunks)
    assert result == "Hello! How can I assist you?"
    assert strip_thinking_tags("<think>analyzing query</think>Hello! How can I assist you?") == "Hello! How can I assist you?"


# Case 4: Multiple reasoning blocks
def test_case_04_multiple_reasoning_blocks():
    flt = StreamingThinkingFilter()
    chunks = [
        "<think>thought 1</think>",
        "Part A. ",
        "<think>thought 2</think>",
        "Part B.",
    ]
    result = run_stream(flt, chunks)
    assert result == "Part A. Part B."
    raw = "<think>thought 1</think>Part A. <think>thought 2</think>Part B."
    assert strip_thinking_tags(raw) == "Part A. Part B."


# Case 5: Opening tag split across chunks
def test_case_05_opening_tag_split_across_chunks():
    flt = StreamingThinkingFilter()
    chunks = ["Preliminary. <t", "h", "ink>pondering</think>Final answer."]
    result = run_stream(flt, chunks)
    assert result == "Preliminary. Final answer."


# Case 6: Closing tag split across chunks
def test_case_06_closing_tag_split_across_chunks():
    flt = StreamingThinkingFilter()
    chunks = ["<think>pondering", "</th", "ink>", "Output."]
    result = run_stream(flt, chunks)
    assert result == "Output."


# Case 7: Tags with surrounding whitespace
def test_case_07_tags_with_surrounding_whitespace():
    flt = StreamingThinkingFilter()
    chunks = ["   \n<think>\n  deep internal thought  \n</think>\n\nResult text."]
    result = run_stream(flt, chunks)
    assert "deep internal thought" not in result
    assert "Result text." in result
    cleaned = strip_thinking_tags("   \n<think>\n  deep internal thought  \n</think>\n\nResult text.")
    assert cleaned == "Result text."


# Case 8: Empty reasoning blocks
def test_case_08_empty_reasoning_blocks():
    flt = StreamingThinkingFilter()
    chunks = ["Before<think></think>After"]
    result = run_stream(flt, chunks)
    assert result == "BeforeAfter"
    assert strip_thinking_tags("Before<think></think>After") == "BeforeAfter"


# Case 9: Unfinished reasoning block at stream termination
def test_case_09_unfinished_reasoning_block_at_stream_end():
    flt = StreamingThinkingFilter()
    chunks = ["Visible start. ", "<think>Unfinished thoughts that cut off abruptly"]
    result = run_stream(flt, chunks)
    assert result == "Visible start. "
    assert "Unfinished thoughts" not in result
    assert strip_thinking_tags("Visible start. <think>Unfinished thoughts") == "Visible start."


# Case 10: Malformed or nested tags
def test_case_10_malformed_or_nested_tags():
    flt = StreamingThinkingFilter()
    chunks = ["<think><think>nested thought</think></think>Clean output."]
    result = run_stream(flt, chunks)
    assert "nested thought" not in result
    assert "Clean output." in result
    assert "</think>" not in result

    # Also test orphan closing tag outside thinking
    flt2 = StreamingThinkingFilter()
    result2 = run_stream(flt2, ["Hello </think>world"])
    assert "</think>" not in result2
    assert "Hello world" in result2.strip() or "Hello  world" in result2.strip() or "Hello" in result2


# Case 11: Uppercase or unexpected tag variants
def test_case_11_uppercase_or_unexpected_tag_variants():
    flt = StreamingThinkingFilter()
    chunks = ["<THINK>Reasoning in upper case</THINK>Upper answer.", "<Think>Title case</Think>Title answer."]
    result = run_stream(flt, chunks)
    assert "Reasoning in upper case" not in result
    assert "Title case" not in result
    assert "Upper answer." in result
    assert "Title answer." in result

    assert strip_thinking_tags("<THINK>SHOUTING</THINK>Calm") == "Calm"
    assert strip_thinking_tags('<think type="scratchpad">Notes</think>Done') == "Done"


# Case 12: Literal tag-like text appearing in an answer
def test_case_12_literal_tag_like_text():
    flt = StreamingThinkingFilter()
    chunks = [
        "In math, 5 < 10 and 10 > 2. ",
        "Also check <thing> and <th if needed.",
    ]
    result = run_stream(flt, chunks)
    assert "5 < 10 and 10 > 2." in result
    assert "<thing>" in result
    assert "<th" in result


# Case 13: Cancellation while filter is inside a reasoning block
def test_case_13_cancellation_inside_reasoning_block():
    flt = StreamingThinkingFilter()
    # Stream starts, emits initial text
    assert flt.process_chunk("Start. ") == "Start. "
    # Model enters thinking
    assert flt.process_chunk("<think>Generating complex plan step 1...") == ""
    assert flt.process_chunk("Step 2...") == ""
    # User clicks 'Stop' / cancellation triggers
    flt.reset()
    assert flt._in_thinking is False
    assert flt._buffer == ""

    # Next generation starts fresh
    assert flt.process_chunk("Fresh new response") == "Fresh new response"
    assert flt.flush() == ""


# Case 14: Final answer begins in the same chunk closing the reasoning block
def test_case_14_answer_in_same_chunk_closing_reasoning():
    flt = StreamingThinkingFilter()
    chunks = [
        "<think>deep thought",
        " conclusion</think>Here is the exact solution!",
    ]
    result = run_stream(flt, chunks)
    assert result == "Here is the exact solution!"
    assert "conclusion" not in result
