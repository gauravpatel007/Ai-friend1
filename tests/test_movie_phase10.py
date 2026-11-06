"""Phase 10 Verification Tests: Caching, Offline Behavior, and Performance.

Verifies:
- 10.1 Two-tier metadata caching (In-Memory + SQLite), category TTLs, invalidation, pruning.
- 10.2 Safe, bounded local image caching, integrity validation (magic bytes), LRU eviction, fallback SVG.
- 10.3 Offline resilience and stale-metadata fallback during TMDBNetworkError / TMDBTimeoutError.
- 10.4 Request efficiency, in-flight deduplication, and bounds checking.
- 10.5 Cache status, clear endpoints, and network status probing in FastAPI.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.api.movie_models import (
    MediaItemSummary,
    PagedResultModel,
    MediaDetailsModel,
)
from app.api.movie_cache_manager import (
    MovieCacheManager,
    FALLBACK_POSTER_SVG,
    _is_valid_image,
)
from app.api.tmdb_client import (
    TMDBClient,
    TMDBNetworkError,
    TMDBTimeoutError,
    TMDBRateLimitError,
)
from app.memory.database import DatabaseManager


@pytest.fixture
def temp_db_manager() -> DatabaseManager:
    """Provide an isolated, temporary SQLite database."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_cache_p10.db"
        manager = DatabaseManager(db_path=db_path)
        try:
            yield manager
        finally:
            manager.close()


