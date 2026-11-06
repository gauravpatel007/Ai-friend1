"""Verification Tests for Movie Hub Movie/Series Status Logic.

Requirements:
1. Favorite — Independent:
   - Adding a movie/series to Favorites works independently of Watchlist and Watched.
   - Adding or removing from Watchlist or Watched NEVER adds or removes it from Favorites.
   - A title can be both Favorited and in the Watchlist or Watched.

2. Watchlist & Watched — Mutually Exclusive:
   - A movie/series can be in the Watchlist OR marked as Watched, but not both simultaneously.
   - Adding to Watchlist automatically removes its Watched status.
   - Marking as Watched automatically removes it from the Watchlist.
   - Neither action affects Favorite status.

Test Scenarios Verified:
1. Favorite -> Watched: Favorite remains active.
2. Favorite -> Watchlist: Favorite remains active.
3. Watchlist -> Watched: Watchlist is removed; Favorite remains unchanged.
4. Watched -> Watchlist: Watched is removed; Favorite remains unchanged.
5. Remove Favorite: Watchlist/Watched status remains unchanged.
6. Works consistently across movies and TV series.
7. Persists after restarting application / re-opening SQLite database.
8. FastAPI HTTP REST Endpoints reflect identical rules.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


@pytest.fixture
def temp_db_path():
    """Provide a path for an isolated temporary SQLite database."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield Path(tmpdir) / "test_status_logic.db"


@pytest.fixture
def temp_db_manager(temp_db_path: Path) -> DatabaseManager:
    """Provide an isolated, temporary SQLite database manager."""
    manager = DatabaseManager(db_path=temp_db_path)
    try:
        yield manager
    finally:
        manager.close()


@pytest.fixture
def movie_repo(temp_db_manager: DatabaseManager) -> MovieStorageRepository:
    """Provide a MovieStorageRepository backed by the temporary database."""
    return MovieStorageRepository(db_manager=temp_db_manager)


# =============================================================================
# 1. Favorite -> Watched: Favorite remains active
# =============================================================================


def test_favorite_then_watched_favorite_remains_active(movie_repo: MovieStorageRepository):
    """Test Scenario 1: Favorite -> Watched keeps Favorite active (movies and series)."""
    for media_type in ["movie", "tv"]:
        item_id = 1001 if media_type == "movie" else 2001
        title = "Inception" if media_type == "movie" else "Breaking Bad"

        # Step 1: Add to Favorites (status='none', is_favorite=True)
        fav = movie_repo.set_favorite(
            tmdb_id=item_id,
            media_type=media_type,
            is_favorite=True,
            item_metadata={"title": title, "release_year": 2010},
        )
        assert fav.is_favorite is True
        assert fav.status == "none"

        # Step 2: Mark as Watched
        watched = movie_repo.mark_as_watched(tmdb_id=item_id, media_type=media_type)
        assert watched.status == "watched"
        assert watched.is_favorite is True  # Favorite MUST remain active!
        assert watched.watched_at is not None

        # Step 3: Verify collections and tracking summary
        summary = movie_repo.get_tracking_summary()
        assert item_id in summary["favorite_ids"]
        assert item_id in summary["watched_ids"]
        assert item_id not in summary["watchlist_ids"]

        fav_list = movie_repo.get_favorites(media_type=media_type)
        watched_list = movie_repo.get_watched(media_type=media_type)
        watchlist = movie_repo.get_watchlist(media_type=media_type)

        assert any(e.tmdb_id == item_id for e in fav_list)
        assert any(e.tmdb_id == item_id for e in watched_list)
        assert not any(e.tmdb_id == item_id for e in watchlist)


# =============================================================================
# 2. Favorite -> Watchlist: Favorite remains active
# =============================================================================


def test_favorite_then_watchlist_favorite_remains_active(movie_repo: MovieStorageRepository):
    """Test Scenario 2: Favorite -> Watchlist keeps Favorite active (movies and series)."""
    for media_type in ["movie", "tv"]:
        item_id = 1002 if media_type == "movie" else 2002
        title = "Interstellar" if media_type == "movie" else "Stranger Things"

        # Step 1: Add to Favorites
        fav = movie_repo.set_favorite(
            tmdb_id=item_id,
            media_type=media_type,
            is_favorite=True,
            item_metadata={"title": title, "release_year": 2014},
        )
        assert fav.is_favorite is True
        assert fav.status == "none"

        # Step 2: Add to Watchlist (without specifying is_favorite, or with is_favorite=None)
        saved = movie_repo.add_or_update_entry(
            tmdb_id=item_id,
            title=title,
            media_type=media_type,
            status="watchlist",
            is_favorite=None,  # Do not overwrite existing favorite
        )
        assert saved.status == "watchlist"
        assert saved.is_favorite is True  # Favorite MUST remain active!

        # Step 3: Verify collections and tracking summary
        summary = movie_repo.get_tracking_summary()
        assert item_id in summary["favorite_ids"]
        assert item_id in summary["watchlist_ids"]
        assert item_id not in summary["watched_ids"]

        fav_list = movie_repo.get_favorites(media_type=media_type)
        watchlist = movie_repo.get_watchlist(media_type=media_type)
        watched_list = movie_repo.get_watched(media_type=media_type)

        assert any(e.tmdb_id == item_id for e in fav_list)
        assert any(e.tmdb_id == item_id for e in watchlist)
        assert not any(e.tmdb_id == item_id for e in watched_list)


