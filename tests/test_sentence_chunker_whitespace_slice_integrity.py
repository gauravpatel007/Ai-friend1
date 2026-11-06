"""Tests for SentenceChunker buffer slicing with leading whitespace (Bug #25).

Verifies that SentenceChunker._extract_next_sentence() correctly accounts for
leading whitespace when segmenting long sentences on clause punctuation,
preventing word truncation, mangling, and duplicated syllable artifacts.
"""

import pytest
from app.voice.sentence_chunker import SentenceChunker


def test_leading_whitespace_clause_split_does_not_mangle_next_chunk():
    """Bug #25: Leading whitespace must not cause buffer slicing offset error on clause split."""
    chunker = SentenceChunker(min_chars=12, max_chars=50)
    text = (
        "   \n\nSure, here is your summary of the topic, "
        "which continues for a very long time. Next sentence."
    )
    chunks = chunker.add_chunk(text)
    chunks.extend(chunker.flush())

    assert len(chunks) == 3
    assert chunks[0] == "Sure, here is your summary of the topic,"
    # Prior to fix, chunk[1] started with 'pic, which continues...'
    assert chunks[1] == "which continues for a very long time."
    assert not chunks[1].startswith("pic,")
    assert chunks[2] == "Next sentence."


def test_markdown_newlines_and_tabs_leading_offset():
    """Verify markdown-style newlines and indentation do not corrupt following clauses."""
    chunker = SentenceChunker(min_chars=15, max_chars=60)
    text = (
        "\n\n\t\tIndeed, I have processed your request thoroughly, "
        "and here are the key findings you asked for. All done!"
    )
    chunks = chunker.add_chunk(text)
    chunks.extend(chunker.flush())

    assert len(chunks) == 3
    assert chunks[0] == "Indeed, I have processed your request thoroughly,"
    assert chunks[1] == "and here are the key findings you asked for."
    assert not chunks[1].startswith("ghly,")
    assert chunks[2] == "All done!"


def test_no_leading_whitespace_baseline():
    """Ensure that sentences without leading whitespace continue to slice cleanly."""
    chunker = SentenceChunker(min_chars=12, max_chars=50)
    text = (
        "Sure, here is your summary of the topic, "
        "which continues for a very long time. Next sentence."
    )
    chunks = chunker.add_chunk(text)
    chunks.extend(chunker.flush())

    assert len(chunks) == 3
    assert chunks[0] == "Sure, here is your summary of the topic,"
    assert chunks[1] == "which continues for a very long time."
    assert chunks[2] == "Next sentence."


def test_streaming_token_arrival_with_leading_spaces():
    """Simulate token-by-token streaming from LLM with initial leading whitespace."""
    chunker = SentenceChunker(min_chars=12, max_chars=55)
    tokens = [
        " ", " \n\n", "Certainly", ",", " here", " is", " your", " detailed",
        " overview", " of", " the", " topic", ",", " which", " will", " answer",
        " your", " questions", " in", " full", ".", " Have", " a", " great", " day", "!"
    ]
    extracted = []
    for token in tokens:
        ready = chunker.add_chunk(token)
        extracted.extend(ready)
    extracted.extend(chunker.flush())

    assert len(extracted) == 4
    assert extracted[0] == "Certainly,"
    assert extracted[1] == "here is your detailed overview of the topic,"
    assert extracted[2] == "which will answer your questions in full."
    assert extracted[3] == "Have a great day!"
