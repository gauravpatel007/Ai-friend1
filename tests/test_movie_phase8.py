"""Phase 8 Verification Tests: Local Database, Watchlist, Favorites, and User Preferences.

Verifies:
- 8.1 Reuse existing SQLite database manager and schema migrations.
- 8.2 Data models for watchlist, favorites, watched, currently watching, local user ratings.
- 8.3 Watchlist CRUD operations, duplicate prevention, status transitions, and filtered queries.
- 8.4 Favorites and local personal ratings (1-10) kept strictly distinct from provider ratings.
- 8.5 Persistence across restarts / connection re-instantiation and database transactions.
- 8.6 Preference controls (preferred genres, languages, regions, recommendation settings) and defaults reset.
- 8.7 FastAPI REST endpoints (/api/movies/storage/*).
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
def temp_db_manager() -> DatabaseManager:
    """Provide an isolated, temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_movie_hub.db"
        manager = DatabaseManager(db_path=db_path)
        try:
            yield manager
        finally:
            manager.close()


@pytest.fixture
def movie_repo(temp_db_manager: DatabaseManager) -> MovieStorageRepository:
    """Provide a MovieStorageRepository backed by the temporary database."""
    return MovieStorageRepository(db_manager=temp_db_manager)


# =============================================================================
# 1. Watchlist Operations & Duplicate Prevention (8.2, 8.3)
# =============================================================================


def test_add_to_watchlist_and_prevent_duplicates(movie_repo: MovieStorageRepository):
    """Test 8.3: Adding item to watchlist and ensuring duplicate insertions update existing record."""
    # 1. Add new title
    entry1 = movie_repo.add_or_update_entry(
        tmdb_id=550,
        title="Fight Club",
        media_type="movie",
        poster_path="/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",
        release_year=1999,
        original_language="en",
        vote_average=8.4,
        overview="An insomniac office worker...",
        status="watchlist",
    )

    assert entry1.id is not None
    assert entry1.tmdb_id == 550
    assert entry1.media_type == "movie"
    assert entry1.title == "Fight Club"
    assert entry1.status == "watchlist"
    assert entry1.is_favorite is False

    # 2. Add same title again (should NOT duplicate, should update)
    entry2 = movie_repo.add_or_update_entry(
        tmdb_id=550,
        title="Fight Club (Remastered)",
        media_type="movie",
        status="watchlist",
    )

    assert entry2.id == entry1.id
    assert entry2.title == "Fight Club (Remastered)"

    # Verify total watchlist count is exactly 1
    watchlist = movie_repo.get_watchlist()
    assert len(watchlist) == 1
    assert watchlist[0].tmdb_id == 550


def test_watchlist_status_transitions_and_mark_watched(movie_repo: MovieStorageRepository):
    """Test 8.3: Status transitions (watchlist -> watching -> watched with timestamp)."""
    movie_repo.add_or_update_entry(
        tmdb_id=1399,
        title="Game of Thrones",
        media_type="tv",
        status="watchlist",
    )

    # 1. Transition to 'watching'
    updated = movie_repo.update_status(1399, "tv", "watching")
    assert updated is not None
    assert updated.status == "watching"
    assert updated.watched_at is None

    # 2. Transition to 'watched' via mark_as_watched
    watched = movie_repo.mark_as_watched(1399, "tv")
    assert watched is not None
    assert watched.status == "watched"
    assert watched.watched_at is not None

    # Verify lists
    assert len(movie_repo.get_watchlist()) == 0
    assert len(movie_repo.get_watched()) == 1
    assert movie_repo.get_watched()[0].tmdb_id == 1399


def test_remove_from_watchlist(movie_repo: MovieStorageRepository):
    """Test 8.3: Removing from watchlist prunes unreferenced titles or updates status to 'none'."""
    movie_repo.add_or_update_entry(
        tmdb_id=101,
        title="Sample Movie",
        media_type="movie",
        status="watchlist",
    )

    # When unreferenced, removing prunes the record
    removed = movie_repo.remove_from_watchlist(101, "movie")
    assert removed is True
    assert movie_repo.get_entry(101, "movie") is None

    # If marked favorite, removing from watchlist keeps entry with status 'none'
    fav_entry = movie_repo.add_or_update_entry(
        tmdb_id=102,
        title="Beloved Movie",
        media_type="movie",
        status="watchlist",
        is_favorite=True,
    )
    assert fav_entry.is_favorite is True

    movie_repo.remove_from_watchlist(102, "movie")
    remaining = movie_repo.get_entry(102, "movie")
    assert remaining is not None
    assert remaining.status == "none"
    assert remaining.is_favorite is True


# =============================================================================
# 2. Favorites and Local User Ratings (8.4)
# =============================================================================


