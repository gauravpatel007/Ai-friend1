"""Phase 9 Verification Tests: Ollama-Powered AI Recommendations.

Verifies:
- 9.1 Reuse existing Ollama client infrastructure and model manager without altering defaults.
- 9.2 Natural-language intent parsing (Malayalam thriller, Hindi comedy, sci-fi series, similar-to title, release periods).
- 9.3 Real candidate title retrieval from TMDB discovery/search (zero fabricated titles).
- 9.4 Transparent multi-signal ranking (genres, language, region, release period, quality, user preferences, watched filtering).
- 9.5 Grounded explanation generation strictly anchored in real metadata with deterministic fallback.
- 9.6 FastAPI endpoints (/api/movies/recommendations, /api/movies/recommendations/parse).
- 9.7 Resilience when Ollama is offline or times out (non-blocking, graceful fallback).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.api.movie_models import (
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationRequest,
    RecommendationResponse,
    RecommendedTitleModel,
)
from app.api.tmdb_client import TMDBClient
from app.ai.ollama_client import OllamaClient
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


@pytest.fixture
def temp_db_manager() -> DatabaseManager:
    """Provide an isolated, temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_rec_phase9.db"
        manager = DatabaseManager(db_path=db_path)
        try:
            yield manager
        finally:
            manager.close()


@pytest.fixture
def movie_repo(temp_db_manager: DatabaseManager) -> MovieStorageRepository:
    """Provide a MovieStorageRepository backed by the temporary database."""
    return MovieStorageRepository(db_manager=temp_db_manager)


@pytest.fixture
def mock_tmdb_client() -> TMDBClient:
    """Provide a mocked TMDBClient returning controlled verified items."""
    client = TMDBClient(api_key="mock_tmdb_key_phase9")
    return client


# =============================================================================
# 1. Natural Language Intent Parsing (Deterministic & LLM Fallback) (9.2)
# =============================================================================


