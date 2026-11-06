"""Phase 7 Verification Tests: Movie Details, Posters, and Related Titles.

Verifies:
- 7.1 Movie Details: Title, overview, release date, genres, runtime, rating, poster, backdrop, cast, director, similar titles, trailer info.
- 7.2 Series Details: Series title, overview, first-air date, genres, rating, cast, creators, seasons, episodes, status, related series.
- 7.3 Poster Loading: Multiple image sizes (w185, w500, w1280, original), missing image handling, safe fallbacks.
- 7.4 Related Titles: Real TMDB similar recommendations, verified identifiers, media type preservation.
- 7.5 Trailer Discovery: Official YouTube trailers from TMDB videos endpoint, safe URL formatting, handling missing trailers.
- 7.6 Graceful Handling: Missing metadata, long descriptions, missing cast/crew, special characters, error normalization.
"""

from __future__ import annotations

import unittest.mock as mock
import pytest
from fastapi.testclient import TestClient

from app.api.movie_models import (
    MediaDetailsModel,
    GenreModel,
    CastMemberModel,
    VideoModel,
    MediaItemSummary,
)
from app.api.server import create_app
from app.api.tmdb_client import TMDBClient


@pytest.fixture
def mock_client() -> TMDBClient:
    return TMDBClient(api_key="test_valid_tmdb_token_xyz")


# =============================================================================
# 1. Movie Details Tests (7.1)
# =============================================================================


def test_get_movie_details_complete(mock_client: TMDBClient):
    """Test 7.1: get_movie_details retrieves complete verified fields."""
    mock_payload = {
        "id": 550,
        "title": "Fight Club",
        "overview": "An insomniac office worker and a devil-may-care soap maker form an underground fight club.",
        "release_date": "1999-10-15",
        "vote_average": 8.433,
        "vote_count": 27000,
        "popularity": 73.5,
        "original_language": "en",
        "poster_path": "/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",
        "backdrop_path": "/hZkgoQYus5vegHoetLkCJzb17zJ.jpg",
        "tagline": "Mischief. Mayhem. Soap.",
        "runtime": 139,
        "status": "Released",
        "genres": [
            {"id": 18, "name": "Drama"},
            {"id": 53, "name": "Thriller"},
        ],
        "credits": {
            "cast": [
                {
                    "id": 819,
                    "name": "Edward Norton",
                    "character": "The Narrator",
                    "profile_path": "/5XBzD5WuTyEGZeS4VI25q2IM1Y4.jpg",
                    "order": 0,
                },
                {
                    "id": 287,
                    "name": "Brad Pitt",
                    "character": "Tyler Durden",
                    "profile_path": "/cckcYc2v0yh1tc9QjRelptsqpHW.jpg",
                    "order": 1,
                },
            ],
            "crew": [
                {"id": 7467, "name": "David Fincher", "job": "Director"},
                {"id": 1254, "name": "Art Linson", "job": "Producer"},
            ],
        },
        "videos": {
            "results": [
                {
                    "id": "vid123",
                    "key": "O1nDozs-Lda",
                    "name": "Official Trailer",
                    "site": "YouTube",
                    "type": "Trailer",
                    "official": True,
                },
                {
                    "id": "vid456",
                    "key": "ignore_vimeo",
                    "name": "Clip",
                    "site": "Vimeo",
                    "type": "Clip",
                    "official": False,
                },
            ]
        },
        "similar": {
            "results": [
                {
                    "id": 551,
                    "title": "The Game",
                    "overview": "A wealthy banker receives a mysterious gift.",
                    "poster_path": "/game.jpg",
                    "vote_average": 7.7,
                    "release_date": "1997-09-12",
                }
            ]
        },
    }

    with mock.patch.object(mock_client, "_request", return_value=mock_payload):
        details = mock_client.get_movie_details(550)

        # Core fields
        assert details.id == 550
        assert details.title == "Fight Club"
        assert details.media_type == "movie"
        assert details.runtime_minutes == 139
        assert details.tagline == "Mischief. Mayhem. Soap."
        assert details.vote_average == 8.433
        assert details.vote_count == 27000
        assert details.status == "Released"

        # Image URLs
        assert details.poster_url is not None
        assert "w500" in details.poster_url
        assert details.backdrop_url is not None
        assert "w1280" in details.backdrop_url

        # Genres
        assert len(details.genres) == 2
        assert details.genres[0].name == "Drama"

        # Cast & Crew
        assert len(details.cast) == 2
        assert details.cast[0].name == "Edward Norton"
        assert details.cast[0].character == "The Narrator"
        assert "w185" in details.cast[0].profile_url
        assert details.directors == ["David Fincher"]

        # Videos (only YouTube allowed)
        assert len(details.trailers) == 1
        assert details.trailers[0].site == "YouTube"
        assert details.trailers[0].key == "O1nDozs-Lda"
        assert details.trailers[0].url == "https://www.youtube.com/watch?v=O1nDozs-Lda"

        # Similar
        assert len(details.similar) == 1
        assert details.similar[0].id == 551
        assert details.similar[0].title == "The Game"
        assert details.similar[0].media_type == "movie"


