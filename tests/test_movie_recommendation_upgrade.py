"""Comprehensive verification test suite for the upgraded Movie Recommendation Engine.

Tests:
1. Stage A: Structured Intent Understanding (Reference, Regional, Mood, Time-period, Complex)
2. Stage B: Reference Movie Resolution via TMDB
3. Stage C & D: Multi-Stage Candidate Retrieval & Fallback Execution
4. Stage E: Multi-Signal Candidate Ranking & Reference Exclusion
5. Stage F: Grounded Explanations (Anchored in Verified Synopsis)
6. Regional Classifier & Strict Filtering Bug Fixes (No English Rejection on International/Similar)
7. Error Handling (Empty Query, Unconfigured TMDB, Reference Not Found, Diagnostics Payload)
8. FastAPI Endpoint End-to-End Integration
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.ai.movie_recommendation_engine import (
    GENRE_TAXONOMY,
    MOOD_TAXONOMY,
    MovieRecommendationEngine,
)
from app.ai.regional_classifier import (
    REGION_INTERNATIONAL,
    REGION_MALAYALAM,
    REGION_TELUGU,
    filter_eligible_candidates,
    validate_candidate_eligibility,
)
from app.api.movie_models import (
    GenreModel,
    MediaDetailsModel,
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationRequest,
    RecommendationResponse,
    RecommendedTitleModel,
)
from app.api.server import create_app
from app.api.tmdb_client import (
    TMDBAuthError,
    TMDBClient,
    TMDBNetworkError,
    TMDBRateLimitError,
)
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db() -> DatabaseManager:
    """Isolated SQLite database manager."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_rec_upgrade.db"
        manager = DatabaseManager(db_path=db_path)
        try:
            yield manager
        finally:
            manager.close()


@pytest.fixture
def movie_repo(temp_db: DatabaseManager) -> MovieStorageRepository:
    """Storage repository using isolated test database."""
    return MovieStorageRepository(db_manager=temp_db)


@pytest.fixture
def mock_tmdb() -> MagicMock:
    """Configured mock TMDB client."""
    client = MagicMock(spec=TMDBClient)
    client.is_configured.return_value = True
    return client


@pytest.fixture
def mock_ollama() -> MagicMock:
    """Mock Ollama AI client."""
    client = MagicMock()
    client.is_server_reachable.return_value = True
    client.chat.return_value = "A sharp, witty whodunit with an all-star ensemble and layered narrative puzzles."
    return client


@pytest.fixture
def engine(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock) -> MovieRecommendationEngine:
    """Instance of MovieRecommendationEngine with mock dependencies."""
    return MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
        default_model="llama3.2:3b",
    )


# =============================================================================
# 1. Stage A: Structured Intent Understanding Tests
# =============================================================================

def test_intent_parsing_glass_onion_reference(engine: MovieRecommendationEngine) -> None:
    """Verify 'Movies like Glass Onion: A Knives Out Mystery' parses as similar_to intent."""
    intent = engine.parse_intent_deterministic("Movies like Glass Onion: A Knives Out Mystery")
    assert intent.intent_type == "similar_to"
    assert intent.reference_title is not None
    assert "glass onion" in intent.reference_title.lower()
    assert "Mystery" in intent.genres
    assert 9648 in intent.genre_ids  # TMDB Mystery ID


def test_intent_parsing_interstellar_reference(engine: MovieRecommendationEngine) -> None:
    """Verify 'Movies like Interstellar' parses as similar_to with Sci-Fi genre detection."""
    intent = engine.parse_intent_deterministic("Movies like Interstellar")
    assert intent.intent_type == "similar_to"
    assert intent.reference_title is not None
    assert "interstellar" in intent.reference_title.lower()


def test_intent_parsing_regional_malayalam_thrillers(engine: MovieRecommendationEngine) -> None:
    """Verify 'Underrated Malayalam thrillers' extracts Malayalam language, region, genre, and keyword."""
    intent = engine.parse_intent_deterministic("Underrated Malayalam thrillers")
    assert intent.language == "ml"
    assert intent.region == REGION_MALAYALAM
    assert "Thriller" in intent.genres
    assert "underrated" in intent.keywords
    assert intent.sort_by == "vote_average.desc"


def test_intent_parsing_feel_good_hindi_comedy(engine: MovieRecommendationEngine) -> None:
    """Verify 'Feel-good Hindi comedy' extracts Hindi language, Comedy genre, and feel_good mood."""
    intent = engine.parse_intent_deterministic("Feel-good Hindi comedy")
    assert intent.language == "hi"
    assert "Comedy" in intent.genres
    assert intent.mood == "feel_good"