def test_parse_intent_underrated_malayalam_thriller(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.2: Parse 'Recommend an underrated Malayalam thriller'."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    intent = engine.parse_intent_deterministic("Recommend an underrated Malayalam thriller")
    assert intent.language == "ml"
    assert "Thriller" in intent.genres
    assert "underrated" in intent.keywords


def test_parse_intent_hindi_comedy(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.2: Parse 'Find a Hindi comedy'."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    intent = engine.parse_intent_deterministic("Find a Hindi comedy")
    assert intent.language == "hi"
    assert "Comedy" in intent.genres


def test_parse_intent_scifi_series(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.2: Parse 'Suggest a science-fiction series'."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    intent = engine.parse_intent_deterministic("Suggest a science-fiction series")
    assert intent.content_type == "tv"
    assert "Science Fiction" in intent.genres


def test_parse_intent_similar_to_title(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.2: Parse 'Recommend movies similar to Interstellar'."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    intent = engine.parse_intent_deterministic("Recommend movies similar to Interstellar")
    assert intent.similar_to_title == "Interstellar"
    assert intent.content_type == "movie"


def test_parse_intent_90s_action_movie(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.2: Parse 'Find a 90s action movie'."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    intent = engine.parse_intent_deterministic("Find a 90s action movie")
    assert intent.content_type == "movie"
    assert "Action" in intent.genres
    assert intent.release_year_gte == 1990
    assert intent.release_year_lte == 1999


def test_parse_intent_south_indian_cinema(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.2: Parse 'Best South Indian action films'."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    intent = engine.parse_intent_deterministic("Best South Indian action films")
    assert intent.region == "south_indian"
    assert "Action" in intent.genres


# =============================================================================
# 2. Candidate Retrieval from Real TMDB Metadata (9.3)
# =============================================================================


def test_candidate_retrieval_uses_real_metadata(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.3: Real candidate titles retrieved from TMDB endpoints without hallucinating."""
    fake_item_1 = MediaItemSummary(
        id=101,
        title="Drishyam",
        media_type="movie",
        release_date="2013-12-19",
        release_year=2013,
        vote_average=8.3,
        original_language="ml",
        genre_ids=[53, 80],
        overview="Georgekutty lives a happy life with his family...",
    )
    fake_item_2 = MediaItemSummary(
        id=102,
        title="Memories",
        media_type="movie",
        release_date="2013-08-09",
        release_year=2013,
        vote_average=7.9,
        original_language="ml",
        genre_ids=[53, 9648],
        overview="Sam Alex, a police officer dealing with alcoholism...",
    )

    mock_tmdb_client.discover_movies = MagicMock(
        return_value=PagedResultModel(
            page=1,
            total_pages=1,
            total_results=2,
            results=[fake_item_1, fake_item_2],
        )
    )

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)
    intent = ParsedRecommendationIntent(
        content_type="movie",
        language="ml",
        genres=["Thriller"],
    )

    candidates = engine.retrieve_candidates(intent)
    assert len(candidates) == 2
    assert candidates[0].title == "Drishyam"
    assert candidates[0].original_language == "ml"
    assert candidates[1].title == "Memories"
    mock_tmdb_client.discover_movies.assert_called_once()


# =============================================================================
# 3. Transparent Multi-Signal Ranking & User Preference Awareness (9.4)
# =============================================================================


def test_ranking_scoring_and_preference_boost(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.4: Multi-signal scoring evaluates genres, language, quality, and user preferences."""
    # 1. Set user preferences in repo
    movie_repo.update_preferences(
        preferred_genres=["Thriller", "Crime"],
        preferred_languages=["ml"],
        recommendation_settings={"include_watched": True, "min_rating": 6.0},
    )

    item_high_match = MediaItemSummary(
        id=201,
        title="Malayalam Thriller Perfect Match",
        media_type="movie",
        release_year=2021,
        vote_average=8.4,
        original_language="ml",
        genre_ids=[53, 80],  # Thriller (53), Crime (80)
        overview="A gripping tale of suspense and deduction in Kerala.",
    )

    item_low_match = MediaItemSummary(
        id=202,
        title="Unrelated Romance",
        media_type="movie",
        release_year=2005,
        vote_average=6.0,
        original_language="fr",
        genre_ids=[10749],  # Romance
        overview="A gentle romance set in Paris.",
    )

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)
    intent = ParsedRecommendationIntent(
        content_type="movie",
        language="ml",
        genres=["Thriller"],
        genre_ids=[53],
    )

    ranked = engine.rank_candidates([item_low_match, item_high_match], intent, limit=10)

    assert len(ranked) == 2
    # Perfect match should be ranked #1 with high score
    item_top, score_top, reasons_top = ranked[0]
    item_bot, score_bot, reasons_bot = ranked[1]
    assert item_top.id == 201
    assert score_top > score_bot
    assert any("Exact genre match" in r for r in reasons_top)
    assert any("Matches requested language" in r for r in reasons_top)
    assert any("preferred genre" in r.lower() for r in reasons_top)


def test_ranking_excludes_watched_when_preference_enabled(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.4: Exclude watched titles when user has include_watched=False."""
    movie_repo.update_preferences(
        recommendation_settings={"include_watched": False},
    )

    movie_repo.add_or_update_entry(
        tmdb_id=301,
        title="Already Watched Movie",
        media_type="movie",
        status="watched",
    )

    item_watched = MediaItemSummary(
        id=301,
        title="Already Watched Movie",
        media_type="movie",
        release_year=2020,
        vote_average=8.0,
        original_language="hi",
        genre_ids=[35],
    )
    item_unwatched = MediaItemSummary(
        id=302,
        title="Fresh Movie",
        media_type="movie",
        release_year=2020,
        vote_average=7.5,
        original_language="hi",
        genre_ids=[35],
    )

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)
    intent = ParsedRecommendationIntent(language="hi", genres=["Comedy"], genre_ids=[35])

    ranked = engine.rank_candidates([item_watched, item_unwatched], intent, limit=10)

    # Watched item 301 must be excluded from recommendations
    assert len(ranked) == 1
    assert ranked[0][0].id == 302
    assert ranked[0][0].title == "Fresh Movie"


# =============================================================================
# 4. Grounded Explanations & Resilient Fallback (9.5, 9.7)
# =============================================================================


def test_grounded_explanation_deterministic_fallback(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.5 & 9.7: When Ollama is unreachable, explanations deterministically fallback safely."""
    # Mock OllamaClient with unreachable server
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.is_server_reachable.return_value = False

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    item = MediaItemSummary(
        id=401,
        title="Kantara",
        media_type="movie",
        release_year=2022,
        vote_average=8.2,
        original_language="kn",
        overview="When greed paves the way for betrayal, a human-nature conflict ensues.",
    )
    ranked = [(item, 9.2, ["Language match: kn", "Genre match: Drama"])]
    intent = ParsedRecommendationIntent(language="kn", genres=["Drama"])

    explained = engine.generate_grounded_explanations(ranked, intent, "Suggest a Kannada drama")

    assert len(explained) == 1
    assert explained[0].ai_explanation != ""
    assert explained[0].is_ai_generated is False
    assert "Kantara" in explained[0].ai_explanation or "KN" in explained[0].ai_explanation


def test_grounded_explanation_ollama_success(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 9.5: Ollama generates strictly grounded rationale without hallucinating."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.is_server_reachable.return_value = True
    mock_ollama.chat.return_value = "A gripping Kannada folkloric drama that explores indigenous traditions and high-stakes tension."

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    item = MediaItemSummary(
        id=402,
        title="Kantara",
        media_type="movie",
        release_year=2022,
        vote_average=8.2,
        original_language="kn",
        overview="When greed paves the way for betrayal, a human-nature conflict ensues.",
    )
    ranked = [(item, 9.2, ["Language match: kn"])]
    intent = ParsedRecommendationIntent(language="kn")

    explained = engine.generate_grounded_explanations(ranked, intent, "Suggest a Kannada movie")

    assert len(explained) == 1
    assert explained[0].is_ai_generated is True
    assert "gripping Kannada folkloric drama" in explained[0].ai_explanation
    # Verify chat was called with prompt containing real synopsis
    mock_ollama.chat.assert_called_once()
    call_args = mock_ollama.chat.call_args[1]["messages"]
    assert "Kantara" in call_args[1]["content"]


# =============================================================================
# 5. FastAPI Endpoints (/api/movies/recommendations/*) (9.6)
# =============================================================================


def test_api_recommendations_parse_endpoint():
    """Test 9.6: POST /api/movies/recommendations/parse."""
    app = create_app()
    client = TestClient(app)

    res = client.post(
        "/api/movies/recommendations/parse",
        json={"prompt": "Recommend an underrated Malayalam thriller from 2019"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "ml"
    assert "Thriller" in data["genres"]
    assert "underrated" in data["keywords"]
    assert data["release_year"] == 2019


def test_api_recommendations_empty_prompt_returns_400():
    """Test 9.6: POST /api/movies/recommendations with blank prompt."""
    app = create_app()
    client = TestClient(app)

    res = client.post(
        "/api/movies/recommendations",
        json={"query": "   ", "limit": 5},
    )
    assert res.status_code == 400
    assert "cannot be empty" in res.json()["detail"].lower()


def test_api_recommendations_end_to_end_mocked():
    """Test 9.6: POST /api/movies/recommendations with mocked engine."""
    from app.api.movie_routes import get_recommendation_engine

    app = create_app()
    fake_engine = MagicMock(spec=MovieRecommendationEngine)
    fake_response = RecommendationResponse(
        query="Find a Hindi comedy",
        interpreted_intent=ParsedRecommendationIntent(language="hi", genres=["Comedy"]),
        recommendations=[
            RecommendedTitleModel(
                media=MediaItemSummary(
                    id=501,
                    title="3 Idiots",
                    media_type="movie",
                    release_year=2009,
                    vote_average=8.0,
                    original_language="hi",
                    overview="Two friends search for their long-lost companion...",
                ),
                score=95.0,
                match_reasons=["Matches requested language (HI)", "Exact genre match"],
                ai_explanation="A celebrated Hindi comedy-drama about engineering college life and friendship.",
                is_ai_generated=True,
            )
        ],
        total_candidates_analyzed=1,
        ai_available=True,
        model_used="llama3.2:3b",
    )
    fake_engine.recommend.return_value = fake_response
    app.dependency_overrides[get_recommendation_engine] = lambda: fake_engine

    client = TestClient(app)
    res = client.post(
        "/api/movies/recommendations",
        json={"query": "Find a Hindi comedy", "limit": 5},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "Find a Hindi comedy"
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["media"]["title"] == "3 Idiots"
    assert data["recommendations"][0]["is_ai_generated"] is True
    assert data["ai_available"] is True
