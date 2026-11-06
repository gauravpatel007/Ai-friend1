"""Phase 1 Verification Tests: Structured Intent Extraction & Strict Eligibility Filtering.

Verifies:
- 1.1 Structured Query Understanding (South Indian, Malayalam, Telugu, Tamil, Kannada, Bollywood, Hollywood, Indian).
- 1.2 Separation of Mandatory Constraints from Optional Preferences & Conflict Handling.
- 1.3 Reference Title Resolution using Verified Catalog Metadata.
- 1.4 Centralized Regional Eligibility Rules (Distinguishing language, origin country, and industry).
- 1.5 Deterministic Candidate Eligibility Stage (Rejecting Hollywood & foreign titles on regional queries).
- 1.6 Diagnostic Logging & Metadata Availability.
- 1.7 Optional Preferences Never Overriding Mandatory Constraints.
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
)
from app.api.tmdb_client import TMDBClient
from app.ai.regional_classifier import (
    REGION_BOLLYWOOD,
    REGION_HOLLYWOOD,
    REGION_INDIAN,
    REGION_MALAYALAM,
    REGION_SOUTH_INDIAN,
    classify_regional_industries,
    filter_eligible_candidates,
    validate_candidate_eligibility,
)
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


@pytest.fixture
def temp_db_manager() -> DatabaseManager:
    """Provide an isolated, temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_rec_phase1.db"
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
    return TMDBClient(api_key="mock_tmdb_key_phase1")


@pytest.fixture
def mock_ollama_client() -> MagicMock:
    """Provide a mocked OllamaClient that simulates offline for deterministic unit tests."""
    client = MagicMock()
    client.is_server_reachable.return_value = False
    return client


# =============================================================================
# 1.1 & 1.2 Structured Query Understanding & Intent Extraction
# =============================================================================


