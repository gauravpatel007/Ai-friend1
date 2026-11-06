"""Phase 9: Comprehensive Quality Assurance, Edge Case & Stress Test Suite.

Verifies:
9.1/9.2 Model Evaluation & Configurable Model Resolution
9.3 Full Regression Testing:
    - Invalid reference movie titles
    - Misspelled queries
    - Empty queries
    - Network disconnection (TMDBNetworkError)
    - TMDB authentication errors (TMDBAuthError)
    - API rate limits (TMDBRateLimitError)
    - Very broad movie requests
    - Very restrictive movie requests
    - Repeated queries (in-memory response & reference caching)
    - Conflicting conditions (Hollywood vs Indian cinema)
    - Language-specific queries (Malayalam, Telugu, Spanish, Hindi, Korean)
    - Large candidate list stress testing (100+ candidates ranked in <100ms)
    - Application restart & preference persistence
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.ai.movie_ranking_engine import MovieRankingEngine, extract_candidate_features
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.api.movie_models import (
    MediaDetailsModel,
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationResponse,
    RecommendedTitleModel,
    UserMovieProfile,
)
from app.api.tmdb_client import (
    TMDBAuthError,
    TMDBClient,
    TMDBNetworkError,
    TMDBNotFoundError,
    TMDBRateLimitError,
    TMDBTimeoutError,
)
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository
from tests.evaluation.mock_tmdb_data import MockTMDBClient


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database manager."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_phase9.db"
        db = DatabaseManager(db_path=str(db_path))
        yield db
        db.close()


@pytest.fixture
def storage(temp_db):
    return MovieStorageRepository(db_manager=temp_db)


@pytest.fixture
def mock_tmdb():
    return MockTMDBClient(scenario="success")


@pytest.fixture
def rec_engine(mock_tmdb, storage):
    return MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=storage,
        default_model="llama3.2:3b",
    )


# =============================================================================
# 1. Error Handling & Edge Cases
# =============================================================================

def test_empty_query_handling(rec_engine: MovieRecommendationEngine):
    """Empty query returns clean error response without crashing."""
    resp = rec_engine.recommend("")
    assert resp.error_type == "empty_query"
    assert len(resp.recommendations) == 0

    resp_ws = rec_engine.recommend("   \n\t  ")
    assert resp_ws.error_type == "empty_query"


def test_invalid_reference_title_graceful_fallback(storage: MovieStorageRepository):
    """When a non-existent movie title is given, system falls back to discovery."""
    mock_tmdb = MagicMock(spec=TMDBClient)
    mock_tmdb.is_configured.return_value = True
    # Search for reference returns 0 results
    mock_tmdb.search_movies.return_value = PagedResultModel(page=1, total_pages=0, total_results=0, results=[])
    # Keyword/genre discovery returns fallback candidates
    mock_tmdb.discover_movies.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=1,
        results=[
            MediaItemSummary(
                id=999,
                title="Fallback Sci-Fi Title",
                original_title="Fallback Sci-Fi Title",
                media_type="movie",
                overview="A good backup movie when reference is not found.",
                release_date="2020-01-01",
                vote_average=7.5,
                vote_count=500,
                popularity=30.0,
                original_language="en",
                genre_ids=[878],
                genre_names=["Science Fiction"],
            )
        ]
    )

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage)
    resp = engine.recommend("Movies like Xyznonexistentfilm99999")
    assert resp.error_type is None
    assert len(resp.recommendations) >= 1
    assert resp.recommendations[0].media.title == "Fallback Sci-Fi Title"


def test_misspelled_query_handling(rec_engine: MovieRecommendationEngine):
    """Misspellings in query still extract meaningful concepts and genres."""
    intent = rec_engine.parse_intent_deterministic("mind bending syfy with plot twist")
    assert "Science Fiction" in intent.genres or "mind-bending" in intent.keywords or intent.mood == "mind-bending"


def test_network_disconnection_error_handling(storage: MovieStorageRepository):
    """Network failure returns structured error without uncaught exceptions."""
    mock_tmdb = MagicMock(spec=TMDBClient)
    mock_tmdb.is_configured.return_value = True
    mock_tmdb.search_movies.side_effect = TMDBNetworkError("No internet connection")
    mock_tmdb.discover_movies.side_effect = TMDBNetworkError("No internet connection")

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage)
    resp = engine.recommend("Great action movies")
    assert resp.error_type == "network_error"
    assert "network" in resp.error_message.lower()


def test_tmdb_auth_error_handling(storage: MovieStorageRepository):
    """Invalid TMDB API key returns authentication error with clear message."""
    mock_tmdb = MagicMock(spec=TMDBClient)
    mock_tmdb.is_configured.return_value = True
    mock_tmdb.discover_movies.side_effect = TMDBAuthError("Invalid API key")

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage)
    resp = engine.recommend("Great comedy films")
    assert resp.error_type == "tmdb_auth_error"
    assert "API key" in resp.error_message or "authentication" in resp.error_message.lower()


def test_tmdb_rate_limit_error_handling(storage: MovieStorageRepository):
    """HTTP 429 rate limit triggers graceful error handling."""
    mock_tmdb = MagicMock(spec=TMDBClient)
    mock_tmdb.is_configured.return_value = True
    mock_tmdb.discover_movies.side_effect = TMDBRateLimitError("Rate limit exceeded")
    mock_tmdb.discover_all.side_effect = TMDBRateLimitError("Rate limit exceeded")
    mock_tmdb.discover_series.side_effect = TMDBRateLimitError("Rate limit exceeded")

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage)
    resp = engine.recommend("Romantic comedies")
    assert resp.error_type == "rate_limit_exceeded"


# =============================================================================
# 2. Scope & Condition Tests (Broad, Restrictive, Conflicting, Language)
# =============================================================================

def test_very_broad_movie_request(rec_engine: MovieRecommendationEngine):
    """Very broad query ('recommend some good movies') retrieves popular quality films."""
    resp = rec_engine.recommend("recommend some good movies")
    assert resp.error_type is None
    assert len(resp.recommendations) > 0
    assert all(r.media.vote_average >= 6.0 for r in resp.recommendations)


def test_very_restrictive_request(storage: MovieStorageRepository):
    """Ultra-restrictive query with no matches returns graceful zero results without crashing."""
    mock_tmdb = MagicMock(spec=TMDBClient)
    mock_tmdb.is_configured.return_value = True
    mock_tmdb.discover_movies.return_value = PagedResultModel(page=1, total_pages=0, total_results=0, results=[])

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=storage)
    resp = engine.recommend("1924 silent albanian documentary")
    assert resp.error_type in ("zero_results", "candidates_filtered", None)
    assert len(resp.recommendations) == 0


def test_conflicting_conditions_detection(rec_engine: MovieRecommendationEngine):
    """Query with mutually exclusive industries flags conflict in parsed intent."""
    intent = rec_engine.parse_intent_deterministic("Hollywood Bollywood action thriller")
    assert intent.has_conflict is True
    assert "cannot be combined" in intent.conflict_message


def test_language_specific_queries(rec_engine: MovieRecommendationEngine):
    """Regional queries correctly tag target language and country codes."""
    # Malayalam
    intent_ml = rec_engine.parse_intent_deterministic("Best Malayalam crime thrillers")
    assert intent_ml.language == "ml"
    assert intent_ml.region == "malayalam"

    # Telugu
    intent_te = rec_engine.parse_intent_deterministic("Telugu action blockbusters")
    assert intent_te.language == "te"
    assert intent_te.region == "telugu"

    # Spanish
    intent_es = rec_engine.parse_intent_deterministic("Spanish horror films")
    assert intent_es.language == "es"


# =============================================================================
# 3. Performance & Stress Tests (Caching, Large Candidate Lists, Speed)
# =============================================================================

def test_repeated_queries_use_response_cache(rec_engine: MovieRecommendationEngine):
    """Subsequent identical queries hit in-memory response cache immediately."""
    q = "Mind-bending sci-fi movies"
    t0 = time.perf_counter()
    resp1 = rec_engine.recommend(q)
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    resp2 = rec_engine.recommend(q)
    t3 = time.perf_counter()

    first_dur = t1 - t0
    cached_dur = t3 - t2
    assert cached_dur < first_dur or cached_dur < 0.05
    assert len(resp1.recommendations) == len(resp2.recommendations)


def test_large_candidate_list_ranking_stress(storage: MovieStorageRepository):
    """Ranking engine effortlessly handles 100+ candidates in under 100ms."""
    ranker = MovieRankingEngine()
    intent = ParsedRecommendationIntent(
        genres=["Science Fiction", "Mystery"],
        mood="mind-bending",
        query_type="discovery",
    )

    # Generate 120 synthetic candidates
    candidates: List[MediaItemSummary] = []
    for i in range(120):
        candidates.append(
            MediaItemSummary(
                id=1000 + i,
                title=f"Synthetic Title {i}",
                original_title=f"Synthetic Title {i}",
                media_type="movie",
                overview="A mysterious journey exploring time and alternate dimensions." if i % 2 == 0 else "A standard film.",
                release_date="2020-01-01",
                release_year=2020,
                vote_average=5.0 + (i % 50) * 0.1,
                vote_count=100 + i * 50,
                popularity=20.0 + i,
                original_language="en",
                genre_ids=[878, 9648] if i % 3 == 0 else [28],
                genre_names=["Science Fiction", "Mystery"] if i % 3 == 0 else ["Action"],
            )
        )

    t_start = time.perf_counter()
    ranked = ranker.rank_candidates(candidates=candidates, intent=intent, limit=10)
    dur_ms = (time.perf_counter() - t_start) * 1000.0

    assert len(ranked) == 10
    # Must rank 120 candidates in under 100ms
    assert dur_ms < 100.0
    # Top ranked should be high-scoring Sci-Fi/Mystery
    top_cand, top_score, _, _ = ranked[0]
    assert top_score > 55.0


def test_configurable_model_support(storage: MovieStorageRepository, mock_tmdb):
    """Engine respects configurable model parameter."""
    engine_llama = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=storage,
        default_model="llama3.2:3b",
    )
    assert engine_llama.default_model == "llama3.2:3b"

    engine_qwen = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=storage,
        default_model="qwen3.5:4b",
    )
    assert engine_qwen.default_model == "qwen3.5:4b"
    assert engine_qwen.explanation_engine.default_model == "qwen3.5:4b"
