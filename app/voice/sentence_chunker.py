"""Sentence-Based Text-to-Speech Chunking Engine.

Splits streamed LLM text tokens into clean, natural sentences or clauses for incremental
speech synthesis, avoiding unnatural breaks on abbreviations or numbers. (Phase 8.5)
"""

from __future__ import annotations

import re
from typing import List

# Common abbreviations that should not trigger sentence boundaries
ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "vs.", "etc.", "e.g.", "i.e.", "u.s.", "u.k.", "a.i.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.", "sep.", "oct.", "nov.", "dec.",
    "approx.", "dept.", "est.", "fig.", "inc.", "ltd.", "no.", "vol.",
    "st.", "rd.", "ave.", "blvd.", "gen.", "gov.", "sgt.", "capt.", "col.", "lt.", "rep.", "sen.",
    "ph.d.", "m.d.", "b.a.", "m.a.", "b.s.", "m.s.", "co.", "corp.", "univ.", "assn.",
}

# Regex to check for terminal punctuation followed by optional quotes/parens and whitespace or end of string
# Supports Western punctuation (.!?) and Devanagari/Hindi purna viram (।)
TERMINAL_PUNCT_PATTERN = re.compile(r'([.!?।]+[\'\"”’»\)]*)(\s+|$)')


class SentenceChunker:
    """Collects streaming tokens and yields ready-to-synthesize sentence segments."""

    def __init__(self, min_chars: int = 12, max_chars: int = 140) -> None:
        """Initialize sentence chunker.

        Args:
            min_chars: Minimum character length before splitting on minor punctuation.
            max_chars: Maximum character length threshold before splitting on clauses/spaces.
        """
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buffer: str = ""
        self._is_first_chunk: bool = True

    @classmethod
    def split_text(cls, text: str) -> List[str]:
        """Split a complete text string into natural sentences (Phase 2)."""
        if not text or not text.strip():
            return []
        chunker = cls()
        sentences = chunker.add_chunk(text)
        sentences.extend(chunker.flush())
        return sentences if sentences else [text.strip()]

    def reset(self) -> None:
        """Clear internal buffer for a new turn."""
        self._buffer = ""
        self._is_first_chunk = True

    def add_chunk(self, token: str) -> List[str]:
        """Add a token chunk from the LLM stream and return any completed sentences.

        Args:
            token: Incoming token string.

        Returns:
            List of completed sentence chunks ready for TTS synthesis.
        """
        if not token:
            return []

        self._buffer += token
        ready_sentences: List[str] = []

        while True:
            sentence = self._extract_next_sentence()
            if sentence:
                cleaned = sentence.strip()
                if cleaned:
                    ready_sentences.append(cleaned)
            else:
                break

        return ready_sentences

    def flush(self) -> List[str]:
        """Flush and return any remaining text in the buffer at stream completion.

        Returns:
            List of final sentence chunks.
        """
        remaining = self._buffer.strip()
        self._buffer = ""
        self._is_first_chunk = True
        if remaining:
            return [remaining]
        return []

    def _extract_next_sentence(self) -> str | None:
        """Attempt to extract the first complete sentence from the buffer."""
        if not self._buffer:
            return None

        # Look for terminal punctuation match
        for match in TERMINAL_PUNCT_PATTERN.finditer(self._buffer):
            punct_end = match.end(1)
            candidate = self._buffer[:punct_end].strip()

            # 1. Skip if this punctuation belongs to a known abbreviation
            last_word = candidate.split()[-1].lower() if candidate.split() else ""
            if last_word in ABBREVIATIONS:
                continue

            # 2. Skip if it's a decimal number like "3.14" or "$10.50"
            if self._is_decimal_number(self._buffer, match.start(1)):
                continue

            # 3. Skip numbered list prefixes like "1." or "Step 1." if not full sentence
            if re.match(r'^\d+\.?$', last_word) and len(candidate.split()) <= 2:
                continue

            # 4. If punctuation is found and candidate meets minimum size or is terminal exclamation/question
            is_strong_punct = any(p in candidate for p in ("!", "?", "।"))
            if len(candidate) >= self.min_chars or is_strong_punct or (len(candidate.split()) >= 2):
                # If candidate is exceptionally long (> max_chars), segment on inner clause punctuation (Phase 2 Requirement 5)
                if len(candidate) > self.max_chars:
                    clause_match = None
                    for cm in re.finditer(r'([,;:—])\s+', candidate[:self.max_chars]):
                        if cm.end() >= self.min_chars:
                            clause_match = cm
                    if clause_match:
                        split_idx = clause_match.end()
                        sentence = candidate[:split_idx].strip()
                        raw_prefix = self._buffer[:punct_end]
                        leading_offset = len(raw_prefix) - len(raw_prefix.lstrip())
                        self._buffer = self._buffer[leading_offset + split_idx:]
                        self._is_first_chunk = False
                        return sentence

                # Valid sentence boundary found!
                sentence = candidate
                # Advance buffer past the match
                self._buffer = self._buffer[match.end():]
                self._is_first_chunk = False
                return sentence

        # Low-latency first-clause extraction: stream first audible chunk quickly (<500ms)
        if self._is_first_chunk and len(self._buffer) >= 12:
            clause_match = re.search(r'([,;:—])\s+', self._buffer)
            if clause_match:
                split_idx = clause_match.end()
                candidate = self._buffer[:split_idx].strip()
                if len(candidate) >= 4:
                    self._buffer = self._buffer[split_idx:]
                    self._is_first_chunk = False
                    return candidate

        # 4. Fallback for runaway long sentences without punctuation
        if len(self._buffer) >= self.max_chars:
            # Try splitting on clause punctuation: comma, semicolon, colon, dash
            clause_match = re.search(r'([,;:—])\s+', self._buffer[self.min_chars:])
            if clause_match:
                split_idx = self.min_chars + clause_match.end()
                sentence = self._buffer[:split_idx].strip()
                self._buffer = self._buffer[split_idx:]
                self._is_first_chunk = False
                return sentence

            # Last resort: split at the last space before max_chars
            last_space = self._buffer[:self.max_chars].rfind(" ")
            if last_space > self.min_chars:
                sentence = self._buffer[:last_space].strip()
                self._buffer = self._buffer[last_space + 1:]
                self._is_first_chunk = False
                return sentence

        return None

    @staticmethod
    def _is_decimal_number(text: str, dot_index: int) -> bool:
        """Check if dot at dot_index is inside a number like '3.14'."""
        if dot_index <= 0 or dot_index >= len(text) - 1:
            return False
        prev_char = text[dot_index - 1]
        next_char = text[dot_index + 1]
        return prev_char.isdigit() and next_char.isdigit()