# =============================================================================
# 3. Watchlist -> Watched: Watchlist is removed; Favorite remains unchanged
# =============================================================================


def test_watchlist_then_watched_removes_watchlist_preserves_favorite(movie_repo: MovieStorageRepository):
    """Test Scenario 3: Watchlist -> Watched removes from Watchlist, Favorite unchanged."""
    for is_fav in [False, True]:
        item_id = 1003 if not is_fav else 1004
        title = f"Title #{item_id}"

        # Step 1: Add to Watchlist (and optionally favorite)
        movie_repo.add_or_update_entry(
            tmdb_id=item_id,
            title=title,
            media_type="movie",
            status="watchlist",
            is_favorite=is_fav,
        )

        entry_before = movie_repo.get_entry(item_id, "movie")
        assert entry_before is not None
        assert entry_before.status == "watchlist"
        assert entry_before.is_favorite is is_fav

        # Step 2: Mark as Watched
        updated = movie_repo.mark_as_watched(tmdb_id=item_id, media_type="movie")
        assert updated.status == "watched"
        assert updated.is_favorite is is_fav  # Favorite remains unchanged!
        assert updated.watched_at is not None

        # Step 3: Mutual exclusivity check
        summary = movie_repo.get_tracking_summary()
        assert item_id not in summary["watchlist_ids"]  # Watchlist removed!
        assert item_id in summary["watched_ids"]        # Marked as watched!
        if is_fav:
            assert item_id in summary["favorite_ids"]   # Favorite preserved!
        else:
            assert item_id not in summary["favorite_ids"]


# =============================================================================
# 4. Watched -> Watchlist: Watched is removed; Favorite remains unchanged
# =============================================================================


def test_watched_then_watchlist_removes_watched_preserves_favorite(movie_repo: MovieStorageRepository):
    """Test Scenario 4: Watched -> Watchlist removes Watched, Favorite unchanged."""
    for is_fav in [False, True]:
        item_id = 2003 if not is_fav else 2004
        title = f"Series #{item_id}"

        # Step 1: Mark as Watched (and optionally favorite)
        movie_repo.add_or_update_entry(
            tmdb_id=item_id,
            title=title,
            media_type="tv",
            status="watched",
            is_favorite=is_fav,
        )

        entry_before = movie_repo.get_entry(item_id, "tv")
        assert entry_before is not None
        assert entry_before.status == "watched"
        assert entry_before.is_favorite is is_fav

        # Step 2: Add to Watchlist
        saved = movie_repo.add_or_update_entry(
            tmdb_id=item_id,
            title=title,
            media_type="tv",
            status="watchlist",
            is_favorite=None,  # Preserves favorite
        )
        assert saved.status == "watchlist"
        assert saved.is_favorite is is_fav  # Favorite remains unchanged!
        assert saved.watched_at is None     # Watched timestamp cleared!

        # Step 3: Mutual exclusivity check
        summary = movie_repo.get_tracking_summary()
        assert item_id in summary["watchlist_ids"]      # Now on watchlist!
        assert item_id not in summary["watched_ids"]    # Watched removed!
        if is_fav:
            assert item_id in summary["favorite_ids"]   # Favorite preserved!
        else:
            assert item_id not in summary["favorite_ids"]


# =============================================================================
# 5. Remove Favorite: Watchlist/Watched status remains unchanged
# =============================================================================


