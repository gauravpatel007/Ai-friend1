"""Phase 8: Personalized Recommendations & User Taste Test Suite.

Verifies:
8.1 Existing Data Reuse (Watchlist, Favorites, Watched, Preferences).
8.2 Recommendation Preferences (disliked genres, exclude_watched, prefer_underrated, prefer_highly_rated, prefer_newer, prefer_classic).
8.3 User Feedback Controls (more_like_this, not_interested, already_watched, not_my_taste).
8.4 Watched vs Favorite distinction in Taste Profile.
8.5 Personalized Ranking Signals & Explicit Prompt Priority over Background Taste.
8.6 Local Persistence across storage restarts.
8.7 FastAPI REST Endpoints integration.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.ai.movie_ranking_engine import CandidateFeatures, MovieRankingEngine, extract_candidate_features
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.api.movie_models import (
    MediaItemSummary,
    MovieFeedbackRequest,
    MovieUserPreferences,
    ParsedRecommendationIntent,
    PreferencesUpdateRequest,
    RecommendedTitleModel,
    UserMovieProfile,
)
from app.api.server import create_app
from app.api.tmdb_client import TMDBClient
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database manager with all migrations applied."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_phase8.db"
        db = DatabaseManager(db_path=str(db_path))
        yield db
        db.close()


@pytest.fixture
def storage(temp_db):
    """Create a MovieStorageRepository backed by temp DB."""
    return MovieStorageRepository(db_manager=temp_db)


@pytest.fixture
def ranking_engine():
    """Create a MovieRankingEngine instance."""
    return MovieRankingEngine()


def _make_candidate(
    cid: int,
    title: str,
    genres: List[str],
    genre_ids: List[int],
    vote_avg: float = 7.5,
    vote_count: int = 1500,
    year: int = 2021,
    overview: str = "A thrilling adventure",
) -> MediaItemSummary:
    """Helper to create a test MediaItemSummary."""
    return MediaItemSummary(
        id=cid,
        title=title,
        original_title=title,
        media_type="movie",
        overview=overview,
        release_date=f"{year}-06-15",
        release_year=year,
        vote_average=vote_avg,
        vote_count=vote_count,
        popularity=45.0,
        original_language="en",
        genre_ids=genre_ids,
        genre_names=genres,
        keywords=["thriller", "mystery"],
    )


# =============================================================================
# 8.1 & 8.2: Preferences & Taste Settings
# =============================================================================

def test_preferences_defaults_and_updates(storage: MovieStorageRepository):
    """Test updating and reading new Phase 8 preference flags."""
    prefs = storage.get_preferences()
    assert prefs.disliked_genres == []
    assert prefs.exclude_watched is False
    assert prefs.prefer_underrated is False
    assert prefs.prefer_highly_rated is False
    assert prefs.prefer_newer is False
    assert prefs.prefer_classic is False

    updated = storage.update_preferences(
        disliked_genres=["Horror", "Musical"],
        exclude_watched=True,
        prefer_underrated=True,
        prefer_highly_rated=True,
        prefer_newer=True,
        prefer_classic=False,
    )
    assert updated.disliked_genres == ["Horror", "Musical"]
    assert updated.exclude_watched is True
    assert updated.prefer_underrated is True
    assert updated.prefer_highly_rated is True
    assert updated.prefer_newer is True
    assert updated.prefer_classic is False

    # Read back from DB
    re_read = storage.get_preferences()
    assert re_read.disliked_genres == ["Horror", "Musical"]
    assert re_read.exclude_watched is True
    assert re_read.prefer_underrated is True


def test_reset_preferences(storage: MovieStorageRepository):
    """Test resetting preferences back to clean defaults."""
    storage.update_preferences(
        disliked_genres=["Romance"],
        exclude_watched=True,
        prefer_classic=True,
    )
    reset = storage.reset_preferences()
    assert reset.disliked_genres == []
    assert reset.exclude_watched is False
    assert reset.prefer_classic is False


# =============================================================================
# 8.3: User Feedback Controls (Recording & Persistence)
# =============================================================================

def test_user_feedback_crud(storage: MovieStorageRepository):
    """Test recording, reading, and deleting feedback."""
    # 1. Record 'more_like_this'
    res1 = storage.record_feedback(
        tmdb_id=157336,
        media_type="movie",
        feedback_type="more_like_this",
        title="Interstellar",
        genres="Science Fiction,Drama",
    )
    assert res1["status"] == "ok"
    assert res1["feedback_type"] == "more_like_this"

    # 2. Record 'not_interested'
    storage.record_feedback(
        tmdb_id=99999,
        media_type="movie",
        feedback_type="not_interested",
        title="Bad Movie",
        genres="Horror",
    )

    all_fb = storage.get_all_feedback()
    assert len(all_fb) == 2
    fb_map = {f["tmdb_id"]: f["feedback_type"] for f in all_fb}
    assert fb_map[157336] == "more_like_this"
    assert fb_map[99999] == "not_interested"

    # 3. Update existing feedback to 'not_my_taste'
    storage.record_feedback(
        tmdb_id=157336,
        media_type="movie",
        feedback_type="not_my_taste",
        title="Interstellar",
        genres="Science Fiction,Drama",
    )
    single_fb = storage.get_feedback(157336, "movie")
    assert single_fb is not None
    assert single_fb["feedback_type"] == "not_my_taste"

    # 4. Delete feedback
    deleted = storage.delete_feedback(157336, "movie")
    assert deleted is True
    assert storage.get_feedback(157336, "movie") is None


# =============================================================================
# 8.4: Profile Construction: Watched vs Favorite Distinction
# =============================================================================

def test_user_profile_construction_distinguishes_watched_and_favorite(storage: MovieStorageRepository):
    """Requirement 8.4: Build profile distinguishing Watched, Liked, Favorited, and Disliked."""
    # Add a favorite movie (Sci-Fi, Adventure)
    storage.set_favorite(100, "movie", True, item_metadata={"title": "SciFi Gem", "genres": "Science Fiction,Adventure"})

    # Add a watched movie (Comedy) - should receive modest familiarity, NOT treated as favorite
    storage.mark_as_watched(200, "movie", item_metadata={"title": "Some Comedy", "genres": "Comedy"})

    # Add feedback: more_like_this for Mystery
    storage.record_feedback(300, "movie", "more_like_this", title="Knives Out", genres="Mystery,Comedy")

    # Add feedback: not_interested for Horror
    storage.record_feedback(400, "movie", "not_interested", title="Scary Movie", genres="Horror")

    # Set preferred and disliked genres in preferences
    storage.update_preferences(
        preferred_genres=["Mystery"],
        disliked_genres=["Romance"],
        exclude_watched=True,
    )

    profile = storage.build_user_profile()

    assert 100 in profile.favorite_ids
    assert 200 in profile.watched_ids
    assert 200 not in profile.favorite_ids  # Watched is distinct from Favorite!
    assert 300 in profile.liked_ids
    assert 400 in profile.disliked_ids
    assert "romance" in profile.disliked_genres
    assert profile.exclude_watched is True

    # Check genre affinities:
    # Mystery has preferred (+2.0) + liked (+1.5) = +3.5
    assert profile.genre_affinities.get("mystery", 0) > 2.0
    # Sci-Fi has favorite (+2.0)
    assert profile.genre_affinities.get("science fiction", 0) >= 2.0
    # Watched Comedy gets small weight (+0.2) + liked (+1.5)
    assert profile.genre_affinities.get("comedy", 0) > 1.0
    # Horror has negative feedback (-1.5)
    assert profile.genre_affinities.get("horror", 0) < 0.0
    # Romance is disliked (-3.0)
    assert profile.genre_affinities.get("romance", 0) <= -3.0


# =============================================================================
# 8.5: Personalized Ranking Engine Signals
# =============================================================================

def test_explicit_prompt_priority_over_learned_disliked_genres(ranking_engine: MovieRankingEngine):
    """Requirement 8.5: If user explicitly queries 'Horror', prompt strictly overrides disliked genres."""
    profile = UserMovieProfile(
        preferred_genres=["Drama"],
        disliked_genres=["horror"],
        genre_affinities={"horror": -3.0, "drama": 2.0},
    )

    # 1. Query explicitly asks for Horror
    intent_horror = ParsedRecommendationIntent(
        genres=["Horror"],
        query_type="discovery",
    )
    cand_horror = _make_candidate(1, "The Conjuring", ["Horror"], [27], vote_avg=7.5)

    features = extract_candidate_features(cand_horror)
    score, reason = ranking_engine.score_contextual_preferences(
        features=features,
        intent=intent_horror,
        user_profile=profile,
    )
    # Because 'Horror' was explicitly requested in prompt, score must NOT be penalized (-0.30)
    assert score >= 0.50
    assert reason is None or "Suppressed" not in reason

    # 2. Query is general (e.g. "Exciting mystery"), candidate has Horror tag
    intent_general = ParsedRecommendationIntent(
        genres=["Mystery"],
        query_type="discovery",
    )
    cand_horror_mystery = _make_candidate(2, "Horror Mystery", ["Mystery", "Horror"], [9648, 27], vote_avg=7.5)
    features_gen = extract_candidate_features(cand_horror_mystery)
    score_gen, reason_gen = ranking_engine.score_contextual_preferences(
        features=features_gen,
        intent=intent_general,
        user_profile=profile,
    )
    # Background disliked genre penalty applies!
    assert score_gen < 0.50
    assert reason_gen is not None and "Suppressed" in reason_gen


def test_liked_and_disliked_feedback_impacts_ranking(ranking_engine: MovieRankingEngine):
    """Test that titles with 'more_like_this' feedback are boosted and 'not_interested' are suppressed."""
    profile = UserMovieProfile(
        liked_ids=[101],
        disliked_ids=[102],
    )
    intent = ParsedRecommendationIntent(query_type="discovery")

    cand_liked = _make_candidate(101, "Liked Title", ["Drama"], [18], vote_avg=7.0)
    cand_neutral = _make_candidate(103, "Neutral Title", ["Drama"], [18], vote_avg=7.0)
    cand_disliked = _make_candidate(102, "Disliked Title", ["Drama"], [18], vote_avg=7.0)

    score_liked, reasons_liked, _, _ = ranking_engine.score_candidate(
        cand_liked, intent, user_profile=profile
    )
    score_neutral, _, _, _ = ranking_engine.score_candidate(
        cand_neutral, intent, user_profile=profile
    )
    score_disliked, reasons_disliked, _, _ = ranking_engine.score_candidate(
        cand_disliked, intent, user_profile=profile
    )

    assert score_liked > score_neutral
    assert score_neutral > score_disliked
    assert any("Aligned with titles you liked" in r for r in reasons_liked)
    assert any("Previously marked as not interested" in r for r in reasons_disliked)


def test_exclude_watched_hard_filter(ranking_engine: MovieRankingEngine):
    """Test that exclude_watched filters out watched movies when enabled."""
    profile_exclude = UserMovieProfile(
        exclude_watched=True,
        watched_ids=[555],
    )
    profile_keep = UserMovieProfile(
        exclude_watched=False,
        watched_ids=[555],
    )
    intent = ParsedRecommendationIntent(query_type="discovery")
    cand = _make_candidate(555, "Watched Movie", ["Action"], [28])
    feats = extract_candidate_features(cand)

    # With exclude_watched=True -> rejected
    passes_excl, reason_excl = ranking_engine.passes_hard_filters(
        features=feats,
        intent=intent,
        user_profile=profile_exclude,
        watched_ids={555},
    )
    assert passes_excl is False
    assert "Already watched by user" in reason_excl

    # With exclude_watched=False -> allowed
    passes_keep, _ = ranking_engine.passes_hard_filters(
        features=feats,
        intent=intent,
        user_profile=profile_keep,
        watched_ids={555},
    )
    assert passes_keep is True


def test_preference_flags_ranking_boosts(ranking_engine: MovieRankingEngine):
    """Test prefer_underrated, prefer_highly_rated, prefer_newer, and prefer_classic flags."""
    intent = ParsedRecommendationIntent(query_type="discovery")

    # 1. prefer_underrated boosts high-rated lesser-voted titles
    profile_underrated = UserMovieProfile(prefer_underrated=True)
    gem_cand = _make_candidate(1, "Hidden Gem", ["Drama"], [18], vote_avg=8.1, vote_count=850)
    feats_gem = extract_candidate_features(gem_cand)
    score_gem, reason_gem = ranking_engine.score_contextual_preferences(
        feats_gem, intent, user_profile=profile_underrated
    )
    assert score_gem > 0.65
    assert "underrated preference" in reason_gem

    # 2. prefer_classic boosts pre-1990 films
    profile_classic = UserMovieProfile(prefer_classic=True)
    classic_cand = _make_candidate(2, "12 Angry Men", ["Drama"], [18], vote_avg=8.5, year=1957)
    feats_classic = extract_candidate_features(classic_cand)
    score_classic, reason_classic = ranking_engine.score_contextual_preferences(
        feats_classic, intent, user_profile=profile_classic
    )
    assert score_classic > 0.65
    assert "Classic film era" in reason_classic

    # 3. prefer_newer boosts 2020+ films
    profile_newer = UserMovieProfile(prefer_newer=True)
    newer_cand = _make_candidate(3, "Oppenheimer", ["Drama", "History"], [18, 36], vote_avg=8.2, year=2023)
    feats_newer = extract_candidate_features(newer_cand)
    score_newer, reason_newer = ranking_engine.score_contextual_preferences(
        feats_newer, intent, user_profile=profile_newer
    )
    assert score_newer > 0.60
    assert "Recent release" in reason_newer


# =============================================================================
# 8.6: Local Persistence Across Restarts
# =============================================================================

def test_persistence_across_storage_restarts(temp_db: DatabaseManager):
    """Requirement 8.6: All preferences and feedback survive app/storage restart."""
    # Instance 1
    repo1 = MovieStorageRepository(db_manager=temp_db)
    repo1.update_preferences(
        preferred_genres=["Sci-Fi"],
        disliked_genres=["Horror"],
        exclude_watched=True,
        prefer_underrated=True,
    )
    repo1.record_feedback(777, "movie", "more_like_this", title="Arrival", genres="Sci-Fi")

    # Instance 2 (simulating restart)
    repo2 = MovieStorageRepository(db_manager=temp_db)
    prefs2 = repo2.get_preferences()
    assert prefs2.disliked_genres == ["Horror"]
    assert prefs2.exclude_watched is True
    assert prefs2.prefer_underrated is True

    fb2 = repo2.get_feedback(777, "movie")
    assert fb2 is not None
    assert fb2["feedback_type"] == "more_like_this"

    profile2 = repo2.build_user_profile()
    assert 777 in profile2.liked_ids
    assert "horror" in profile2.disliked_genres


# =============================================================================
# 8.7: FastAPI REST Endpoints Integration
# =============================================================================

def test_api_preferences_and_feedback_routes(temp_db: DatabaseManager):
    """Test full HTTP endpoints for preferences and recommendation feedback."""
    app = create_app()
    app.state.db_manager = temp_db
    app.state.movie_storage = MovieStorageRepository(db_manager=temp_db)

    client = TestClient(app)

    # 1. Update preferences via PUT
    put_res = client.put(
        "/api/movies/storage/preferences",
        json={
            "preferred_genres": ["Mystery"],
            "disliked_genres": ["Horror", "Musical"],
            "exclude_watched": True,
            "prefer_underrated": True,
            "prefer_highly_rated": True,
            "prefer_newer": False,
            "prefer_classic": True,
        },
    )
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["disliked_genres"] == ["Horror", "Musical"]
    assert data["exclude_watched"] is True
    assert data["prefer_classic"] is True

    # 2. Get profile via GET
    prof_res = client.get("/api/movies/storage/profile")
    assert prof_res.status_code == 200
    prof = prof_res.json()
    assert prof["exclude_watched"] is True
    assert "horror" in prof["disliked_genres"]

    # 3. Post feedback via POST
    fb_res = client.post(
        "/api/movies/feedback",
        json={
            "tmdb_id": 12345,
            "media_type": "movie",
            "feedback_type": "more_like_this",
            "title": "Knives Out",
            "genres": "Mystery,Comedy",
        },
    )
    assert fb_res.status_code == 200
    assert fb_res.json()["status"] == "ok"

    # 4. Get all feedback via GET
    list_res = client.get("/api/movies/feedback")
    assert list_res.status_code == 200
    fb_list = list_res.json()
    assert len(fb_list) == 1
    assert fb_list[0]["tmdb_id"] == 12345
    assert fb_list[0]["feedback_type"] == "more_like_this"

    # 5. Delete feedback via DELETE
    del_res = client.delete("/api/movies/feedback/movie/12345")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True
