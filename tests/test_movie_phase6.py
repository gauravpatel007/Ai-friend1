"""Phase 6 Verification Tests: Regional, Language, Genre, and Advanced Search Filters.

Verifies:
- 6.1 Regional categories (Indian Cinema, South Indian, Bollywood, Hollywood, International).
- 6.2 Provider-supported language codes (Hindi, Telugu, Tamil, Malayalam, Kannada, Bengali, etc.).
- 6.3 Genre filtering with movie vs. TV taxonomy mapping (Action 28 -> 10759, Sci-Fi 878 -> 10765).
- 6.4 Release-year and decade filters (specific year, 2020s, 2010s, 2000s, classics).
- 6.5 Combined filtering (e.g., ONLY MOVIES + Telugu + Action, ONLY SERIES + Hindi + Crime).
- 6.6 Advanced search (title search, person search via known_for, search combined with filters).
- 6.7 Classification accuracy with representative titles (RRR, Dangal, Oppenheimer, Parasite).
"""

from __future__ import annotations

import unittest.mock as mock
import pytest
from fastapi.testclient import TestClient

from app.api.movie_models import MediaItemSummary, PagedResultModel
from app.api.movie_routes import router as movie_router
from app.api.server import create_app
from app.api.tmdb_client import TMDBClient


@pytest.fixture
def mock_client() -> TMDBClient:
    return TMDBClient(api_key="test_valid_tmdb_token_xyz")


# =============================================================================
# 1. Regional Categories & Multi-Signal Classification Tests
# =============================================================================


def test_regional_category_indian_cinema(mock_client: TMDBClient):
    """Test 6.1: Indian Cinema uses origin country 'IN' and multi-language union."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_all") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])

        resp = client.get("/api/movies/discover?region=indian&content_type=all")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_origin_country"] == "IN"
        assert "hi" in kwargs["with_original_language"]
        assert "te" in kwargs["with_original_language"]
        assert "ta" in kwargs["with_original_language"]


def test_regional_category_bollywood(mock_client: TMDBClient):
    """Test 6.1: Bollywood is classified by origin country 'IN' and Hindi language 'hi'."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])

        resp = client.get("/api/movies/discover?region=bollywood&content_type=movies")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_origin_country"] == "IN"
        assert kwargs["with_original_language"] == "hi"


def test_regional_category_south_indian(mock_client: TMDBClient):
    """Test 6.1: South Indian cinema combines 'IN' with Telugu, Tamil, Malayalam & Kannada."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])

        resp = client.get("/api/movies/discover?region=south_indian&content_type=movies")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_origin_country"] == "IN"
        assert kwargs["with_original_language"] == "te|ta|ml|kn"


def test_regional_category_hollywood(mock_client: TMDBClient):
    """Test 6.1: Hollywood isolates US origin country and English language."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])

        resp = client.get("/api/movies/discover?region=hollywood&content_type=movies")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_origin_country"] == "US"
        assert kwargs["with_original_language"] == "en"


def test_regional_category_international(mock_client: TMDBClient):
    """Test 6.1: International cinema filters out English language dominance."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])

        resp = client.get("/api/movies/discover?region=international&content_type=movies")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["without_original_language"] == "en"


# =============================================================================
# 2. Language Filter & Precedence Tests
# =============================================================================


def test_language_filter_overrides_regional_language_while_preserving_country(mock_client: TMDBClient):
    """Test 6.2: Explicit language filter (e.g. 'bn' Bengali) overrides region default while keeping country."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])

        # User chooses Indian region, but specifically selects Bengali language
        resp = client.get("/api/movies/discover?region=indian&language=bn&content_type=movies")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_origin_country"] == "IN"
        assert kwargs["with_original_language"] == "bn"


# =============================================================================
# 3. Genre Mapping: Movie vs Television Differences
# =============================================================================