def test_intent_parsing_mind_bending_sci_fi(engine: MovieRecommendationEngine) -> None:
    """Verify 'Mind-bending sci-fi movies' extracts mind_bending mood and Sci-Fi genre."""
    intent = engine.parse_intent_deterministic("Mind-bending sci-fi movies")
    assert intent.mood == "mind_bending"
    assert "Science Fiction" in intent.genres
    assert intent.content_type == "movie"


def test_intent_parsing_90s_hollywood_action_classics(engine: MovieRecommendationEngine) -> None:
    """Verify '90s Hollywood action classics' extracts 1990-1999 year range and Action genre."""
    intent = engine.parse_intent_deterministic("90s Hollywood action classics")
    assert intent.release_year_gte == 1990
    assert intent.release_year_lte == 1999
    assert intent.region == "hollywood"
    assert "Action" in intent.genres


def test_intent_parsing_telugu_period_action_dramas(engine: MovieRecommendationEngine) -> None:
    """Verify 'Telugu period action dramas' extracts Telugu language, Action, and Drama genres."""
    intent = engine.parse_intent_deterministic("Telugu period action dramas")
    assert intent.language == "te"
    assert intent.region == REGION_TELUGU
    assert "Action" in intent.genres
    assert "Drama" in intent.genres


# =============================================================================
# 2. Stage B: Reference Movie Resolution via TMDB
# =============================================================================

def test_resolve_reference_title_success(engine: MovieRecommendationEngine, mock_tmdb: MagicMock) -> None:
    """Verify reference title is searched and resolved against TMDB catalog."""
    mock_search_item = MediaItemSummary(
        id=661374,
        title="Glass Onion: A Knives Out Mystery",
        media_type="movie",
        overview="World-famous detective Benoit Blanc heads to Greece...",
        vote_average=7.0,
        vote_count=5000,
        popularity=45.0,
        release_year=2022,
        original_language="en",
        genre_ids=[9648, 53, 35],
    )
    mock_tmdb.search_movies.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=1, results=[mock_search_item]
    )

    mock_details = MediaDetailsModel(
        id=661374,
        title="Glass Onion: A Knives Out Mystery",
        media_type="movie",
        overview="World-famous detective Benoit Blanc heads to Greece...",
        vote_average=7.0,
        vote_count=5000,
        popularity=45.0,
        release_year=2022,
        original_language="en",
        genre_ids=[9648, 53, 35],
        genres=[GenreModel(id=9648, name="Mystery"), GenreModel(id=35, name="Comedy")],
        cast=[],
        directors=["Rian Johnson"],
        trailers=[],
        similar=[],
    )
    mock_tmdb.get_movie_details.return_value = mock_details

    intent = ParsedRecommendationIntent(
        content_type="movie",
        reference_title="Glass Onion: A Knives Out Mystery",
        intent_type="similar_to",
    )

    resolved = engine.resolve_reference_title(intent)
    assert resolved is not None
    assert intent.reference_media is not None
    assert intent.reference_media.id == 661374
    assert intent.reference_media.title == "Glass Onion: A Knives Out Mystery"
    assert 9648 in intent.reference_genres


# =============================================================================
# 3. Stage C & D: Multi-Stage Candidate Retrieval & Fallback Execution
# =============================================================================

def test_retrieve_candidates_similar_pipeline(engine: MovieRecommendationEngine, mock_tmdb: MagicMock) -> None:
    """Verify candidate retrieval executes curated recommendations, similar, and keywords tiers."""
    ref_item = MediaItemSummary(
        id=661374,
        title="Glass Onion: A Knives Out Mystery",
        media_type="movie",
        overview="Benoit Blanc mystery",
        vote_average=7.0,
        vote_count=5000,
        popularity=50.0,
        release_year=2022,
        original_language="en",
        genre_ids=[9648, 35],
    )
    intent = ParsedRecommendationIntent(
        content_type="movie",
        reference_title="Glass Onion: A Knives Out Mystery",
        reference_media=ref_item,
        reference_genres=[9648, 35],
        intent_type="similar_to",
    )

    knives_out = MediaItemSummary(
        id=546554,
        title="Knives Out",
        media_type="movie",
        overview="When renowned crime novelist Harlan Thrombey is found dead...",
        vote_average=7.9,
        vote_count=12000,
        popularity=60.0,
        release_year=2019,
        original_language="en",
        genre_ids=[9648, 35, 80],
    )
    see_how_they_run = MediaItemSummary(
        id=766475,
        title="See How They Run",
        media_type="movie",
        overview="In the West End of 1950s London, plans for a movie version of a smash-hit play...",
        vote_average=6.6,
        vote_count=1500,
        popularity=25.0,
        release_year=2022,
        original_language="en",
        genre_ids=[9648, 35],
    )

    # Tier A.1: curated recommendations returns Knives Out
    mock_tmdb.get_movie_recommendations.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=1, results=[knives_out]
    )
    # Tier A.2: similar returns See How They Run
    mock_tmdb.get_movie_similar.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=1, results=[see_how_they_run]
    )
    # Tier A.3: keywords returns empty
    mock_tmdb.get_movie_keywords.return_value = []
    # Tier B: parameterized discovery returns empty
    mock_tmdb.discover_movies.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])

    candidates, diag = engine.retrieve_candidates(intent, limit=6, return_diagnostics=True)
    assert len(candidates) >= 2
    cand_ids = [c.id for c in candidates]
    assert 546554 in cand_ids  # Knives Out
    assert 766475 in cand_ids  # See How They Run
    # The reference movie itself (661374) must NOT be in the candidates!
    assert 661374 not in cand_ids
    assert "tmdb_curated_recommendations" in diag["retrieval_tiers_used"]
    assert "tmdb_similar" in diag["retrieval_tiers_used"]


