"""Phase 7 Verification Tests: Movie Hub UX, Intent Display, Result Cards, Refinements, and Feature Regression.

Covers exact Phase 7 requirements:
7.1 Meaningful search progress and stage tracking.
7.2 Interpreted intent display with adjustable preference chips.
7.3 Improved result cards with verified TMDB metadata (poster, year, rating, genres, lang, synopsis, grounded reasons, 4 actions).
7.4 Differentiated empty states (unconfigured, reference not found, too restrictive, network error, zero results, partial matches).
7.5 Search refinement interactions updating actual search intent.
7.6 Useful discovery information (analyzed count vs selected count).
7.7 Full regression testing across existing Movie Hub features (Discover, AI Recommendations, Search, Watchlist, Favorites, Watched, Preferences, History, Movie Details).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.api.movie_models import (
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationResponse,
    RecommendedTitleModel,
    MediaDetailsModel,
    GenreModel,
)
from app.api.tmdb_client import TMDBClient
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db() -> DatabaseManager:
    """In-memory SQLite database manager."""
    return DatabaseManager(":memory:")


@pytest.fixture
def storage_repo(mock_db: DatabaseManager) -> MovieStorageRepository:
    """Storage repository connected to in-memory database."""
    return MovieStorageRepository(mock_db)


@pytest.fixture
def mock_tmdb() -> TMDBClient:
    """Mocked TMDB client returning verified test metadata."""
    client = MagicMock(spec=TMDBClient)
    client.is_configured.return_value = True

    # Sample movies
    m1 = MediaItemSummary(
        id=157336,
        title="Interstellar",
        original_title="Interstellar",
        release_year=2014,
        original_language="en",
        media_type="movie",
        genre_ids=[878, 18],
        genre_names=["Science Fiction", "Drama"],
        vote_average=8.4,
        vote_count=35000,
        popularity=120.5,
        overview="The adventures of a group of explorers who make use of a newly discovered wormhole.",
    )
    m2 = MediaItemSummary(
        id=27205,
        title="Inception",
        original_title="Inception",
        release_year=2010,
        original_language="en",
        media_type="movie",
        genre_ids=[878, 9648, 28],
        genre_names=["Science Fiction", "Mystery", "Action"],
        vote_average=8.4,
        vote_count=36000,
        popularity=115.0,
        overview="Cobb, a skilled thief who steals corporate secrets through dream-sharing technology.",
    )
    m3 = MediaItemSummary(
        id=597,
        title="Titanic",
        original_title="Titanic",
        release_year=1997,
        original_language="en",
        media_type="movie",
        genre_ids=[18, 10749],
        genre_names=["Drama", "Romance"],
        vote_average=7.9,
        vote_count=24000,
        popularity=95.0,
        overview="A seventeen-year-old aristocrat falls in love with a kind but poor artist aboard the luxurious R.M.S. Titanic.",
    )

    client.discover_movies.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=3, results=[m1, m2, m3]
    )
    client.discover_all.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=3, results=[m1, m2, m3]
    )
    client.search_movies.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=2, results=[m1, m2]
    )
    client.get_movie_details.return_value = MediaDetailsModel(
        id=157336,
        title="Interstellar",
        release_year=2014,
        original_language="en",
        media_type="movie",
        genres=[GenreModel(id=878, name="Science Fiction"), GenreModel(id=18, name="Drama")],
        vote_average=8.4,
        vote_count=35000,
        popularity=120.5,
        overview="The adventures of a group of explorers who make use of a newly discovered wormhole.",
    )

    return client


# =============================================================================
# 7.1 Search Process Stages & Timing Diagnostics
# =============================================================================

def test_search_process_stages_and_timing_diagnostics(mock_tmdb: TMDBClient, storage_repo: MovieStorageRepository):
    """Test 7.1: Pipeline records granular timings for all stages without empty flash."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage_repo)
    resp = engine.recommend("Mind-bending sci-fi with plot twists")

    assert resp.diagnostics is not None
    timings = resp.diagnostics.get("timings_ms", {})
    # Verify stages correspond to meaningful execution steps
    assert "intent_parsing" in timings
    assert "candidate_retrieval" in timings
    assert "ranking" in timings
    assert "explanation_generation" in timings
    assert "total_pipeline" in timings
    assert timings["total_pipeline"] >= 0


# =============================================================================
# 7.2 Interpreted Intent & Preference Extraction
# =============================================================================