def test_remove_favorite_preserves_watchlist_and_watched_status(movie_repo: MovieStorageRepository):
    """Test Scenario 5: Removing Favorite preserves Watchlist or Watched status."""
    # Case A: In Watchlist + Favorited -> Unfavorite -> Remains in Watchlist
    movie_repo.add_or_update_entry(
        tmdb_id=3001,
        title="Watchlisted & Favorited",
        media_type="movie",
        status="watchlist",
        is_favorite=True,
    )
    unfav_a = movie_repo.set_favorite(tmdb_id=3001, media_type="movie", is_favorite=False)
    assert unfav_a.is_favorite is False
    assert unfav_a.status == "watchlist"  # Watchlist status preserved!

    summary_a = movie_repo.get_tracking_summary()
    assert 3001 in summary_a["watchlist_ids"]
    assert 3001 not in summary_a["favorite_ids"]
    assert 3001 not in summary_a["watched_ids"]

    # Case B: Watched + Favorited -> Unfavorite -> Remains Watched
    movie_repo.add_or_update_entry(
        tmdb_id=3002,
        title="Watched & Favorited",
        media_type="tv",
        status="watched",
        is_favorite=True,
    )
    unfav_b = movie_repo.set_favorite(tmdb_id=3002, media_type="tv", is_favorite=False)
    assert unfav_b.is_favorite is False
    assert unfav_b.status == "watched"  # Watched status preserved!

    summary_b = movie_repo.get_tracking_summary()
    assert 3002 in summary_b["watched_ids"]
    assert 3002 not in summary_b["favorite_ids"]
    assert 3002 not in summary_b["watchlist_ids"]


# =============================================================================
# 6. Persistence across DB Reconnection (Simulated Application Restart)
# =============================================================================


def test_status_logic_persists_across_application_restart(temp_db_path: Path):
    """Verify that all independent/mutually-exclusive states survive application restart."""
    # 1. First session: Create records with distinct states
    manager1 = DatabaseManager(db_path=temp_db_path)
    repo1 = MovieStorageRepository(db_manager=manager1)

    # 4001: Favorite + Watchlist
    repo1.set_favorite(4001, "movie", True, {"title": "Title 4001"})
    repo1.add_or_update_entry(4001, "Title 4001", "movie", status="watchlist")

    # 4002: Favorite + Watched
    repo1.set_favorite(4002, "tv", True, {"title": "Title 4002"})
    repo1.mark_as_watched(4002, "tv")

    # 4003: Only Favorite
    repo1.set_favorite(4003, "movie", True, {"title": "Title 4003"})

    # 4004: Only Watchlist
    repo1.add_or_update_entry(4004, "Title 4004", "movie", status="watchlist")

    # 4005: Only Watched
    repo1.mark_as_watched(4005, "tv", {"title": "Title 4005"})

    manager1.close()

    # 2. Second session (Simulated application restart): Read from same DB
    manager2 = DatabaseManager(db_path=temp_db_path)
    repo2 = MovieStorageRepository(db_manager=manager2)

    try:
        e4001 = repo2.get_entry(4001, "movie")
        assert e4001 is not None
        assert e4001.is_favorite is True
        assert e4001.status == "watchlist"

        e4002 = repo2.get_entry(4002, "tv")
        assert e4002 is not None
        assert e4002.is_favorite is True
        assert e4002.status == "watched"

        e4003 = repo2.get_entry(4003, "movie")
        assert e4003 is not None
        assert e4003.is_favorite is True
        assert e4003.status == "none"

        e4004 = repo2.get_entry(4004, "movie")
        assert e4004 is not None
        assert e4004.is_favorite is False
        assert e4004.status == "watchlist"

        e4005 = repo2.get_entry(4005, "tv")
        assert e4005 is not None
        assert e4005.is_favorite is False
        assert e4005.status == "watched"

        summary = repo2.get_tracking_summary()
        assert set(summary["favorite_ids"]) == {4001, 4002, 4003}
        assert set(summary["watchlist_ids"]) == {4001, 4004}
        assert set(summary["watched_ids"]) == {4002, 4005}

        # Mutual exclusivity strictly preserved: No ID is in both watchlist and watched!
        assert set(summary["watchlist_ids"]).isdisjoint(set(summary["watched_ids"]))

    finally:
        manager2.close()


# =============================================================================
# 7. FastAPI Endpoints Integration Verification
# =============================================================================