# =============================================================================
# 2. Series Details Tests (7.2)
# =============================================================================


def test_get_series_details_complete(mock_client: TMDBClient):
    """Test 7.2: get_series_details retrieves TV series metadata, seasons, and creators."""
    mock_tv_payload = {
        "id": 1399,
        "name": "Game of Thrones",
        "overview": "Seven noble families fight for control of the mythical land of Westeros.",
        "first_air_date": "2011-04-17",
        "vote_average": 8.448,
        "vote_count": 22000,
        "popularity": 320.5,
        "original_language": "en",
        "poster_path": "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
        "backdrop_path": "/2OMB0ynKlyIenMJWI2Dy9IWT4c.jpg",
        "tagline": "Winter Is Coming",
        "status": "Ended",
        "number_of_seasons": 8,
        "number_of_episodes": 73,
        "episode_run_time": [55],
        "created_by": [
            {"id": 9813, "name": "David Benioff"},
            {"id": 228068, "name": "D.B. Weiss"},
        ],
        "genres": [
            {"id": 10765, "name": "Sci-Fi & Fantasy"},
            {"id": 18, "name": "Drama"},
            {"id": 10759, "name": "Action & Adventure"},
        ],
        "credits": {
            "cast": [
                {
                    "id": 239019,
                    "name": "Emilia Clarke",
                    "character": "Daenerys Targaryen",
                    "profile_path": "/emilia.jpg",
                    "order": 0,
                },
                {
                    "id": 1223786,
                    "name": "Kit Harington",
                    "character": "Jon Snow",
                    "profile_path": "/kit.jpg",
                    "order": 1,
                },
            ]
        },
        "videos": {
            "results": [
                {
                    "id": "got_trailer_1",
                    "key": "KPLWWIOCOOQ",
                    "name": "Season 1 Official Trailer",
                    "site": "YouTube",
                    "type": "Trailer",
                    "official": True,
                }
            ]
        },
        "similar": {
            "results": [
                {
                    "id": 94997,
                    "name": "House of the Dragon",
                    "overview": "The Targaryen dynasty at the absolute apex of its power.",
                    "poster_path": "/hotd.jpg",
                    "vote_average": 8.4,
                    "first_air_date": "2022-08-21",
                }
            ]
        },
    }

    with mock.patch.object(mock_client, "_request", return_value=mock_tv_payload):
        details = mock_client.get_series_details(1399)

        assert details.id == 1399
        assert details.title == "Game of Thrones"
        assert details.media_type == "tv"
        assert details.number_of_seasons == 8
        assert details.number_of_episodes == 73
        assert details.runtime_minutes == 55
        assert details.status == "Ended"
        assert details.directors == ["David Benioff", "D.B. Weiss"]
        assert len(details.genres) == 3
        assert len(details.cast) == 2
        assert details.cast[0].character == "Daenerys Targaryen"
        assert len(details.trailers) == 1
        assert details.trailers[0].key == "KPLWWIOCOOQ"
        assert len(details.similar) == 1
        assert details.similar[0].title == "House of the Dragon"
        assert details.similar[0].media_type == "tv"