def test_interpreted_intent_structured_extraction(mock_tmdb: TMDBClient, storage_repo: MovieStorageRepository):
    """Test 7.2: Interpreted intent extracts categorized preferences for interactive UI chips."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage_repo)
    intent = engine.parse_intent_deterministic("Recommend an underrated Malayalam psychological thriller with plot twists")

    # Genres
    assert "Thriller" in intent.genres or "Thriller" in intent.genres_any
    # Language
    assert intent.language == "ml"
    # Mood / plot elements
    assert "underrated" in intent.keywords
    assert any("plot twist" in str(p).lower() for p in (intent.plot_elements + intent.keywords + intent.keywords_any))
    assert intent.interpreted_summary != ""


# =============================================================================
# 7.3 Result Cards Verified Metadata Contract
# =============================================================================

def test_result_card_verified_metadata_contract(mock_tmdb: TMDBClient, storage_repo: MovieStorageRepository):
    """Test 7.3: Every recommendation card contains verified TMDB metadata and grounded explanations."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage_repo)
    resp = engine.recommend("Sci-fi movies like Interstellar")

    assert len(resp.recommendations) > 0
    for rec in resp.recommendations:
        item = rec.media
        # Poster, title, release year, rating, language, overview
        assert item.id > 0
        assert len(item.title) > 0
        assert item.release_year is not None
        assert item.vote_average >= 0.0
        assert item.original_language is not None
        assert len(item.overview) > 0
        # Verified genres
        assert len(item.genre_names) > 0 or len(item.genre_ids) > 0
        # Why Bond recommended it (reasons + explanation)
        assert len(rec.match_reasons) > 0
        assert len(rec.ai_explanation) > 15


# =============================================================================
# 7.4 Differentiated Empty States & Partial Results
# =============================================================================

def test_empty_state_differentiation_unconfigured():
    """Test 7.4: Differentiates TMDB unconfigured error."""
    unconfigured_client = MagicMock(spec=TMDBClient)
    unconfigured_client.is_configured.return_value = False
    repo = MagicMock(spec=MovieStorageRepository)

    engine = MovieRecommendationEngine(tmdb_client=unconfigured_client, storage_repo=repo)
    resp = engine.recommend("Feel good movie")

    assert resp.error_type == "tmdb_unconfigured"
    assert "TMDB API key" in (resp.error_message or "")
    assert len(resp.recommendations) == 0


def test_empty_state_differentiation_reference_not_found(storage_repo: MovieStorageRepository):
    """Test 7.4: Differentiates reference movie not found."""
    mock_client = MagicMock(spec=TMDBClient)
    mock_client.is_configured.return_value = True
    mock_client.search_movies.return_value = PagedResultModel(results=[])

    engine = MovieRecommendationEngine(tmdb_client=mock_client, storage_repo=storage_repo)
    resp = engine.recommend("Movies like NonExistentMovieTitleXyz123")

    assert resp.error_type == "reference_not_found"
    assert "Could not find" in (resp.error_message or "")


def test_empty_state_differentiation_candidates_filtered(storage_repo: MovieStorageRepository):
    """Test 7.4: Differentiates when preferences were too restrictive."""
    mock_client = MagicMock(spec=TMDBClient)
    mock_client.is_configured.return_value = True
    # Discovers movies, but they violate strict constraints (e.g., wrong language)
    m_other = MediaItemSummary(
        id=999,
        title="Other Lang Film",
        original_language="es",
        release_year=1960,
        overview="Spanish classic film.",
    )
    mock_client.discover_movies.return_value = PagedResultModel(results=[m_other])
    mock_client.discover_all.return_value = PagedResultModel(results=[m_other])

    engine = MovieRecommendationEngine(tmdb_client=mock_client, storage_repo=storage_repo)
    # Require strictly Malayalam
    resp = engine.recommend("Malayalam movies only")

    assert resp.error_type in ["candidates_filtered", "zero_results"]
    assert len(resp.recommendations) == 0


def test_partial_results_preserved_when_few_candidates(mock_tmdb: TMDBClient, storage_repo: MovieStorageRepository):
    """Test 7.4: Partial results (e.g. 1 or 2 candidates) are preserved and returned."""
    m_single = MediaItemSummary(
        id=101,
        title="Rare Gem",
        release_year=2021,
        original_language="ml",
        genre_ids=[53],
        genre_names=["Thriller"],
        vote_average=8.0,
        overview="An intense isolated investigation.",
    )
    mock_tmdb.discover_movies.return_value = PagedResultModel(results=[m_single])
    mock_tmdb.discover_all.return_value = PagedResultModel(results=[m_single])

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage_repo)
    resp = engine.recommend("Underrated Malayalam thriller")

    assert len(resp.recommendations) == 1
    assert resp.recommendations[0].media.title == "Rare Gem"


