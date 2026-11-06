"""Memory Manager — Short-Term, Long-Term, and Summary Persistence (Phase 10).

Implements:
- 10.1 Three memory layers (Short-term context, Long-term facts, Summaries)
- 10.2 SQLite database with FTS5 full-text indexing
- 10.3 Automatic memory extraction heuristics & controls
- 10.4 Query-based memory retrieval & context ranking
- 10.5 Intelligent memory update & contradiction avoidance
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from app.memory.database import DatabaseManager
from app.memory.models import ConversationSummary, Memory
from app.utils.logger import get_logger

logger = get_logger(__name__)

VALID_CATEGORIES = {
    "preference",
    "project",
    "goal",
    "learning",
    "interest",
    "fact",
    "general",
    "custom",
}


def _clean_fts_query(query: str) -> str:
    """Sanitize user query for SQLite FTS5 MATCH expression."""
    # Strip special FTS5 operators/characters
    cleaned = re.sub(r'["*^():{}]', ' ', query)
    tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 1]
    if not tokens:
        return ""
    # Use OR across tokens or prefix match for flexibility
    return " OR ".join(f'"{t}"*' for t in tokens)


class MemoryManager:
    """Coordinates long-term memory extraction, persistence, FTS5 retrieval, and updates."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        db_path: Optional[Path | str] = None,
    ) -> None:
        if db_manager is not None:
            self.db = db_manager
        elif db_path is not None:
            self.db = DatabaseManager(db_path=db_path)
        else:
            self.db = DatabaseManager()
        self._lock = threading.Lock()

    # ─── 10.2 Memory CRUD ──────────────────────────────────────────────

    def add_memory(
        self,
        content: str,
        category: str = "fact",
        source_conv_id: Optional[str] = None,
    ) -> Memory:
        """Store a new long-term memory item."""
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("Memory content cannot be empty.")

        cat = category.lower().strip()
        if cat not in VALID_CATEGORIES:
            cat = "fact"

        mem_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()

        with self._lock:
            conn = self.db.get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO memories (id, category, content, source_conversation_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (mem_id, cat, cleaned, source_conv_id, now, now),
                )
                try:
                    conn.execute(
                        """
                        INSERT INTO memories_fts (id, category, content)
                        VALUES (?, ?, ?);
                        """,
                        (mem_id, cat, cleaned),
                    )
                except sqlite3.OperationalError:
                    pass

        logger.info("Saved memory [%s]: '%s' (ID: %s)", cat, cleaned, mem_id)
        return Memory(
            id=mem_id,
            category=cat,
            content=cleaned,
            source_conversation_id=source_conv_id,
            created_at=now,
            updated_at=now,
        )

    def store_memory(
        self,
        category: str = "fact",
        content: str = "",
        source_conversation_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Memory:
        """Store a long-term memory item (alias for add_memory with flexible argument ordering)."""
        if "content" in kwargs and not content:
            content = kwargs["content"]
        if "category" in kwargs:
            category = kwargs["category"]

        if category in VALID_CATEGORIES and content and content not in VALID_CATEGORIES:
            actual_cat = category
            actual_content = content
        elif content in VALID_CATEGORIES:
            actual_cat = content
            actual_content = category
        elif not content and category:
            actual_content = category
            actual_cat = "fact"
        else:
            actual_cat = category
            actual_content = content

        return self.add_memory(
            content=actual_content,
            category=actual_cat,
            source_conv_id=source_conversation_id,
        )

    def update_memory(
        self,
        memory_id: str,
        content: str,
        category: Optional[str] = None,
    ) -> Optional[Memory]:
        """Update existing memory content and/or category."""
        cleaned = content.strip()
        if not cleaned:
            return None

        now = datetime.now().isoformat()

        with self._lock:
            conn = self.db.get_connection()
            with conn:
                existing = conn.execute(
                    "SELECT category, source_conversation_id, created_at FROM memories WHERE id = ?;",
                    (memory_id,),
                ).fetchone()

                if not existing:
                    return None

                cat = category.lower().strip() if category else existing["category"]
                if cat not in VALID_CATEGORIES:
                    cat = existing["category"]

                conn.execute(
                    """
                    UPDATE memories 
                    SET content = ?, category = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (cleaned, cat, now, memory_id),
                )

                try:
                    conn.execute("DELETE FROM memories_fts WHERE id = ?;", (memory_id,))
                    conn.execute(
                        "INSERT INTO memories_fts (id, category, content) VALUES (?, ?, ?);",
                        (memory_id, cat, cleaned),
                    )
                except sqlite3.OperationalError:
                    pass

        logger.info("Updated memory %s -> [%s]: '%s'", memory_id, cat, cleaned)
        return Memory(
            id=memory_id,
            category=cat,
            content=cleaned,
            source_conversation_id=existing["source_conversation_id"],
            created_at=existing["created_at"],
            updated_at=now,
        )

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        with self._lock:
            conn = self.db.get_connection()
            with conn:
                cursor = conn.execute("DELETE FROM memories WHERE id = ?;", (memory_id,))
                deleted = cursor.rowcount > 0
                if deleted:
                    try:
                        conn.execute("DELETE FROM memories_fts WHERE id = ?;", (memory_id,))
                    except sqlite3.OperationalError:
                        pass

        if deleted:
            logger.info("Deleted memory %s", memory_id)
        return deleted

    def clear_all_memories(self) -> int:
        """Clear all stored long-term memories."""
        with self._lock:
            conn = self.db.get_connection()
            with conn:
                count = conn.execute("DELETE FROM memories;").rowcount
                try:
                    conn.execute("DELETE FROM memories_fts;")
                except sqlite3.OperationalError:
                    pass

        logger.info("Cleared all %d memories.", count)
        return count

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Fetch a single memory item by ID."""
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT id, category, content, source_conversation_id, created_at, updated_at FROM memories WHERE id = ?;",
            (memory_id,),
        ).fetchone()
        if not row:
            return None
        return Memory(
            id=row["id"],
            category=row["category"],
            content=row["content"],
            source_conversation_id=row["source_conversation_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_memories(self, category: Optional[str] = None, limit: int = 100) -> List[Memory]:
        """List stored memories ordered by most recent."""
        conn = self.db.get_connection()
        if category:
            rows = conn.execute(
                """
                SELECT id, category, content, source_conversation_id, created_at, updated_at 
                FROM memories 
                WHERE category = ?
                ORDER BY updated_at DESC LIMIT ?;
                """,
                (category.lower(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, category, content, source_conversation_id, created_at, updated_at 
                FROM memories 
                ORDER BY updated_at DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()

        return [
            Memory(
                id=r["id"],
                category=r["category"],
                content=r["content"],
                source_conversation_id=r["source_conversation_id"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get_memory_count(self) -> int:
        """Return total count of stored long-term memories."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT COUNT(*) as count FROM memories;").fetchone()
        return int(row["count"]) if row else 0

    def get_all_memories(self, limit: int = 100) -> List[Memory]:
        """Fetch all stored memories (alias for list_memories)."""
        return self.list_memories(limit=limit)

    # ─── 10.4 Retrieval with SQLite FTS5 ───────────────────────────────

    def search_memories(self, query: str, limit: int = 5) -> List[Memory]:
        """Search long-term memories using FTS5 with fallback to LIKE search."""
        cleaned = query.strip()
        if not cleaned:
            return []

        conn = self.db.get_connection()
        fts_expr = _clean_fts_query(cleaned)
        memories: List[Memory] = []

        if fts_expr:
            try:
                rows = conn.execute(
                    """
                    SELECT m.id, m.category, m.content, m.source_conversation_id, m.created_at, m.updated_at
                    FROM memories_fts f
                    JOIN memories m ON m.id = f.id
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?;
                    """,
                    (fts_expr, limit),
                ).fetchall()
                memories = [
                    Memory(
                        id=r["id"],
                        category=r["category"],
                        content=r["content"],
                        source_conversation_id=r["source_conversation_id"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                    )
                    for r in rows
                ]
            except sqlite3.OperationalError:
                pass

        # Fallback to standard LIKE if FTS produced 0 results
        if not memories:
            tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 2]
            if tokens:
                clauses = " OR ".join("content LIKE ?" for _ in tokens)
                params = [f"%{t}%" for t in tokens] + [limit]
                rows = conn.execute(
                    f"""
                    SELECT id, category, content, source_conversation_id, created_at, updated_at
                    FROM memories
                    WHERE {clauses}
                    ORDER BY updated_at DESC
                    LIMIT ?;
                    """,
                    params,
                ).fetchall()
                memories = [
                    Memory(
                        id=r["id"],
                        category=r["category"],
                        content=r["content"],
                        source_conversation_id=r["source_conversation_id"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                    )
                    for r in rows
                ]

        return memories

    # ─── 10.1 & 10.2 Conversation Summaries ────────────────────────────

    def add_summary(self, conversation_id: str, summary: str) -> ConversationSummary:
        """Store a compact summary of a conversation session."""
        cleaned = summary.strip()
        summary_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()

        with self._lock:
            conn = self.db.get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO conversation_summaries (id, conversation_id, summary, created_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (summary_id, conversation_id, cleaned, now),
                )
                try:
                    conn.execute(
                        """
                        INSERT INTO summaries_fts (id, conversation_id, summary)
                        VALUES (?, ?, ?);
                        """,
                        (summary_id, conversation_id, cleaned),
                    )
                except sqlite3.OperationalError:
                    pass

        logger.info("Saved conversation summary for %s: '%s'", conversation_id, cleaned[:50])
        return ConversationSummary(
            id=summary_id,
            conversation_id=conversation_id,
            summary=cleaned,
            created_at=now,
        )

    def store_summary(self, conversation_id: str, summary: str) -> ConversationSummary:
        """Store a compact summary of a conversation session (alias for add_summary)."""
        return self.add_summary(conversation_id=conversation_id, summary=summary)

    def get_summaries(self, conversation_id: Optional[str] = None, limit: int = 5) -> List[ConversationSummary]:
        """Fetch past conversation summaries."""
        conn = self.db.get_connection()
        if conversation_id:
            rows = conn.execute(
                """
                SELECT id, conversation_id, summary, created_at
                FROM conversation_summaries
                WHERE conversation_id = ?
                ORDER BY created_at DESC LIMIT ?;
                """,
                (conversation_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, conversation_id, summary, created_at
                FROM conversation_summaries
                ORDER BY created_at DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()

        return [
            ConversationSummary(
                id=r["id"],
                conversation_id=r["conversation_id"],
                summary=r["summary"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_summaries_for_conversation(self, conversation_id: str, limit: int = 5) -> List[ConversationSummary]:
        """Fetch summaries for a specific conversation session."""
        return self.get_summaries(conversation_id=conversation_id, limit=limit)

    def search_summaries(self, query: str, limit: int = 3) -> List[ConversationSummary]:
        """Search past summaries via FTS5 or LIKE."""
        cleaned = query.strip()
        if not cleaned:
            return []

        conn = self.db.get_connection()
        fts_expr = _clean_fts_query(cleaned)
        summaries: List[ConversationSummary] = []

        if fts_expr:
            try:
                rows = conn.execute(
                    """
                    SELECT s.id, s.conversation_id, s.summary, s.created_at
                    FROM summaries_fts f
                    JOIN conversation_summaries s ON s.id = f.id
                    WHERE summaries_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?;
                    """,
                    (fts_expr, limit),
                ).fetchall()
                summaries = [
                    ConversationSummary(
                        id=r["id"],
                        conversation_id=r["conversation_id"],
                        summary=r["summary"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
            except sqlite3.OperationalError:
                pass

        if not summaries:
            tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 2]
            if tokens:
                clauses = " OR ".join("summary LIKE ?" for _ in tokens)
                params = [f"%{t}%" for t in tokens] + [limit]
                rows = conn.execute(
                    f"""
                    SELECT id, conversation_id, summary, created_at
                    FROM conversation_summaries
                    WHERE {clauses}
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    params,
                ).fetchall()
                summaries = [
                    ConversationSummary(
                        id=r["id"],
                        conversation_id=r["conversation_id"],
                        summary=r["summary"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]

        return summaries

    # ─── 10.5 Intelligent Memory Update & Contradiction Resolution ────

    def store_or_update_memory(
        self,
        content: str = "",
        category: str = "fact",
        source_conv_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Memory:
        """Store new memory or update existing memory if superseding/contradicting."""
        if "content" in kwargs and not content:
            content = kwargs["content"]
        if "category" in kwargs:
            category = kwargs["category"]

        # Handle potential parameter order swapping
        if category in VALID_CATEGORIES and content and content not in VALID_CATEGORIES:
            cat = category
            cleaned = content.strip()
        elif content in VALID_CATEGORIES:
            cat = content
            cleaned = category.strip()
        else:
            cat = category
            cleaned = content.strip()

        cat = cat.lower().strip()
        if cat not in VALID_CATEGORIES:
            cat = "fact"

        # Check existing memories in the same category
        existing_memories = self.list_memories(category=cat, limit=50)

        # Extract core keywords from incoming content
        content_tokens = set(re.findall(r"\b\w{3,}\b", cleaned.lower()))

        best_match: Optional[Memory] = None
        highest_overlap = 0

        for mem in existing_memories:
            mem_tokens = set(re.findall(r"\b\w{3,}\b", mem.content.lower()))
            overlap = len(content_tokens.intersection(mem_tokens))

            # Heuristics for direct contradictions / attribute updates:
            # e.g., "favorite color is blue" vs "favorite color is green" -> overlap on ("favorite", "color")
            # e.g., "name is Alex" vs "call me Gaurav"
            # e.g., "project is desktop companion" vs "project is desktop friend"
            is_preference_override = (
                cat == "preference"
                and any(kw in content_tokens and kw in mem_tokens for kw in ["color", "food", "name", "prefer", "like", "favorite"])
            )
            is_goal_or_project_override = (
                cat in ("goal", "learning", "project")
                and overlap >= 2
            )

            if is_preference_override or is_goal_or_project_override or overlap >= 3:
                if overlap > highest_overlap:
                    highest_overlap = overlap
                    best_match = mem

        if best_match:
            logger.info(
                "Updating existing memory '%s' (ID %s) with new info '%s' to resolve contradiction.",
                best_match.content,
                best_match.id,
                cleaned,
            )
            updated = self.update_memory(best_match.id, cleaned, category=cat)
            return updated if updated else best_match

        return self.add_memory(cleaned, category=cat, source_conv_id=source_conv_id)

    # ─── 10.3 Memory Extraction Heuristics ────────────────────────────

    def extract_memories_from_text(
        self,
        user_text: str,
        source_conv_id: Optional[str] = None,
    ) -> List[Memory]:
        """Analyze user text and extract important preferences, goals, projects, and facts."""
        text = user_text.strip()
        if not text:
            return []

        extracted: List[Memory] = []

        patterns: List[Tuple[str, str, int]] = [
            # Explicit request: "remember that ...", "remember: ..."
            (r"(?:please\s+)?remember(?:\s+that|:)\s+(.+)", "fact", 1),
            (r"(?:don't\s+forget(?:\s+that)?)\s+(.+)", "fact", 1),
            # Preference: "I prefer X over Y", "I like X", "My favorite X is Y", "Call me X"
            (r"(?:call\s+me|my\s+name\s+is)\s+([A-Za-z]+)", "preference", 0),
            (r"(?:my\s+favorite\s+\w+\s+is\s+[^.,!?]+)", "preference", 0),
            (r"(?:i\s+prefer\s+[^.,!?]+)", "preference", 0),
            (r"(?:i\s+(?:really\s+)?(?:like|dislike|hate)\s+[^.,!?]+)", "preference", 0),
            # Projects: "I am working on X", "I'm building X", "My project is X"
            (r"(?:i\s+am|i'm)\s+(?:working\s+on|building|developing|creating)\s+([^.,!?]+)", "project", 0),
            (r"(?:my\s+project\s+is\s+[^.,!?]+)", "project", 0),
            # Learning goals: "I am learning X", "My goal is to learn X"
            (r"(?:i\s+am|i'm)\s+(?:currently\s+|now\s+)?(?:learning|studying)\s+([^.,!?]+)", "learning", 0),
            (r"(?:my\s+goal\s+is\s+to\s+[^.,!?]+)", "learning", 0),
            # Interests: "I love X", "I enjoy X"
            (r"(?:i\s+(?:love|enjoy)\s+[^.,!?]+)", "interest", 0),
        ]

        for pattern, category, group_idx in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for m in matches:
                matched_snippet = m.group(group_idx).strip() if group_idx > 0 else m.group(0).strip()
                # Clean tail punctuation
                matched_snippet = matched_snippet.rstrip(".,;!?")
                if len(matched_snippet) >= 4:
                    mem = self.store_or_update_memory(
                        content=matched_snippet,
                        category=category,
                        source_conv_id=source_conv_id,
                    )
                    extracted.append(mem)

        return extracted