# =============================================================================
# 3. Graceful Fallbacks & Incomplete Metadata (7.1, 7.2)
# =============================================================================


def test_movie_details_missing_fields_graceful(mock_client: TMDBClient):
    """Test 7.1: Missing overview, runtime, images, or credits handled honestly with empty/None."""
    mock_payload = {
        "id": 99999,
        "title": "Minimal Movie",
        "overview": None,
        "release_date": None,
        "vote_average": 0.0,
        "vote_count": 0,
        "poster_path": None,
        "backdrop_path": None,
        "runtime": None,
        "tagline": None,
        "status": None,
        "genres": None,
        "credits": None,
        "videos": None,
        "similar": None,
    }

    with mock.patch.object(mock_client, "_request", return_value=mock_payload):
        details = mock_client.get_movie_details(99999)

        assert details.id == 99999
        assert details.title == "Minimal Movie"
        assert details.overview == ""
        assert details.poster_url is None
        assert details.backdrop_url is None
        assert details.runtime_minutes is None
        assert details.genres == []
        assert details.cast == []
        assert details.directors == []
        assert details.trailers == []
        assert details.similar == []


def test_series_details_missing_fields_graceful(mock_client: TMDBClient):
    """Test 7.2: TV series with missing creators, episodes, seasons, or videos handled safely."""
    mock_payload = {
        "id": 88888,
        "name": "Obscure Indie Show",
        "overview": "",
        "first_air_date": "",
        "poster_path": None,
        "number_of_seasons": None,
        "number_of_episodes": None,
        "episode_run_time": [],
        "created_by": None,
        "genres": [],
        "credits": {},
        "videos": {},
        "similar": {},
    }

    with mock.patch.object(mock_client, "_request", return_value=mock_payload):
        details = mock_client.get_series_details(88888)

        assert details.id == 88888
        assert details.title == "Obscure Indie Show"
        assert details.number_of_seasons is None
        assert details.number_of_episodes is None
        assert details.runtime_minutes is None
        assert details.directors == []
        assert details.cast == []
        assert details.trailers == []


# =============================================================================
# 4. Poster & Image Size Verification (7.3)
# =============================================================================


def test_image_url_approved_resolutions(mock_client: TMDBClient):
    """Test 7.3: Verifies approved sizes (w185, w500, w1280, original) and None handling."""
    path = "/sample_image.jpg"

    w185 = mock_client._construct_image_url(path, "w185")
    assert w185 == "https://image.tmdb.org/t/p/w185/sample_image.jpg"

    w500 = mock_client._construct_image_url(path, "w500")
    assert w500 == "https://image.tmdb.org/t/p/w500/sample_image.jpg"

    w1280 = mock_client._construct_image_url(path, "w1280")
    assert w1280 == "https://image.tmdb.org/t/p/w1280/sample_image.jpg"

    original = mock_client._construct_image_url(path, "original")
    assert original == "https://image.tmdb.org/t/p/original/sample_image.jpg"

    # Missing image path returns None
    assert mock_client._construct_image_url(None) is None
    assert mock_client._construct_image_url("") is None


# =============================================================================
# 5. Trailer Discovery & Safe External Links (7.5)
# =============================================================================