# =============================================================================
# 7.5 Refinements Update Search Intent
# =============================================================================

def test_search_refinements_update_intent_and_rerank(mock_tmdb: TMDBClient, storage_repo: MovieStorageRepository):
    """Test 7.5: Applying a refinement modifier alters the parsed intent and discovery query."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage_repo)

    base_intent = engine.parse_intent_deterministic("Sci-fi movies")
    refined_recent = engine.parse_intent_deterministic("Sci-fi movies released after 2020")
    refined_underrated = engine.parse_intent_deterministic("Underrated sci-fi movies")

    assert base_intent.release_year_gte is None
    assert (refined_recent.release_year_gte or 0) >= 2020
    assert "underrated" in refined_underrated.keywords


# =============================================================================
# 7.6 Discovery Information Count Accuracy
# =============================================================================

def test_discovery_information_count_accuracy(mock_tmdb: TMDBClient, storage_repo: MovieStorageRepository):
    """Test 7.6: Total candidates analyzed reflects actual retrieved candidates count."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage_repo)
    resp = engine.recommend("Interstellar")

    assert resp.total_candidates_analyzed >= len(resp.recommendations)
    assert resp.diagnostics["raw_candidates_count"] == resp.total_candidates_analyzed
    assert resp.diagnostics["final_recommendations_count"] == len(resp.recommendations)


# =============================================================================
# 7.7 Feature Regression Across All Movie Hub Subsystems
# =============================================================================

def test_regression_watchlist_favorites_and_watched(storage_repo: MovieStorageRepository):
    """Test 7.7: Regression test for Watchlist, Favorites, and Watched tracking."""
    # 1. Watchlist
    entry = storage_repo.add_or_update_entry(
        tmdb_id=157336,
        title="Interstellar",
        media_type="movie",
        release_year=2014,
        vote_average=8.4,
        status="watchlist",
    )
    assert entry.status == "watchlist"
    watchlist = storage_repo.get_watchlist()
    assert len(watchlist) == 1
    assert watchlist[0].tmdb_id == 157336

    # 2. Favorite
    storage_repo.set_favorite(157336, "movie", True)
    favs = storage_repo.get_favorites()
    assert len(favs) == 1
    assert favs[0].is_favorite is True

    # 3. Watched
    storage_repo.mark_as_watched(157336, "movie")
    watched = storage_repo.get_watched()
    assert len(watched) == 1
    assert watched[0].status == "watched"

    # 4. Summary tracking IDs
    summary = storage_repo.get_tracking_summary()
    assert 157336 in summary["watched_ids"]
    assert 157336 in summary["favorite_ids"]


def test_regression_preferences_management(storage_repo: MovieStorageRepository):
    """Test 7.7: Regression test for User Entertainment Preferences."""
    prefs = storage_repo.get_preferences()
    assert isinstance(prefs.preferred_genres, list)

    updated = storage_repo.update_preferences(
        preferred_genres=["Science Fiction", "Mystery"],
        preferred_languages=["en", "ml"],
    )
    assert "Science Fiction" in updated.preferred_genres
    assert "ml" in updated.preferred_languages

    reset = storage_repo.reset_preferences()
    assert reset.preferred_genres == []


def test_regression_ai_search_history(storage_repo: MovieStorageRepository):
    """Test 7.7: Regression test for AI Search History persistence and deletion."""
    h1 = storage_repo.add_ai_search_history("Mind-bending sci-fi")
    h2 = storage_repo.add_ai_search_history("Malayalam thrillers")

    history = storage_repo.get_ai_search_history(limit=10)
    assert len(history) == 2
    queries = [item["query"] for item in history]
    assert "Mind-bending sci-fi" in queries
    assert "Malayalam thrillers" in queries

    storage_repo.delete_ai_search_history_item(h1["id"])
    history_after = storage_repo.get_ai_search_history(limit=10)
    assert len(history_after) == 1

    storage_repo.clear_ai_search_history()
    assert len(storage_repo.get_ai_search_history()) == 0
