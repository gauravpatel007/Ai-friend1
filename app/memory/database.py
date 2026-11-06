"""SQLite Database Manager for Conversation Persistence.

Provides thread-safe connections, WAL journaling mode, schema migrations,
and automated index creation in the Windows AppData directory.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
from typing import Optional

from platformdirs import user_data_dir

from app.utils.logger import get_logger

logger = get_logger(__name__)

APP_NAME = "AIDesktopFriend"
DB_FILENAME = "conversations.db"


class DatabaseManager:
    """Manages SQLite connections and schema initialization."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path:
            self.db_path = Path(db_path)
        else:
            app_dir = Path(user_data_dir(appname=APP_NAME, appauthor=APP_NAME))
            app_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = app_dir / DB_FILENAME

        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=20.0,
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode and foreign key constraints
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        """Initialize database schema and required indexes."""
        with self._lock:
            conn = self.get_connection()
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'completed',
                        feedback TEXT,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                    );
                """)

                # Schema migration: Ensure 'feedback' column exists in existing messages table
                try:
                    cursor = conn.execute("PRAGMA table_info(messages);")
                    existing_cols = [row[1] for row in cursor.fetchall()]
                    if "feedback" not in existing_cols:
                        conn.execute("ALTER TABLE messages ADD COLUMN feedback TEXT;")
                        logger.info("Migrated messages table: added 'feedback' column.")
                except Exception as e:
                    logger.debug("Schema migration notice for messages.feedback: %s", e)

                # Message feedback table for personalized style adaptation and training
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS message_feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id INTEGER UNIQUE,
                        conversation_id TEXT NOT NULL,
                        rating TEXT NOT NULL,
                        user_prompt TEXT,
                        assistant_response TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    );
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_rating 
                    ON message_feedback(rating);
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_conv_id 
                    ON message_feedback(conversation_id);
                """)

                # Performance indexes for fast chronological and parent queries
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
                    ON messages(conversation_id, id ASC);
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conversations_updated_at 
                    ON conversations(updated_at DESC);
                """)

                # Phase 10: Long-Term Memories table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source_conversation_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_category 
                    ON memories(category);
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_updated_at 
                    ON memories(updated_at DESC);
                """)

                # Phase 10: Conversation Summaries table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_summaries (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_summaries_conversation_id 
                    ON conversation_summaries(conversation_id);
                """)

                # Phase 10: SQLite FTS5 Full-Text Search Virtual Tables
                try:
                    conn.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                            id UNINDEXED,
                            category,
                            content,
                            tokenize = 'porter unicode61'
                        );
                    """)
                    conn.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS summaries_fts USING fts5(
                            id UNINDEXED,
                            conversation_id UNINDEXED,
                            summary,
                            tokenize = 'porter unicode61'
                        );
                    """)
                except sqlite3.OperationalError as e:
                    logger.warning("SQLite FTS5 virtual table initialization notice: %s", e)

                # Movie Hub (Phase 8): User Media Entries (Watchlist, Favorites, Watched, Ratings)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_media_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tmdb_id INTEGER NOT NULL,
                        media_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        poster_path TEXT,
                        poster_url TEXT,
                        backdrop_path TEXT,
                        backdrop_url TEXT,
                        release_year INTEGER,
                        release_date TEXT,
                        original_language TEXT,
                        vote_average REAL DEFAULT 0.0,
                        overview TEXT DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'watchlist',
                        is_favorite INTEGER NOT NULL DEFAULT 0,
                        user_rating INTEGER DEFAULT NULL,
                        user_notes TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        watched_at TEXT DEFAULT NULL,
                        genres TEXT DEFAULT '',
                        CONSTRAINT unq_user_media UNIQUE (tmdb_id, media_type)
                    );
                """)

                # Automatic schema migration: ensure genres column exists if table already existed
                try:
                    cols = [r[1] for r in conn.execute("PRAGMA table_info(user_media_entries);").fetchall()]
                    if "genres" not in cols:
                        conn.execute("ALTER TABLE user_media_entries ADD COLUMN genres TEXT DEFAULT '';")
                except Exception as ex:
                    logger.debug("user_media_entries genres column migration note: %s", ex)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_media_tmdb_type
                    ON user_media_entries(tmdb_id, media_type);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_media_status
                    ON user_media_entries(status);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_media_is_favorite
                    ON user_media_entries(is_favorite);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_media_updated_at
                    ON user_media_entries(updated_at DESC);
                """)

                # Movie Hub (Phase 8): User Entertainment Preferences
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_movie_preferences (
                        user_id TEXT PRIMARY KEY DEFAULT 'default',
                        preferred_genres TEXT NOT NULL DEFAULT '[]',
                        preferred_languages TEXT NOT NULL DEFAULT '["all"]',
                        preferred_regions TEXT NOT NULL DEFAULT '["all"]',
                        disliked_genres TEXT NOT NULL DEFAULT '[]',
                        recommendation_settings TEXT NOT NULL DEFAULT '{"min_rating": 6.0, "include_watched": false, "exclude_watched": true, "prefer_underrated": false, "prefer_highly_rated": false, "prefer_newer": false, "prefer_classic": false}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)

                # Automatic schema migration: ensure disliked_genres exists in user_movie_preferences
                try:
                    p_cols = [r[1] for r in conn.execute("PRAGMA table_info(user_movie_preferences);").fetchall()]
                    if "disliked_genres" not in p_cols:
                        conn.execute("ALTER TABLE user_movie_preferences ADD COLUMN disliked_genres TEXT NOT NULL DEFAULT '[]';")
                except Exception as ex:
                    logger.debug("user_movie_preferences disliked_genres migration note: %s", ex)

                # Movie Hub (Phase 8): Recommendation Feedback Table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS movie_recommendation_feedback (
                        id TEXT PRIMARY KEY,
                        tmdb_id INTEGER NOT NULL,
                        media_type TEXT NOT NULL DEFAULT 'movie',
                        feedback_type TEXT NOT NULL,
                        title TEXT DEFAULT '',
                        genres TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        CONSTRAINT unq_movie_feedback UNIQUE (tmdb_id, media_type)
                    );
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_movie_feedback_tmdb
                    ON movie_recommendation_feedback(tmdb_id, media_type);
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_movie_feedback_type
                    ON movie_recommendation_feedback(feedback_type);
                """)

                # Movie Hub (Phase 10): Persistent Metadata Cache
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS movie_metadata_cache (
                        cache_key TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        data_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        is_stale INTEGER NOT NULL DEFAULT 0
                    );
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_movie_cache_category
                    ON movie_metadata_cache(category);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_movie_cache_expires
                    ON movie_metadata_cache(expires_at);
                """)

                # Movie Hub: AI Search History table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS movie_ai_search_history (
                        id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    );
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_movie_ai_history_timestamp
                    ON movie_ai_search_history(timestamp DESC);
                """)

                # Movie Hub (Phase 5): Persistent Movie Embeddings Cache
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS movie_embeddings_cache (
                        tmdb_id INTEGER NOT NULL,
                        media_type TEXT NOT NULL DEFAULT 'movie',
                        model_name TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1,
                        doc_hash TEXT NOT NULL,
                        embedding_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (tmdb_id, media_type, model_name)
                    );
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_movie_embeddings_tmdb
                    ON movie_embeddings_cache(tmdb_id, media_type);
                """)

                # Phase 3: Model Capability Benchmarks Table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS model_benchmarks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model_id TEXT NOT NULL,
                        digest TEXT,
                        category TEXT NOT NULL,
                        run_type TEXT NOT NULL DEFAULT 'warm',
                        ttft_ms REAL,
                        tokens_per_sec REAL,
                        total_duration_ms REAL,
                        eval_count INTEGER,
                        model_load_ms REAL,
                        peak_ram_mb REAL,
                        peak_gpu_mb REAL,
                        context_capacity INTEGER,
                        quality_score REAL,
                        quality_details TEXT,
                        raw_response TEXT,
                        test_outcome TEXT NOT NULL DEFAULT 'passed',
                        created_at TEXT NOT NULL
                    );
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_benchmarks_model_cat
                    ON model_benchmarks(model_id, category);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_benchmarks_created
                    ON model_benchmarks(created_at DESC);
                """)

            logger.info("Database schema initialized at %s", self.db_path)

    def close(self) -> None:
        """Close connection for the current thread."""
        conn = getattr(self._local, "conn", None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None


def init_db(db_path: Optional[Path | str] = None) -> DatabaseManager:
    """Helper to initialize and return a DatabaseManager instance."""
    return DatabaseManager(db_path=db_path)