def test_trailer_filtering_and_safe_url(mock_client: TMDBClient):
    """Test 7.5: Trailers prefer official YouTube trailers and construct safe watch URLs."""
    mock_payload = {
        "id": 101,
        "title": "Trailer Test",
        "videos": {
            "results": [
                {"id": "v1", "key": "abc1234", "site": "YouTube", "type": "Trailer", "official": True, "name": "Main Trailer"},
                {"id": "v2", "key": "def5678", "site": "YouTube", "type": "Teaser", "official": False, "name": "Teaser 1"},
                {"id": "v3", "key": "not_yt", "site": "Dailymotion", "type": "Trailer", "official": True, "name": "DM Clip"},
                {"id": "v4", "key": "", "site": "YouTube", "type": "Trailer", "official": True, "name": "No Key"},
            ]
        },
    }

    with mock.patch.object(mock_client, "_request", return_value=mock_payload):
        details = mock_client.get_movie_details(101)

        # Only the 2 valid YouTube entries with keys should be preserved
        assert len(details.trailers) == 2
        assert details.trailers[0].key == "abc1234"
        assert details.trailers[0].url == "https://www.youtube.com/watch?v=abc1234"
        assert details.trailers[0].official is True

        assert details.trailers[1].key == "def5678"
        assert details.trailers[1].official is False


# =============================================================================
# 6. Long Descriptions & Unicode Titles (7.6)
# =============================================================================


def test_details_with_long_description_and_unicode(mock_client: TMDBClient):
    """Test 7.6: Handles long 2000+ char synopsis and diverse international script titles."""
    long_synopsis = "A " * 1500  # 3000 chars
    mock_payload = {
        "id": 579974,
        "title": "రౌద్రం రణం రుధిరం (RRR)",
        "overview": long_synopsis,
        "release_date": "2022-03-24",
        "vote_average": 7.8,
        "credits": {
            "cast": [{"id": 1, "name": "N. T. Rama Rao Jr.", "character": "Komaram Bheem", "profile_path": "/ntr.jpg"}],
            "crew": [{"id": 2, "name": "S. S. Rajamouli", "job": "Director"}],
        },
    }

    with mock.patch.object(mock_client, "_request", return_value=mock_payload):
        details = mock_client.get_movie_details(579974)

        assert details.id == 579974
        assert "RRR" in details.title
        assert len(details.overview) == len(long_synopsis)
        assert details.directors == ["S. S. Rajamouli"]


# =============================================================================
# 7. FastAPI Endpoint Integration (7.1, 7.2)
# =============================================================================


def test_fastapi_movie_details_route(mock_client: TMDBClient):
    """Test GET /api/movies/movie/{id} returns full MediaDetailsModel."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    expected = MediaDetailsModel(
        id=550,
        title="Fight Club",
        media_type="movie",
        overview="Soap and anarchy.",
        runtime_minutes=139,
        genres=[GenreModel(id=18, name="Drama")],
    )

    with mock.patch.object(mock_client, "get_movie_details", return_value=expected) as mock_get:
        resp = client.get("/api/movies/movie/550")
        assert resp.status_code == 200
        data = resp.json()

        mock_get.assert_called_once_with(movie_id=550)
        assert data["id"] == 550
        assert data["title"] == "Fight Club"
        assert data["media_type"] == "movie"
        assert data["runtime_minutes"] == 139


def test_fastapi_series_details_route_and_alias(mock_client: TMDBClient):
    """Test GET /api/movies/tv/{id} and /api/movies/series/{id} alias both route to get_series_details."""
    app = create_app()
    app.state.tmdb_client = mock_client
    client = TestClient(app)

    expected = MediaDetailsModel(
        id=1399,
        title="Game of Thrones",
        media_type="tv",
        number_of_seasons=8,
        number_of_episodes=73,
    )

    with mock.patch.object(mock_client, "get_series_details", return_value=expected) as mock_get:
        # 1. Test canonical /tv/{id}
        resp1 = client.get("/api/movies/tv/1399")
        assert resp1.status_code == 200
        assert resp1.json()["number_of_seasons"] == 8

        # 2. Test user-friendly /series/{id} alias
        resp2 = client.get("/api/movies/series/1399")
        assert resp2.status_code == 200
        assert resp2.json()["title"] == "Game of Thrones"

        assert mock_get.call_count == 2
