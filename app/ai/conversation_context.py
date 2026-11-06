"""Conversation Context and History Budget Management.

Maintains multi-turn conversational dialogue with system instructions,
turn-budget constraints, memory injection hooks, and sliding-window pruning.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

DEFAULT_MAX_TURNS = 20
DEFAULT_TOKEN_BUDGET = 8192


def estimate_token_count(text: str) -> int:
    """Rough token estimation heuristic (~4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class ConversationContext:
    """Manages conversational history, budgeting, and message payload construction."""

    def __init__(
        self,
        system_prompt: str = "",
        max_turns: int = DEFAULT_MAX_TURNS,
        max_token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.max_token_budget = max_token_budget
        self._history: List[Dict[str, str]] = []
        self._injected_memories: List[str] = []
        self._injected_summaries: List[str] = []
        self._injected_feedback_guidance: Optional[str] = None

    # ─── System & Memory Controls ─────────────────────────────────────

    def set_system_prompt(self, prompt: str) -> None:
        """Update system prompt."""
        self.system_prompt = prompt

    def inject_memories(self, memories: List[str]) -> None:
        """Set relevant long-term memory snippets to be included in context (Phase 10.4)."""
        self._injected_memories = [m.strip() for m in memories if m and m.strip()]

    def clear_memories(self) -> None:
        """Clear active memory injections."""
        self._injected_memories.clear()

    def inject_summaries(self, summaries: List[str]) -> None:
        """Set compact summaries of older conversation sessions (Phase 10.1)."""
        self._injected_summaries = [s.strip() for s in summaries if s and s.strip()]

    def clear_summaries(self) -> None:
        """Clear active summary injections."""
        self._injected_summaries.clear()

    def inject_feedback_guidance(self, guidance: str) -> None:
        """Inject learned user feedback guidance instructions (Like/Dislike style adaptation)."""
        self._injected_feedback_guidance = guidance.strip() if guidance else None

    def clear_feedback_guidance(self) -> None:
        """Clear active feedback guidance injection."""
        self._injected_feedback_guidance = None

    # ─── Message Appending ─────────────────────────────────────────────

    def add_user_message(self, content: str) -> None:
        """Append a user utterance to conversation history."""
        cleaned = content.strip()
        if cleaned:
            # Prevent duplicate consecutive identical user messages
            if self._history and self._history[-1].get("role") == "user" and self._history[-1].get("content") == cleaned:
                return
            self._history.append({"role": "user", "content": cleaned})
            self._prune_history()

    def add_assistant_message(self, content: str) -> None:
        """Append an AI assistant response to conversation history."""
        cleaned = content.strip()
        if cleaned:
            # Prevent duplicate consecutive identical assistant messages
            if self._history and self._history[-1].get("role") == "assistant" and self._history[-1].get("content") == cleaned:
                return
            self._history.append({"role": "assistant", "content": cleaned})
            self._prune_history()

    def record_interrupted_turn(self, actually_spoken_text: str) -> None:
        """Record what was actually spoken by the assistant before an interruption (Phase 4)."""
        spoken = actually_spoken_text.strip()
        if not spoken:
            return
        formatted = f"{spoken} [interrupted]"
        if self._history and self._history[-1].get("role") == "assistant":
            self._history[-1]["content"] = formatted
        else:
            self._history.append({"role": "assistant", "content": formatted})
            self._prune_history()

    def add_message(self, role: str, content: str) -> None:
        """Append a message with explicit role validation."""
        role_clean = role.strip().lower()
        if role_clean not in ("user", "assistant", "system"):
            raise ValueError(f"Invalid message role '{role}'. Expected 'user', 'assistant', or 'system'.")
        if role_clean == "user":
            self.add_user_message(content)
        elif role_clean == "assistant":
            self.add_assistant_message(content)
        else:
            cleaned = content.strip()
            if cleaned:
                self._history.append({"role": "system", "content": cleaned})
                self._prune_history()

    def clear(self) -> None:
        """Clear all conversation history (retaining system prompt)."""
        self._history.clear()
        self._injected_memories.clear()
        self._injected_feedback_guidance = None

    @property
    def history_length(self) -> int:
        """Number of messages currently stored in history."""
        return len(self._history)

    # ─── Budgeting & Pruning ──────────────────────────────────────────

    def _prune_history(self) -> None:
        """Prune older message pairs if turn limit or token budget is exceeded.

        Guarantees that pruned history always begins with a user turn, avoiding
        orphaned assistant responses at the start of conversation context.
        """
        # 1. Turn-based pruning (2 messages per turn)
        max_messages = self.max_turns * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]

        # 2. Token budget pruning
        system_tokens = estimate_token_count(self._build_system_content())
        available_budget = max(256, self.max_token_budget - system_tokens)

        total_tokens = sum(estimate_token_count(m["content"]) for m in self._history)
        while self._history and total_tokens > available_budget:
            # Drop the oldest message
            dropped = self._history.pop(0)
            total_tokens -= estimate_token_count(dropped["content"])

        # 3. Prompt integrity: ensure history always begins with a user turn
        if any(m.get("role") == "user" for m in self._history):
            while self._history and self._history[0].get("role") != "user":
                self._history.pop(0)

    def _build_system_content(self) -> str:
        """Combine system prompt with any active memories and conversation summaries."""
        sections: List[str] = []
        if self.system_prompt:
            sections.append(self.system_prompt)

        if self._injected_memories:
            mem_text = "\n".join(f"- {m}" for m in self._injected_memories)
            sections.append(f"Relevant memories about the user:\n{mem_text}")

        if self._injected_summaries:
            summary_text = "\n".join(f"- {s}" for s in self._injected_summaries)
            sections.append(f"Summaries of previous conversations:\n{summary_text}")

        if getattr(self, "_injected_feedback_guidance", None):
            sections.append(self._injected_feedback_guidance)

        return "\n\n".join(sections)

    # ─── Message Export for Ollama ────────────────────────────────────

    def get_messages(self) -> List[Dict[str, str]]:
        """Construct the complete message sequence ready for the inference engine."""
        self._prune_history()
        messages: List[Dict[str, str]] = []

        system_text = self._build_system_content()
        if system_text:
            messages.append({"role": "system", "content": system_text})

        # Append pruned conversation history with role verification
        for msg in self._history:
            role = msg.get("role", "")
            if role not in ("system", "user", "assistant"):
                continue
            messages.append({"role": role, "content": msg["content"]})

        return messages

    # ─── Serialization ────────────────────────────────────────────────

    def serialize(self) -> Dict[str, Any]:
        """Serialize current state for persistence."""
        return {
            "system_prompt": self.system_prompt,
            "max_turns": self.max_turns,
            "max_token_budget": self.max_token_budget,
            "history": copy.deepcopy(self._history),
            "memories": list(self._injected_memories),
            "summaries": list(self._injected_summaries),
        }

    def deserialize(self, data: Dict[str, Any]) -> None:
        """Restore conversation context from dictionary."""
        self.system_prompt = data.get("system_prompt", "")
        self.max_turns = int(data.get("max_turns", DEFAULT_MAX_TURNS))
        self.max_token_budget = int(data.get("max_token_budget", DEFAULT_TOKEN_BUDGET))
        raw_history = data.get("history", [])
        self._history = [
            {"role": m["role"], "content": m["content"]}
            for m in raw_history
            if isinstance(m, dict) and m.get("role") in ("user", "assistant", "system") and m.get("content")
        ]
        self._injected_memories = list(data.get("memories", []))
        self._injected_summaries = list(data.get("summaries", []))
        self._prune_history()
