"""Movie Hub Phase 10 Performance Profiler.

Benchmarks and measures actual execution times for:
1. Local SQLite Database operations (inserts, queries, tracking summary).
2. Two-tier Metadata Caching (in-memory vs SQLite persistent tier).
3. Image Caching (read, write, verification, LRU pruning).
4. Search/Discovery cache hit vs cold round-trip speedup.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository
from app.api.movie_cache_manager import MovieCacheManager, FALLBACK_POSTER_SVG
from app.api.movie_models import MovieUserPreferences


def profile_database_operations(repo: MovieStorageRepository) -> Dict[str, float]:
    """Measure SQLite read/write latency for movie tracking and preferences."""
    results = {}

    # 1. Benchmark 100 upserts
    start = time.perf_counter()
    for i in range(100):
        repo.add_or_update_entry(
            tmdb_id=1000 + i,
            title=f"Benchmark Movie #{i}",
            media_type="movie",
            release_year=2020 + (i % 5),
            original_language="hi" if i % 2 == 0 else "en",
            vote_average=7.5 + (i % 20) / 10.0,
            status="watchlist" if i % 3 == 0 else ("watched" if i % 3 == 1 else "none"),
            is_favorite=(i % 5 == 0),
            user_rating=8 if i % 4 == 0 else None,
        )
    dur_upsert = (time.perf_counter() - start) * 1000
    results["100_upserts_ms"] = round(dur_upsert, 2)
    results["avg_upsert_ms"] = round(dur_upsert / 100, 3)

    # 2. Benchmark tracking summary retrieval
    start = time.perf_counter()
    for _ in range(50):
        repo.get_tracking_summary()
    dur_summary = (time.perf_counter() - start) * 1000
    results["avg_tracking_summary_ms"] = round(dur_summary / 50, 3)

    # 3. Benchmark filtered list query
    start = time.perf_counter()
    for _ in range(50):
        repo.list_entries(status="watchlist", limit=50)
    dur_list = (time.perf_counter() - start) * 1000
    results["avg_watchlist_query_ms"] = round(dur_list / 50, 3)

    # 4. Benchmark preference save and read
    start = time.perf_counter()
    for _ in range(50):
        repo.update_preferences(
            preferred_genres=["Action", "Thriller"],
            preferred_languages=["ml", "hi"],
        )
        repo.get_preferences()
    dur_prefs = (time.perf_counter() - start) * 1000
    results["avg_preference_cycle_ms"] = round(dur_prefs / 50, 3)

    return results


def profile_metadata_cache(cache: MovieCacheManager) -> Dict[str, float]:
    """Measure latency of memory tier vs SQLite tier for metadata caching."""
    results = {}

    dummy_data = {
        "page": 1,
        "total_pages": 10,
        "total_results": 200,
        "results": [
            {"id": i, "title": f"Cached Item #{i}", "media_type": "movie", "vote_average": 8.0}
            for i in range(20)
        ],
    }

    # 1. Benchmark set_metadata (memory + SQLite write)
    start = time.perf_counter()
    for i in range(50):
        cache.set_metadata(f"discover:benchmark:{i}", "discover", dummy_data, ttl_seconds=1800)
    dur_set = (time.perf_counter() - start) * 1000
    results["avg_metadata_write_ms"] = round(dur_set / 50, 3)

    # 2. Benchmark Tier 1 In-Memory Cache Read
    start = time.perf_counter()
    for i in range(100):
        data, is_stale = cache.get_metadata(f"discover:benchmark:{i % 50}")
        assert data is not None
        assert not is_stale
    dur_mem_read = (time.perf_counter() - start) * 1000
    results["avg_memory_cache_read_ms"] = round(dur_mem_read / 100, 4)

    # 3. Benchmark Tier 2 SQLite Persistent Read (clear memory cache to force disk hit)
    cache._mem_cache.clear()
    start = time.perf_counter()
    for i in range(50):
        data, is_stale = cache.get_metadata(f"discover:benchmark:{i}")
        assert data is not None
        # Clear memory cache each loop to force SQLite read
        cache._mem_cache.clear()
    dur_sqlite_read = (time.perf_counter() - start) * 1000
    results["avg_sqlite_cache_read_ms"] = round(dur_sqlite_read / 50, 3)

    return results


def profile_image_cache(cache: MovieCacheManager) -> Dict[str, float]:
    """Measure disk image cache read, write, and LRU pruning times."""
    results = {}

    # Valid dummy JPEG bytes (FF D8 FF ...)
    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00" + (b"\x00" * 4096)

    # 1. Benchmark image write
    start = time.perf_counter()
    for i in range(50):
        cache.save_image(f"/test_poster_{i}.jpg", "w500", dummy_jpeg)
    dur_write = (time.perf_counter() - start) * 1000
    results["avg_image_disk_write_ms"] = round(dur_write / 50, 3)

    # 2. Benchmark image read
    start = time.perf_counter()
    for i in range(100):
        data = cache.get_image(f"/test_poster_{i % 50}.jpg", "w500")
        assert data is not None
    dur_read = (time.perf_counter() - start) * 1000
    results["avg_image_disk_read_ms"] = round(dur_read / 100, 4)

    # 3. Benchmark LRU eviction
    start = time.perf_counter()
    cache.prune_image_cache_if_needed()
    dur_prune = (time.perf_counter() - start) * 1000
    results["lru_pruning_check_ms"] = round(dur_prune, 3)

    return results


def run_benchmark():
    print("=" * 60)
    print(" Movie Hub Phase 10: Performance Profiling Benchmark")
    print("=" * 60)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "profile_movie_hub.db"
        img_dir = Path(tmpdir) / "img_cache"

        db_mgr = DatabaseManager(db_path=db_path)
        repo = MovieStorageRepository(db_manager=db_mgr)
        cache = MovieCacheManager(db_manager=db_mgr, image_cache_dir=img_dir)

        try:
            print("\n1. Profiling SQLite Database Operations...")
            db_res = profile_database_operations(repo)
            for k, v in db_res.items():
                print(f"   - {k}: {v} ms")

            print("\n2. Profiling Two-Tier Metadata Caching...")
            meta_res = profile_metadata_cache(cache)
            for k, v in meta_res.items():
                print(f"   - {k}: {v} ms")

            print("\n3. Profiling Bounded Image Disk Caching...")
            img_res = profile_image_cache(cache)
            for k, v in img_res.items():
                print(f"   - {k}: {v} ms")

            stats = cache.get_stats()
            print("\n4. Final Cache Storage Metrics:")
            print(f"   - Metadata Entries: {stats['metadata_entries']}")
            print(f"   - Image Files: {stats['image_files']} ({stats['image_megabytes']} MB)")

            speedup = (
                meta_res["avg_sqlite_cache_read_ms"] / meta_res["avg_memory_cache_read_ms"]
                if meta_res["avg_memory_cache_read_ms"] > 0 else 0
            )
            print(f"\n>> In-Memory Tier vs SQLite Tier Speedup: {speedup:.1f}x faster")
            print("=" * 60)
            print(" Benchmark completed successfully.")
            print("=" * 60)
        finally:
            db_mgr.close()


if __name__ == "__main__":
    run_benchmark()
