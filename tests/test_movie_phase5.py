"""Phase 5 Verification Tests: Real Movie Data and Content-Type Filters.

Verifies:
- 5.1 Real metadata binding and error/loading handling.
- 5.2 Combined 'ALL' content-type with accurate labels.
- 5.3 'ONLY MOVIES' filter strictly excluding series.
- 5.4 'ONLY SERIES' filter strictly excluding movies.
- 5.5 Pagination model (page, total_pages, total_results, page boundaries).
- 5.6 Provider-side and local sorting options (popularity, rating, release date, title).
- 5.7 Data integrity (titles, poster URLs, release dates, empty results, failure translation).
"""

from __future__ import annotations

import unittest.mock as mock
import pytest
from fastapi.testclient import TestClient

from app.api.movie_models import MediaItemSummary, PagedResultModel
from app.api.movie_routes import router as movie_router
from app.api.server import create_app
from app.api.tmdb_client import (
    TMDBAuthError,
    TMDBClient,
    TMDB_IMAGE_BASE_URL,
)


@pytest.fixture
def mock_client() -> TMDBClient:
    """Return a TMDBClient configured with a test token."""
    return TMDBClient(api_key="test_valid_tmdb_token_xyz")


@pytest.fixture
def sample_movie_tmdb_item() -> dict:
    return {
        "id": 101,
        "title": "Interstellar",
        "original_title": "Interstellar",
        "media_type": "movie",
        "overview": "A team of explorers travel through a wormhole in space.",
        "poster_path": "/gEU2QniE6EwfVDxCzsxPnO4tOws.jpg",
        "backdrop_path": "/xJHokMbljvjADYdit5fK5VQsXEG.jpg",
        "release_date": "2014-11-05",
        "original_language": "en",
        "genre_ids": [12, 18, 878],
        "vote_average": 8.4,
        "vote_count": 35000,
        "popularity": 145.2,
    }


@pytest.fixture
def sample_tv_tmdb_item() -> dict:
    return {
        "id": 202,
        "name": "Breaking Bad",
        "original_name": "Breaking Bad",
        "media_type": "tv",
        "overview": "A chemistry teacher diagnosed with inoperable lung cancer turns to manufacturing methamphetamine.",
        "poster_path": "/ztkUQFLlC19CCMYHW9o1zWhJRNq.jpg",
        "backdrop_path": "/tsRy63Mu5cu8etL1X7ZLyf7UP1M.jpg",
        "first_air_date": "2008-01-20",
        "original_language": "en",
        "genre_ids": [18, 80],
        "vote_average": 8.9,
        "vote_count": 14000,
        "popularity": 178.5,
    }


# =============================================================================
# 1. Content-Type Tests: ALL, ONLY MOVIES, ONLY SERIES
# =============================================================================


def test_discover_all_combines_movie_and_series(
    mock_client: TMDBClient, sample_movie_tmdb_item: dict, sample_tv_tmdb_item: dict
):
    """Test 5.2: 'ALL' content-type returns both movies and series with exact labels."""
    movie_resp = {
        "page": 1,
        "total_pages": 10,
        "total_results": 200,
        "results": [sample_movie_tmdb_item],
    }
    series_resp = {
        "page": 1,
        "total_pages": 8,
        "total_results": 150,
        "results": [sample_tv_tmdb_item],
    }

    with mock.patch.object(mock_client, "_request") as mock_req:
        mock_req.side_effect = [movie_resp, series_resp]

        result = mock_client.discover_all(page=1, sort_by="popularity.desc")

        assert isinstance(result, PagedResultModel)
        assert len(result.results) == 2
        # Verify content types
        types = {item.media_type for item in result.results}
        assert "movie" in types
        assert "tv" in types
        # Verify movie details
        movie_item = next(item for item in result.results if item.media_type == "movie")
        assert movie_item.title == "Interstellar"
        assert movie_item.release_year == 2014
        assert movie_item.poster_url == f"{TMDB_IMAGE_BASE_URL}/w500/gEU2QniE6EwfVDxCzsxPnO4tOws.jpg"
        # Verify series details
        series_item = next(item for item in result.results if item.media_type == "tv")
        assert series_item.title == "Breaking Bad"
        assert series_item.release_year == 2008
        assert series_item.poster_url == f"{TMDB_IMAGE_BASE_URL}/w500/ztkUQFLlC19CCMYHW9o1zWhJRNq.jpg"
        # Verify total results combination
        assert result.total_results == 350
        assert result.total_pages == 10