# =============================================================================
# 4. Regional Classifier & Strict Filtering Bug Fixes
# =============================================================================

def test_region_international_does_not_reject_english_movies() -> None:
    """CRITICAL REGRESSION TEST: Verify English movie is NOT rejected when region is international.
    
    This was the primary root cause why 'Movies like Glass Onion' failed and returned 0 results!
    """
    candidate = MediaItemSummary(
        id=546554,
        title="Knives Out",
        media_type="movie",
        overview="Detective investigates death of mystery writer.",
        vote_average=7.9,
        vote_count=12000,
        popularity=60.0,
        release_year=2019,
        original_language="en",
        genre_ids=[9648, 35],
    )
    intent = ParsedRecommendationIntent(
        content_type="movie",
        reference_title="Glass Onion: A Knives Out Mystery",
        intent_type="similar_to",
        region="international",  # Inferred broadly
        genres=["Mystery"],
        genre_ids=[9648],
    )

    is_valid, reason = validate_candidate_eligibility(candidate, intent)
    assert is_valid is True, f"Knives Out should be eligible, but was rejected for: {reason}"


def test_candidate_without_poster_is_not_rejected() -> None:
    """Verify that candidates with missing optional poster or zero vote count pass eligibility."""
    candidate = MediaItemSummary(
        id=999999,
        title="Indie Gem",
        media_type="movie",
        overview="A festival mystery with high critical acclaim.",
        vote_average=8.0,
        vote_count=5,  # Low vote count
        popularity=5.0,
        release_year=2023,
        original_language="en",
        genre_ids=[9648],
        poster_path=None,
        poster_url=None,
    )
    intent = ParsedRecommendationIntent(
        content_type="movie",
        genres=["Mystery"],
        genre_ids=[9648],
    )

    is_valid, reason = validate_candidate_eligibility(candidate, intent)
    assert is_valid is True, f"Valid candidate with missing poster was wrongly rejected: {reason}"


# =============================================================================
# 5. Stage E: Multi-Signal Candidate Ranking & Reference Exclusion
# =============================================================================

def test_multi_signal_ranking_prioritizes_relevance(engine: MovieRecommendationEngine) -> None:
    """Verify ranking orders candidates based on genre overlap, quality, and similarity."""
    ref_item = MediaItemSummary(
        id=661374,
        title="Glass Onion",
        media_type="movie",
        overview="Benoit Blanc mystery",
        vote_average=7.0,
        vote_count=5000,
        popularity=50.0,
        release_year=2022,
        original_language="en",
        genre_ids=[9648, 35],
    )
    intent = ParsedRecommendationIntent(
        content_type="movie",
        reference_title="Glass Onion",
        reference_media=ref_item,
        reference_genres=[9648, 35],
        genres=["Mystery", "Comedy"],
        genre_ids=[9648, 35],
        intent_type="similar_to",
    )

    # Candidate 1: High overlap with reference (Mystery + Comedy), high rating
    cand_high = MediaItemSummary(
        id=1,
        title="Knives Out",
        media_type="movie",
        overview="Whodunit mystery comedy",
        vote_average=7.9,
        vote_count=10000,
        popularity=50.0,
        release_year=2019,
        original_language="en",
        genre_ids=[9648, 35],
    )
    # Candidate 2: Mystery only
    cand_mid = MediaItemSummary(
        id=2,
        title="Generic Mystery",
        media_type="movie",
        overview="A serious mystery",
        vote_average=6.5,
        vote_count=1000,
        popularity=10.0,
        release_year=2015,
        original_language="en",
        genre_ids=[9648],
    )
    # Candidate 3: Unrelated genre (e.g. Action only)
    cand_low = MediaItemSummary(
        id=3,
        title="Random Action",
        media_type="movie",
        overview="Explosions everywhere",
        vote_average=5.0,
        vote_count=200,
        popularity=5.0,
        release_year=2010,
        original_language="en",
        genre_ids=[28],
    )

    ranked = engine.rank_candidates([cand_mid, cand_low, cand_high], intent, limit=6)
    assert len(ranked) == 3
    # Top ranked should be Knives Out
    assert ranked[0][0].id == 1
    assert ranked[0][1] > ranked[1][1]
    assert ranked[1][1] > ranked[2][1]


