"""Unit and integration tests for TMDB API Service and FastAPI Movie Routes.

Uses mocked HTTP responses to test valid discovery, search, details, rate limiting,
authentication errors, timeouts, and network failures.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
import requests
from fastapi.testclient import TestClient

from app.api.movie_models import (
    MediaDetailsModel,
    PagedResultModel,
    TMDBConfigStatus,
)
from app.api.server import app
from app.api.tmdb_client import (
    TMDBAuthError,
    TMDBClient,
    TMDBError,
    TMDBNetworkError,
    TMDBNotFoundError,
    TMDBRateLimitError,
    TMDBTimeoutError,
)


@pytest.fixture
def mock_session():
    """Create a mocked requests.Session for testing."""
    session = MagicMock(spec=requests.Session)
    return session


@pytest.fixture
def tmdb_client(mock_session):
    """Instantiate a TMDBClient wired with the mocked session."""
    return TMDBClient(api_key="test_api_key_12345", session=mock_session)


def _make_mock_response(status_code=200, json_data=None, text=""):
    """Helper to build a mocked HTTP response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = (200 <= status_code < 300)
    resp.headers = {}
    if json_data is not None:
        resp.json.return_value = json_data
        resp.text = json.dumps(json_data)
    else:
        resp.text = text
        resp.json.side_effect = ValueError("No JSON")
    return resp


# =============================================================================
# 1. Configuration & Authentication Tests
# =============================================================================

def test_client_configuration():
    # Unconfigured client
    unconfigured = TMDBClient(api_key="")
    assert not unconfigured.is_configured()

    with pytest.raises(TMDBAuthError) as exc_info:
        unconfigured.discover_movies()
    assert "not configured" in str(exc_info.value).lower()

    # Configured client
    configured = TMDBClient(api_key="my_secret_key")
    assert configured.is_configured()


