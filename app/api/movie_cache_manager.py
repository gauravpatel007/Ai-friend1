"""Movie Hub Caching & Offline Resilience Manager.

Provides:
- 10.1 Two-tier metadata caching (In-Memory + SQLite persistent cache) with category TTLs.
- 10.2 Safe, bounded local image caching with integrity validation and LRU eviction.
- 10.3 Offline resilience and stale-metadata fallback during network disruptions.
- 10.4 Request efficiency, deduplication support, and cache pruning.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from platformdirs import user_data_dir

from app.memory.database import DatabaseManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Cache TTL Policies (in seconds) per category
CACHE_TTLS: Dict[str, int] = {
    "search": 900,            # 15 minutes: search results
    "discover": 1800,         # 30 minutes: discovery browse catalogs
    "movie_details": 86400,   # 24 hours: movie metadata & cast
    "tv_details": 86400,      # 24 hours: series metadata & cast
    "genres": 604800,         # 7 days: genre taxonomies (static)
    "similar": 86400,         # 24 hours: related and recommended titles
    "watch_providers": 86400, # 24 hours: streaming watch providers
    "recommendations": 7200,  # 2 hours: AI recommendation responses
    "default": 3600,          # 1 hour: fallback
}

DEFAULT_MAX_IMAGE_CACHE_BYTES = 150 * 1024 * 1024  # 150 MB bounded cache limit
DEFAULT_MAX_IMAGE_FILES = 1000

# SVG fallback placeholder for missing/offline images
FALLBACK_POSTER_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 750" width="500" height="750">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1C1C1E"/>
      <stop offset="100%" stop-color="#0A0A0C"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect x="20" y="20" width="460" height="710" rx="16" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="2"/>
  <circle cx="250" cy="330" r="44" fill="rgba(255,255,255,0.05)"/>
  <path d="M232 316 L272 316 L272 344 L232 344 Z M224 352 L280 352" stroke="rgba(255,255,255,0.3)" stroke-width="3" stroke-linecap="round" fill="none"/>
  <text x="250" y="420" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="500" fill="rgba(255,255,255,0.4)" text-anchor="middle">Poster Preview Offline</text>
  <text x="250" y="445" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="12" fill="rgba(255,255,255,0.25)" text-anchor="middle">Cached locally for offline viewing</text>
</svg>"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_valid_image(data: bytes) -> Tuple[bool, str]:
    """Validate image magic bytes and return (is_valid, mime_type)."""
    if len(data) < 100:
        return False, ""
    # JPEG magic bytes: FF D8 FF
    if data.startswith(b"\xff\xd8\xff"):
        return True, "image/jpeg"
    # PNG magic bytes: \x89PNG\r\n\x1a\n
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, "image/png"
    # WebP magic bytes: RIFF....WEBP
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True, "image/webp"
    # SVG detection
    if b"<svg" in data[:200].lower():
        return True, "image/svg+xml"
    return False, ""


class MovieCacheManager:
    """Central cache controller for metadata and bounded image storage."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        image_cache_dir: Optional[Path | str] = None,
        max_image_cache_bytes: int = DEFAULT_MAX_IMAGE_CACHE_BYTES,
        max_image_files: int = DEFAULT_MAX_IMAGE_FILES,
    ) -> None:
        self.db = db_manager
        self.max_image_cache_bytes = max_image_cache_bytes
        self.max_image_files = max_image_files
        self._lock = threading.RLock()

        # Tier 1 In-Memory Fast Cache: key -> (timestamp, expires_at_ts, data)
        self._mem_cache: Dict[str, Tuple[float, float, Dict[str, Any]]] = {}

        # Set up image cache directory
        if image_cache_dir:
            self.image_cache_dir = Path(image_cache_dir)
        else:
            base_data = Path(user_data_dir("AIDesktopFriend", "AIDesktopFriend"))
            self.image_cache_dir = base_data / "cache" / "movie_images"

        self.image_cache_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # 1. Metadata Caching (10.1)
    # =========================================================================

    def get_metadata(
        self,
        cache_key: str,
        allow_stale: bool = False,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """Retrieve metadata from memory or SQLite persistent cache.
        
        Returns:
            (cached_data, is_stale)
            If not found: (None, False)
        """
        now_ts = time.time()

        with self._lock:
            # 1. Check in-memory fast tier
            if cache_key in self._mem_cache:
                _, expires_at_ts, data = self._mem_cache[cache_key]
                if now_ts < expires_at_ts:
                    return data, False
                if allow_stale:
                    return data, True

            # 2. Check SQLite persistent tier
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT data_json, expires_at, is_stale FROM movie_metadata_cache WHERE cache_key = ?;",
                (cache_key,),
            ).fetchone()

            if not row:
                return None, False

            try:
                data = json.loads(row["data_json"])
                exp_dt = datetime.fromisoformat(row["expires_at"])
                exp_ts = exp_dt.timestamp()

                # Refresh in-memory tier
                self._mem_cache[cache_key] = (now_ts, exp_ts, data)

                if now_ts < exp_ts:
                    return data, False

                if allow_stale:
                    return data, True

                return None, False
            except Exception as e:
                logger.warning("Error parsing cached metadata for '%s': %s", cache_key, e)
                return None, False

    def set_metadata(
        self,
        cache_key: str,
        category: str,
        data: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Store metadata in both in-memory and persistent SQLite cache with category TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else CACHE_TTLS.get(category, CACHE_TTLS["default"])
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl, tz=timezone.utc)

        now_iso = now.isoformat()
        expires_iso = expires_at.isoformat()
        data_json = json.dumps(data)

        with self._lock:
            # 1. Update in-memory tier
            self._mem_cache[cache_key] = (now.timestamp(), expires_at.timestamp(), data)

            # 2. Upsert in SQLite persistent tier
            conn = self.db.get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO movie_metadata_cache (
                        cache_key, category, data_json, created_at, expires_at, is_stale
                    ) VALUES (?, ?, ?, ?, ?, 0)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        category = excluded.category,
                        data_json = excluded.data_json,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at,
                        is_stale = 0;
                    """,
                    (cache_key, category, data_json, now_iso, expires_iso),
                )

    def invalidate_metadata(self, category: Optional[str] = None) -> int:
        """Invalidate cached metadata across all or a specific category."""
        with self._lock:
            conn = self.db.get_connection()
            with conn:
                if category:
                    cursor = conn.execute(
                        "DELETE FROM movie_metadata_cache WHERE category = ?;",
                        (category,),
                    )
                    # Purge from memory cache
                    self._mem_cache = {
                        k: v for k, v in self._mem_cache.items()
                        if not k.startswith(f"{category}:")
                    }
                else:
                    cursor = conn.execute("DELETE FROM movie_metadata_cache;")
                    self._mem_cache.clear()

                count = cursor.rowcount
                logger.info("Invalidated %d metadata cache entries (category=%s)", count, category or "ALL")
                return count

    def prune_expired_metadata(self) -> int:
        """Delete expired metadata records from persistent SQLite storage."""
        now_iso = _now_iso()
        with self._lock:
            conn = self.db.get_connection()
            with conn:
                cursor = conn.execute(
                    "DELETE FROM movie_metadata_cache WHERE expires_at < ?;",
                    (now_iso,),
                )
                deleted = cursor.rowcount
                if deleted > 0:
                    logger.debug("Pruned %d expired metadata cache entries", deleted)
                return deleted

    # =========================================================================
    # 2. Safe, Bounded Image Caching (10.2)
    # =========================================================================

    def _get_image_file_path(self, image_path: str, size: str = "w500") -> Path:
        """Derive safe local disk path for an image."""
        clean_name = image_path.lstrip("/").replace("/", "_").replace("\\", "_")
        if not clean_name.endswith((".jpg", ".jpeg", ".png", ".webp")):
            clean_name += ".jpg"
        return self.image_cache_dir / f"{size}_{clean_name}"

    def get_image(self, image_path: str, size: str = "w500") -> Optional[Tuple[bytes, str]]:
        """Retrieve cached image bytes from disk if present and uncorrupted.
        
        Returns:
            (bytes, mime_type) if found and valid, else None.
        """
        file_path = self._get_image_file_path(image_path, size)
        if not file_path.exists():
            return None

        try:
            data = file_path.read_bytes()
            valid, mime_type = _is_valid_image(data)
            if not valid:
                logger.warning("Corrupted image file detected at %s. Purging.", file_path)
                file_path.unlink(missing_ok=True)
                return None

            # Update access time for LRU tracking
            try:
                os.utime(file_path, None)
            except OSError:
                pass

            return data, mime_type
        except Exception as e:
            logger.warning("Failed to read cached image %s: %s", file_path, e)
            file_path.unlink(missing_ok=True)
            return None

    def save_image(
        self,
        image_path: str,
        size: str,
        image_bytes: bytes,
    ) -> bool:
        """Validate and save image to local disk cache, triggering LRU pruning if bounded cap is exceeded."""
        valid, _ = _is_valid_image(image_bytes)
        if not valid:
            logger.warning("Refusing to cache invalid image bytes for '%s' (size=%d)", image_path, len(image_bytes))
            return False

        file_path = self._get_image_file_path(image_path, size)
        with self._lock:
            try:
                file_path.write_bytes(image_bytes)
                # Bounded cache check
                self.prune_image_cache_if_needed()
                return True
            except Exception as e:
                logger.error("Failed to write image cache for %s: %s", file_path, e)
                return False

    def prune_image_cache_if_needed(self) -> int:
        """LRU eviction: if total image cache size exceeds limit, remove least-recently-accessed files."""
        if not self.image_cache_dir.exists():
            return 0

        files: List[Tuple[Path, os.stat_result]] = []
        total_bytes = 0

        for p in self.image_cache_dir.iterdir():
            if p.is_file():
                try:
                    stat = p.stat()
                    files.append((p, stat))
                    total_bytes += stat.st_size
                except OSError:
                    pass

        # Check bounds
        if total_bytes <= self.max_image_cache_bytes and len(files) <= self.max_image_files:
            return 0

        # Sort files ascending by atime (oldest accessed first)
        files.sort(key=lambda x: x[1].st_atime)

        target_bytes = int(self.max_image_cache_bytes * 0.75)  # Prune to 75% watermark
        target_files = int(self.max_image_files * 0.75)

        pruned_count = 0
        pruned_bytes = 0

        for p, stat in files:
            if total_bytes <= target_bytes and len(files) - pruned_count <= target_files:
                break
            try:
                p.unlink(missing_ok=True)
                pruned_count += 1
                pruned_bytes += stat.st_size
                total_bytes -= stat.st_size
            except OSError:
                pass

        if pruned_count > 0:
            logger.info(
                "LRU Cache Pruned: removed %d images (%.2f MB freed). Current size: %.2f MB",
                pruned_count,
                pruned_bytes / (1024 * 1024),
                total_bytes / (1024 * 1024),
            )
        return pruned_count

    def get_fallback_poster_svg(self) -> bytes:
        """Provide a clean fallback poster SVG when offline and image is not cached."""
        return FALLBACK_POSTER_SVG

    # =========================================================================
    # 3. Cache Metrics & Statistics (10.5)
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Return comprehensive cache statistics."""
        with self._lock:
            conn = self.db.get_connection()
            row = conn.execute("SELECT COUNT(*) as count FROM movie_metadata_cache;").fetchone()
            meta_count = row["count"] if row else 0

            # Image files stat
            img_count = 0
            img_bytes = 0
            if self.image_cache_dir.exists():
                for p in self.image_cache_dir.iterdir():
                    if p.is_file():
                        try:
                            st = p.stat()
                            img_count += 1
                            img_bytes += st.st_size
                        except OSError:
                            pass

            return {
                "metadata_entries": meta_count,
                "memory_cache_entries": len(self._mem_cache),
                "image_files": img_count,
                "image_bytes": img_bytes,
                "image_megabytes": round(img_bytes / (1024 * 1024), 2),
                "max_image_megabytes": round(self.max_image_cache_bytes / (1024 * 1024), 2),
                "cache_directory": str(self.image_cache_dir),
            }
