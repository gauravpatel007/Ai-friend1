"""Internal reasoning / thinking tag filter.

Filters out internal chain-of-thought outputs (such as <think>...</think> tags or
Ollama message.thought fields) from models like Qwen3 and DeepSeek-R1, ensuring
only the natural assistant response is presented to the user.
"""

from __future__ import annotations

import re
from typing import List, Optional


def strip_thinking_tags(text: str) -> str:
    """Remove all <think>...</think> blocks and orphan thinking tags from completed text."""
    if not text:
        return ""
    # Remove complete think blocks (case-insensitive, multiline, attributes allowed)
    cleaned = re.sub(r"<think(?:\s[^>]*)?>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Clean unclosed <think> if any
    cleaned = re.sub(r"<think(?:\s[^>]*)?>.*$", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Clean any stray or orphan </think> tags
    cleaned = re.sub(r"</think\s*>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


class StreamingThinkingFilter:
    """Stateful streaming filter that suppresses internal reasoning tags in real time."""

    RE_OPEN = re.compile(r"<think(?:\s[^>]*)?>", re.IGNORECASE)
    RE_CLOSE = re.compile(r"</think\s*>", re.IGNORECASE)

    # Valid prefixes for opening/closing tags for chunk boundary handling
    OPEN_TAG_CANONICAL = "<think>"
    CLOSE_TAG_CANONICAL = "</think>"

    def __init__(self) -> None:
        self._nesting_depth = 0
        self._buffer = ""

    @property
    def _in_thinking(self) -> bool:
        return self._nesting_depth > 0

    @_in_thinking.setter
    def _in_thinking(self, val: bool) -> None:
        self._nesting_depth = 1 if val else 0

    def _is_potential_tag_prefix(self, candidate: str, inside_thinking: bool) -> bool:
        """Check if candidate text ending a chunk could be the beginning of a tag."""
        cand_lower = candidate.lower()
        if cand_lower == "<":
            return True
        if inside_thinking:
            if "<think".startswith(cand_lower) or "</think".startswith(cand_lower):
                return True
            if cand_lower.startswith("<think") and ">" not in cand_lower:
                return True
        else:
            if "<think".startswith(cand_lower) or "</think".startswith(cand_lower):
                return True
            if cand_lower.startswith("<think") and ">" not in cand_lower:
                return True
        return False

    def process_chunk(self, chunk: str) -> str:
        """Process incoming text chunk and return only user-visible text."""
        if not chunk:
            return ""

        self._buffer += chunk
        output_parts: List[str] = []

        while self._buffer:
            if not self._in_thinking:
                m_open = self.RE_OPEN.search(self._buffer)
                m_close = self.RE_CLOSE.search(self._buffer)

                # Find earliest tag match
                first_tag = None
                tag_type = None
                if m_open and m_close:
                    if m_open.start() <= m_close.start():
                        first_tag, tag_type = m_open, "open"
                    else:
                        first_tag, tag_type = m_close, "close"
                elif m_open:
                    first_tag, tag_type = m_open, "open"
                elif m_close:
                    first_tag, tag_type = m_close, "close"

                if first_tag:
                    # Text before tag is user visible
                    if first_tag.start() > 0:
                        output_parts.append(self._buffer[:first_tag.start()])
                    self._buffer = self._buffer[first_tag.end():]
                    if tag_type == "open":
                        self._nesting_depth = 1
                    # If stray closing tag outside thinking, discard it and remain not in thinking
                else:
                    # No complete tag. Check if buffer ends with a potential opening or closing tag prefix
                    last_lt = self._buffer.rfind("<")
                    if last_lt != -1:
                        candidate = self._buffer[last_lt:]
                        if self._is_potential_tag_prefix(candidate, inside_thinking=False):
                            emit_len = last_lt
                            if emit_len > 0:
                                output_parts.append(self._buffer[:emit_len])
                                self._buffer = self._buffer[emit_len:]
                            break
                    # Entire buffer is visible text
                    output_parts.append(self._buffer)
                    self._buffer = ""
                    break
            else:
                # Inside thinking: search for close tag or nested open tag
                m_open = self.RE_OPEN.search(self._buffer)
                m_close = self.RE_CLOSE.search(self._buffer)

                first_tag = None
                tag_type = None
                if m_open and m_close:
                    if m_open.start() <= m_close.start():
                        first_tag, tag_type = m_open, "open"
                    else:
                        first_tag, tag_type = m_close, "close"
                elif m_open:
                    first_tag, tag_type = m_open, "open"
                elif m_close:
                    first_tag, tag_type = m_close, "close"

                if first_tag:
                    # Skip internal reasoning text before tag
                    self._buffer = self._buffer[first_tag.end():]
                    if tag_type == "open":
                        self._nesting_depth += 1
                    else:
                        self._nesting_depth = max(0, self._nesting_depth - 1)
                else:
                    # Look for potential prefix of close tag or nested open tag at end of buffer
                    last_lt = self._buffer.rfind("<")
                    if last_lt != -1:
                        candidate = self._buffer[last_lt:]
                        if self._is_potential_tag_prefix(candidate, inside_thinking=True):
                            self._buffer = self._buffer[last_lt:]
                            break
                    # All current buffer is internal thought, discard
                    self._buffer = ""
                    break

        return "".join(output_parts)

    def flush(self) -> str:
        """Flush any remaining buffered text when stream concludes."""
        if not self._in_thinking and self._buffer:
            remaining = self._buffer
            self._buffer = ""
            return remaining
        self._buffer = ""
        return ""

    def reset(self) -> None:
        """Reset internal buffer and thinking state."""
        self._nesting_depth = 0
        self._buffer = ""

    @classmethod
    def filter(cls, text: str) -> str:
        """Synchronously filter out thinking tags from a full text string."""
        return strip_thinking_tags(text)

    def filter_text(self, text: str) -> str:
        """Alias for synchronous filter()."""
        return self.filter(text)

    def __call__(self, text: str) -> str:
        """Allow filter instances to be used directly as a callable."""
        return self.filter(text)


ThinkingFilter = StreamingThinkingFilter