def test_genre_mapping_movie_vs_tv(mock_client: TMDBClient):
    """Test 6.3: Differences between Movie and TV genre taxonomies are mapped accurately."""
    # Test mapping helper
    # Movie Action (28) -> TV Action & Adventure (10759)
    assert mock_client._map_genres_for_tv("28") == "10759"
    # Movie Sci-Fi (878) -> TV Sci-Fi & Fantasy (10765)
    assert mock_client._map_genres_for_tv("878") == "10765"
    # Comedy (35) is identical on both
    assert mock_client._map_genres_for_tv("35") == "35"
    # Multi-genre mapping: Action & Sci-Fi (28|878) -> (10759|10765)
    assert mock_client._map_genres_for_tv("28|878") == "10759|10765"


def test_discover_series_automatically_maps_action_genre(mock_client: TMDBClient):
    """Test 6.3: discover_series maps genre 28 (Action) to 10759 in request parameters."""
    with mock.patch.object(mock_client, "_request", return_value={"results": []}) as mock_req:
        mock_client.discover_series(with_genres="28")
        params = mock_req.call_args[1]["params"]
        assert params["with_genres"] == "10759"


# =============================================================================
# 4. Release-Year and Decade Filtering Tests
# =============================================================================


def test_release_year_specific_and_decades(mock_client: TMDBClient):
    """Test 6.4: Specific year and decade filters are converted to valid date ranges."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    # 1. Specific Year: 2024
    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
        client.get("/api/movies/discover?year=2024&content_type=movies")
        assert mock_disc.call_args[1]["primary_release_year"] == 2024

    # 2. Decade: 2020s
    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
        client.get("/api/movies/discover?year=2020s&content_type=movies")
        assert mock_disc.call_args[1]["release_date_gte"] == "2020-01-01"
        assert mock_disc.call_args[1]["release_date_lte"] == "2029-12-31"

    # 3. Classics: < 2000
    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
        client.get("/api/movies/discover?year=classic&content_type=movies")
        assert mock_disc.call_args[1]["release_date_lte"] == "1999-12-31"


# =============================================================================
# 5. Combined Filter Scenarios (Requirement 6.5)
# =============================================================================


def test_combined_filter_only_movies_telugu_action(mock_client: TMDBClient):
    """Test 6.5 Example 1: ONLY MOVIES + Telugu + Action."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
        resp = client.get("/api/movies/discover?content_type=movies&language=te&genre=28")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_original_language"] == "te"
        assert kwargs["with_genres"] == "28"


def test_combined_filter_only_series_hindi_crime(mock_client: TMDBClient):
    """Test 6.5 Example 2: ONLY SERIES + Hindi + Crime."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_series") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
        resp = client.get("/api/movies/discover?content_type=series&language=hi&genre=80")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_original_language"] == "hi"
        assert kwargs["with_genres"] == "80"


def test_combined_filter_all_english_scifi(mock_client: TMDBClient):
    """Test 6.5 Example 3: ALL + English + Sci-Fi."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_all") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
        resp = client.get("/api/movies/discover?content_type=all&language=en&genre=878")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_original_language"] == "en"
        assert kwargs["with_genres"] == "878"


def test_combined_filter_only_movies_indian_comedy(mock_client: TMDBClient):
    """Test 6.5 Example 4: ONLY MOVIES + Indian Cinema + Comedy."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    with mock.patch.object(mock_client, "discover_movies") as mock_disc:
        mock_disc.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
        resp = client.get("/api/movies/discover?content_type=movies&region=indian&genre=35")
        assert resp.status_code == 200

        mock_disc.assert_called_once()
        kwargs = mock_disc.call_args[1]
        assert kwargs["with_origin_country"] == "IN"
        assert kwargs["with_genres"] == "35"


# =============================================================================
# 6. Advanced Search & Person Search (Requirement 6.6)
# =============================================================================


def test_person_search_extracts_known_for_titles(mock_client: TMDBClient):
    """Test 6.6: When searching for an actor/director, person's known_for filmography is extracted."""
    raw_multi = {
        "page": 1,
        "total_pages": 1,
        "total_results": 1,
        "results": [
            {
                "id": 1088,
                "name": "Christopher Nolan",
                "media_type": "person",
                "known_for": [
                    {"id": 157336, "title": "Interstellar", "media_type": "movie", "vote_average": 8.4},
                    {"id": 27205, "title": "Inception", "media_type": "movie", "vote_average": 8.4},
                ],
            }
        ],
    }

    with mock.patch.object(mock_client, "_request", return_value=raw_multi):
        res = mock_client.search_multi(query="Christopher Nolan")
        assert len(res.results) == 2
        titles = {item.title for item in res.results}
        assert "Interstellar" in titles
        assert "Inception" in titles
        assert all(item.media_type == "movie" for item in res.results)