def test_fastapi_endpoints_status_logic_flow(temp_db_manager: DatabaseManager):
    """Test that FastAPI HTTP routes enforce the identical status rules."""
    app = create_app()
    app.state.db_manager = temp_db_manager

    with TestClient(app) as client:
        # 1. Favorite an item
        fav_res = client.post(
            "/api/movies/storage/favorite/movie/5001",
            json={"is_favorite": True, "title": "The Matrix", "release_year": 1999},
        )
        assert fav_res.status_code == 200
        assert fav_res.json()["is_favorite"] is True
        assert fav_res.json()["status"] == "none"

        # 2. Add to Watchlist via HTTP POST (does not send is_favorite -> defaults to None)
        wl_res = client.post(
            "/api/movies/storage/watchlist",
            json={"tmdb_id": 5001, "media_type": "movie", "title": "The Matrix"},
        )
        assert wl_res.status_code == 200
        data = wl_res.json()
        assert data["status"] == "watchlist"
        assert data["is_favorite"] is True  # Favorite preserved!

        # 3. Transition Watchlist -> Watched via HTTP POST
        watched_res = client.post("/api/movies/storage/watched/movie/5001")
        assert watched_res.status_code == 200
        data = watched_res.json()
        assert data["status"] == "watched"
        assert data["is_favorite"] is True  # Favorite preserved!

        # Verify summary reflects watched and favorite, NOT watchlist
        sum_res = client.get("/api/movies/storage/summary")
        assert sum_res.status_code == 200
        summary = sum_res.json()
        assert 5001 in summary["favorite_ids"]
        assert 5001 in summary["watched_ids"]
        assert 5001 not in summary["watchlist_ids"]

        # 4. Transition Watched -> Watchlist via HTTP POST
        wl_res2 = client.post(
            "/api/movies/storage/watchlist",
            json={"tmdb_id": 5001, "media_type": "movie", "title": "The Matrix"},
        )
        assert wl_res2.status_code == 200
        data2 = wl_res2.json()
        assert data2["status"] == "watchlist"
        assert data2["is_favorite"] is True  # Favorite preserved!

        # Verify summary reflects watchlist and favorite, NOT watched
        sum_res2 = client.get("/api/movies/storage/summary")
        summary2 = sum_res2.json()
        assert 5001 in summary2["favorite_ids"]
        assert 5001 in summary2["watchlist_ids"]
        assert 5001 not in summary2["watched_ids"]

        # 5. Unfavorite via HTTP POST -> Watchlist remains active!
        unfav_res = client.post(
            "/api/movies/storage/favorite/movie/5001",
            json={"is_favorite": False},
        )
        assert unfav_res.status_code == 200
        data3 = unfav_res.json()
        assert data3["is_favorite"] is False
        assert data3["status"] == "watchlist"  # Watchlist remains intact!

        sum_res3 = client.get("/api/movies/storage/summary")
        summary3 = sum_res3.json()
        assert 5001 in summary3["watchlist_ids"]
        assert 5001 not in summary3["favorite_ids"]
        assert 5001 not in summary3["watched_ids"]


# =============================================================================
# 9. Genres Storage & Retrieval across Watchlist, Favorites, Watched
# =============================================================================


def test_genres_persistence_and_retrieval(movie_repo: MovieStorageRepository, temp_db_manager: DatabaseManager):
    """Verify genres metadata persists and is retrieved across watchlist, favorites, and watched."""
    # 1. Add to watchlist with genres
    entry = movie_repo.add_or_update_entry(
        tmdb_id=8888,
        media_type="movie",
        title="La La Land",
        genres="Comedy, Romance, Drama",
        release_year=2016,
        status="watchlist",
    )
    assert entry.genres == "Comedy, Romance, Drama"

    # Verify retrieved from watchlist
    wl = movie_repo.get_watchlist(media_type="movie")
    found = [e for e in wl if e.tmdb_id == 8888][0]
    assert found.genres == "Comedy, Romance, Drama"

    # 2. Mark as watched, preserving genres
    watched_entry = movie_repo.mark_as_watched(tmdb_id=8888, media_type="movie")
    assert watched_entry.genres == "Comedy, Romance, Drama"

    watched_list = movie_repo.get_watched(media_type="movie")
    found_watched = [e for e in watched_list if e.tmdb_id == 8888][0]
    assert found_watched.genres == "Comedy, Romance, Drama"

    # 3. Mark as favorite with custom genres
    fav_entry = movie_repo.set_favorite(
        tmdb_id=9999,
        media_type="tv",
        is_favorite=True,
        item_metadata={"title": "Friends", "genres": "Comedy, Romance"},
    )
    assert fav_entry.genres == "Comedy, Romance"

    fav_list = movie_repo.get_favorites(media_type="tv")
    found_fav = [e for e in fav_list if e.tmdb_id == 9999][0]
    assert found_fav.genres == "Comedy, Romance"


def test_genres_via_rest_endpoints(temp_db_manager: DatabaseManager):
    """Verify genres sent via REST API are persisted and returned in responses."""
    test_app = create_app()
    test_app.state.movie_storage_repo = MovieStorageRepository(db_manager=temp_db_manager)

    with TestClient(test_app) as client:
        # Add to watchlist with genres
        res = client.post(
            "/api/movies/storage/watchlist",
            json={
                "tmdb_id": 7777,
                "media_type": "movie",
                "title": "Interstellar",
                "genres": "Adventure, Drama, Science Fiction",
                "release_year": 2014,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["genres"] == "Adventure, Drama, Science Fiction"

        # Query watchlist
        wl_res = client.get("/api/movies/storage/watchlist")
        assert wl_res.status_code == 200
        items = wl_res.json()
        match = [i for i in items if i["tmdb_id"] == 7777][0]
        assert match["genres"] == "Adventure, Drama, Science Fiction"