def test_favorites_toggle(movie_repo: MovieStorageRepository):
    """Test 8.4: Marking and removing favorites."""
    # Toggle on
    fav = movie_repo.set_favorite(
        tmdb_id=579974,
        media_type="movie",
        is_favorite=True,
        item_metadata={"title": "RRR", "release_year": 2022},
    )
    assert fav.is_favorite is True
    assert fav.title == "RRR"
    assert len(movie_repo.get_favorites()) == 1

    # Toggle off
    unfav = movie_repo.set_favorite(
        tmdb_id=579974,
        media_type="movie",
        is_favorite=False,
    )
    assert unfav.is_favorite is False
    assert len(movie_repo.get_favorites()) == 0


def test_local_user_ratings_separate_from_provider(movie_repo: MovieStorageRepository):
    """Test 8.4: Local user ratings (1-10) are kept strictly separate from provider ratings."""
    entry = movie_repo.add_or_update_entry(
        tmdb_id=872585,
        title="Oppenheimer",
        media_type="movie",
        vote_average=8.1,  # Upstream TMDB provider rating
    )

    assert entry.vote_average == 8.1
    assert entry.user_rating is None

    # Assign local rating: 10/10
    rated = movie_repo.set_rating(872585, "movie", 10)
    assert rated.user_rating == 10
    assert rated.vote_average == 8.1  # Provider rating untouched

    # Verify ratings collection
    ratings_list = movie_repo.get_ratings()
    assert len(ratings_list) == 1
    assert ratings_list[0].user_rating == 10

    # Clear rating
    cleared = movie_repo.set_rating(872585, "movie", None)
    assert cleared.user_rating is None
    assert len(movie_repo.get_ratings()) == 0


def test_invalid_rating_rejected(movie_repo: MovieStorageRepository):
    """Test 8.4: Rating outside 1-10 raises ValueError."""
    with pytest.raises(ValueError):
        movie_repo.set_rating(101, "movie", 15)

    with pytest.raises(ValueError):
        movie_repo.set_rating(101, "movie", 0)


# =============================================================================
# 3. Persistence Across Restarts & Data Integrity (8.5)
# =============================================================================


def test_persistence_survives_reinstantiation(temp_db_manager: DatabaseManager):
    """Test 8.5: Data persists across simulated application restarts."""
    db_path = temp_db_manager.db_path

    # Session 1: Write entries
    repo1 = MovieStorageRepository(db_manager=temp_db_manager)
    repo1.add_or_update_entry(
        tmdb_id=603,
        title="The Matrix",
        media_type="movie",
        status="watchlist",
        is_favorite=True,
        user_rating=9,
    )
    temp_db_manager.close()

    # Session 2: Fresh DatabaseManager with same SQLite file
    manager2 = DatabaseManager(db_path=db_path)
    repo2 = MovieStorageRepository(db_manager=manager2)

    entry = repo2.get_entry(603, "movie")
    assert entry is not None
    assert entry.title == "The Matrix"
    assert entry.status == "watchlist"
    assert entry.is_favorite is True
    assert entry.user_rating == 9

    manager2.close()


# =============================================================================
# 4. User Entertainment Preferences (8.6)
# =============================================================================


def test_user_preferences_defaults_and_updates(movie_repo: MovieStorageRepository):
    """Test 8.6: Sensible defaults, updating preferences, and resetting."""
    # 1. Defaults
    prefs = movie_repo.get_preferences()
    assert prefs.preferred_genres == []
    assert prefs.preferred_languages == ["all"]
    assert prefs.preferred_regions == ["all"]
    assert prefs.recommendation_settings.get("min_rating") == 6.0

    # 2. Update preferences
    updated = movie_repo.update_preferences(
        preferred_genres=["Action", "Science Fiction"],
        preferred_languages=["te", "hi", "en"],
        preferred_regions=["south_indian", "hollywood"],
        recommendation_settings={"min_rating": 7.5, "include_watched": True},
    )

    assert "Action" in updated.preferred_genres
    assert "te" in updated.preferred_languages
    assert "south_indian" in updated.preferred_regions
    assert updated.recommendation_settings["min_rating"] == 7.5

    # 3. Reset preferences to defaults
    reset = movie_repo.reset_preferences()
    assert reset.preferred_genres == []
    assert reset.preferred_languages == ["all"]
    assert reset.preferred_regions == ["all"]
    assert reset.recommendation_settings["min_rating"] == 6.0


# =============================================================================
# 5. FastAPI Storage Endpoints Integration (8.7)
# =============================================================================


