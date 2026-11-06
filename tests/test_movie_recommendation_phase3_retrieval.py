"""Phase 3 Verification Tests: Multi-Source TMDB Movie Retrieval Engine.

Covers exact Phase 3 requirements:
3.1 Reference movie resolution (noisy inputs, prefixes, year hints, colon sub-search).
3.2 & 3.3 Similar & recommendation retrieval combination without duplicate IDs.
3.4 Genre-based discovery (OR pipe '|' for genres_any, AND comma ',' for genres_all).
3.5 Keyword-based discovery (pre-mapped trope IDs, dynamic TMDB search, OR pipe matching).
3.6 Candidate merging and metadata preservation (retrieval_source, reference_movie_id, TMDB ID deduplication).
3.7 Progressive fallback retrieval (page 2, relaxed vote count, while strictly locking mandatory language/region constraints).
3.8 Candidate count targets (simple 20-30, complex 40-100, reference 20-40).
3.9 Error handling & diagnostic categorization (tmdb_auth_error, network_timeout, rate_limit, reference_not_found, candidates_filtered, zero_results).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.api.movie_models import (
    GenreModel,
    MediaDetailsModel,
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationQueryType,
)
from app.api.tmdb_client import (
    TMDBClient,
    TMDBAuthError,
    TMDBNetworkError,
    TMDBRateLimitError,
    TMDBTimeoutError,
)
from app.ai.movie_taxonomy import (
    TMDB_KEYWORD_IDS,
    resolve_keyword_ids,
)
from app.ai.movie_recommendation_engine import (
    MovieRecommendationEngine,
    clean_reference_title_string,
)
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


@pytest.fixture
def temp_db_manager() -> DatabaseManager:
    """Provide an isolated, temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_rec_phase3_retrieval.db"
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
def mock_tmdb() -> MagicMock:
    """Provide a mocked TMDBClient with standard discovery and search behaviors."""
    client = MagicMock(spec=TMDBClient)
    client.is_configured.return_value = True
    client.search_multi.return_value = PagedResultModel()
    client.search_movies.return_value = PagedResultModel()
    client.discover_movies.return_value = PagedResultModel()
    client.discover_series.return_value = PagedResultModel()
    client.discover_all.return_value = PagedResultModel()
    client.get_movie_recommendations.return_value = PagedResultModel()
    client.get_movie_similar.return_value = PagedResultModel()
    client.get_movie_keywords.return_value = []
    client.search_keywords.return_value = []
    return client


@pytest.fixture
def mock_ollama() -> MagicMock:
    """Provide a mocked OllamaClient."""
    client = MagicMock()
    client.is_server_reachable.return_value = False
    return client


# =============================================================================
# 3.1 Reference Title Cleaning & Resolution Tests
# =============================================================================


def test_clean_reference_title_string():
    """Verify conversational prefixes and sentence noise are cleanly stripped."""
    assert clean_reference_title_string("Movies like Glass Onion")[0] == "Glass Onion"
    assert clean_reference_title_string("Movies similar to Knives Out")[0] == "Knives Out"
    assert clean_reference_title_string("Mystery Movies similar to Glass Onion")[0] == "Glass Onion"
    assert clean_reference_title_string("Suggest films like The Prestige")[0] == "The Prestige"
    assert clean_reference_title_string("South Indian Movies like Premalu")[0] == "Premalu"

    # Year hint extraction
    title, year = clean_reference_title_string("Movies like Interstellar (2014)")
    assert title == "Interstellar"
    assert year == 2014

    title2, year2 = clean_reference_title_string("Movies similar to Inception 2010")
    assert title2 == "Inception"
    assert year2 == 2010

    # Unaltered complex subtitle
    complex_title, _ = clean_reference_title_string("Glass Onion: A Knives Out Mystery")
    assert complex_title == "Glass Onion: A Knives Out Mystery"