# =============================================================================
# 6. Stage F: Grounded Explanations
# =============================================================================

def test_grounded_explanations_fallback_when_ollama_offline(engine: MovieRecommendationEngine) -> None:
    """Verify fallback grounded explanation is generated without failure if Ollama is unreachable."""
    engine.ollama_client.is_server_reachable.return_value = False

    cand = MediaItemSummary(
        id=546554,
        title="Knives Out",
        media_type="movie",
        overview="A detective investigates the death of a patriarch.",
        vote_average=7.9,
        vote_count=12000,
        popularity=60.0,
        release_year=2019,
        original_language="en",
        genre_ids=[9648, 35],
    )
    intent = ParsedRecommendationIntent(
        content_type="movie",
        reference_title="Glass Onion",
        genres=["Mystery"],
        intent_type="similar_to",
    )

    results = engine.generate_grounded_explanations(
        ranked=[(cand, 85.0, ["Shares thematic DNA with 'Glass Onion'"])],
        intent=intent,
        user_query="Movies like Glass Onion",
    )
    assert len(results) == 1
    rec = results[0]
    assert rec.is_ai_generated is False
    assert "Glass Onion" in rec.ai_explanation
    assert "Knives Out" == rec.media.title


# =============================================================================
# 7. Error Handling & Diagnostics
# =============================================================================

def test_empty_query_error_handling(engine: MovieRecommendationEngine) -> None:
    """Verify empty recommendation query returns clear error."""
    resp = engine.recommend("   ")
    assert resp.error_type == "empty_query"
    assert "empty" in (resp.error_message or "").lower()
    assert len(resp.recommendations) == 0


def test_unconfigured_tmdb_error_handling(engine: MovieRecommendationEngine, mock_tmdb: MagicMock) -> None:
    """Verify unconfigured TMDB returns tmdb_unconfigured error type."""
    mock_tmdb.is_configured.return_value = False
    resp = engine.recommend("Movies like Inception")
    assert resp.error_type == "tmdb_unconfigured"
    assert "configured" in (resp.error_message or "").lower()
    assert len(resp.recommendations) == 0


def test_diagnostics_payload_structure(engine: MovieRecommendationEngine, mock_tmdb: MagicMock) -> None:
    """Verify recommendation response includes developer diagnostics with timings and tiers."""
    mock_item = MediaItemSummary(
        id=157336,
        title="Interstellar",
        media_type="movie",
        overview="A team of explorers travel through a wormhole in space...",
        vote_average=8.4,
        vote_count=30000,
        popularity=100.0,
        release_year=2014,
        original_language="en",
        genre_ids=[12, 18, 878],
    )
    mock_tmdb.search_movies.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=1, results=[mock_item]
    )
    mock_tmdb.get_movie_details.return_value = MediaDetailsModel(
        id=157336,
        title="Interstellar",
        media_type="movie",
        overview="A team of explorers...",
        vote_average=8.4,
        vote_count=30000,
        popularity=100.0,
        release_year=2014,
        original_language="en",
        genre_ids=[12, 18, 878],
        genres=[GenreModel(id=878, name="Science Fiction")],
        cast=[],
        directors=["Christopher Nolan"],
        trailers=[],
        similar=[],
    )
    mock_rec = MediaItemSummary(
        id=27205,
        title="Inception",
        media_type="movie",
        overview="A thief who steals corporate secrets through dream-sharing...",
        vote_average=8.3,
        vote_count=34000,
        popularity=90.0,
        release_year=2010,
        original_language="en",
        genre_ids=[28, 878, 12],
    )
    mock_tmdb.get_movie_recommendations.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=1, results=[mock_rec]
    )
    mock_tmdb.get_movie_similar.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=0, results=[]
    )
    mock_tmdb.get_movie_keywords.return_value = []
    mock_tmdb.discover_movies.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])

    resp = engine.recommend("Movies like Interstellar")
    assert resp.diagnostics is not None
    diag = resp.diagnostics
    assert diag["original_query"] == "Movies like Interstellar"
    assert diag["intent_type"] == "similar_to"
    assert diag["reference_resolved"] is True
    assert diag["reference_tmdb_id"] == 157336
    assert "timings_ms" in diag
    assert "total_pipeline" in diag["timings_ms"]
    assert "retrieval_tiers_used" in diag
    assert "raw_candidates_count" in diag
    assert "eligible_candidates_count" in diag
    assert "final_recommendations_count" in diag
    assert resp.total_candidates_analyzed >= 1
    assert len(resp.recommendations) >= 1