def test_fastapi_storage_endpoints_flow(movie_repo: MovieStorageRepository):
    """Test 8.7: Comprehensive REST API operations on /api/movies/storage/*."""
    app = create_app()
    app.state.movie_repo = movie_repo
    client = TestClient(app)

    # 1. Add to Watchlist via POST
    add_payload = {
        "tmdb_id": 999,
        "title": "Interstellar",
        "media_type": "movie",
        "release_year": 2014,
        "vote_average": 8.6,
        "status": "watchlist",
    }
    res_add = client.post("/api/movies/storage/watchlist", json=add_payload)
    assert res_add.status_code == 200
    assert res_add.json()["tmdb_id"] == 999

    # 2. Check Summary via GET
    res_summary = client.get("/api/movies/storage/summary")
    assert res_summary.status_code == 200
    summary = res_summary.json()
    assert 999 in summary["watchlist_ids"]

    # 3. Mark as Favorite via POST
    res_fav = client.post(
        "/api/movies/storage/favorite/movie/999",
        json={"is_favorite": True, "title": "Interstellar"},
    )
    assert res_fav.status_code == 200
    assert res_fav.json()["is_favorite"] is True

    # 4. Set Local Rating via POST
    res_rate = client.post(
        "/api/movies/storage/rating/movie/999",
        json={"rating": 9},
    )
    assert res_rate.status_code == 200
    assert res_rate.json()["user_rating"] == 9

    # 5. Mark Watched via POST
    res_watched = client.post("/api/movies/storage/watched/movie/999")
    assert res_watched.status_code == 200
    assert res_watched.json()["status"] == "watched"

    # 6. Preferences GET, PUT, RESET
    res_prefs = client.get("/api/movies/storage/preferences")
    assert res_prefs.status_code == 200

    res_pref_put = client.put(
        "/api/movies/storage/preferences",
        json={"preferred_genres": ["Drama"], "preferred_languages": ["en"]},
    )
    assert res_pref_put.status_code == 200
    assert "Drama" in res_pref_put.json()["preferred_genres"]

    res_pref_reset = client.post("/api/movies/storage/preferences/reset")
    assert res_pref_reset.status_code == 200
    assert res_pref_reset.json()["preferred_genres"] == []


def test_mark_as_watched_and_favorite_untracked_titles(temp_db_manager: DatabaseManager):
    """Verify marking untracked titles as watched or favorites creates records without 404 or NOT NULL errors."""
    app = create_app()
    app.state.db_manager = temp_db_manager
    app.state.movie_repo = MovieStorageRepository(db_manager=temp_db_manager)
    client = TestClient(app)

    # 1. Mark untracked movie as watched with metadata
    res_w1 = client.post(
        "/api/movies/storage/watched/movie/8001",
        json={
            "title": "Untracked Movie 1",
            "poster_path": "/poster1.jpg",
            "release_year": 2024,
            "vote_average": 7.9,
            "overview": "Exciting plot",
        },
    )
    assert res_w1.status_code == 200
    w1_data = res_w1.json()
    assert w1_data["tmdb_id"] == 8001
    assert w1_data["status"] == "watched"
    assert w1_data["watched_at"] is not None
    assert w1_data["title"] == "Untracked Movie 1"

    # 2. Mark untracked TV show as watched with NO body
    res_w2 = client.post("/api/movies/storage/watched/tv/8002")
    assert res_w2.status_code == 200
    w2_data = res_w2.json()
    assert w2_data["tmdb_id"] == 8002
    assert w2_data["status"] == "watched"
    assert w2_data["watched_at"] is not None
    assert w2_data["title"] == "Title #8002"

    # 3. Mark untracked movie as favorite with minimal payload (title=None)
    res_fav = client.post(
        "/api/movies/storage/favorite/movie/8003",
        json={"is_favorite": True, "title": None, "vote_average": 8.0},
    )
    assert res_fav.status_code == 200
    fav_data = res_fav.json()
    assert fav_data["tmdb_id"] == 8003
    assert fav_data["is_favorite"] is True
    assert fav_data["title"] == "Title #8003"

    # 4. Check Tracking Summary includes all newly tracked IDs
    res_summary = client.get("/api/movies/storage/summary")
    assert res_summary.status_code == 200
    summary = res_summary.json()
    assert 8001 in summary["watched_ids"]
    assert 8002 in summary["watched_ids"]
    assert 8003 in summary["favorite_ids"]

    # 5. Query watched collection
    res_watched_list = client.get("/api/movies/storage/entries?status=watched")
    assert res_watched_list.status_code == 200
    watched_ids = [e["tmdb_id"] for e in res_watched_list.json()]
    assert 8001 in watched_ids
    assert 8002 in watched_ids

    # 6. Query favorites collection
    res_fav_list = client.get("/api/movies/storage/entries?is_favorite=true")
    assert res_fav_list.status_code == 200
    fav_ids = [e["tmdb_id"] for e in res_fav_list.json()]
    assert 8003 in fav_ids

    # 7. Unmark watched
    res_unwatch = client.patch(
        "/api/movies/storage/status/movie/8001",
        json={"status": "none"},
    )
    assert res_unwatch.status_code == 200
    assert res_unwatch.json()["status"] == "none"

    # 8. Unmark favorite
    res_unfav = client.post(
        "/api/movies/storage/favorite/movie/8003",
        json={"is_favorite": False},
    )
    assert res_unfav.status_code == 200
    assert res_unfav.json()["is_favorite"] is False