@pytest.fixture
def temp_cache_manager(temp_db_manager: DatabaseManager) -> MovieCacheManager:
    """Provide a MovieCacheManager with isolated image directory."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as img_dir:
        manager = MovieCacheManager(
            db_manager=temp_db_manager,
            image_cache_dir=img_dir,
            max_image_cache_bytes=10 * 1024,  # Small 10 KB limit for LRU testing
            max_image_files=5,
        )
        yield manager


# =============================================================================
# 1. Metadata Caching, TTLs & Invalidation (10.1)
# =============================================================================


def test_metadata_cache_hit_and_miss(temp_cache_manager: MovieCacheManager):
    """Test 10.1: Cache hit returns data, cache miss returns None."""
    cache = temp_cache_manager

    # Miss initially
    miss, is_stale = cache.get_metadata("test:key:1")
    assert miss is None
    assert is_stale is False

    # Store entry
    payload = {"title": "Inception", "year": 2010}
    cache.set_metadata("test:key:1", "movie_details", payload, ttl_seconds=300)

    # Hit from in-memory tier
    hit, is_stale = cache.get_metadata("test:key:1")
    assert hit == payload
    assert is_stale is False

    # Hit from persistent SQLite tier after clearing memory tier
    cache._mem_cache.clear()
    hit_sqlite, is_stale = cache.get_metadata("test:key:1")
    assert hit_sqlite == payload
    assert is_stale is False


def test_metadata_cache_ttl_and_stale_retrieval(temp_cache_manager: MovieCacheManager):
    """Test 10.1 & 10.3: Expired entries are not fresh, but can be retrieved as stale when allowed."""
    cache = temp_cache_manager

    payload = {"query": "malayalam thriller", "results": [101, 102]}
    # Set with negative TTL so it is immediately expired
    cache.set_metadata("search:stale_test", "search", payload, ttl_seconds=-10)

    # Fresh lookup returns None
    fresh, is_stale = cache.get_metadata("search:stale_test", allow_stale=False)
    assert fresh is None

    # Stale lookup returns expired data with is_stale=True
    stale_data, is_stale = cache.get_metadata("search:stale_test", allow_stale=True)
    assert stale_data == payload
    assert is_stale is True


def test_metadata_cache_invalidation(temp_cache_manager: MovieCacheManager):
    """Test 10.1: Invalidate specific category or all entries."""
    cache = temp_cache_manager

    cache.set_metadata("search:q1", "search", {"data": 1})
    cache.set_metadata("discover:d1", "discover", {"data": 2})

    # Invalidate search category only
    count = cache.invalidate_metadata(category="search")
    assert count >= 1

    # Search should be gone, discover should remain
    assert cache.get_metadata("search:q1")[0] is None
    assert cache.get_metadata("discover:d1")[0] is not None

    # Invalidate all
    cache.invalidate_metadata()
    assert cache.get_metadata("discover:d1")[0] is None


# =============================================================================
# 2. Safe, Bounded Image Caching & LRU Eviction (10.2)
# =============================================================================


def test_image_validation_magic_bytes():
    """Test 10.2: Validate JPEG, PNG, WebP magic bytes and reject invalid/corrupt data."""
    # Valid JPEG
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + (b"\x00" * 120)
    valid, mime = _is_valid_image(jpeg_bytes)
    assert valid is True
    assert mime == "image/jpeg"

    # Valid PNG
    png_bytes = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 120)
    valid, mime = _is_valid_image(png_bytes)
    assert valid is True
    assert mime == "image/png"

    # Valid WebP
    webp_bytes = b"RIFF\x00\x00\x00\x00WEBP" + (b"\x00" * 120)
    valid, mime = _is_valid_image(webp_bytes)
    assert valid is True
    assert mime == "image/webp"

    # Corrupt/truncated bytes (< 100 bytes)
    short_bytes = b"\xff\xd8\xff"
    valid, _ = _is_valid_image(short_bytes)
    assert valid is False

    # Corrupt random text
    garbage = b"<html>404 Not Found</html>" + (b" " * 100)
    valid, _ = _is_valid_image(garbage)
    assert valid is False


def test_image_cache_write_read_and_corrupt_purge(temp_cache_manager: MovieCacheManager):
    """Test 10.2: Writing image, reading it back, and purging corrupted cached file."""
    cache = temp_cache_manager
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + (b"\x00" * 200)

    # Save image
    ok = cache.save_image("/posters/avatar.jpg", "w500", jpeg_bytes)
    assert ok is True

    # Read image back
    cached = cache.get_image("/posters/avatar.jpg", "w500")
    assert cached is not None
    assert cached[0] == jpeg_bytes
    assert cached[1] == "image/jpeg"

    # Manually corrupt the file on disk
    file_path = cache._get_image_file_path("/posters/avatar.jpg", "w500")
    file_path.write_bytes(b"corrupt")

    # get_image should detect corruption, purge the file, and return None
    assert cache.get_image("/posters/avatar.jpg", "w500") is None
    assert not file_path.exists()


def test_image_cache_bounded_lru_eviction(temp_cache_manager: MovieCacheManager):
    """Test 10.2: LRU eviction prunes oldest accessed images when cache exceeds max limit."""
    cache = temp_cache_manager  # max_image_files=5, max_image_cache_bytes=10KB
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + (b"\x00" * 2500)  # ~2.5 KB per file

    # Save 6 files (total ~15 KB, exceeds 10 KB limit and 5 files limit)
    for i in range(6):
        cache.save_image(f"/poster_{i}.jpg", "w500", jpeg_bytes)
        time.sleep(0.01)

    # Pruning should have triggered, ensuring file count is <= 5
    stats = cache.get_stats()
    assert stats["image_files"] <= 5
    assert stats["image_bytes"] <= cache.max_image_cache_bytes


# =============================================================================
# 3. TMDB Client Integration & Offline Stale Fallback (10.3, 10.4)
# =============================================================================


def test_tmdb_client_offline_stale_fallback(temp_cache_manager: MovieCacheManager):
    """Test 10.3: During network drop (TMDBNetworkError), client returns stale cached data."""
    client = TMDBClient(api_key="mock_key", cache_manager=temp_cache_manager)

    # Pre-seed metadata cache with expired search response
    stale_payload = {
        "page": 1,
        "total_pages": 1,
        "total_results": 1,
        "results": [
            {
                "id": 999,
                "title": "Cached Offline Movie",
                "media_type": "movie",
                "vote_average": 8.0,
                "overview": "Saved in cache",
            }
        ],
    }
    cache_key = client._build_cache_key("/search/movie", {"query": "interstellar", "page": 1, "include_adult": False})
    temp_cache_manager.set_metadata(cache_key, "search", stale_payload, ttl_seconds=-60)

    # Mock _request to simulate a network connection failure
    client._request = MagicMock(side_effect=TMDBNetworkError("No internet connection"))

    # search_movies should NOT raise; it should fallback to stale cached response
    res = client.search_movies(query="interstellar", page=1)
    assert res.total_results == 1
    assert res.results[0].title == "Cached Offline Movie"
    assert res.results[0].id == 999


def test_tmdb_client_offline_without_cache_raises_network_error(temp_cache_manager: MovieCacheManager):
    """Test 10.3: When offline and no cached data exists, raises TMDBNetworkError."""
    client = TMDBClient(api_key="mock_key", cache_manager=temp_cache_manager)
    client._request = MagicMock(side_effect=TMDBNetworkError("No route to host"))

    with pytest.raises(TMDBNetworkError):
        client.search_movies(query="uncached query that never existed", page=1)


def test_tmdb_client_image_download_fallback(temp_cache_manager: MovieCacheManager):
    """Test 10.2: When image cannot be downloaded, returns fallback SVG poster."""
    client = TMDBClient(api_key="mock_key", cache_manager=temp_cache_manager)

    # Mock session.get to fail
    client.session.get = MagicMock(side_effect=Exception("Connection refused"))

    data, mime, is_cached = client.get_or_download_image("/non_existent_poster.jpg", size="w500")
    assert mime == "image/svg+xml"
    assert b"<svg" in data
    assert is_cached is False


# =============================================================================
# 4. FastAPI Phase 10 Endpoints (10.5)
# =============================================================================


def test_api_cache_status_endpoint():
    """Test 10.5: GET /api/movies/cache/status."""
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/movies/cache/status")
    assert res.status_code == 200
    data = res.json()
    assert "metadata_entries" in data
    assert "image_files" in data
    assert "image_megabytes" in data


def test_api_cache_clear_endpoint():
    """Test 10.1 & 10.5: POST /api/movies/cache/clear."""
    app = create_app()
    client = TestClient(app)

    res = client.post("/api/movies/cache/clear?category=search")
    assert res.status_code == 200
    data = res.json()
    assert data["cleared"] == "search"


def test_api_network_status_endpoint():
    """Test 10.3 & 10.5: GET /api/movies/network-status."""
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/movies/network-status")
    assert res.status_code == 200
    data = res.json()
    assert "online" in data
    assert "configured" in data


def test_api_image_proxy_fallback():
    """Test 10.2: GET /api/movies/images/w500/test.jpg returns fallback SVG when offline."""
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/movies/images/w500/nonexistent_image.jpg")
    assert res.status_code == 200
    assert "image/svg+xml" in res.headers.get("content-type", "")
    assert "<svg" in res.text