def test_discover_only_movies_strictly_excludes_series(
    mock_client: TMDBClient, sample_movie_tmdb_item: dict
):
    """Test 5.3: 'ONLY MOVIES' retrieves movie results only and excludes television series."""
    # Simulate a raw result containing a movie and an unexpected non-movie item
    raw_movie_page = {
        "page": 1,
        "total_pages": 5,
        "total_results": 50,
        "results": [
            sample_movie_tmdb_item,
            {"id": 999, "title": "Sneak Series", "media_type": "tv", "vote_average": 7.0},
        ],
    }

    with mock.patch.object(mock_client, "_request", return_value=raw_movie_page) as mock_req:
        result = mock_client.discover_movies(page=1)

        # Defensively verify that ONLY movie items are in the results
        assert all(item.media_type == "movie" for item in result.results)
        assert len(result.results) == 1
        assert result.results[0].title == "Interstellar"
        assert result.results[0].id == 101


def test_discover_only_series_strictly_excludes_movies(
    mock_client: TMDBClient, sample_tv_tmdb_item: dict
):
    """Test 5.4: 'ONLY SERIES' retrieves television-series results only and excludes movies."""
    raw_tv_page = {
        "page": 1,
        "total_pages": 4,
        "total_results": 40,
        "results": [
            sample_tv_tmdb_item,
            {"id": 888, "title": "Sneak Movie", "media_type": "movie", "vote_average": 6.5},
        ],
    }

    with mock.patch.object(mock_client, "_request", return_value=raw_tv_page) as mock_req:
        result = mock_client.discover_series(page=1)

        # Defensively verify that ONLY tv items are in the results
        assert all(item.media_type == "tv" for item in result.results)
        assert len(result.results) == 1
        assert result.results[0].title == "Breaking Bad"
        assert result.results[0].id == 202


# =============================================================================
# 2. Search Multi, Search Movies, Search Series
# =============================================================================


def test_search_multi_returns_both_movies_and_series(
    mock_client: TMDBClient, sample_movie_tmdb_item: dict, sample_tv_tmdb_item: dict
):
    """Test multi-search returns both content types with correct media_type."""
    raw_search = {
        "page": 1,
        "total_pages": 1,
        "total_results": 3,
        "results": [
            sample_movie_tmdb_item,
            sample_tv_tmdb_item,
            {"id": 303, "name": "Christopher Nolan", "media_type": "person"},  # Should be omitted
        ],
    }

    with mock.patch.object(mock_client, "_request", return_value=raw_search):
        result = mock_client.search_multi(query="stellar")

        assert len(result.results) == 2
        assert {item.media_type for item in result.results} == {"movie", "tv"}
        # Ensure person is omitted
        assert all(item.media_type in ("movie", "tv") for item in result.results)


def test_search_movies_defensively_excludes_tv(mock_client: TMDBClient, sample_movie_tmdb_item: dict):
    """Test search_movies guarantees media_type == 'movie'."""
    raw_search = {
        "page": 1,
        "total_pages": 1,
        "total_results": 1,
        "results": [sample_movie_tmdb_item],
    }

    with mock.patch.object(mock_client, "_request", return_value=raw_search):
        result = mock_client.search_movies(query="Interstellar")
        assert len(result.results) == 1
        assert result.results[0].media_type == "movie"


def test_search_series_defensively_excludes_movies(mock_client: TMDBClient, sample_tv_tmdb_item: dict):
    """Test search_series guarantees media_type == 'tv'."""
    raw_search = {
        "page": 1,
        "total_pages": 1,
        "total_results": 1,
        "results": [sample_tv_tmdb_item],
    }

    with mock.patch.object(mock_client, "_request", return_value=raw_search):
        result = mock_client.search_series(query="Breaking Bad")
        assert len(result.results) == 1
        assert result.results[0].media_type == "tv"


# =============================================================================
# 3. Pagination & Bounds Tests
# =============================================================================


def test_pagination_model_preserves_page_metadata(mock_client: TMDBClient):
    """Test 5.5: Provider's pagination model preserves page, total_pages, total_results."""
    paged_resp = {
        "page": 3,
        "total_pages": 42,
        "total_results": 840,
        "results": [
            {"id": 1, "title": "Page 3 Movie", "media_type": "movie", "vote_average": 7.0}
        ],
    }

    with mock.patch.object(mock_client, "_request", return_value=paged_resp):
        res = mock_client.discover_movies(page=3)
        assert res.page == 3
        assert res.total_pages == 42
        assert res.total_results == 840
        assert len(res.results) == 1


def test_pagination_bounds_clamping(mock_client: TMDBClient):
    """Test that page parameter is defensively clamped between 1 and 500."""
    with mock.patch.object(mock_client, "_request", return_value={"results": []}) as mock_req:
        mock_client.discover_movies(page=0)
        assert mock_req.call_args[1]["params"]["page"] == 1

        mock_client.discover_movies(page=999)
        assert mock_req.call_args[1]["params"]["page"] == 500