def test_auth_header_format():
    # v4 JWT / Bearer token
    jwt_client = TMDBClient(api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy")
    headers = jwt_client._get_headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ey")

    # v3 API Key (32 hex characters)
    v3_client = TMDBClient(api_key="a1b2c3d4e5f60718293a4b5c6d7e8f90")
    params = v3_client._prepare_params({"page": 1})
    assert params["api_key"] == "a1b2c3d4e5f60718293a4b5c6d7e8f90"


# =============================================================================
# 2. Movie & Series Discovery Tests
# =============================================================================

def test_discover_movies_success(tmdb_client, mock_session):
    sample_payload = {
        "page": 1,
        "total_pages": 42,
        "total_results": 840,
        "results": [
            {
                "id": 550,
                "title": "Fight Club",
                "overview": "An insomniac office worker...",
                "poster_path": "/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",
                "backdrop_path": "/hZkgoQYus5vegHoetLkCJzb17zJ.jpg",
                "release_date": "1999-10-15",
                "original_language": "en",
                "genre_ids": [18, 53],
                "vote_average": 8.4,
                "vote_count": 27000,
                "popularity": 85.3,
            }
        ],
    }
    mock_session.request.return_value = _make_mock_response(200, sample_payload)

    result = tmdb_client.discover_movies(page=1, sort_by="popularity.desc")
    assert isinstance(result, PagedResultModel)
    assert result.page == 1
    assert result.total_pages == 42
    assert len(result.results) == 1

    item = result.results[0]
    assert item.id == 550
    assert item.title == "Fight Club"
    assert item.media_type == "movie"
    assert item.release_year == 1999
    assert item.poster_url == "https://image.tmdb.org/t/p/w500/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg"
    assert item.backdrop_url == "https://image.tmdb.org/t/p/w1280/hZkgoQYus5vegHoetLkCJzb17zJ.jpg"


def test_discover_series_success(tmdb_client, mock_session):
    sample_payload = {
        "page": 1,
        "total_pages": 10,
        "total_results": 200,
        "results": [
            {
                "id": 1399,
                "name": "Game of Thrones",
                "overview": "Seven noble families fight for control...",
                "poster_path": "/u3bZgnGQ9T01sWNhyveQz0wH0Hl.jpg",
                "first_air_date": "2011-04-17",
                "original_language": "en",
                "genre_ids": [10765, 18],
                "vote_average": 8.4,
                "vote_count": 23000,
                "popularity": 120.5,
            }
        ],
    }
    mock_session.request.return_value = _make_mock_response(200, sample_payload)

    result = tmdb_client.discover_series(page=1, with_original_language="en")
    assert len(result.results) == 1
    item = result.results[0]
    assert item.id == 1399
    assert item.title == "Game of Thrones"  # Normalized from 'name'
    assert item.media_type == "tv"
    assert item.release_year == 2011


# =============================================================================
# 3. Search Operations Tests
# =============================================================================

def test_search_movies(tmdb_client, mock_session):
    mock_session.request.return_value = _make_mock_response(
        200,
        {
            "page": 1,
            "total_pages": 1,
            "total_results": 1,
            "results": [
                {
                    "id": 857,
                    "title": "Saving Private Ryan",
                    "release_date": "1998-07-24",
                    "vote_average": 8.2,
                }
            ],
        },
    )

    res = tmdb_client.search_movies(query="Ryan")
    assert len(res.results) == 1
    assert res.results[0].title == "Saving Private Ryan"


def test_search_empty_query(tmdb_client):
    # Empty query returns immediate empty PagedResultModel without network call
    res = tmdb_client.search_movies(query="   ")
    assert res.results == []
    assert res.total_results == 0


# =============================================================================
# 4. Rich Details with Credits and Videos
# =============================================================================

def test_get_movie_details(tmdb_client, mock_session):
    details_payload = {
        "id": 157336,
        "title": "Interstellar",
        "tagline": "Mankind was born on Earth. It was never meant to die here.",
        "runtime": 169,
        "status": "Released",
        "release_date": "2014-11-05",
        "vote_average": 8.4,
        "genres": [{"id": 12, "name": "Adventure"}, {"id": 18, "name": "Drama"}],
        "credits": {
            "cast": [
                {"id": 10297, "name": "Matthew McConaughey", "character": "Cooper", "order": 0},
                {"id": 1813, "name": "Anne Hathaway", "character": "Brand", "order": 1},
            ],
            "crew": [
                {"id": 525, "name": "Christopher Nolan", "job": "Director"},
            ],
        },
        "videos": {
            "results": [
                {"id": "v1", "key": "zSWdZVtXT7E", "name": "Official Trailer", "site": "YouTube", "type": "Trailer"}
            ]
        },
        "similar": {
            "results": [
                {"id": 286217, "title": "The Martian", "media_type": "movie", "release_date": "2015-09-30"}
            ]
        },
    }
    mock_session.request.return_value = _make_mock_response(200, details_payload)

    details = tmdb_client.get_movie_details(157336)
    assert isinstance(details, MediaDetailsModel)
    assert details.id == 157336
    assert details.title == "Interstellar"
    assert details.runtime_minutes == 169
    assert details.directors == ["Christopher Nolan"]
    assert len(details.cast) == 2
    assert details.cast[0].name == "Matthew McConaughey"
    assert len(details.trailers) == 1
    assert details.trailers[0].url == "https://www.youtube.com/watch?v=zSWdZVtXT7E"
    assert len(details.similar) == 1
    assert details.similar[0].title == "The Martian"


# =============================================================================
# 5. Error Handling & Edge Cases Tests
# =============================================================================

def test_tmdb_401_unauthorized(tmdb_client, mock_session):
    mock_session.request.return_value = _make_mock_response(401, text="Invalid API key")
    with pytest.raises(TMDBAuthError):
        tmdb_client.discover_movies()


def test_tmdb_404_not_found(tmdb_client, mock_session):
    mock_session.request.return_value = _make_mock_response(404, text="Not Found")
    with pytest.raises(TMDBNotFoundError):
        tmdb_client.get_movie_details(99999999)


def test_tmdb_429_rate_limit(tmdb_client, mock_session):
    resp = _make_mock_response(429, text="Rate limit exceeded")
    resp.headers = {"Retry-After": "15"}
    mock_session.request.return_value = resp
    with pytest.raises(TMDBRateLimitError) as exc_info:
        tmdb_client.discover_movies()
    assert "15s" in str(exc_info.value)


def test_tmdb_timeout(tmdb_client, mock_session):
    mock_session.request.side_effect = requests.Timeout("Connection timed out")
    with pytest.raises(TMDBTimeoutError):
        tmdb_client.discover_movies()


def test_tmdb_network_error(tmdb_client, mock_session):
    mock_session.request.side_effect = requests.ConnectionError("DNS failure")
    with pytest.raises(TMDBNetworkError):
        tmdb_client.discover_movies()


def test_tmdb_malformed_json(tmdb_client, mock_session):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.ok = True
    resp.json.side_effect = ValueError("Invalid JSON syntax")
    mock_session.request.return_value = resp
    with pytest.raises(TMDBError) as exc_info:
        tmdb_client.discover_movies()
    assert "malformed json" in str(exc_info.value).lower()


# =============================================================================
# 6. FastAPI Route Integration Tests (/api/movies/*)
# =============================================================================

@pytest.fixture
def api_client(tmdb_client):
    """FastAPI test client with TMDB client dependency injected."""
    app.state.tmdb_client = tmdb_client
    return TestClient(app)


def test_fastapi_movie_config(api_client, tmdb_client):
    res = api_client.get("/api/movies/config")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert data["configured"] is True
    assert "image_base_url" in data


def test_fastapi_discover_endpoint(api_client, mock_session):
    mock_session.request.return_value = _make_mock_response(
        200,
        {
            "page": 1,
            "total_pages": 5,
            "total_results": 100,
            "results": [
                {"id": 1, "title": "RRR", "release_date": "2022-03-24", "vote_average": 7.8}
            ],
        },
    )

    res = api_client.get("/api/movies/discover?region=south_indian&content_type=movies")
    assert res.status_code == 200
    data = res.json()
    assert data["page"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "RRR"


def test_fastapi_search_endpoint(api_client, mock_session):
    mock_session.request.return_value = _make_mock_response(
        200,
        {
            "page": 1,
            "total_pages": 1,
            "total_results": 1,
            "results": [
                {"id": 2, "name": "Breaking Bad", "first_air_date": "2008-01-20", "media_type": "tv"}
            ],
        },
    )

    res = api_client.get("/api/movies/search?query=Breaking&content_type=series")
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "Breaking Bad"


def test_fastapi_error_translation_401(api_client, mock_session):
    mock_session.request.return_value = _make_mock_response(401, text="Invalid API key")
    res = api_client.get("/api/movies/search?query=unseen_auth_fail_401_test")
    assert res.status_code == 401
    assert "unauthorized" in res.json()["detail"].lower() or "invalid" in res.json()["detail"].lower()


def test_discover_movies_49_items_pagination(tmdb_client, mock_session):
    """Verify that requesting page_size=49 aggregates across 3 TMDB pages and slices exactly 49 items (7x7 grid)."""
    def side_effect(method, url, **kwargs):
        page = kwargs.get("params", {}).get("page", 1)
        # Each TMDB page has 20 items
        results = [
            {"id": page * 100 + i, "title": f"Movie {page}_{i}", "media_type": "movie"}
            for i in range(20)
        ]
        return _make_mock_response(
            200,
            {
                "page": page,
                "total_pages": 10,
                "total_results": 200,
                "results": results,
            },
        )

    mock_session.request.side_effect = side_effect

    res = tmdb_client.discover_movies(page=1, page_size=49)
    assert isinstance(res, PagedResultModel)
    assert len(res.results) == 49
    assert res.page == 1
    # 200 total results / 49 per page = 5 total pages (ceil(200/49) = 5)
    assert res.total_pages == 5
    assert res.total_results == 200
    assert res.results[0].title == "Movie 1_0"
    assert res.results[48].title == "Movie 3_8"

