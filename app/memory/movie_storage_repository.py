"""Movie Hub Persistent Storage Repository.

Encapsulates all database operations for Watchlist, Favorites, Watched Status,
Local Personal Ratings, and User Entertainment Preferences using the application's
central SQLite database manager.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from app.api.movie_models import MovieUserPreferences, UserMediaEntry, UserMovieProfile
from app.memory.database import DatabaseManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PREFERENCES = {
    "preferred_genres": [],
    "preferred_languages": ["all"],
    "preferred_regions": ["all"],
    "disliked_genres": [],
    "recommendation_settings": {
        "min_rating": 6.0,
        "include_watched": False,
        "exclude_watched": False,
        "prefer_underrated": False,
        "prefer_highly_rated": False,
        "prefer_newer": False,
        "prefer_classic": False,
    },
}


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_media_type(media_type: str) -> str:
    """Normalize input string to 'movie' or 'tv'."""
    clean = (media_type or "movie").strip().lower()
    return "tv" if clean in ("tv", "series") else "movie"


def _normalize_image_fields(
    raw_path: Optional[str], raw_url: Optional[str], default_size: str = "w500"
) -> tuple[Optional[str], Optional[str]]:
    """Clean and repair image path and full URL, preventing double-prefix corruption."""
    raw = (raw_url or raw_path or "").strip()
    if not raw:
        return None, None

    # Repair duplicate http(s) prefixes if present
    while "http://" in raw and raw.find("http://") != raw.rfind("http://"):
        raw = raw[raw.rfind("http://") :]
    while "https://" in raw and raw.find("https://") != raw.rfind("https://"):
        raw = raw[raw.rfind("https://") :]
    while "https://image.tmdb.org/t/p/" in raw and raw.count("https://image.tmdb.org/t/p/") > 1:
        raw = raw[raw.rfind("https://image.tmdb.org/t/p/") :]

    if raw.startswith("http://") or raw.startswith("https://"):
        url = raw
        if "/t/p/" in raw:
            path_part = raw.split("/t/p/")[-1]
            path_part = re.sub(r"^w\d+/", "", path_part)
            path_part = re.sub(r"^original/", "", path_part)
            path = "/" + path_part.lstrip("/")
        else:
            path = raw
    else:
        path = "/" + raw.lstrip("/")
        url = f"https://image.tmdb.org/t/p/{default_size}{path}"

    return path, url


class MovieStorageRepository:
    """Repository handling ACID persistence for Movie Hub tracking and preferences."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager()

    # =========================================================================
    # 1. Row Mapping Helper
    # =========================================================================

    @staticmethod
    def _row_to_entry(row: Any) -> UserMediaEntry:
        """Convert SQLite Row to validated UserMediaEntry model with clean URLs."""
        p_path, p_url = _normalize_image_fields(row["poster_path"], row["poster_url"], default_size="w500")
        b_path, b_url = _normalize_image_fields(row["backdrop_path"], row["backdrop_url"], default_size="w1280")

        genres_val = ""
        try:
            if "genres" in row.keys():
                genres_val = row["genres"] or ""
        except Exception:
            pass

        return UserMediaEntry(
            id=row["id"],
            tmdb_id=row["tmdb_id"],
            media_type=row["media_type"],
            title=row["title"],
            poster_path=p_path,
            poster_url=p_url,
            backdrop_path=b_path,
            backdrop_url=b_url,
            release_year=row["release_year"],
            release_date=row["release_date"],
            original_language=row["original_language"],
            vote_average=float(row["vote_average"] or 0.0),
            overview=row["overview"] or "",
            status=row["status"],
            is_favorite=bool(row["is_favorite"]),
            user_rating=row["user_rating"],
            user_notes=row["user_notes"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            watched_at=row["watched_at"],
            genres=genres_val,
        )

    # =========================================================================
    # 2. Watchlist & Entry CRUD Operations (8.2, 8.3)
    # =========================================================================

    def add_or_update_entry(
        self,
        tmdb_id: int,
        title: str,
        media_type: str = "movie",
        poster_path: Optional[str] = None,
        poster_url: Optional[str] = None,
        backdrop_path: Optional[str] = None,
        backdrop_url: Optional[str] = None,
        release_year: Optional[int] = None,
        release_date: Optional[str] = None,
        original_language: Optional[str] = None,
        vote_average: float = 0.0,
        overview: str = "",
        status: str = "watchlist",
        is_favorite: Optional[bool] = None,
        user_rating: Optional[int] = None,
        user_notes: Optional[str] = None,
        genres: Optional[str] = None,
    ) -> UserMediaEntry:
        """Add new media entry or update existing entry with strict duplicate prevention."""
        norm_type = _normalize_media_type(media_type)
        now = _now_iso()
        title = (title or "").strip() or f"Title #{tmdb_id}"
        vote_average = float(vote_average or 0.0)
        overview = str(overview or "")
        clean_genres = str(genres).strip() if genres else None

        norm_p_path, norm_p_url = _normalize_image_fields(poster_path, poster_url, default_size="w500")
        norm_b_path, norm_b_url = _normalize_image_fields(backdrop_path, backdrop_url, default_size="w1280")

        if user_rating is not None and not (1 <= user_rating <= 10):
            raise ValueError("user_rating must be between 1 and 10")

        conn = self.db.get_connection()
        with conn:
            existing = conn.execute(
                "SELECT * FROM user_media_entries WHERE tmdb_id = ? AND media_type = ?;",
                (tmdb_id, norm_type),
            ).fetchone()

            if existing:
                # Merge existing flags if not explicitly provided
                effective_fav = bool(is_favorite if is_favorite is not None else existing["is_favorite"])
                effective_rating = user_rating if user_rating is not None else existing["user_rating"]
                effective_notes = user_notes if user_notes is not None else existing["user_notes"]
                effective_status = status if status is not None else existing["status"]

                watched_at = existing["watched_at"]
                if effective_status == "watched" and not watched_at:
                    watched_at = now
                elif effective_status != "watched" and status != "watched":
                    # If explicitly changing status away from watched
                    watched_at = None

                conn.execute(
                    """
                    UPDATE user_media_entries
                    SET title = COALESCE(?, title),
                        poster_path = COALESCE(?, poster_path),
                        poster_url = COALESCE(?, poster_url),
                        backdrop_path = COALESCE(?, backdrop_path),
                        backdrop_url = COALESCE(?, backdrop_url),
                        release_year = COALESCE(?, release_year),
                        release_date = COALESCE(?, release_date),
                        original_language = COALESCE(?, original_language),
                        vote_average = CASE WHEN ? > 0 THEN ? ELSE vote_average END,
                        overview = CASE WHEN LENGTH(?) > 0 THEN ? ELSE overview END,
                        genres = COALESCE(?, genres),
                        status = ?,
                        is_favorite = ?,
                        user_rating = ?,
                        user_notes = ?,
                        updated_at = ?,
                        watched_at = ?
                    WHERE tmdb_id = ? AND media_type = ?;
                    """,
                    (
                        title,
                        norm_p_path,
                        norm_p_url,
                        norm_b_path,
                        norm_b_url,
                        release_year,
                        release_date,
                        original_language,
                        vote_average,
                        vote_average,
                        overview,
                        overview,
                        clean_genres,
                        effective_status,
                        1 if effective_fav else 0,
                        effective_rating,
                        effective_notes,
                        now,
                        watched_at,
                        tmdb_id,
                        norm_type,
                    ),
                )
                logger.info("Updated media entry (%d, %s) to status '%s'", tmdb_id, norm_type, effective_status)
            else:
                watched_at = now if status == "watched" else None
                conn.execute(
                    """
                    INSERT INTO user_media_entries (
                        tmdb_id, media_type, title, poster_path, poster_url,
                        backdrop_path, backdrop_url, release_year, release_date,
                        original_language, vote_average, overview, genres, status,
                        is_favorite, user_rating, user_notes, created_at, updated_at, watched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        tmdb_id,
                        norm_type,
                        title,
                        norm_p_path,
                        norm_p_url,
                        norm_b_path,
                        norm_b_url,
                        release_year,
                        release_date,
                        original_language,
                        vote_average,
                        overview,
                        clean_genres or "",
                        status,
                        1 if (is_favorite or False) else 0,
                        user_rating,
                        user_notes or "",
                        now,
                        now,
                        watched_at,
                    ),
                )
                logger.info("Inserted new media entry (%d, %s) with status '%s'", tmdb_id, norm_type, status)

        entry = self.get_entry(tmdb_id, norm_type)
        if entry is None:
            raise RuntimeError(f"Failed to retrieve upserted media entry ({tmdb_id}, {norm_type})")
        return entry

    def get_entry(self, tmdb_id: int, media_type: str = "movie") -> Optional[UserMediaEntry]:
        """Fetch tracking record for a specific title by provider ID and content type."""
        norm_type = _normalize_media_type(media_type)
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM user_media_entries WHERE tmdb_id = ? AND media_type = ?;",
            (tmdb_id, norm_type),
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def update_status(self, tmdb_id: int, media_type: str, status: str) -> Optional[UserMediaEntry]:
        """Alter status (e.g. watchlist, watching, watched, dropped, none)."""
        norm_type = _normalize_media_type(media_type)
        now = _now_iso()
        watched_at_clause = ", watched_at = ?" if status == "watched" else ", watched_at = NULL"
        params = [status, now]
        if status == "watched":
            params.append(now)
        params.extend([tmdb_id, norm_type])

        conn = self.db.get_connection()
        with conn:
            cur = conn.execute(
                f"""
                UPDATE user_media_entries
                SET status = ?, updated_at = ? {watched_at_clause}
                WHERE tmdb_id = ? AND media_type = ?;
                """,
                params,
            )
            if cur.rowcount == 0:
                return None
        return self.get_entry(tmdb_id, norm_type)

    def mark_as_watched(
        self,
        tmdb_id: int,
        media_type: str = "movie",
        item_metadata: Optional[Dict[str, Any]] = None,
    ) -> UserMediaEntry:
        """Mark title as watched with timestamp recording, creating entry if not already present."""
        norm_type = _normalize_media_type(media_type)
        entry = self.get_entry(tmdb_id, norm_type)
        if entry:
            self.update_status(tmdb_id, norm_type, "watched")
            updated = self.get_entry(tmdb_id, norm_type)
            if updated:
                return updated

        # If entry does not exist, create using metadata with status='watched'
        meta = item_metadata or {}
        raw_title = meta.get("title")
        clean_title = (raw_title or "").strip() or f"Title #{tmdb_id}"
        return self.add_or_update_entry(
            tmdb_id=tmdb_id,
            title=clean_title,
            media_type=norm_type,
            poster_path=meta.get("poster_path"),
            poster_url=meta.get("poster_url"),
            backdrop_path=meta.get("backdrop_path"),
            backdrop_url=meta.get("backdrop_url"),
            release_year=meta.get("release_year"),
            release_date=meta.get("release_date"),
            original_language=meta.get("original_language"),
            vote_average=float(meta.get("vote_average") or 0.0),
            overview=str(meta.get("overview") or ""),
            genres=meta.get("genres"),
            status="watched",
            is_favorite=bool(meta.get("is_favorite")) if meta.get("is_favorite") is not None else None,
        )

    def remove_from_watchlist(self, tmdb_id: int, media_type: str, delete_if_unreferenced: bool = True) -> bool:
        """Remove title from watchlist.
        
        If the entry is marked favorite or has a user rating, its status is updated to 'none'.
        Otherwise, if delete_if_unreferenced is True, the row is permanently pruned.
        """
        norm_type = _normalize_media_type(media_type)
        entry = self.get_entry(tmdb_id, norm_type)
        if not entry or entry.status != "watchlist":
            return False

        conn = self.db.get_connection()
        with conn:
            if delete_if_unreferenced and not entry.is_favorite and entry.user_rating is None:
                conn.execute(
                    "DELETE FROM user_media_entries WHERE tmdb_id = ? AND media_type = ?;",
                    (tmdb_id, norm_type),
                )
            else:
                conn.execute(
                    """
                    UPDATE user_media_entries
                    SET status = 'none', updated_at = ?
                    WHERE tmdb_id = ? AND media_type = ?;
                    """,
                    (_now_iso(), tmdb_id, norm_type),
                )
        return True

    def delete_entry(self, tmdb_id: int, media_type: str) -> bool:
        """Unconditionally delete a title record from persistent storage."""
        norm_type = _normalize_media_type(media_type)
        conn = self.db.get_connection()
        with conn:
            cur = conn.execute(
                "DELETE FROM user_media_entries WHERE tmdb_id = ? AND media_type = ?;",
                (tmdb_id, norm_type),
            )
            return cur.rowcount > 0

    # =========================================================================
    # 3. Favorites and Ratings (8.4)
    # =========================================================================

    def set_favorite(
        self,
        tmdb_id: int,
        media_type: str,
        is_favorite: bool,
        item_metadata: Optional[Dict[str, Any]] = None,
    ) -> UserMediaEntry:
        """Toggle favorite state for a title, creating an entry if not already present."""
        norm_type = _normalize_media_type(media_type)
        entry = self.get_entry(tmdb_id, norm_type)

        meta = item_metadata or {}
        if entry:
            conn = self.db.get_connection()
            update_genres = ""
            params = [1 if is_favorite else 0]
            if meta.get("genres") and not entry.genres:
                update_genres = ", genres = ?"
                params.append(str(meta.get("genres")).strip())
            params.extend([_now_iso(), tmdb_id, norm_type])
            with conn:
                conn.execute(
                    f"""
                    UPDATE user_media_entries
                    SET is_favorite = ?{update_genres}, updated_at = ?
                    WHERE tmdb_id = ? AND media_type = ?;
                    """,
                    params,
                )
            return self.get_entry(tmdb_id, norm_type)  # type: ignore

        if not is_favorite:
            raw_title = meta.get("title")
            clean_title = (raw_title or "").strip() or f"Title #{tmdb_id}"
            return UserMediaEntry(
                tmdb_id=tmdb_id,
                media_type=norm_type,
                title=clean_title,
                status="none",
                is_favorite=False,
            )

        # If entry does not exist, create using metadata
        raw_title = meta.get("title")
        clean_title = (raw_title or "").strip() or f"Title #{tmdb_id}"
        return self.add_or_update_entry(
            tmdb_id=tmdb_id,
            title=clean_title,
            media_type=norm_type,
            poster_path=meta.get("poster_path"),
            poster_url=meta.get("poster_url"),
            backdrop_path=meta.get("backdrop_path"),
            backdrop_url=meta.get("backdrop_url"),
            release_year=meta.get("release_year"),
            release_date=meta.get("release_date"),
            original_language=meta.get("original_language"),
            vote_average=float(meta.get("vote_average") or 0.0),
            overview=str(meta.get("overview") or ""),
            genres=meta.get("genres"),
            status="none",
            is_favorite=is_favorite,
        )

    def set_rating(
        self,
        tmdb_id: int,
        media_type: str,
        rating: Optional[int],
        item_metadata: Optional[Dict[str, Any]] = None,
    ) -> UserMediaEntry:
        """Assign or clear personal local user rating (1-10 integer).
        
        Keeps local user rating separate from provider vote_average.
        """
        if rating is not None and not (1 <= rating <= 10):
            raise ValueError(f"Rating must be between 1 and 10, got {rating}")

        norm_type = _normalize_media_type(media_type)
        entry = self.get_entry(tmdb_id, norm_type)

        if entry:
            conn = self.db.get_connection()
            with conn:
                conn.execute(
                    """
                    UPDATE user_media_entries
                    SET user_rating = ?, updated_at = ?
                    WHERE tmdb_id = ? AND media_type = ?;
                    """,
                    (rating, _now_iso(), tmdb_id, norm_type),
                )
            return self.get_entry(tmdb_id, norm_type)  # type: ignore

        # If entry does not exist, create using metadata
        meta = item_metadata or {}
        raw_title = meta.get("title")
        clean_title = (raw_title or "").strip() or f"Title #{tmdb_id}"
        return self.add_or_update_entry(
            tmdb_id=tmdb_id,
            title=clean_title,
            media_type=norm_type,
            poster_path=meta.get("poster_path"),
            poster_url=meta.get("poster_url"),
            backdrop_path=meta.get("backdrop_path"),
            backdrop_url=meta.get("backdrop_url"),
            release_year=meta.get("release_year"),
            release_date=meta.get("release_date"),
            original_language=meta.get("original_language"),
            vote_average=float(meta.get("vote_average") or 0.0),
            overview=str(meta.get("overview") or ""),
            status="none",
            user_rating=rating,
        )

    # =========================================================================
    # 4. Filtered Querying & Saved Titles Collections (8.3, 8.4)
    # =========================================================================

    def list_entries(
        self,
        status: Optional[str] = None,
        is_favorite: Optional[bool] = None,
        min_rating: Optional[int] = None,
        media_type: Optional[str] = None,
        sort_by: str = "updated_at",
        desc: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[UserMediaEntry]:
        """Retrieve stored titles matching arbitrary status and category filters."""
        query_clauses = []
        params: List[Any] = []

        if status:
            if status != "all":
                query_clauses.append("status = ?")
                params.append(status)
        if is_favorite is not None:
            query_clauses.append("is_favorite = ?")
            params.append(1 if is_favorite else 0)
        if min_rating is not None:
            query_clauses.append("user_rating >= ?")
            params.append(min_rating)
        if media_type and media_type != "all":
            norm_type = _normalize_media_type(media_type)
            query_clauses.append("media_type = ?")
            params.append(norm_type)

        where_stmt = ("WHERE " + " AND ".join(query_clauses)) if query_clauses else ""

        # Validate order column to prevent injection
        valid_cols = {"updated_at", "created_at", "title", "user_rating", "vote_average", "release_year"}
        col = sort_by if sort_by in valid_cols else "updated_at"
        direction = "DESC" if desc else "ASC"

        sql = f"""
            SELECT * FROM user_media_entries
            {where_stmt}
            ORDER BY {col} {direction}
            LIMIT ? OFFSET ?;
        """
        params.extend([max(1, limit), max(0, offset)])

        conn = self.db.get_connection()
        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_watchlist(self, media_type: Optional[str] = None) -> List[UserMediaEntry]:
        """Fetch all titles currently on the user's watchlist."""
        return self.list_entries(status="watchlist", media_type=media_type, sort_by="updated_at", desc=True)

    def get_favorites(self, media_type: Optional[str] = None) -> List[UserMediaEntry]:
        """Fetch all titles marked as favorites."""
        return self.list_entries(is_favorite=True, media_type=media_type, sort_by="updated_at", desc=True)

    def get_watched(self, media_type: Optional[str] = None) -> List[UserMediaEntry]:
        """Fetch all titles marked as watched."""
        return self.list_entries(status="watched", media_type=media_type, sort_by="updated_at", desc=True)

    def get_ratings(self, media_type: Optional[str] = None) -> List[UserMediaEntry]:
        """Fetch all titles with a local personal rating."""
        return self.list_entries(min_rating=1, media_type=media_type, sort_by="user_rating", desc=True)

    def get_tracking_summary(self) -> Dict[str, Any]:
        """Return sets of tracked IDs for rapid badging in UI."""
        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT tmdb_id, media_type, status, is_favorite, user_rating FROM user_media_entries;"
        ).fetchall()

        watchlist_ids = []
        favorite_ids = []
        watched_ids = []
        user_ratings = {}

        for r in rows:
            tid = r["tmdb_id"]
            if r["status"] == "watchlist":
                watchlist_ids.append(tid)
            if r["status"] == "watched":
                watched_ids.append(tid)
            if r["is_favorite"]:
                favorite_ids.append(tid)
            if r["user_rating"] is not None:
                user_ratings[str(tid)] = r["user_rating"]

        return {
            "watchlist_ids": watchlist_ids,
            "favorite_ids": favorite_ids,
            "watched_ids": watched_ids,
            "user_ratings": user_ratings,
        }

    # =========================================================================
    # 5. User Entertainment Preferences (8.6)
    # =========================================================================

    def get_preferences(self, user_id: str = "default") -> MovieUserPreferences:
        """Retrieve user viewing preferences, initializing defaults if absent."""
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM user_movie_preferences WHERE user_id = ?;",
            (user_id,),
        ).fetchone()

        if not row:
            now = _now_iso()
            with conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO user_movie_preferences (
                        user_id, preferred_genres, preferred_languages,
                        preferred_regions, disliked_genres, recommendation_settings, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        user_id,
                        json.dumps(DEFAULT_PREFERENCES["preferred_genres"]),
                        json.dumps(DEFAULT_PREFERENCES["preferred_languages"]),
                        json.dumps(DEFAULT_PREFERENCES["preferred_regions"]),
                        json.dumps(DEFAULT_PREFERENCES["disliked_genres"]),
                        json.dumps(DEFAULT_PREFERENCES["recommendation_settings"]),
                        now,
                        now,
                    ),
                )
            recs = dict(DEFAULT_PREFERENCES["recommendation_settings"])
            return MovieUserPreferences(
                preferred_genres=list(DEFAULT_PREFERENCES["preferred_genres"]),
                preferred_languages=list(DEFAULT_PREFERENCES["preferred_languages"]),
                preferred_regions=list(DEFAULT_PREFERENCES["preferred_regions"]),
                disliked_genres=list(DEFAULT_PREFERENCES["disliked_genres"]),
                exclude_watched=bool(recs.get("exclude_watched", False)),
                prefer_underrated=bool(recs.get("prefer_underrated", False)),
                prefer_highly_rated=bool(recs.get("prefer_highly_rated", False)),
                prefer_newer=bool(recs.get("prefer_newer", False)),
                prefer_classic=bool(recs.get("prefer_classic", False)),
                recommendation_settings=recs,
                updated_at=now,
            )

        # Parse stored row
        p_genres = json.loads(row["preferred_genres"] or "[]")
        p_langs = json.loads(row["preferred_languages"] or '["all"]')
        p_regions = json.loads(row["preferred_regions"] or '["all"]')
        d_genres: List[str] = []
        try:
            if "disliked_genres" in row.keys() and row["disliked_genres"]:
                d_genres = json.loads(row["disliked_genres"])
        except Exception:
            pass

        rec_settings = json.loads(row["recommendation_settings"] or "{}")
        if not d_genres and "disliked_genres" in rec_settings:
            d_genres = rec_settings.get("disliked_genres", [])

        exclude_watched = bool(rec_settings.get("exclude_watched", False))
        prefer_underrated = bool(rec_settings.get("prefer_underrated", False))
        prefer_highly_rated = bool(rec_settings.get("prefer_highly_rated", False))
        prefer_newer = bool(rec_settings.get("prefer_newer", False))
        prefer_classic = bool(rec_settings.get("prefer_classic", False))

        return MovieUserPreferences(
            preferred_genres=p_genres,
            preferred_languages=p_langs,
            preferred_regions=p_regions,
            disliked_genres=d_genres,
            exclude_watched=exclude_watched,
            prefer_underrated=prefer_underrated,
            prefer_highly_rated=prefer_highly_rated,
            prefer_newer=prefer_newer,
            prefer_classic=prefer_classic,
            recommendation_settings=rec_settings,
            updated_at=row["updated_at"],
        )

    def update_preferences(
        self,
        preferred_genres: Optional[List[str]] = None,
        preferred_languages: Optional[List[str]] = None,
        preferred_regions: Optional[List[str]] = None,
        disliked_genres: Optional[List[str]] = None,
        exclude_watched: Optional[bool] = None,
        prefer_underrated: Optional[bool] = None,
        prefer_highly_rated: Optional[bool] = None,
        prefer_newer: Optional[bool] = None,
        prefer_classic: Optional[bool] = None,
        recommendation_settings: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> MovieUserPreferences:
        """Update entertainment preferences with atomic database commit."""
        current = self.get_preferences(user_id=user_id)
        now = _now_iso()

        new_genres = preferred_genres if preferred_genres is not None else current.preferred_genres
        new_languages = preferred_languages if preferred_languages is not None else current.preferred_languages
        new_regions = preferred_regions if preferred_regions is not None else current.preferred_regions
        new_disliked = disliked_genres if disliked_genres is not None else current.disliked_genres

        new_recs = dict(current.recommendation_settings)
        if recommendation_settings is not None:
            new_recs.update(recommendation_settings)

        if exclude_watched is not None:
            new_recs["exclude_watched"] = exclude_watched
            new_recs["include_watched"] = not exclude_watched
        if prefer_underrated is not None:
            new_recs["prefer_underrated"] = prefer_underrated
        if prefer_highly_rated is not None:
            new_recs["prefer_highly_rated"] = prefer_highly_rated
        if prefer_newer is not None:
            new_recs["prefer_newer"] = prefer_newer
        if prefer_classic is not None:
            new_recs["prefer_classic"] = prefer_classic
        new_recs["disliked_genres"] = new_disliked

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE user_movie_preferences
                SET preferred_genres = ?,
                    preferred_languages = ?,
                    preferred_regions = ?,
                    disliked_genres = ?,
                    recommendation_settings = ?,
                    updated_at = ?
                WHERE user_id = ?;
                """,
                (
                    json.dumps(new_genres),
                    json.dumps(new_languages),
                    json.dumps(new_regions),
                    json.dumps(new_disliked),
                    json.dumps(new_recs),
                    now,
                    user_id,
                ),
            )
        logger.info("Updated Movie Hub preferences for user '%s'", user_id)
        return self.get_preferences(user_id=user_id)

    def reset_preferences(self, user_id: str = "default") -> MovieUserPreferences:
        """Reset entertainment preferences to sensible defaults."""
        now = _now_iso()
        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE user_movie_preferences
                SET preferred_genres = ?,
                    preferred_languages = ?,
                    preferred_regions = ?,
                    disliked_genres = ?,
                    recommendation_settings = ?,
                    updated_at = ?
                WHERE user_id = ?;
                """,
                (
                    json.dumps(DEFAULT_PREFERENCES["preferred_genres"]),
                    json.dumps(DEFAULT_PREFERENCES["preferred_languages"]),
                    json.dumps(DEFAULT_PREFERENCES["preferred_regions"]),
                    json.dumps(DEFAULT_PREFERENCES["disliked_genres"]),
                    json.dumps(DEFAULT_PREFERENCES["recommendation_settings"]),
                    now,
                    user_id,
                ),
            )
        logger.info("Reset Movie Hub preferences for user '%s' to defaults", user_id)
        return self.get_preferences(user_id=user_id)

    # =========================================================================
    # Phase 8: User Feedback & Preference Profiling
    # =========================================================================

    def record_feedback(
        self,
        tmdb_id: int,
        media_type: str,
        feedback_type: str,
        title: str = "",
        genres: str = "",
    ) -> Dict[str, Any]:
        """Record or update user feedback ('more_like_this', 'not_interested', 'already_watched', 'not_my_taste')."""
        norm_type = _normalize_media_type(media_type)
        now = _now_iso()
        item_id = f"fb-{tmdb_id}-{norm_type}"

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO movie_recommendation_feedback (
                    id, tmdb_id, media_type, feedback_type, title, genres, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tmdb_id, media_type) DO UPDATE SET
                    feedback_type = excluded.feedback_type,
                    title = CASE WHEN LENGTH(excluded.title) > 0 THEN excluded.title ELSE movie_recommendation_feedback.title END,
                    genres = CASE WHEN LENGTH(excluded.genres) > 0 THEN excluded.genres ELSE movie_recommendation_feedback.genres END,
                    updated_at = excluded.updated_at;
                """,
                (item_id, tmdb_id, norm_type, feedback_type, title or "", genres or "", now, now),
            )

        # If user indicated 'already_watched', automatically sync to watched storage
        if feedback_type == "already_watched":
            try:
                self.mark_as_watched(tmdb_id, norm_type, item_metadata={"title": title, "genres": genres})
            except Exception as e:
                logger.debug("Failed to auto-mark as watched on feedback: %s", e)

        logger.info("Recorded feedback '%s' for %s %d (%s)", feedback_type, norm_type, tmdb_id, title)
        return {
            "status": "ok",
            "id": item_id,
            "tmdb_id": tmdb_id,
            "media_type": norm_type,
            "feedback_type": feedback_type,
            "title": title,
            "genres": genres,
            "created_at": now,
            "updated_at": now,
        }

    def get_feedback(self, tmdb_id: int, media_type: str = "movie") -> Optional[Dict[str, Any]]:
        """Retrieve feedback for a specific movie if present."""
        norm_type = _normalize_media_type(media_type)
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM movie_recommendation_feedback WHERE tmdb_id = ? AND media_type = ?;",
            (tmdb_id, norm_type),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_all_feedback(self) -> List[Dict[str, Any]]:
        """Retrieve all recorded recommendation feedback items."""
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM movie_recommendation_feedback ORDER BY updated_at DESC;"
        )
        return [dict(r) for r in cursor.fetchall()]

    def delete_feedback(self, tmdb_id: int, media_type: str = "movie") -> bool:
        """Delete feedback record for a specific movie."""
        norm_type = _normalize_media_type(media_type)
        conn = self.db.get_connection()
        with conn:
            cur = conn.execute(
                "DELETE FROM movie_recommendation_feedback WHERE tmdb_id = ? AND media_type = ?;",
                (tmdb_id, norm_type),
            )
            return cur.rowcount > 0

    def build_user_profile(self, user_id: str = "default") -> UserMovieProfile:
        """Construct consolidated lightweight preference profile from preferences, history, and feedback."""
        prefs = self.get_preferences(user_id=user_id)
        favorites = self.get_favorites()
        watched = self.get_watched()
        watchlist = self.get_watchlist()
        all_feedback = self.get_all_feedback()

        fav_ids = {f.tmdb_id for f in favorites}
        watched_ids = {w.tmdb_id for w in watched}
        watchlist_ids = {wl.tmdb_id for wl in watchlist}

        liked_ids = {fb["tmdb_id"] for fb in all_feedback if fb["feedback_type"] == "more_like_this"}
        disliked_ids = {fb["tmdb_id"] for fb in all_feedback if fb["feedback_type"] in ("not_interested", "not_my_taste")}

        # Tally genre affinities
        genre_affinities: Dict[str, float] = {}

        def add_genre_weight(genre_str: str, weight: float):
            if not genre_str:
                return
            for part in re.split(r"[,|/]", str(genre_str)):
                g = part.strip().lower()
                if g:
                    genre_affinities[g] = round(genre_affinities.get(g, 0.0) + weight, 2)

        # 1. Explicit preferences (+2.0 for preferred, -3.0 for disliked)
        for g in prefs.preferred_genres:
            add_genre_weight(g, 2.0)
        for g in prefs.disliked_genres:
            add_genre_weight(g, -3.0)

        # 2. Favorites (+2.0 per genre)
        for fav in favorites:
            add_genre_weight(fav.genres or "", 2.0)

        # 3. Feedback: 'more_like_this' (+1.5 per genre)
        for fb in all_feedback:
            if fb["feedback_type"] == "more_like_this":
                add_genre_weight(fb.get("genres") or "", 1.5)
            elif fb["feedback_type"] in ("not_my_taste", "not_interested"):
                add_genre_weight(fb.get("genres") or "", -1.5)

        # 4. Watchlist (+0.5 per genre)
        for wl in watchlist:
            add_genre_weight(wl.genres or "", 0.5)

        # 5. Watched (+0.2 per genre - avoid treating every watched movie as favorite)
        for w in watched:
            add_genre_weight(w.genres or "", 0.2)

        return UserMovieProfile(
            preferred_genres=list(prefs.preferred_genres),
            disliked_genres=[g.strip().lower() for g in prefs.disliked_genres if g],
            preferred_languages=list(prefs.preferred_languages),
            exclude_watched=prefs.exclude_watched,
            prefer_underrated=prefs.prefer_underrated,
            prefer_highly_rated=prefs.prefer_highly_rated,
            prefer_newer=prefs.prefer_newer,
            prefer_classic=prefs.prefer_classic,
            favorite_ids=fav_ids,
            watched_ids=watched_ids,
            watchlist_ids=watchlist_ids,
            liked_ids=liked_ids,
            disliked_ids=disliked_ids,
            genre_affinities=genre_affinities,
        )

    # =========================================================================
    # 6. AI Search History Management
    # =========================================================================

    def get_ai_search_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent AI recommendation search queries ordered newest first."""
        conn = self.db.get_connection()
        cursor = conn.execute(
            """
            SELECT id, query, timestamp, created_at
            FROM movie_ai_search_history
            ORDER BY timestamp DESC, rowid DESC
            LIMIT ?;
            """,
            (max(1, min(limit, 100)),),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "query": row["query"],
                "timestamp": int(row["timestamp"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def add_ai_search_history(self, query: str) -> Dict[str, Any]:
        """Record an AI search query with deduplication and timestamp updating."""
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("Query string cannot be empty")

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        now_ts = int(now_dt.timestamp() * 1000)
        item_id = f"{now_ts}-{uuid.uuid4().hex[:6]}"

        conn = self.db.get_connection()
        with conn:
            # Deduplicate: Remove existing entry with exact case-insensitive match
            conn.execute(
                "DELETE FROM movie_ai_search_history WHERE LOWER(query) = LOWER(?);",
                (clean_query,),
            )
            # Insert the fresh entry at the top
            conn.execute(
                """
                INSERT INTO movie_ai_search_history (id, query, timestamp, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (item_id, clean_query, now_ts, now_iso),
            )
            # Prune oldest records beyond max 100 to keep DB lean
            conn.execute(
                """
                DELETE FROM movie_ai_search_history
                WHERE id NOT IN (
                    SELECT id FROM movie_ai_search_history
                    ORDER BY timestamp DESC, rowid DESC
                    LIMIT 100
                );
                """
            )

        logger.info("Recorded AI search query to database: '%s' (id: %s)", clean_query, item_id)
        return {
            "id": item_id,
            "query": clean_query,
            "timestamp": now_ts,
            "created_at": now_iso,
        }

    def delete_ai_search_history_item(self, item_id: str) -> bool:
        """Delete an individual AI search query by ID."""
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                "DELETE FROM movie_ai_search_history WHERE id = ?;",
                (item_id,),
            )
            deleted = cursor.rowcount > 0
        logger.info("Deleted AI search query id '%s': %s", item_id, deleted)
        return deleted

    def clear_ai_search_history(self) -> bool:
        """Clear all stored AI search queries."""
        conn = self.db.get_connection()
        with conn:
            conn.execute("DELETE FROM movie_ai_search_history;")
        logger.info("Cleared all AI search queries from database")
        return True

    # =========================================================================
    # 7. Phase 5: Semantic Movie Embeddings Cache
    # =========================================================================

    def get_movie_embedding(
        self,
        tmdb_id: int,
        media_type: str = "movie",
        model_name: str = "all-minilm",
    ) -> Optional[Tuple[str, List[float]]]:
        """Retrieve cached embedding and doc_hash for a given movie/TV ID and model.
        
        Returns:
            Tuple of (doc_hash, embedding_floats) if found, else None.
        """
        conn = self.db.get_connection()
        norm_type = _normalize_media_type(media_type)
        cursor = conn.execute(
            """
            SELECT doc_hash, embedding_json
            FROM movie_embeddings_cache
            WHERE tmdb_id = ? AND media_type = ? AND model_name = ?;
            """,
            (tmdb_id, norm_type, model_name),
        )
        row = cursor.fetchone()
        if not row:
            return None
        try:
            emb = json.loads(row["embedding_json"])
            return row["doc_hash"], emb
        except Exception as e:
            logger.warning("Failed to parse cached embedding for tmdb_id %s: %s", tmdb_id, e)
            return None

    def get_movie_embeddings_batch(
        self,
        tmdb_ids: List[int],
        media_type: str = "movie",
        model_name: str = "all-minilm",
    ) -> Dict[int, Tuple[str, List[float]]]:
        """Batch retrieve cached embeddings for a list of TMDB IDs in a single query."""
        if not tmdb_ids:
            return {}
        conn = self.db.get_connection()
        norm_type = _normalize_media_type(media_type)
        placeholders = ",".join("?" for _ in tmdb_ids)
        query = f"""
            SELECT tmdb_id, doc_hash, embedding_json
            FROM movie_embeddings_cache
            WHERE media_type = ? AND model_name = ? AND tmdb_id IN ({placeholders});
        """
        params = [norm_type, model_name] + list(tmdb_ids)
        cursor = conn.execute(query, params)
        results: Dict[int, Tuple[str, List[float]]] = {}
        for row in cursor.fetchall():
            try:
                emb = json.loads(row["embedding_json"])
                results[row["tmdb_id"]] = (row["doc_hash"], emb)
            except Exception:
                continue
        return results

    def save_movie_embedding(
        self,
        tmdb_id: int,
        media_type: str,
        model_name: str,
        doc_hash: str,
        embedding: List[float],
        version: int = 1,
    ) -> None:
        """Persist or update an embedding for a movie in SQLite cache."""
        now_iso = _now_iso()
        conn = self.db.get_connection()
        norm_type = _normalize_media_type(media_type)
        emb_json = json.dumps(embedding)
        with conn:
            conn.execute(
                """
                INSERT INTO movie_embeddings_cache (
                    tmdb_id, media_type, model_name, version, doc_hash,
                    embedding_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tmdb_id, media_type, model_name) DO UPDATE SET
                    version = excluded.version,
                    doc_hash = excluded.doc_hash,
                    embedding_json = excluded.embedding_json,
                    updated_at = excluded.updated_at;
                """,
                (tmdb_id, norm_type, model_name, version, doc_hash, emb_json, now_iso, now_iso),
            )

    def save_movie_embeddings_batch(self, entries: List[Dict[str, Any]]) -> None:
        """Batch insert/update embeddings in SQLite in a single transaction."""
        if not entries:
            return
        now_iso = _now_iso()
        conn = self.db.get_connection()
        rows = []
        for e in entries:
            norm_type = _normalize_media_type(e.get("media_type", "movie"))
            emb_json = json.dumps(e["embedding"])
            rows.append((
                e["tmdb_id"],
                norm_type,
                e["model_name"],
                e.get("version", 1),
                e["doc_hash"],
                emb_json,
                now_iso,
                now_iso,
            ))
        with conn:
            conn.executemany(
                """
                INSERT INTO movie_embeddings_cache (
                    tmdb_id, media_type, model_name, version, doc_hash,
                    embedding_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tmdb_id, media_type, model_name) DO UPDATE SET
                    version = excluded.version,
                    doc_hash = excluded.doc_hash,
                    embedding_json = excluded.embedding_json,
                    updated_at = excluded.updated_at;
                """,
                rows,
            )