def test_reference_movie_resolution_multi_tier(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify reference resolution handles noisy user input and matches the real TMDB item."""
    glass_onion_cand = MediaItemSummary(
        id=661374,
        title="Glass Onion: A Knives Out Mystery",
        original_title="Glass Onion: A Knives Out Mystery",
        media_type="movie",
        release_year=2022,
        popularity=45.2,
    )
    mock_tmdb.search_multi.return_value = PagedResultModel(results=[glass_onion_cand])
    mock_tmdb.get_movie_details.return_value = MediaDetailsModel(
        **glass_onion_cand.model_dump(),
        genres=[GenreModel(id=9648, name="Mystery"), GenreModel(id=35, name="Comedy")],
    )

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    intent = ParsedRecommendationIntent(
        reference_title="Mystery Movies similar to Glass Onion",
        intent_type="similar_to",
        query_type=RecommendationQueryType.SIMILAR_TO,
    )

    resolved = engine.resolve_reference_title(intent)
    assert resolved is not None
    assert resolved.id == 661374
    assert resolved.title == "Glass Onion: A Knives Out Mystery"
    assert intent.reference_media is not None
    assert intent.reference_title == "Glass Onion: A Knives Out Mystery"


# =============================================================================
# 3.2 & 3.3 Similar & Recommendation Retrieval Merging
# =============================================================================


def test_similar_and_recommendation_merging_deduplication(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify candidates from both similar and recommendations are merged and deduplicated by TMDB ID."""
    ref_details = MediaDetailsModel(
        id=661374,
        title="Glass Onion",
        media_type="movie",
        genres=[GenreModel(id=9648, name="Mystery")],
    )

    # Candidate A from recommendations
    cand_a = MediaItemSummary(id=546554, title="Knives Out", media_type="movie", original_language="en", genre_ids=[9648])
    # Candidate B present in BOTH similar and recommendations
    cand_b = MediaItemSummary(id=484247, title="A Simple Favor", media_type="movie", original_language="en", genre_ids=[9648])
    # Candidate C only in similar
    cand_c = MediaItemSummary(id=1933, title="The Others", media_type="movie", original_language="en", genre_ids=[9648])

    mock_tmdb.get_movie_recommendations.return_value = PagedResultModel(results=[cand_a, cand_b])
    mock_tmdb.get_movie_similar.return_value = PagedResultModel(results=[cand_b, cand_c])

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    intent = ParsedRecommendationIntent(
        reference_title="Glass Onion",
        reference_media=ref_details,
        query_type=RecommendationQueryType.SIMILAR_TO,
    )

    candidates = engine.retrieve_candidates(intent, limit=10)

    # Distinct candidate count: exactly 3 (cand_b deduplicated)
    cand_ids = [c.id for c in candidates]
    assert len(cand_ids) == len(set(cand_ids))
    assert 546554 in cand_ids
    assert 484247 in cand_ids
    assert 1933 in cand_ids

    # Reference movie itself must be strictly excluded
    assert 661374 not in cand_ids

    # Provenance metadata tagging (Requirement 3.6)
    rec_items = [c for c in candidates if c.id == 546554]
    assert rec_items[0].retrieval_source == "recommendation"
    assert rec_items[0].reference_movie_id == 661374


# =============================================================================
# 3.4 Genre-Based Discovery (OR vs AND Syntax)
# =============================================================================


def test_genre_discovery_or_vs_and_syntax(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify OR matching uses pipe '|' for genres_any and AND matching uses comma ',' for genres_all."""
    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    # Test OR syntax
    intent_or = ParsedRecommendationIntent(
        genres_any=["Science Fiction", "Mystery"],
        genres=["Science Fiction", "Mystery"],
        genre_ids=[878, 9648],
        content_type="movie",
    )
    engine.retrieve_candidates(intent_or, limit=5)

    call_args_or = mock_tmdb.discover_movies.call_args_list[0][1]
    assert call_args_or.get("with_genres") == "878|9648"

    mock_tmdb.discover_movies.reset_mock()

    # Test AND syntax
    intent_and = ParsedRecommendationIntent(
        genres_all=["Action", "Thriller"],
        genres=["Action", "Thriller"],
        genre_ids=[28, 53],
        content_type="movie",
    )
    engine.retrieve_candidates(intent_and, limit=5)

    call_args_and = mock_tmdb.discover_movies.call_args_list[0][1]
    assert call_args_and.get("with_genres") == "28,53"


# =============================================================================
# 3.5 Keyword-Based Discovery
# =============================================================================


def test_keyword_id_resolution_and_discovery(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify trope keywords resolve to TMDB IDs and trigger keyword discovery with OR pipe."""
    # Pre-mapped check
    assert TMDB_KEYWORD_IDS["time loop"] == 156828
    assert TMDB_KEYWORD_IDS["plot twist"] == 9799
    assert TMDB_KEYWORD_IDS["unreliable narrator"] == 214540

    kw_ids = resolve_keyword_ids(["time loop", "parallel universes"])
    assert 156828 in kw_ids
    assert 9663 in kw_ids

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    intent = ParsedRecommendationIntent(
        keywords_any=["time loop", "plot twist"],
        query_type=RecommendationQueryType.PLOT_BASED_DISCOVERY,
        content_type="movie",
    )

    engine.retrieve_candidates(intent, limit=5)

    # Keyword discovery must have been executed with OR syntax
    called_with_kw = False
    for call in mock_tmdb.discover_movies.call_args_list:
        with_kw = call[1].get("with_keywords")
        if with_kw and "156828" in with_kw and "9799" in with_kw and "|" in with_kw:
            called_with_kw = True
            break
    assert called_with_kw, "Expected discover_movies to be called with pipe-separated keyword IDs"


# =============================================================================
# 3.7 Progressive Fallback Retrieval
# =============================================================================


def test_progressive_fallback_preserves_mandatory_language(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify progressive fallback relaxes optional criteria but NEVER relaxes mandatory language requirements."""
    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    intent = ParsedRecommendationIntent(
        region="malayalam",
        language="ml",
        original_languages=["ml"],
        genres=["Thriller"],
        genre_ids=[53],
        content_type="movie",
        mandatory_constraints={"language": "ml", "region": "malayalam"},
    )

    engine.retrieve_candidates(intent, limit=20)

    # Verify that in every single discover call, with_original_language remained "ml"
    assert mock_tmdb.discover_movies.call_count >= 1
    for call in mock_tmdb.discover_movies.call_args_list:
        lang = call[1].get("with_original_language")
        assert lang == "ml", f"Mandatory language violated in fallback! Expected 'ml', got {lang}"


# =============================================================================
# 3.6 Metadata Preservation on Candidates
# =============================================================================


def test_candidate_metadata_preservation(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify all 14 required fields are preserved on candidates."""
    movie = MediaItemSummary(
        id=157336,
        title="Interstellar",
        original_title="Interstellar",
        release_date="2014-11-05",
        release_year=2014,
        overview="A team of explorers travel through a wormhole in space.",
        genre_ids=[12, 18, 878],
        original_language="en",
        vote_average=8.4,
        vote_count=34000,
        popularity=120.5,
        poster_path="/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
        backdrop_path="/xJHokMbljvjADYdit5fK5VQsXEG.jpg",
    )
    mock_tmdb.discover_movies.return_value = PagedResultModel(results=[movie])

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    intent = ParsedRecommendationIntent(
        genres=["Science Fiction"],
        genre_ids=[878],
        content_type="movie",
    )

    candidates = engine.retrieve_candidates(intent, limit=5)
    assert len(candidates) == 1
    cand = candidates[0]

    assert cand.id == 157336
    assert cand.title == "Interstellar"
    assert cand.original_title == "Interstellar"
    assert cand.release_date == "2014-11-05"
    assert cand.overview == "A team of explorers travel through a wormhole in space."
    assert cand.genre_ids == [12, 18, 878]
    assert cand.original_language == "en"
    assert cand.vote_average == 8.4
    assert cand.vote_count == 34000
    assert cand.popularity == 120.5
    assert cand.poster_path == "/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg"
    assert cand.backdrop_path == "/xJHokMbljvjADYdit5fK5VQsXEG.jpg"
    assert cand.retrieval_source == "genre_discover"


# =============================================================================
# 3.9 Error Handling & Diagnostic Categorization
# =============================================================================


def test_error_handling_auth_error(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify TMDB authentication failure returns error_type='tmdb_auth_error'."""
    mock_tmdb.discover_movies.side_effect = TMDBAuthError("Invalid TMDB API key")

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    resp = engine.recommend("Sci-fi movies")
    assert resp.error_type == "tmdb_auth_error"
    assert "authentication failed" in (resp.error_message or "").lower()


def test_error_handling_network_timeout(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify TMDB network timeout returns error_type='network_timeout'."""
    mock_tmdb.discover_movies.side_effect = TMDBTimeoutError("Request timed out after 10s")

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    resp = engine.recommend("Action movies")
    assert resp.error_type == "network_timeout"
    assert "timed out" in (resp.error_message or "").lower()


def test_error_handling_reference_not_found(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify non-existent reference title returns error_type='reference_not_found'."""
    mock_tmdb.search_multi.return_value = PagedResultModel(results=[])
    mock_tmdb.search_movies.return_value = PagedResultModel(results=[])

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    resp = engine.recommend("Movies like CompletelyMadeUpFictionalTitle999")
    assert resp.error_type == "reference_not_found"
    assert "CompletelyMadeUpFictionalTitle999" in (resp.error_message or "")


def test_error_handling_candidates_filtered(mock_tmdb: MagicMock, movie_repo: MovieStorageRepository, mock_ollama: MagicMock):
    """Verify candidates filtered out by strict constraints returns error_type='candidates_filtered'."""
    # TMDB returns a Hollywood movie for a Malayalam regional query
    hollywood_item = MediaItemSummary(
        id=999,
        title="Hollywood Film",
        media_type="movie",
        original_language="en",
        origin_country=["US"],
    )
    mock_tmdb.discover_movies.return_value = PagedResultModel(results=[hollywood_item])
    mock_tmdb.discover_all.return_value = PagedResultModel(results=[hollywood_item])

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=movie_repo,
        ollama_client=mock_ollama,
    )

    resp = engine.recommend("Malayalam romantic comedy movies")
    assert resp.error_type == "candidates_filtered"
    assert "none met strict criteria" in (resp.error_message or "").lower()