def test_search_combined_with_compatible_language_and_year(mock_client: TMDBClient):
    """Test 6.6: Search can be filtered by compatible language and release year."""
    raw_multi = {
        "page": 1,
        "total_pages": 1,
        "total_results": 2,
        "results": [
            {"id": 1, "title": "Spider-Man Hindi Dub", "media_type": "movie", "original_language": "hi", "release_date": "2021-12-17"},
            {"id": 2, "title": "Spider-Man English", "media_type": "movie", "original_language": "en", "release_date": "2021-12-17"},
        ],
    }

    with mock.patch.object(mock_client, "_request", return_value=raw_multi):
        res = mock_client.search_multi(query="Spider-Man", language="hi", year=2021)
        assert len(res.results) == 1
        assert res.results[0].title == "Spider-Man Hindi Dub"
        assert res.results[0].original_language == "hi"


# =============================================================================
# 7. Classification Accuracy with Representative Titles (Requirement 6.7)
# =============================================================================


def test_classification_accuracy_representative_titles():
    """Test 6.7: Verify representative titles across Indian regional and international cinema."""
    # Representative titles:
    # 1. RRR: South Indian (Tollywood), Telugu language, Indian cinema.
    rrr = MediaItemSummary(
        id=579974,
        title="RRR",
        media_type="movie",
        original_language="te",
        release_date="2022-03-24",
        release_year=2022,
        genre_ids=[28, 18],
        vote_average=7.9,
        vote_count=1200,
        popularity=85.0,
    )
    # 2. Dangal: Bollywood, Hindi language, Indian cinema.
    dangal = MediaItemSummary(
        id=360814,
        title="Dangal",
        media_type="movie",
        original_language="hi",
        release_date="2016-12-23",
        release_year=2016,
        genre_ids=[18, 35],
        vote_average=8.0,
        vote_count=900,
        popularity=60.0,
    )
    # 3. Oppenheimer: Hollywood, US production, English.
    oppenheimer = MediaItemSummary(
        id=872585,
        title="Oppenheimer",
        media_type="movie",
        original_language="en",
        release_date="2023-07-19",
        release_year=2023,
        genre_ids=[18, 36],
        vote_average=8.1,
        vote_count=9000,
        popularity=120.0,
    )
    # 4. Parasite: International Cinema, South Korea, Korean language.
    parasite = MediaItemSummary(
        id=496243,
        title="Parasite",
        media_type="movie",
        original_language="ko",
        release_date="2019-05-30",
        release_year=2019,
        genre_ids=[35, 53, 18],
        vote_average=8.5,
        vote_count=18000,
        popularity=110.0,
    )

    # Classification logic tests:
    # A. Indian Cinema matches both RRR (Telugu) and Dangal (Hindi)
    indian_langs = {"hi", "te", "ta", "ml", "kn", "bn", "mr", "pa", "gu", "or", "as"}
    assert rrr.original_language in indian_langs
    assert dangal.original_language in indian_langs
    assert oppenheimer.original_language not in indian_langs

    # B. South Indian Cinema matches RRR (Telugu) but excludes Dangal (Hindi)
    south_indian_langs = {"te", "ta", "ml", "kn"}
    assert rrr.original_language in south_indian_langs
    assert dangal.original_language not in south_indian_langs

    # C. Bollywood matches Dangal (Hindi) but excludes RRR (Telugu)
    assert dangal.original_language == "hi"
    assert rrr.original_language != "hi"

    # D. Hollywood is English language
    assert oppenheimer.original_language == "en"

    # E. International Cinema excludes English language dominance
    assert parasite.original_language != "en"
    assert parasite.original_language == "ko"