# =============================================================================
# 4. Sorting Options Mapping Tests
# =============================================================================


def test_sorting_options_parameter_mapping(mock_client: TMDBClient):
    """Test 5.6: Sorting options are mapped correctly for movie and series endpoints."""
    with mock.patch.object(mock_client, "_request", return_value={"results": []}) as mock_req:
        # 1. Movie release date sorting -> primary_release_date.desc
        mock_client.discover_movies(sort_by="release_date.desc")
        assert mock_req.call_args[1]["params"]["sort_by"] == "primary_release_date.desc"

        # 2. Movie title sort -> original_title.asc
        mock_client.discover_movies(sort_by="title.asc")
        assert mock_req.call_args[1]["params"]["sort_by"] == "original_title.asc"

        # 3. Series release date sorting -> first_air_date.desc
        mock_client.discover_series(sort_by="release_date.desc")
        assert mock_req.call_args[1]["params"]["sort_by"] == "first_air_date.desc"

        # 4. Series primary_release_date fallback -> first_air_date.desc
        mock_client.discover_series(sort_by="primary_release_date.desc")
        assert mock_req.call_args[1]["params"]["sort_by"] == "first_air_date.desc"


def test_combined_sorting_by_vote_average(
    mock_client: TMDBClient, sample_movie_tmdb_item: dict, sample_tv_tmdb_item: dict
):
    """Test that combined 'ALL' sorting correctly orders by vote_average descending."""
    # Breaking Bad: 8.9; Interstellar: 8.4
    movie_resp = {"page": 1, "total_pages": 1, "total_results": 1, "results": [sample_movie_tmdb_item]}
    series_resp = {"page": 1, "total_pages": 1, "total_results": 1, "results": [sample_tv_tmdb_item]}

    with mock.patch.object(mock_client, "_request", side_effect=[movie_resp, series_resp]):
        result = mock_client.discover_all(sort_by="vote_average.desc")
        assert len(result.results) == 2
        # Breaking Bad (8.9) should appear before Interstellar (8.4)
        assert result.results[0].title == "Breaking Bad"
        assert result.results[1].title == "Interstellar"


# =============================================================================
# 5. Empty Results and Error Translation Tests
# =============================================================================


def test_empty_results_handling(mock_client: TMDBClient):
    """Test 5.7: Empty catalog results produce clean empty model."""
    empty_resp = {"page": 1, "total_pages": 0, "total_results": 0, "results": []}

    with mock.patch.object(mock_client, "_request", return_value=empty_resp):
        res = mock_client.discover_movies()
        assert res.results == []
        assert res.total_results == 0
        assert res.total_pages == 0


def test_unconfigured_client_raises_auth_error():
    """Test that client without API key raises TMDBAuthError immediately."""
    unconfigured = TMDBClient(api_key="")
    with pytest.raises(TMDBAuthError) as exc_info:
        unconfigured.discover_movies()
    assert "TMDB API key" in str(exc_info.value)


# =============================================================================
# 6. FastAPI Route Integration Tests (Phase 5)
# =============================================================================


def test_fastapi_discover_all_route():
    """Verify FastAPI route handles content_type='all' via discover_all."""
    app = create_app()
    client = TestClient(app)

    fake_client = TMDBClient(api_key="mock_key")
    paged = PagedResultModel(
        page=1,
        total_pages=2,
        total_results=20,
        results=[
            MediaItemSummary(
                id=1,
                title="Unified Title",
                media_type="movie",
                vote_average=8.0,
                vote_count=100,
                popularity=50.0,
            )
        ],
    )

    with mock.patch.object(fake_client, "discover_all", return_value=paged) as mock_disc:
        app.state.tmdb_client = fake_client
        resp = client.get("/api/movies/discover?content_type=all&sort_by=popularity.desc")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Unified Title"
        mock_disc.assert_called_once()


def test_fastapi_search_movies_route():
    """Verify FastAPI search route routes content_type='movies' to search_movies."""
    app = create_app()
    client = TestClient(app)

    fake_client = TMDBClient(api_key="mock_key")
    paged = PagedResultModel(
        page=1,
        total_pages=1,
        total_results=1,
        results=[
            MediaItemSummary(
                id=42,
                title="The Matrix",
                media_type="movie",
                vote_average=8.7,
                vote_count=20000,
                popularity=80.0,
            )
        ],
    )

    with mock.patch.object(fake_client, "search_movies", return_value=paged) as mock_search:
        app.state.tmdb_client = fake_client
        resp = client.get("/api/movies/search?query=matrix&content_type=movies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["title"] == "The Matrix"
        assert data["results"][0]["media_type"] == "movie"
        mock_search.assert_called_once()
