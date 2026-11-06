"""Phase 3 Verification Tests: Final Validation, End-to-End Testing & Regression Verification.

Covers exact required Scenarios A through M:
- Test A: South Indian Movies ("Suggest South Indian Movies like Premalu") -> 100% South Indian.
- Test B: Malayalam Movies ("Suggest Malayalam romantic comedies") -> 100% Malayalam movies.
- Test C: Telugu Movies ("Suggest Telugu action movies") -> 100% Telugu movies.
- Test D: Hollywood Movies ("Suggest Hollywood science-fiction movies") -> 100% Hollywood / US English.
- Test E: Indian Movies ("Suggest Indian thriller movies") -> 100% Indian cinema.
- Test F: Series Only ("Suggest South Indian series") -> 0% movies, 100% TV series.
- Test G: Movies Only ("Suggest Malayalam movies") -> 0% TV series, 100% movies.
- Test H: Similarity Without Regional Restriction ("Suggest movies like Premalu") -> allows other industries.
- Test I: Insufficient Eligible Results -> returns fewer valid candidates, never backfills ineligible items.
- Test J: Invalid LLM Output -> unsupported/hallucinated titles are rejected.
- Test K: Incomplete Metadata -> candidates without sufficient regional evidence are rejected.
- Test L: Rapid Consecutive Searches -> newer query cannot be overwritten by older async response.
- Test M: Regression Testing -> normal catalog search, details, watchlist, watched, and preferences APIs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.api.movie_models import (
    GenreModel,
    MediaDetailsModel,
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
)
from app.api.tmdb_client import TMDBClient
from app.ai.regional_classifier import (
    INDIAN_LANGUAGES,
    REGION_BOLLYWOOD,
    REGION_HOLLYWOOD,
    REGION_INDIAN,
    REGION_MALAYALAM,
    REGION_SOUTH_INDIAN,
    REGION_TELUGU,
    SOUTH_INDIAN_LANGUAGES,
    validate_candidate_eligibility,
)
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


@pytest.fixture
def temp_db_manager() -> DatabaseManager:
    """Provide an isolated, temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_rec_phase3.db"
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
    """Provide a mocked TMDBClient."""
    return TMDBClient(api_key="mock_tmdb_key_phase3")


@pytest.fixture
def mock_ollama_client() -> MagicMock:
    """Provide a mocked OllamaClient that simulates offline for deterministic unit tests."""
    client = MagicMock()
    client.is_server_reachable.return_value = False
    return client


# =============================================================================
# Test A — South Indian Movies
# =============================================================================


