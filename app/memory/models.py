"""Data models for conversations and messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Message:
    """Represents a single conversational turn."""

    id: Optional[int]
    conversation_id: str
    role: str           # "user", "assistant", "system"
    content: str
    created_at: str     # ISO format string
    status: str = "completed"  # "pending", "streaming", "completed", "error", "cancelled"
    feedback: Optional[str] = None  # None, "like", "dislike"


@dataclass
class Conversation:
    """Represents a conversational session containing dialogue turns."""

    id: str
    title: str
    created_at: str     # ISO format string
    updated_at: str     # ISO format string
    message_count: int = 0


@dataclass
class Memory:
    """Represents a long-term memory item (Phase 10.2)."""

    id: str
    category: str       # "preference", "project", "goal", "interest", "fact", "custom"
    content: str
    source_conversation_id: Optional[str]
    created_at: str     # ISO format string
    updated_at: str     # ISO format string


@dataclass
class ConversationSummary:
    """Represents a compact summary of a conversation session (Phase 10.1, 10.2)."""

    id: str
    conversation_id: str
    summary: str
    created_at: str     # ISO format string
