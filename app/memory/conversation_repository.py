"""Conversation and Message Data Access Repository.

Encapsulates all database queries and transactions, providing high-level
methods for conversational lifecycle, pagination, and full-text message search.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from app.memory.database import DatabaseManager
from app.memory.models import Conversation, Message
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class ConversationRepository:
    """Repository handling all CRUD operations for conversations and message logs."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager()

    # ─── Conversation Operations ──────────────────────────────────────

    def create_conversation(self, title: Optional[str] = None) -> Conversation:
        """Create a new conversation session."""
        conv_id = str(uuid.uuid4())
        now = _now_iso()
        conv_title = (title or "New Chat").strip()

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?);
                """,
                (conv_id, conv_title, now, now),
            )

        logger.info("Created conversation %s ('%s')", conv_id, conv_title)
        return Conversation(id=conv_id, title=conv_title, created_at=now, updated_at=now, message_count=0)

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        """Fetch a conversation by ID."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
            WHERE c.id = ?;
            """,
            (conv_id,),
        ).fetchone()

        if not row:
            return None

        return Conversation(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            message_count=row["message_count"],
        )

    def list_conversations(self, limit: int = 50) -> List[Conversation]:
        """List recent conversations sorted by last update timestamp."""
        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
            ORDER BY c.updated_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

        return [
            Conversation(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                message_count=r["message_count"],
            )
            for r in rows
        ]

    def rename_conversation(self, conv_id: str, new_title: str) -> bool:
        """Update conversation title."""
        title = new_title.strip()
        if not title:
            return False

        conn = self.db.get_connection()
        with conn:
            cur = conn.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?;
                """,
                (title, _now_iso(), conv_id),
            )
            return cur.rowcount > 0

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation and all its associated messages."""
        conn = self.db.get_connection()
        with conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?;", (conv_id,))
            return cur.rowcount > 0

    # ─── Message Operations ───────────────────────────────────────────

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        status: str = "completed",
        feedback: Optional[str] = None,
    ) -> Message:
        """Insert a message and update conversation metadata."""
        role_clean = role.strip().lower()
        if role_clean not in ("user", "assistant", "system"):
            raise ValueError(f"Invalid message role '{role}'. Expected 'user', 'assistant', or 'system'.")

        if role_clean == "user" and not content.strip():
            raise ValueError("User message content cannot be empty.")

        now = _now_iso()
        conn = self.db.get_connection()
        with conn:
            # Prevent duplicate rapid user turn insertions:
            # Only reject if the very last message in the entire conversation is already that exact
            # user message AND no assistant response was ever recorded after it.
            # If the last message was from the assistant, always allow the user's new message.
            if role_clean == "user":
                last_row = conn.execute(
                    """
                    SELECT id, conversation_id, role, content, created_at, status, feedback
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT 1;
                    """,
                    (conversation_id,),
                ).fetchone()
                if last_row and last_row["role"] == "user" and last_row["content"] == content:
                    try:
                        last_ts = datetime.fromisoformat(last_row["created_at"]).timestamp()
                        now_ts = datetime.now(timezone.utc).timestamp()
                        if (now_ts - last_ts) < 4.0:
                            logger.warning(
                                "[DIAGNOSTIC] Duplicate request rejected: identical user message already added (#%d) with no assistant response yet.",
                                last_row["id"],
                            )
                            duplicate_msg = Message(
                                id=last_row["id"],
                                conversation_id=last_row["conversation_id"],
                                role=last_row["role"],
                                content=last_row["content"],
                                created_at=last_row["created_at"],
                                status=last_row["status"],
                                feedback=last_row["feedback"] if "feedback" in last_row.keys() else None,
                            )
                            setattr(duplicate_msg, "_is_duplicate", True)
                            return duplicate_msg
                    except Exception:
                        pass

            cur = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at, status, feedback)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (conversation_id, role_clean, content, now, status, feedback),
            )
            msg_id = cur.lastrowid

            if role_clean == "user":
                logger.info("[DIAGNOSTIC] User message accepted (id=%s).", msg_id)

            # Update conversation updated_at
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now, conversation_id),
            )

            # Auto-title conversation if this is the first user message and title is default
            if role_clean == "user":
                conv_row = conn.execute(
                    "SELECT title FROM conversations WHERE id = ?;",
                    (conversation_id,),
                ).fetchone()
                if conv_row and conv_row["title"] == "New Chat":
                    snippet = content.strip().replace("\n", " ")
                    auto_title = (snippet[:45] + "...") if len(snippet) > 45 else snippet
                    if auto_title:
                        conn.execute(
                            "UPDATE conversations SET title = ? WHERE id = ?;",
                            (auto_title, conversation_id),
                        )

        return Message(
            id=msg_id,
            conversation_id=conversation_id,
            role=role_clean,
            content=content,
            created_at=now,
            status=status,
            feedback=feedback,
        )

    def update_message_content(
        self,
        msg_id: int,
        content: str,
        status: str = "completed",
    ) -> bool:
        """Update content and status of an in-progress or completed message."""
        conn = self.db.get_connection()
        with conn:
            cur = conn.execute(
                """
                UPDATE messages
                SET content = ?, status = ?
                WHERE id = ?;
                """,
                (content, status, msg_id),
            )
            return cur.rowcount > 0

    def delete_message(self, msg_id: int) -> bool:
        """Delete an individual message and any associated feedback from database."""
        conn = self.db.get_connection()
        with conn:
            conn.execute("DELETE FROM message_feedback WHERE message_id = ?;", (msg_id,))
            cur = conn.execute("DELETE FROM messages WHERE id = ?;", (msg_id,))
            return cur.rowcount > 0

    def delete_message_pair(self, msg_id: int) -> List[int]:
        """Delete a message and its paired conversation turn from database.

        If msg_id is a user message: deletes msg_id and the subsequent assistant response.
        If msg_id is an assistant message: deletes msg_id and the preceding user message.
        Returns the list of deleted message IDs.
        """
        conn = self.db.get_connection()
        msg_row = conn.execute(
            "SELECT id, conversation_id, role FROM messages WHERE id = ?;",
            (msg_id,),
        ).fetchone()

        if not msg_row:
            return []

        conv_id = msg_row["conversation_id"]
        role = msg_row["role"]
        ids_to_delete = [msg_id]

        if role == "user":
            following_rows = conn.execute(
                """
                SELECT id, role FROM messages
                WHERE conversation_id = ? AND id > ?
                ORDER BY id ASC;
                """,
                (conv_id, msg_id),
            ).fetchall()
            for r in following_rows:
                if r["role"] == "assistant":
                    ids_to_delete.append(r["id"])
                else:
                    break

        elif role == "assistant":
            prev_row = conn.execute(
                """
                SELECT id, role FROM messages
                WHERE conversation_id = ? AND id < ?
                ORDER BY id DESC
                LIMIT 1;
                """,
                (conv_id, msg_id),
            ).fetchone()
            if prev_row and prev_row["role"] == "user":
                ids_to_delete.append(prev_row["id"])

        with conn:
            for mid in ids_to_delete:
                conn.execute("DELETE FROM message_feedback WHERE message_id = ?;", (mid,))
                conn.execute("DELETE FROM messages WHERE id = ?;", (mid,))

        logger.info("Deleted message pair from DB: %s (in conversation %s)", ids_to_delete, conv_id)
        return ids_to_delete

    def get_paired_user_message(self, assistant_msg_id: int) -> Optional[Message]:
        """Find the user prompt that generated this assistant message."""
        conn = self.db.get_connection()
        msg_row = conn.execute(
            "SELECT id, conversation_id, role FROM messages WHERE id = ?;",
            (assistant_msg_id,),
        ).fetchone()
        if not msg_row:
            return None

        conv_id = msg_row["conversation_id"]
        prev_row = conn.execute(
            """
            SELECT id, conversation_id, role, content, created_at, status, feedback
            FROM messages
            WHERE conversation_id = ? AND role = 'user' AND id < ?
            ORDER BY id DESC
            LIMIT 1;
            """,
            (conv_id, assistant_msg_id),
        ).fetchone()

        if not prev_row:
            return None

        return Message(
            id=prev_row["id"],
            conversation_id=prev_row["conversation_id"],
            role=prev_row["role"],
            content=prev_row["content"],
            created_at=prev_row["created_at"],
            status=prev_row["status"],
            feedback=prev_row["feedback"] if "feedback" in prev_row.keys() else None,
        )

    def get_paired_assistant_message(self, user_msg_id: int) -> Optional[Message]:
        """Find the assistant response generated for this user message."""
        conn = self.db.get_connection()
        msg_row = conn.execute(
            "SELECT id, conversation_id, role FROM messages WHERE id = ?;",
            (user_msg_id,),
        ).fetchone()
        if not msg_row:
            return None

        conv_id = msg_row["conversation_id"]
        next_row = conn.execute(
            """
            SELECT id, conversation_id, role, content, created_at, status, feedback
            FROM messages
            WHERE conversation_id = ? AND role = 'assistant' AND id > ?
            ORDER BY id ASC
            LIMIT 1;
            """,
            (conv_id, user_msg_id),
        ).fetchone()

        if not next_row:
            return None

        return Message(
            id=next_row["id"],
            conversation_id=next_row["conversation_id"],
            role=next_row["role"],
            content=next_row["content"],
            created_at=next_row["created_at"],
            status=next_row["status"],
            feedback=next_row["feedback"] if "feedback" in next_row.keys() else None,
        )

    def get_message(self, msg_id: int) -> Optional[Message]:
        """Fetch a single message by ID."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT id, conversation_id, role, content, created_at, status, feedback
            FROM messages
            WHERE id = ?;
            """,
            (msg_id,),
        ).fetchone()
        if not row:
            return None
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            status=row["status"],
            feedback=row["feedback"] if "feedback" in row.keys() else None,
        )

    def get_messages(self, conversation_id: str) -> List[Message]:
        """Fetch all messages for a conversation in chronological order."""
        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT id, conversation_id, role, content, created_at, status, feedback
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC;
            """,
            (conversation_id,),
        ).fetchall()

        return [
            Message(
                id=r["id"],
                conversation_id=r["conversation_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
                status=r["status"],
                feedback=r["feedback"] if "feedback" in r.keys() else None,
            )
            for r in rows
        ]

    def set_message_feedback(self, msg_id: int, feedback: Optional[str]) -> bool:
        """Store or clear like/dislike rating on a message and maintain style preferences."""
        rating = (feedback.strip().lower() if isinstance(feedback, str) else None)
        if rating not in ("like", "dislike", None):
            rating = None

        conn = self.db.get_connection()
        with conn:
            # 1. Update messages table
            cur = conn.execute(
                "UPDATE messages SET feedback = ? WHERE id = ?;",
                (rating, msg_id),
            )
            if cur.rowcount == 0:
                logger.warning("Attempted to set feedback on non-existent message #%s", msg_id)
                return False

            # 2. Synchronize with message_feedback table for training/personalization
            if rating in ("like", "dislike"):
                msg_row = conn.execute(
                    "SELECT id, conversation_id, role, content, created_at FROM messages WHERE id = ?;",
                    (msg_id,),
                ).fetchone()

                if msg_row:
                    conv_id = msg_row["conversation_id"]
                    assistant_content = msg_row["content"]

                    # Find the preceding user prompt for context
                    user_row = conn.execute(
                        """
                        SELECT content FROM messages
                        WHERE conversation_id = ? AND role = 'user' AND id < ?
                        ORDER BY id DESC
                        LIMIT 1;
                        """,
                        (conv_id, msg_id),
                    ).fetchone()
                    user_prompt = user_row["content"] if user_row else ""

                    now = _now_iso()
                    conn.execute(
                        """
                        INSERT INTO message_feedback (message_id, conversation_id, rating, user_prompt, assistant_response, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(message_id) DO UPDATE SET
                            rating = excluded.rating,
                            user_prompt = excluded.user_prompt,
                            assistant_response = excluded.assistant_response,
                            created_at = excluded.created_at;
                        """,
                        (msg_id, conv_id, rating, user_prompt, assistant_content, now),
                    )
                    logger.info("Persisted feedback in DB: msg_id=%d rating=%s (prompt='%s...')", msg_id, rating, user_prompt[:30])
            else:
                # Feedback cleared / untoggled
                conn.execute("DELETE FROM message_feedback WHERE message_id = ?;", (msg_id,))
                logger.info("Cleared feedback in DB for msg_id=%d", msg_id)

        return True

    def get_latest_assistant_message(self, conversation_id: str) -> Optional[Message]:
        """Fetch the most recent assistant message in a conversation."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT id, conversation_id, role, content, created_at, status, feedback
            FROM messages
            WHERE conversation_id = ? AND role = 'assistant'
            ORDER BY id DESC
            LIMIT 1;
            """,
            (conversation_id,),
        ).fetchone()
        if not row:
            return None
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            status=row["status"],
            feedback=row["feedback"] if "feedback" in row.keys() else None,
        )

    def get_feedback_preferences(self, limit_liked: int = 5, limit_disliked: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieve recent liked and disliked responses from database."""
        conn = self.db.get_connection()
        liked_rows = conn.execute(
            """
            SELECT message_id, conversation_id, rating, user_prompt, assistant_response, created_at
            FROM message_feedback
            WHERE rating = 'like'
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit_liked,),
        ).fetchall()

        disliked_rows = conn.execute(
            """
            SELECT message_id, conversation_id, rating, user_prompt, assistant_response, created_at
            FROM message_feedback
            WHERE rating = 'dislike'
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit_disliked,),
        ).fetchall()

        return {
            "liked": [dict(r) for r in liked_rows],
            "disliked": [dict(r) for r in disliked_rows],
        }

    def get_feedback_prompt_guidance(self) -> str:
        """Construct prompt guidance based on saved liked and disliked responses.

        Teaches the LLM what kind of answers the user likes (tone, structure, formatting, suggestions)
        and explicitly instructs it to avoid types of answers the user disliked.
        """
        prefs = self.get_feedback_preferences(limit_liked=5, limit_disliked=5)
        liked = prefs.get("liked", [])
        disliked = prefs.get("disliked", [])

        if not liked and not disliked:
            return ""

        parts = [
            "[Personalized User Feedback & Style Preferences - CRITICAL]:",
            "The user actively trains and guides your responses using Like (Thumbs Up) and Dislike (Thumbs Down) feedback.",
            "You MUST emulate what the user liked (suggesting/generating answers in that preferred style) and STRICTLY AVOID generating or suggesting content similar to what the user disliked.",
        ]

        if liked:
            parts.append("\nPREFERRED STYLES & APPROVED CONTENT (The user LIKES this kind of answer — suggest and generate answers like this):")
            for item in liked:
                prompt = (item.get("user_prompt") or "").strip()
                resp = (item.get("assistant_response") or "").strip()
                resp_snippet = (resp[:200] + "...") if len(resp) > 200 else resp
                if prompt:
                    prompt_snippet = (prompt[:80] + "...") if len(prompt) > 80 else prompt
                    parts.append(f"  • When asked '{prompt_snippet}', user liked: \"{resp_snippet}\"")
                else:
                    parts.append(f"  • Approved response style: \"{resp_snippet}\"")
            parts.append("  -> DIRECTIVE: Match the tone, helpfulness, formatting, and spirit of these liked answers.")

        if disliked:
            parts.append("\nREJECTED STYLES & FORBIDDEN CONTENT (The user DISLIKES this kind of answer — DO NOT suggest or generate answers like this):")
            for item in disliked:
                prompt = (item.get("user_prompt") or "").strip()
                resp = (item.get("assistant_response") or "").strip()
                resp_snippet = (resp[:200] + "...") if len(resp) > 200 else resp
                if prompt:
                    prompt_snippet = (prompt[:80] + "...") if len(prompt) > 80 else prompt
                    parts.append(f"  • When asked '{prompt_snippet}', user rejected: \"{resp_snippet}\"")
                else:
                    parts.append(f"  • Rejected response snippet: \"{resp_snippet}\"")
            parts.append("  -> DIRECTIVE: DO NOT generate answers or suggestions like these. Strictly avoid this tone, verbosity, structure, or content.")

        return "\n".join(parts)

    def clear_conversation_messages(self, conversation_id: str) -> bool:
        """Remove all messages in a conversation."""
        conn = self.db.get_connection()
        with conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?;", (conversation_id,))
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (_now_iso(), conversation_id),
            )
            return True

    def search_messages(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search message text across all conversations."""
        clean_q = f"%{query.strip()}%"
        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT m.id, m.conversation_id, m.role, m.content, m.created_at, c.title AS conversation_title
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.content LIKE ?
            ORDER BY m.id DESC
            LIMIT ?;
            """,
            (clean_q, limit),
        ).fetchall()

        return [
            {
                "id": r["id"],
                "conversation_id": r["conversation_id"],
                "conversation_title": r["conversation_title"],
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