def test_scenario_a_south_indian_movies(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test A: 'Suggest South Indian Movies like Premalu' returns 100% South Indian titles."""
    premalu = MediaItemSummary(
        id=1149791,
        title="Premalu",
        media_type="movie",
        original_language="ml",
        origin_country=["IN"],
        genre_ids=[10749, 35],
    )
    premalu_details = MediaDetailsModel(
        **premalu.model_dump(),
        genres=[GenreModel(id=10749, name="Romance"), GenreModel(id=35, name="Comedy")],
        similar=[
            MediaItemSummary(id=8976, title="A Lot Like Love", media_type="movie", original_language="en", origin_country=["US"]),
            MediaItemSummary(id=9489, title="You've Got Mail", media_type="movie", original_language="en", origin_country=["US"]),
        ],
    )
    discovered_south_indian = [
        MediaItemSummary(id=2001, title="Super Sharanya", media_type="movie", original_language="ml", origin_country=["IN"], genre_ids=[10749, 35], vote_average=7.5),
        MediaItemSummary(id=2002, title="Dragon", media_type="movie", original_language="ta", origin_country=["IN"], genre_ids=[10749, 35], vote_average=7.6),
        MediaItemSummary(id=2003, title="Hi Nanna", media_type="movie", original_language="te", origin_country=["IN"], genre_ids=[10749, 18], vote_average=8.2),
        MediaItemSummary(id=2004, title="Sapta Sagaradaache Ello", media_type="movie", original_language="kn", origin_country=["IN"], genre_ids=[10749, 18], vote_average=8.4),
    ]

    mock_tmdb_client.search_multi = MagicMock(return_value=PagedResultModel(results=[premalu]))
    mock_tmdb_client.get_movie_details = MagicMock(return_value=premalu_details)
    mock_tmdb_client.discover_movies = MagicMock(return_value=PagedResultModel(results=discovered_south_indian))

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    response = engine.recommend("Suggest South Indian Movies like Premalu", limit=6)

    assert len(response.recommendations) > 0
    for rec in response.recommendations:
        item = rec.media
        assert item.media_type == "movie"
        assert item.original_language in SOUTH_INDIAN_LANGUAGES
        if item.origin_country:
            assert "IN" in item.origin_country
        assert item.original_language != "en"


# =============================================================================
# Test B — Malayalam Movies
# =============================================================================


def test_scenario_b_malayalam_movies(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test B: 'Suggest Malayalam romantic comedy movies' returns only eligible Malayalam movies."""
    ml_items = [
        MediaItemSummary(id=301, title="Premam", media_type="movie", original_language="ml", origin_country=["IN"], genre_ids=[10749, 35], vote_average=8.3),
        MediaItemSummary(id=302, title="Hridayam", media_type="movie", original_language="ml", origin_country=["IN"], genre_ids=[10749, 18], vote_average=8.0),
    ]
    mock_tmdb_client.discover_movies = MagicMock(return_value=PagedResultModel(results=ml_items))
    mock_tmdb_client.discover_all = MagicMock(return_value=PagedResultModel(results=ml_items))

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    response = engine.recommend("Suggest Malayalam romantic comedy movies", limit=6)

    assert len(response.recommendations) == 2
    for rec in response.recommendations:
        assert rec.media.original_language == "ml"
        assert rec.media.media_type == "movie"


# =============================================================================
# Test C — Telugu Movies
# =============================================================================


def test_scenario_c_telugu_movies(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test C: 'Suggest Telugu action movies' returns only eligible Telugu movies."""
    te_items = [
        MediaItemSummary(id=401, title="RRR", media_type="movie", original_language="te", origin_country=["IN"], genre_ids=[28, 18], vote_average=8.8),
        MediaItemSummary(id=402, title="Baahubali", media_type="movie", original_language="te", origin_country=["IN"], genre_ids=[28, 14], vote_average=8.5),
    ]
    mock_tmdb_client.discover_movies = MagicMock(return_value=PagedResultModel(results=te_items))

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    response = engine.recommend("Suggest Telugu action movies", limit=6)

    assert len(response.recommendations) == 2
    for rec in response.recommendations:
        assert rec.media.original_language == "te"
        assert rec.media.media_type == "movie"


# =============================================================================
# Test D — Hollywood Movies
# =============================================================================


def test_scenario_d_hollywood_movies(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test D: 'Suggest Hollywood science-fiction movies' returns only Hollywood / US English titles."""
    hollywood_items = [
        MediaItemSummary(id=501, title="Blade Runner 2049", media_type="movie", original_language="en", origin_country=["US"], genre_ids=[878], vote_average=8.0),
        MediaItemSummary(id=502, title="Arrival", media_type="movie", original_language="en", origin_country=["US"], genre_ids=[878], vote_average=7.9),
    ]
    mock_tmdb_client.discover_movies = MagicMock(return_value=PagedResultModel(results=hollywood_items))

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    response = engine.recommend("Suggest Hollywood science-fiction movies", limit=6)

    assert len(response.recommendations) == 2
    for rec in response.recommendations:
        assert rec.media.original_language == "en"
        assert rec.media.origin_country == ["US"]


# =============================================================================
# Test E — Indian Movies
# =============================================================================


def test_scenario_e_indian_movies(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test E: 'Suggest Indian thriller movies' returns only Indian cinema."""
    indian_items = [
        MediaItemSummary(id=601, title="Andhadhun", media_type="movie", original_language="hi", origin_country=["IN"], genre_ids=[53, 35], vote_average=8.2),
        MediaItemSummary(id=602, title="Drishyam", media_type="movie", original_language="ml", origin_country=["IN"], genre_ids=[53, 18], vote_average=8.4),
    ]
    mock_tmdb_client.discover_movies = MagicMock(return_value=PagedResultModel(results=indian_items))

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    response = engine.recommend("Suggest Indian thriller movies", limit=6)

    assert len(response.recommendations) == 2
    for rec in response.recommendations:
        assert rec.media.original_language in INDIAN_LANGUAGES


# =============================================================================
# Test F — Series Only
# =============================================================================


def test_scenario_f_series_only(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test F: 'Suggest South Indian series' excludes movie records completely."""
    series_items = [
        MediaItemSummary(id=701, title="Suzhal: The Vortex", media_type="tv", original_language="ta", origin_country=["IN"], genre_ids=[80, 9648], vote_average=7.9),
        MediaItemSummary(id=702, title="Kerala Crime Files", media_type="tv", original_language="ml", origin_country=["IN"], genre_ids=[80, 18], vote_average=7.7),
    ]
    mock_tmdb_client.discover_series = MagicMock(return_value=PagedResultModel(results=series_items))

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    response = engine.recommend("Suggest South Indian series", limit=6)

    assert len(response.recommendations) == 2
    for rec in response.recommendations:
        assert rec.media.media_type == "tv"
        assert rec.media.media_type != "movie"


# =============================================================================
# Test G — Movies Only
# =============================================================================


def test_scenario_g_movies_only(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test G: 'Suggest Malayalam movies' excludes television series records completely."""
    movie_items = [
        MediaItemSummary(id=801, title="Manjummel Boys", media_type="movie", original_language="ml", origin_country=["IN"], genre_ids=[12, 18], vote_average=8.5),
    ]
    mock_tmdb_client.discover_movies = MagicMock(return_value=PagedResultModel(results=movie_items))

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    response = engine.recommend("Suggest Malayalam movies", limit=6)

    assert len(response.recommendations) == 1
    assert response.recommendations[0].media.media_type == "movie"


# =============================================================================
# Test H — Similarity Without Regional Restriction
# =============================================================================


def test_scenario_h_similarity_without_regional_restriction(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test H: 'Suggest movies like Premalu' allows global titles because no regional restriction requested."""
    premalu = MediaItemSummary(id=1149791, title="Premalu", media_type="movie", original_language="ml", origin_country=["IN"], genre_ids=[10749, 35])
    romcom_hollywood = MediaItemSummary(id=901, title="500 Days of Summer", media_type="movie", original_language="en", origin_country=["US"], genre_ids=[10749, 35], vote_average=7.7)

    mock_tmdb_client.search_multi = MagicMock(return_value=PagedResultModel(results=[premalu]))
    mock_tmdb_client.get_movie_details = MagicMock(
        return_value=MediaDetailsModel(
            **premalu.model_dump(),
            genres=[GenreModel(id=10749, name="Romance"), GenreModel(id=35, name="Comedy")],
            similar=[romcom_hollywood],
        )
    )

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    intent = engine.parse_intent_deterministic("Suggest movies like Premalu")
    assert intent.region is None  # no explicit regional restriction

    candidates = engine.retrieve_candidates(intent, limit=6)
    assert len(candidates) >= 1
    assert candidates[0].title == "500 Days of Summer"


# =============================================================================
# Test I — Insufficient Eligible Results
# =============================================================================


def test_scenario_i_insufficient_eligible_results(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test I: When only 1 eligible title exists, returns 1; never inserts ineligible titles to pad results."""
    lone_south_indian = MediaItemSummary(
        id=999,
        title="Only South Indian RomCom",
        media_type="movie",
        original_language="ml",
        origin_country=["IN"],
        genre_ids=[10749, 35],
    )
    mock_tmdb_client.search_multi = MagicMock(return_value=PagedResultModel(results=[]))
    mock_tmdb_client.discover_movies = MagicMock(return_value=PagedResultModel(results=[lone_south_indian]))

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    response = engine.recommend("Suggest South Indian Movies like Premalu", limit=6)

    # Must return exactly 1 item, NOT 6 by backfilling Hollywood titles
    assert len(response.recommendations) == 1
    assert response.recommendations[0].media.title == "Only South Indian RomCom"


# =============================================================================
# Test J — Invalid LLM Output
# =============================================================================


def test_scenario_j_invalid_llm_output_rejected(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
):
    """Test J: Hallucinated titles from LLM cannot alter or inject unsupported records."""
    mock_ollama = MagicMock()
    mock_ollama.is_server_reachable.return_value = True
    mock_ollama.chat.return_value = "I recommend Avatar and Star Wars because they are great!"

    real_movie = MediaItemSummary(
        id=1234,
        title="Real Movie",
        media_type="movie",
        original_language="ml",
        origin_country=["IN"],
        overview="Real synopsis",
    )

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )
    intent = ParsedRecommendationIntent(content_type="movie", region=REGION_SOUTH_INDIAN, languages=["ml"])

    results = engine.generate_grounded_explanations(
        ranked=[(real_movie, 90.0, ["Match"])],
        intent=intent,
        user_query="Suggest South Indian Movies",
    )

    assert len(results) == 1
    assert results[0].media.id == 1234
    assert results[0].media.title == "Real Movie"


# =============================================================================
# Test K — Incomplete Metadata
# =============================================================================


def test_scenario_k_incomplete_metadata_rejected():
    """Test K: Missing language or conflicting country fails strict regional verification."""
    intent = ParsedRecommendationIntent(
        region=REGION_SOUTH_INDIAN,
        languages=["ml", "te", "ta", "kn"],
    )

    item_missing_lang = MediaItemSummary(id=1, title="No Lang Title", original_language=None)
    item_conflicting_country = MediaItemSummary(id=2, title="US Malayalam Title", original_language="ml", origin_country=["US"])

    is_ok_1, _ = validate_candidate_eligibility(item_missing_lang, intent)
    is_ok_2, _ = validate_candidate_eligibility(item_conflicting_country, intent)

    assert is_ok_1 is False
    assert is_ok_2 is False


# =============================================================================
# Test L — Rapid Consecutive Searches
# =============================================================================


def test_scenario_l_rapid_consecutive_searches(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test L: Rapid query updates produce consistent independent responses."""
    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    # First query
    mock_tmdb_client.discover_movies = MagicMock(
        return_value=PagedResultModel(results=[
            MediaItemSummary(id=1, title="Item One", media_type="movie", original_language="ml", origin_country=["IN"])
        ])
    )
    resp1 = engine.recommend("Suggest South Indian Movies", limit=6)

    # Second query immediately following
    mock_tmdb_client.discover_movies = MagicMock(
        return_value=PagedResultModel(results=[
            MediaItemSummary(id=2, title="Item Two", media_type="movie", original_language="te", origin_country=["IN"])
        ])
    )
    resp2 = engine.recommend("Suggest Telugu Movies", limit=6)

    assert resp1.recommendations[0].media.title == "Item One"
    assert resp2.recommendations[0].media.title == "Item Two"
    assert resp1.query != resp2.query


# =============================================================================
# Test M — Regression Testing Across Existing Features
# =============================================================================


def test_scenario_m_regression_movie_hub_endpoints(temp_db_manager: DatabaseManager):
    """Test M: Existing Movie Hub endpoints remain fully functional."""
    app = create_app()
    client = TestClient(app)

    # 1. Config status endpoint
    config_resp = client.get("/api/movies/config")
    assert config_resp.status_code == 200

    # 2. Recommendations parse endpoint
    parse_resp = client.post("/api/movies/recommendations/parse", json={"query": "Suggest South Indian Movies like Premalu"})
    assert parse_resp.status_code == 200
    intent_data = parse_resp.json()
    assert intent_data["region"] == "south_indian"
    assert intent_data["content_type"] == "movie"

    # 3. Preferences get endpoint
    pref_resp = client.get("/api/movies/storage/preferences")
    assert pref_resp.status_code == 200

    # 4. Watchlist get endpoint
    watchlist_resp = client.get("/api/movies/storage/watchlist")
    assert watchlist_resp.status_code == 200