def test_parse_intent_south_indian_movies_like_premalu(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 1.1: 'Suggest South Indian Movies like Premalu' extracts structured intent."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)
    intent = engine.parse_intent_deterministic("Suggest South Indian Movies like Premalu")

    assert intent.content_type == "movie"
    assert intent.region == REGION_SOUTH_INDIAN
    assert set(intent.languages) == {"ml", "te", "ta", "kn"}
    assert intent.reference_title == "Premalu"
    assert intent.similar_to_title == "Premalu"
    assert intent.similarity_mode == "reference_title"
    assert intent.has_conflict is False


def test_parse_intent_individual_south_indian_languages(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 1.1: Specific South Indian language cinema requests."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    # Malayalam
    intent_ml = engine.parse_intent_deterministic("Malayalam movies similar to Premalu")
    assert intent_ml.region == "malayalam"
    assert intent_ml.language == "ml"
    assert intent_ml.languages == ["ml"]
    assert intent_ml.reference_title == "Premalu"

    # Telugu
    intent_te = engine.parse_intent_deterministic("Telugu action movies")
    assert intent_te.region == "telugu"
    assert intent_te.language == "te"
    assert intent_te.languages == ["te"]
    assert "Action" in intent_te.genres

    # Tamil
    intent_ta = engine.parse_intent_deterministic("Tamil romantic comedies")
    assert intent_ta.region == "tamil"
    assert intent_ta.language == "ta"
    assert intent_ta.languages == ["ta"]
    assert "Romance" in intent_ta.genres
    assert "Comedy" in intent_ta.genres

    # Kannada
    intent_kn = engine.parse_intent_deterministic("Kannada thriller movies")
    assert intent_kn.region == "kannada"
    assert intent_kn.language == "kn"
    assert intent_kn.languages == ["kn"]
    assert "Thriller" in intent_kn.genres


def test_parse_intent_desire_phrasing_does_not_overmatch_like(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Bug #6: Verify desire phrases ('would like', 'i'd like', 'i like') do not extract false reference titles."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    # 1. "I would like a good thriller" -> desire verb, not a comparison
    intent1 = engine.parse_intent_deterministic("I would like a good thriller")
    assert intent1.similar_to_title is None
    assert intent1.reference_title is None
    assert "Thriller" in intent1.genres

    # 2. "I'd like an action movie from 2020"
    intent2 = engine.parse_intent_deterministic("I'd like an action movie from 2020")
    assert intent2.similar_to_title is None
    assert intent2.reference_title is None
    assert "Action" in intent2.genres
    assert intent2.release_year == 2020

    # 3. "I like horror films"
    intent3 = engine.parse_intent_deterministic("I like horror films")
    assert intent3.similar_to_title is None
    assert intent3.reference_title is None
    assert "Horror" in intent3.genres

    # 4. "Can you give me something like exciting"
    intent4 = engine.parse_intent_deterministic("Can you give me something like exciting")
    assert intent4.similar_to_title is None
    assert intent4.reference_title is None

    # 5. Legitimate comparison within a desire statement: "I would like movies like Inception"
    intent5 = engine.parse_intent_deterministic("I would like movies like Inception")
    assert intent5.similar_to_title == "Inception"
    assert intent5.reference_title == "Inception"


def test_parse_intent_bollywood_hollywood_and_indian(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 1.1: Bollywood, Hollywood, and Indian cinema extraction."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    # Bollywood
    intent_bolly = engine.parse_intent_deterministic("Bollywood movies like 3 Idiots")
    assert intent_bolly.region == "bollywood"
    assert intent_bolly.language == "hi"
    assert intent_bolly.reference_title == "3 Idiots"

    # Hollywood
    intent_holly = engine.parse_intent_deterministic("Hollywood science-fiction movies")
    assert intent_holly.region == "hollywood"
    assert intent_holly.language == "en"
    assert "Science Fiction" in intent_holly.genres

    # Indian series
    intent_ind = engine.parse_intent_deterministic("Indian thriller series")
    assert intent_ind.content_type == "tv"
    assert intent_ind.region == "indian"
    assert "Thriller" in intent_ind.genres


def test_parse_intent_year_and_era_boundaries(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 1.1: Release period extraction (after YYYY, between YYYY and YYYY)."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    # After 2010
    intent_after = engine.parse_intent_deterministic("Movies like Interstellar released after 2010")
    assert intent_after.reference_title == "Interstellar"
    assert intent_after.release_year_min == 2011

    # Between 2020 and 2025
    intent_range = engine.parse_intent_deterministic("South Indian movies released between 2020 and 2025")
    assert intent_range.region == "south_indian"
    assert intent_range.release_year_min == 2020
    assert intent_range.release_year_max == 2025


def test_parse_intent_conflicting_constraints(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 1.2: Conflicting constraints are flagged."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)

    intent_conflict = engine.parse_intent_deterministic("Hollywood Malayalam movie")
    assert intent_conflict.has_conflict is True
    assert intent_conflict.conflict_message is not None


def test_mandatory_constraints_vs_optional_preferences_separation(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 1.2: Strict separation of mandatory constraints and optional preferences."""
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)
    intent = engine.parse_intent_deterministic("Suggest South Indian Movies like Premalu")

    # Mandatory constraints should include content_type, region, languages
    assert "content_type" in intent.mandatory_constraints
    assert "region" in intent.mandatory_constraints
    assert "languages" in intent.mandatory_constraints
    assert intent.mandatory_constraints["region"] == "south_indian"

    # Optional preferences should include reference_title, sort_by
    assert "reference_title" in intent.optional_preferences
    assert intent.optional_preferences["reference_title"] == "Premalu"


# =============================================================================
# 1.3 Reference Title Resolution with Verified Metadata
# =============================================================================


def test_resolve_reference_title_verified_metadata(movie_repo: MovieStorageRepository, mock_tmdb_client: TMDBClient):
    """Test 1.3: Reference title is resolved against TMDB and inherits verified metadata."""
    premalu_summary = MediaItemSummary(
        id=1149791,
        title="Premalu",
        original_title="പ്രേമലു",
        media_type="movie",
        original_language="ml",
        origin_country=["IN"],
        release_date="2024-02-09",
        release_year=2024,
        genre_ids=[10749, 35],
    )
    premalu_details = MediaDetailsModel(
        **premalu_summary.model_dump(),
        genres=[GenreModel(id=10749, name="Romance"), GenreModel(id=35, name="Comedy")],
    )

    mock_tmdb_client.search_multi = MagicMock(return_value=PagedResultModel(results=[premalu_summary]))
    mock_tmdb_client.get_movie_details = MagicMock(return_value=premalu_details)

    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb_client, storage_repo=movie_repo)
    intent = engine.parse_intent_deterministic("Suggest South Indian Movies like Premalu")

    resolved = engine.resolve_reference_title(intent)
    assert resolved is not None
    assert resolved.title == "Premalu"
    assert resolved.original_language == "ml"
    assert resolved.origin_country == ["IN"]
    assert intent.reference_genres == [10749, 35]
    assert intent.reference_media is not None


# =============================================================================
# 1.4 Centralized Regional Eligibility Rules
# =============================================================================


def test_regional_classification_distinguishes_country_and_language():
    """Test 1.4: Production country, language, and industry are not interchangeable."""
    # 1. US English -> Hollywood
    us_movie = MediaItemSummary(id=1, title="Inception", original_language="en", origin_country=["US"])
    classes_us = classify_regional_industries(us_movie)
    assert REGION_HOLLYWOOD in classes_us

    # 2. British English -> International, NOT Hollywood
    uk_movie = MediaItemSummary(id=2, title="The King's Speech", original_language="en", origin_country=["GB"])
    classes_uk = classify_regional_industries(uk_movie)
    assert REGION_HOLLYWOOD not in classes_uk

    # 3. Indian Hindi -> Bollywood & Indian, NOT South Indian
    hi_movie = MediaItemSummary(id=3, title="3 Idiots", original_language="hi", origin_country=["IN"])
    classes_hi = classify_regional_industries(hi_movie)
    assert REGION_BOLLYWOOD in classes_hi
    assert REGION_INDIAN in classes_hi
    assert REGION_SOUTH_INDIAN not in classes_hi

    # 4. Indian Malayalam -> South Indian & Indian & Malayalam
    ml_movie = MediaItemSummary(id=4, title="Premalu", original_language="ml", origin_country=["IN"])
    classes_ml = classify_regional_industries(ml_movie)
    assert REGION_SOUTH_INDIAN in classes_ml
    assert REGION_MALAYALAM in classes_ml
    assert REGION_INDIAN in classes_ml


# =============================================================================
# 1.5 Strict Candidate Eligibility Stage & Hard Rejections
# =============================================================================


def test_hard_filter_rejects_hollywood_for_south_indian_query():
    """Test 1.5: Rejection of Hollywood titles when South Indian cinema requested."""
    intent = ParsedRecommendationIntent(
        content_type="movie",
        region=REGION_SOUTH_INDIAN,
        languages=["ml", "te", "ta", "kn"],
        reference_title="Premalu",
    )

    hollywood_item = MediaItemSummary(
        id=8976,
        title="A Lot Like Love",
        media_type="movie",
        original_language="en",
        origin_country=["US"],
        genre_ids=[35, 18, 10749],
    )

    south_indian_item = MediaItemSummary(
        id=1149791,
        title="Premalu",
        media_type="movie",
        original_language="ml",
        origin_country=["IN"],
        genre_ids=[10749, 35],
    )

    foreign_item = MediaItemSummary(
        id=60242,
        title="Dream.net",
        media_type="movie",
        original_language="hu",
        origin_country=["HU"],
        genre_ids=[35],
    )

    candidates = [hollywood_item, south_indian_item, foreign_item]
    eligible, rejected = filter_eligible_candidates(candidates, intent)

    assert len(eligible) == 1
    assert eligible[0].title == "Premalu"

    rejected_titles = [item.title for item, _ in rejected]
    assert "A Lot Like Love" in rejected_titles
    assert "Dream.net" in rejected_titles


def test_hard_filter_content_type_enforcement():
    """Test 1.5: Strict media type hard filter (movies only vs tv series only)."""
    intent_movies_only = ParsedRecommendationIntent(content_type="movie")

    movie_item = MediaItemSummary(id=1, title="Interstellar", media_type="movie")
    series_item = MediaItemSummary(id=2, title="Dark", media_type="tv")

    is_ok_m, _ = validate_candidate_eligibility(movie_item, intent_movies_only)
    is_ok_s, _ = validate_candidate_eligibility(series_item, intent_movies_only)

    assert is_ok_m is True
    assert is_ok_s is False


def test_hard_filter_missing_metadata_uncertainty():
    """Test 1.5: Incomplete metadata does not silently pass strict regional filter."""
    intent = ParsedRecommendationIntent(
        region=REGION_SOUTH_INDIAN,
        languages=["ml", "te", "ta", "kn"],
    )

    # Missing original language
    item_no_lang = MediaItemSummary(id=99, title="Mystery Film", original_language=None)
    is_ok, reason = validate_candidate_eligibility(item_no_lang, intent)

    assert is_ok is False
    assert "Missing original_language" in str(reason)


def test_optional_preference_cannot_override_mandatory_rejection(
    movie_repo: MovieStorageRepository,
    mock_tmdb_client: TMDBClient,
    mock_ollama_client: MagicMock,
):
    """Test 1.7: Optional high rating/genre score cannot bypass regional eligibility."""
    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb_client,
        storage_repo=movie_repo,
        ollama_client=mock_ollama_client,
    )

    # Hollywood rom-com with 10.0 rating and exact genres
    hollywood_perfect_score = MediaItemSummary(
        id=999,
        title="Hollywood RomCom Star",
        media_type="movie",
        original_language="en",
        origin_country=["US"],
        vote_average=10.0,
        genre_ids=[10749, 35],
    )

    # South Indian movie with lower rating
    south_indian_movie = MediaItemSummary(
        id=888,
        title="Real Malayalam RomCom",
        media_type="movie",
        original_language="ml",
        origin_country=["IN"],
        vote_average=7.0,
        genre_ids=[10749, 35],
    )

    mock_tmdb_client.search_multi = MagicMock(return_value=PagedResultModel(results=[south_indian_movie]))
    mock_tmdb_client.get_movie_details = MagicMock(return_value=MediaDetailsModel(**south_indian_movie.model_dump()))

    # Engine retrieve_candidates returns both
    engine.retrieve_candidates = MagicMock(return_value=[hollywood_perfect_score, south_indian_movie])

    # Run recommend
    response = engine.recommend("Suggest South Indian Movies like Premalu")

    # Hollywood movie MUST NOT be present in final recommendations despite 10.0 score
    recommended_titles = [r.media.title for r in response.recommendations]
    assert "Real Malayalam RomCom" in recommended_titles
    assert "Hollywood RomCom Star" not in recommended_titles
